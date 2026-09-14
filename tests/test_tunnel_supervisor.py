# -*- coding: utf-8 -*-
"""Named tunnel sidecar: авто-рестарт при ночном DNS/argotunnel timeout.

Инцидент 2026-09-14: cloudflared писал
  Failed to refresh DNS local resolver … argotunnel.com: i/o timeout
и sidecar умирал со строкой «следующий запуск бота поднимет снова» —
панель по домену падала на всю ночь, пока бот не перезапустят.
Локальный Flask (:5001) при этом жил. Нужен supervisor-цикл.

Запуск: python3 tests/test_tunnel_supervisor.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_tunnel_sup_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


SRC = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()

print('== 1. supervisor вместо одноразового echo ==')
a = SRC.find('def _start_tunnel_sidecar')
b = SRC.find('def _stop_tunnel_sidecar')
body = SRC[a:b]
check('tunnel-supervisor' in body or "name='tunnel-supervisor'" in body
      or 'name="tunnel-supervisor"' in body,
      'поток tunnel-supervisor запускается')
check('def _supervisor' in body, 'внутренний _supervisor есть')
check('перезапуск через' in body, 'лог обещает перезапуск, не «до следующего бота»')
check('следующий запуск бота поднимет снова' not in body,
      'старый «умри до рестарта бота» убран')
check('while not _tunnel_stop.is_set()' in body,
      'цикл живёт пока бот не остановит sidecar')

print('== 2. DNS/credentials не на каждом рестарте ==')
# ensure_credentials должен быть ДО цикла supervisor, не внутри
cred_pos = body.find('ensure_credentials')
sup_pos = body.find('def _supervisor')
check(cred_pos >= 0 and sup_pos > cred_pos,
      'ensure_credentials только на старте, до supervisor-цикла')
sup_body = body[sup_pos:]
check('ensure_credentials' not in sup_body,
      'внутри supervisor нет DNS route / ensure_credentials')
check('route dns' not in (sup_body or '').lower(),
      'supervisor не зовёт route dns')

print('== 3. stop сигналит и гасит процесс ==')
stop = SRC[b:SRC.find('_cleanup_done', b)]
check('_tunnel_stop.set()' in stop, '_stop_tunnel_sidecar ставит stop-event')
check('terminate' in stop, '_stop_tunnel_sidecar terminate процесса')

print('== 4. http2 остаётся дефолтом (QUIC ночные флапы) ==')
check("TUNNEL_PROTOCOL', '') or 'http2'" in body
      or 'or \'http2\')' in body,
      'дефолт протокола http2')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
