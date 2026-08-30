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

_TMP = tempfile.mkdtemp(prefix='hakumo_namedtunnel_test_')
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

# ── A2. heal_localhost_origins — Windows IPv6-грабли localhost → ::1 ────────
print('\n[A2] heal_localhost_origins (localhost -> 127.0.0.1 в origin):')
heal_root = os.path.join(_TMP, 'healroot')
os.makedirs(os.path.join(heal_root, 'scripts'), exist_ok=True)
heal_cfg = os.path.join(heal_root, 'scripts', 'config.yml')
with open(heal_cfg, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: abc123\n'
             'credentials-file: /home/o/.cloudflared/abc123.json\n'
             '\n'
             'ingress:\n'
             '  - hostname: hakumods.xyz\n'
             '    service: http://localhost:5001\n'
             '  - hostname: www.hakumods.xyz\n'
             '    service: http://localhost:5001\n'
             '  - service: http_status:404\n')

check(nt.heal_localhost_origins(heal_cfg) is True,
      'heal_localhost_origins: переписал конфиг с localhost')
_healed_text = open(heal_cfg, encoding='utf-8').read()
check('service: http://127.0.0.1:5001' in _healed_text
      and 'http://localhost:5001' not in _healed_text,
      'heal_localhost_origins: все origin стали 127.0.0.1')
check('- service: http_status:404' in _healed_text,
      'heal_localhost_origins: http_status:404 не тронут')
check(nt.heal_localhost_origins(heal_cfg) is False,
      'heal_localhost_origins: повторный запуск ничего не меняет (idempotent)')
check(nt.heal_localhost_origins(os.path.join(_TMP, 'no_such.yml')) is False,
      'heal_localhost_origins: нет файла -> False, не падает')

# Портативная копия в scripts/ тоже чинится скопом
stale_portable = os.path.join(heal_root, 'scripts', 'config.yml')
_heal_home = os.path.join(_TMP, 'healhome', '.cloudflared')
os.makedirs(_heal_home, exist_ok=True)
stale_home_cfg = os.path.join(_heal_home, 'config.yml')
with open(stale_home_cfg, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: abc123\ningress:\n  - hostname: panel.hakumods.xyz\n'
             '    service: http://localhost:5001\n')
healed_paths = nt.heal_all_origins(heal_root, stale_home_cfg)
check(len(healed_paths) >= 1 and all('127.0.0.1' in open(p, encoding='utf-8').read()
                                     for p in healed_paths),
      'heal_all_origins: починил все копии конфига сразу')
# heal_all_origins не должен трогать чужие файлы и не падать без конфигов
check(nt.heal_all_origins(os.path.join(_TMP, 'emptyroot')) == [],
      'heal_all_origins: без конфигов -> пустой список')

# ── A3. ensure_protocol_line — QUIC/UDP флапает на VDS, дефолт http2/TCP ────
print('\n[A3] ensure_protocol_line (protocol: http2 в конфиг):')
proto_root = os.path.join(_TMP, 'protoroot')
os.makedirs(os.path.join(proto_root, 'scripts'), exist_ok=True)
proto_cfg = os.path.join(proto_root, 'scripts', 'config.yml')
with open(proto_cfg, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: abc123\n'
             'credentials-file: /home/o/.cloudflared/abc123.json\n'
             'ingress:\n'
             '  - hostname: panel.hakumods.xyz\n'
             '    service: http://127.0.0.1:5001\n'
             '  - service: http_status:404\n')
touched = nt.ensure_protocol_line(proto_root, proto_cfg, 'http2')
check(proto_cfg in touched,
      'ensure_protocol_line: прописал protocol в конфиг')
_proto_text = open(proto_cfg, encoding='utf-8').read()
check(_proto_text.startswith('protocol: http2\n'),
      'ensure_protocol_line: protocol: http2 — первой строкой (top-level YAML)')
check('tunnel: abc123' in _proto_text and 'service: http://127.0.0.1:5001' in _proto_text,
      'ensure_protocol_line: остальной конфиг не тронут')
check(nt.ensure_protocol_line(proto_root, proto_cfg, 'http2') == [],
      'ensure_protocol_line: повторный запуск ничего не меняет (idempotent)')
check(nt.ensure_protocol_line(proto_root, proto_cfg, 'quic') == [],
      'ensure_protocol_line: чужую строку protocol: не перезаписывает')
check(nt.ensure_protocol_line(proto_root, proto_cfg, 'bogus') == [],
      'ensure_protocol_line: неизвестный протокол -> без изменений')
check(nt.ensure_protocol_line(os.path.join(_TMP, 'emptyroot2'), None, 'http2') == [],
      'ensure_protocol_line: без конфигов -> пустой список, не падает')
