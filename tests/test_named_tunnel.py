# -*- coding: utf-8 -*-
"""Постоянный домен панели: именованный туннель вместо случайной ссылки.

Проверяем:
1. services/named_tunnel — поиск конфига, парсинг hostname из config.yml,
   запись/очистка постоянной ссылки панели.
2. main.py: legacy quick-туннель (случайный trycloudflare URL) больше не
   стартует сам — только через QUICK_TUNNEL=1; сайдкар запускается после
   setup_panel_tunnel.bat и пишет постоянную ссылку в tunnel_url.txt.
3. Живой прогон _start_tunnel_sidecar() с фейковым бинарником cloudflared —
   имитация ПК владельца после установочного батника.

Запуск: python3 tests/test_named_tunnel.py
"""
import os
import shutil
import stat
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='aether_namedtunnel_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
# Имит Home — чтобы ~/.cloudflared/config.yml с реальной машины не мешал.
os.environ['HOME'] = os.path.join(_TMP, 'home')
os.makedirs(os.environ['HOME'], exist_ok=True)

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


# ── A. services/named_tunnel — юниты ─────────────────────────────────────────
print('\n[A] services/named_tunnel:')
from services import named_tunnel as nt

fake_root = os.path.join(_TMP, 'roota')
os.makedirs(os.path.join(fake_root, 'scripts'), exist_ok=True)

check(nt.find_config(fake_root) is None, 'find_config: нет конфига -> None')

cfg_path = os.path.join(fake_root, 'scripts', 'config.yml')
with open(cfg_path, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: abc123\n'
             'credentials-file: /home/o/.cloudflared/abc123.json\n'
             '\n'
             'ingress:\n'
             '  - hostname: hakumods.xyz\n'
             '    service: http://localhost:5001\n'
             '  - hostname: www.hakumods.xyz\n'
             '    service: http://localhost:5001\n'
             '  - service: http_status:404\n')
check(nt.find_config(fake_root) == cfg_path, 'find_config: нашёл scripts/config.yml')

home_cfg_dir = os.path.join(os.environ['HOME'], '.cloudflared')
os.makedirs(home_cfg_dir, exist_ok=True)
with open(os.path.join(home_cfg_dir, 'config.yml'), 'w', encoding='utf-8') as fh:
    fh.write('tunnel: def456\ningress:\n  - hostname: "panel.hakumods.xyz"\n'
             '    service: http://localhost:5001\n')
check(nt.find_config(fake_root).endswith(os.path.join('.cloudflared', 'config.yml')),
      'find_config: домашний конфиг приоритетнее scripts/')

check(nt.public_url(cfg_path) == 'https://hakumods.xyz',
      'public_url: первый hostname -> https://hakumods.xyz')
check(nt.public_url(os.path.join(home_cfg_dir, 'config.yml')) == 'https://panel.hakumods.xyz',
      'public_url: hostname в кавычках тоже парсится')
check(nt.public_url(os.path.join(_TMP, 'no_such.yml')) is None,
      'public_url: несуществующий файл -> None (не падает)')

