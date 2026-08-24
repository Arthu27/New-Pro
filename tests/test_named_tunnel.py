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

# ── D. VDS-режим: автодокачка бинарника + портативный конфиг ────────────────
print('\n[D] VDS-режим (ensure_binary / runtime_config):')
from services import named_tunnel as nt2

vds_scripts = os.path.join(_TMP, 'vdsroot', 'scripts')
os.makedirs(vds_scripts, exist_ok=True)

import urllib.request as _urlreq
_orig_retrieve = _urlreq.urlretrieve
def _fake_retrieve(url, path):
    with open(path, 'wb') as fh:
        fh.write(b'\0' * (6 * 1024 * 1024))  # «настоящий» бинарник
    return path, None
_urlreq.urlretrieve = _fake_retrieve
try:
    got = nt2.ensure_binary(vds_scripts)
    check(got is not None and os.path.isfile(got) and os.path.getsize(got) > 5 * 1024 * 1024,
          'ensure_binary: бинарник докачался сам и остался на месте')
    got2 = nt2.ensure_binary(vds_scripts)
    check(got2 == got, 'ensure_binary: повторно не качает (переиспользование)')
finally:
    _urlreq.urlretrieve = _orig_retrieve

def _boom(url, path):
    raise OSError('no internet')
_urlreq.urlretrieve = _boom
try:
    dead = os.path.join(_TMP, 'deadroot', 'scripts')
    check(nt2.ensure_binary(dead) is None, 'ensure_binary: без интернета -> None, не падает')
    big = os.path.join(dead, 'cloudflared')
    check(not (os.path.isfile(big) and os.path.getsize(big) > 0), 'обрыв скачивания не оставляет битый файл')
finally:
    _urlreq.urlretrieve = _orig_retrieve

# runtime_config: creds-путь мёртв (переезд) + ключ рядом → рантайм-копия
vds_root = os.path.dirname(vds_scripts)
cfg_dead = os.path.join(vds_scripts, 'config.yml')
with open(cfg_dead, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: tt-1\ncredentials-file: C:\\Users\\OldPC\\.cloudflared\\tt-1.json\n'
             'ingress:\n  - hostname: hakumods.xyz\n    service: http://localhost:5001\n'
             '  - service: http_status:404\n')
with open(os.path.join(vds_scripts, 'tunnel-creds.json'), 'w', encoding='utf-8') as fh:
    fh.write('{"AccountTag":"x"}')
rc = nt2.runtime_config(vds_root, cfg_dead)
check(rc != cfg_dead and os.path.isfile(rc), 'runtime_config: сделана рантайм-копия конфига')
rt = open(rc, encoding='utf-8').read()
check('tunnel-creds.json' in rt and 'OldPC' not in rt,
      'credentials-путь переписан на локальный ключ')

# creds-путь жив (та же машина) — конфиг не трогаем
alive_creds = os.path.join(_TMP, 'alive.json')
with open(alive_creds, 'w', encoding='utf-8') as fh:
    fh.write('{}')
cfg_alive = os.path.join(_TMP, 'alive_cfg.yml')
with open(cfg_alive, 'w', encoding='utf-8') as fh:
    fh.write(f'tunnel: t2\ncredentials-file: {alive_creds}\ningress:\n  - service: http_status:404\n')
check(nt2.runtime_config(_TMP, cfg_alive) == cfg_alive, 'runtime_config: живой путь -> без изменений')