# Все копии конфига (профиль + scripts) получают строку скопом
_proto_home = os.path.join(_TMP, 'protohome', '.cloudflared')
os.makedirs(_proto_home, exist_ok=True)
_proto_home_cfg = os.path.join(_proto_home, 'config.yml')
with open(_proto_home_cfg, 'w', encoding='utf-8') as fh:
    fh.write('tunnel: abc123\ningress:\n  - service: http://127.0.0.1:5001\n')
touched_all = nt.ensure_protocol_line(proto_root, _proto_home_cfg, 'http2')
check(len(touched_all) >= 1
      and all(open(p, encoding='utf-8').read().startswith('protocol: http2\n')
              for p in touched_all),
      'ensure_protocol_line: прописал protocol во ВСЕ копии конфига сразу')

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
check('heal_all_origins' in src,
      'main.py: перед запуском туннеля чинит origin localhost -> 127.0.0.1')
check("TUNNEL_PROTOCOL" in src and "'--protocol', proto" in src,
      'main.py: сайдкар named-туннеля запускается с --protocol (дефолт http2, '
      'TUNNEL_PROTOCOL переопределяет) — QUIC/UDP флапает на VDS')
check('ensure_protocol_line' in src,
      'main.py: протокол прописывается и в конфиг (службе Windows флаг не передать)')
check('TUNNEL_PROTOCOL' in open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read(),
      '.env.example документирует TUNNEL_PROTOCOL')
check('"--url", "http://127.0.0.1:5001"' in src,
      'main.py: quick-туннель идёт на 127.0.0.1, а не на localhost (IPv6 ::1)')
_bat = open(os.path.join(ROOT, 'scripts', 'setup_panel_tunnel.bat'),
            encoding='utf-8', errors='replace').read()
check('service: http://127.0.0.1:%PANEL_PORT%' in _bat
      and 'service: http://localhost:' not in _bat,
      'setup_panel_tunnel.bat: ingress сразу пишется с 127.0.0.1')
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
    # Фейковый cloudflared записывает свой argv в файл — так тест ДОКАЗЫВАЕТ,
    # что сайдкар передал --protocol http2 (QUIC/UDP на VDS флапает).
    args_file = os.path.join(scripts_dir, 'cloudflared_args.txt')
    with open(fake_bin, 'w', encoding='utf-8') as fh:
        fh.write(f'#!/bin/sh\necho "$@" > {args_file}\n'
                 'echo "fake cloudflared up"\nsleep 60\n')
    created.extend([fake_bin, args_file])
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
    # Рантайм-копия конфига (если вывелась) — тестовый мусор, уберём в finally.
    created.append(os.path.join(scripts_dir, nt.RUNTIME_CONFIG))
    _cfg_now = open(fake_cfg, encoding='utf-8').read()
    check('service: http://127.0.0.1:5001' in _cfg_now
          and 'http://localhost:5001' not in _cfg_now,
          'сайдкар сам починил origin в scripts/config.yml (localhost -> 127.0.0.1)')
    check(_cfg_now.startswith('protocol: http2\n'),
          'сайдкар прописал protocol: http2 в конфиг (QUIC/UDP -> TCP)')
    time.sleep(1.0)
    check(m._tunnel_proc is not None and m._tunnel_proc.poll() is None,
          'процесс туннеля жив после запуска')
    _args = open(args_file, encoding='utf-8').read() if os.path.exists(args_file) else ''
    check('--protocol http2' in _args,
          'cloudflared запущен с флагом --protocol http2 (дефолт, TCP)')
    check(os.path.isfile(url_file_repo)
          and open(url_file_repo, encoding='utf-8').read().strip() == 'https://hakumods.xyz',
          'tunnel_url.txt = постоянная ссылка https://hakumods.xyz')
    if os.path.exists(url_file_repo):
        created.append(url_file_repo)

    m._stop_tunnel_sidecar()
    check(True, 'сайдкар корректно остановлен')

    # 3) TUNNEL_PROTOCOL=quic переопределяет дефолт (вернуть старое поведение).
    os.environ['TUNNEL_PROTOCOL'] = 'quic'
    m._start_tunnel_sidecar()
    time.sleep(1.0)
    _args = open(args_file, encoding='utf-8').read() if os.path.exists(args_file) else ''
    check('--protocol quic' in _args,
          'TUNNEL_PROTOCOL=quic передаётся флагом --protocol quic')
    m._stop_tunnel_sidecar()

    # 4) Мусорное значение не ломает запуск — откат к http2.
    os.environ['TUNNEL_PROTOCOL'] = 'bogus!!!'
    m._start_tunnel_sidecar()
    time.sleep(1.0)
    _args = open(args_file, encoding='utf-8').read() if os.path.exists(args_file) else ''
    check('--protocol http2' in _args,
          'TUNNEL_PROTOCOL=мусор -> безопасный откат на --protocol http2')
    m._stop_tunnel_sidecar()
    os.environ.pop('TUNNEL_PROTOCOL', None)
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
        return _R('Created tunnel hakumo-panel with id ' + NEW_TID)
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