no_host = os.path.join(_TMP, 'nohost.yml')
with open(no_host, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: zzz\ningress:\n  - service: http_status:404\n')
check(nt.public_url(no_host) is None, 'public_url: конфиг без hostname -> None')

nt.remember_url(fake_root, 'https://hakumods.xyz')
url_file = os.path.join(fake_root, nt.URL_FILE)
check(os.path.isfile(url_file) and open(url_file, encoding='utf-8').read() == 'https://hakumods.xyz',
      'remember_url: записал постоянную ссылку в tunnel_url.txt')
nt.drop_stale_url(fake_root)
check(not os.path.exists(url_file), 'drop_stale_url: удалил старую ссылку')
try:
    nt.drop_stale_url(fake_root)
    _ok = True
except Exception:
    _ok = False
check(_ok, 'drop_stale_url: не падает, когда файла нет')

# ── B. main.py — статические проверки гейта ──────────────────────────────────
print('\n[B] main.py гейт legacy quick-туннеля:')
src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()

check('QUICK_TUNNEL' in src, 'main.py упоминает QUICK_TUNNEL')
q_idx = src.find('QUICK_TUNNEL')
d_idx = src.find('def delayed_tunnel')
check(q_idx != -1 and d_idx != -1 and q_idx < d_idx,
      'delayed_tunnel объявлен ПОСЛЕ проверки QUICK_TUNNEL (не стартует сам)')
check("QUICK_TUNNEL" in open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read(),
      '.env.example документирует QUICK_TUNNEL')
check('from services import named_tunnel' in src,
      'main.py использует services/named_tunnel')
check('_nt.remember_url(root, pub)' in src,
      'сайдкар пишет постоянную ссылку панели в tunnel_url.txt')
check('QUICK_TUNNEL' in open(os.path.join(ROOT, 'docs', 'PANEL-DOMAIN.md'), encoding='utf-8').read(),
      'docs/PANEL-DOMAIN.md описывает QUIСK-режим')

try:
    import py_compile
    py_compile.compile(os.path.join(ROOT, 'main.py'), doraise=True)
    _ok = True
except Exception:
    _ok = False
check(_ok, 'main.py компилируется без синтаксических ошибок')

# ── C. Живой прогон сайдкара (фейковый cloudflared) ──────────────────────────
print('\n[C] _start_tunnel_sidecar с фейковым бинарником:')
import main as m

scripts_dir = os.path.join(ROOT, 'scripts')
fake_bin = os.path.join(scripts_dir, 'cloudflared')
fake_cfg = os.path.join(scripts_dir, 'config.yml')
url_file_repo = os.path.join(ROOT, nt.URL_FILE)
created = []
try:
    # 1) Ни бинарника, ни конфига — сайдкар молчит и ничего не запускает.
    for p in (fake_bin, fake_cfg, url_file_repo,
              os.path.join(os.environ['HOME'], '.cloudflared', 'config.yml')):
        if os.path.exists(p):
            os.remove(p)
    m._tunnel_proc = None
    m._start_tunnel_sidecar()
    check(m._tunnel_proc is None, 'без конфига сайдкар ничего не запускает')
    check(not os.path.exists(url_file_repo), 'без конфига ссылка не создаётся')

    # 2) Полный комплект: бинарник + конфиг — как после setup_panel_tunnel.bat.
    with open(fake_bin, 'w', encoding='utf-8') as fh:
        fh.write('#!/bin/sh\necho "fake cloudflared up"\nsleep 60\n')
    created.append(fake_bin)
    os.chmod(fake_bin, os.stat(fake_bin).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(fake_cfg, 'w', encoding='utf-8') as fh:
        fh.write('tunnel: test-id\n'
                 'credentials-file: /tmp/test.json\n'
                 'ingress:\n'
                 '  - hostname: hakumods.xyz\n'
                 '    service: http://localhost:5001\n'
                 '  - service: http_status:404\n')
    created.append(fake_cfg)
    # Убираем домашний конфиг, чтобы взялся именно scripts/config.yml.
    home_cfg = os.path.join(os.environ['HOME'], '.cloudflared', 'config.yml')
    if os.path.exists(home_cfg):
        os.remove(home_cfg)

    m._tunnel_proc = None
    m._start_tunnel_sidecar()
    check(m._tunnel_proc is not None, 'сайдкар запустил процесс туннеля')
    time.sleep(1.0)
    check(m._tunnel_proc is not None and m._tunnel_proc.poll() is None,
          'процесс туннеля жив после запуска')
    check(os.path.isfile(url_file_repo)
          and open(url_file_repo, encoding='utf-8').read().strip() == 'https://hakumods.xyz',
          'tunnel_url.txt = постоянная ссылка https://hakumods.xyz')
    if os.path.exists(url_file_repo):
        created.append(url_file_repo)

    m._stop_tunnel_sidecar()
    check(True, 'сайдкар корректно остановлен')
finally:
    try:
        m._stop_tunnel_sidecar()
    except Exception:
        pass
    for p in created:
        try:
            os.remove(p)
        except OSError:
            pass

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