# нет ключа рядом — вернёт исходник (cloudflared сам скажет, что не так)
solo = os.path.join(_TMP, 'solocfg.yml')
with open(solo, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: t3\ncredentials-file: /none/here.json\ningress:\n  - service: http_status:404\n')
check(nt2.runtime_config(_TMP, solo) == solo, 'runtime_config: нет ключа -> исходник, без падения')

# ── E. export_portable: профиль → scripts/ для VDS ──────────────────────────
print('\n[E] export_portable:')
pc_root = os.path.join(_TMP, 'pcroot')
pc_scripts = os.path.join(pc_root, 'scripts')
home_cfg_dir = os.path.join(_TMP, 'profile', '.cloudflared')
os.makedirs(home_cfg_dir, exist_ok=True)
creds_src = os.path.join(home_cfg_dir, 'tt-9.json')
with open(creds_src, 'w', encoding='utf-8') as fh:
    fh.write('{"k":1}')
prof_cfg = os.path.join(home_cfg_dir, 'config.yml')
with open(prof_cfg, 'w', encoding='utf-8') as fh:
    fh.write(f'tunnel: tt-9\ncredentials-file: {creds_src}\n'
             'ingress:\n  - hostname: hakumods.xyz\n    service: http://localhost:5001\n'
             '  - service: http_status:404\n')

nt2.export_portable(pc_root, prof_cfg)
check(os.path.isfile(os.path.join(pc_scripts, 'config.yml')), 'config.yml скопирован в scripts/')
check(os.path.isfile(os.path.join(pc_scripts, 'tunnel-creds.json')), 'ключ скопирован как tunnel-creds.json')
# повторный вызов не затирает (исходник могли поменять под VDS)
with open(os.path.join(pc_scripts, 'tunnel-creds.json'), 'w', encoding='utf-8') as fh:
    fh.write('{"k":2}')
nt2.export_portable(pc_root, prof_cfg)
check(open(os.path.join(pc_scripts, 'tunnel-creds.json'), encoding='utf-8').read() == '{"k":2}',
      'повторный вызов не затирает существующие копии')
try:
    nt2.export_portable(pc_root, os.path.join(_TMP, 'no_such.yml'))
    _ok = True
except Exception:
    _ok = False
check(_ok, 'битый путь — тихо, без падения')

# ── F. ensure_credentials: ключ туннеля на новой машине (переезд на VDS) ─────
print('\n[F] ensure_credentials (переезд на VDS):')
import importlib
nt3 = importlib.import_module('services.named_tunnel')
_orig_home_fn = nt3._cloudflared_home
_orig_run_fn = nt3._run_cmd
_orig_isfile = os.path.isfile

f_root = os.path.join(_TMP, 'froot')
f_scripts = os.path.join(f_root, 'scripts')
f_home = os.path.join(_TMP, 'fhome', '.cloudflared')
os.makedirs(f_scripts, exist_ok=True)
os.makedirs(f_home, exist_ok=True)
OLD_TID = 'b0404cba-429b-4314-b574-cdbcbe3bd077'
NEW_TID = 'c1515dcb-1111-4222-8333-444455556666'
CFG_OLD = ('tunnel: ' + OLD_TID + '\n'
           'credentials-file: C:\\Users\\OldPC\\.cloudflared\\' + OLD_TID + '.json\n'
           'ingress:\n'
           '  - hostname: hakumods.xyz\n    service: http://localhost:5001\n'
           '  - hostname: panel.hakumods.xyz\n    service: http://localhost:5001\n'
           '  - service: http_status:404\n')

calls = []


class _R:
    def __init__(self, out=''):
        self.stdout = out
        self.stderr = ''


def _fake_run(cmd, timeout=120):
    calls.append(cmd)
    if cmd[1:3] == ['tunnel', 'create']:
        with open(os.path.join(f_home, NEW_TID + '.json'), 'w', encoding='utf-8') as fh:
            fh.write('{"fresh":true}')
        return _R('Created tunnel aether-panel with id ' + NEW_TID)
    return _R('')


nt3._cloudflared_home = lambda: f_home
nt3._run_cmd = _fake_run
try:
    prof_cfg = os.path.join(f_home, 'config.yml')
    scr_cfg = os.path.join(f_scripts, 'config.yml')

    # 1) Нет конфигов вообще — нечего чинить, cloudflared не дёргаем.
    check(nt3.ensure_credentials(f_root, f_scripts, 'exe') is None and not calls,
          'нет конфигов -> None, без вызовов cloudflared')

    # 2) Ключ на месте в профиле — None (чинить нечего).
    with open(prof_cfg, 'w', encoding='utf-8') as fh:
        fh.write(CFG_OLD)
    prof_creds = os.path.join(f_home, OLD_TID + '.json')
    with open(prof_creds, 'w', encoding='utf-8') as fh:
        fh.write('{"k":1}')
    check(nt3.ensure_credentials(f_root, f_scripts, 'exe') is None and not calls,
          'ключ в профиле на месте -> None')

    # 3) Ключа в профиле нет, но есть портативная копия в scripts/ -> поднимаем.
    os.remove(prof_creds)
    with open(os.path.join(f_scripts, 'tunnel-creds.json'), 'w', encoding='utf-8') as fh:
        fh.write('{"k":9}')
    got = nt3.ensure_credentials(f_root, f_scripts, 'exe')
    check(got == (OLD_TID, prof_creds), 'ключ поднят из scripts/tunnel-creds.json')
    check(os.path.isfile(prof_creds)
          and open(prof_creds, encoding='utf-8').read() == '{"k":9}',
          'ключ скопирован в профиль с верным содержимым')
    check(not calls, 'подъём из копии — без вызовов cloudflared')

    # 4) Нет ни ключа, ни копий, ни cert.pem -> None, ничего не ломаем.
    os.remove(prof_creds)
    os.remove(os.path.join(f_scripts, 'tunnel-creds.json'))
    check(nt3.ensure_credentials(f_root, f_scripts, 'exe') is None and not calls,
          'нет ключа и нет cert.pem -> None, без побочек')

    # 5) Есть cert.pem (логин делался) -> туннель пересоздаётся на этой машине.
    with open(os.path.join(f_home, 'cert.pem'), 'w', encoding='utf-8') as fh:
        fh.write('CERT')
    with open(scr_cfg, 'w', encoding='utf-8') as fh:
        fh.write(CFG_OLD)
    got = nt3.ensure_credentials(f_root, f_scripts, 'exe')
    check(got == (NEW_TID, os.path.join(f_home, NEW_TID + '.json')),
          'туннель пересоздан, вернулись свежие id и ключ')
    check(calls[0][1:] == ['tunnel', 'delete', '-f', OLD_TID],
          'старый туннель снесён принудительно (-f)')
    routes = [c for c in calls if c[1:3] == ['tunnel', 'route']]
    check(len(routes) == 2
          and all(c[3:6] == ['dns', '--overwrite-dns', NEW_TID] for c in routes)
          and {c[6] for c in routes} == {'hakumods.xyz', 'panel.hakumods.xyz'},
          'DNS перепривязан для всех хостов из конфига')
    patched = open(prof_cfg, encoding='utf-8').read()
    check('tunnel: ' + NEW_TID in patched
          and 'credentials-file: ' + os.path.join(f_home, NEW_TID + '.json') in patched,
          'профильный конфиг переписан на новый ключ')
    patched2 = open(scr_cfg, encoding='utf-8').read()
    check('tunnel: ' + NEW_TID in patched2 and 'OldPC' not in patched2,
          'scripts/config.yml тоже переписан')
    check(open(os.path.join(f_scripts, 'tunnel-creds.json'), encoding='utf-8').read()
          == '{"fresh":true}', 'свежий ключ экспортирован в scripts/ для след. переезда')
    check(_orig_isfile(os.path.join(f_home, NEW_TID + '.json')),
          'файл ключа реально лежит в профиле')
finally:
    nt3._cloudflared_home = _orig_home_fn
    nt3._run_cmd = _orig_run_fn

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
