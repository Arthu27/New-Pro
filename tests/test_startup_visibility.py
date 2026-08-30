# -*- coding: utf-8 -*-
"""Тесты стартовой видимости: [ВЕРСИЯ] и фильтр эха туннеля.

Инцидент 30.08: владелец запустил /update со стандартным источником
(main — БЕЗ фиксов), бот молча откатился на старый код. В логе не было
НИ ОДНОГО признака, что фиксов нет. Теперь первая строка запуска —
[ВЕРСИЯ] с sha кода, а эхо cloudflared сжато до значимых строк
(60 строк шума за ресткт топили сообщения бота).

Запуск: python3 tests/test_startup_visibility.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.startup_info import tunnel_line_worth, version_stamp

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


print('== Фильтр эха туннеля: значимое остаётся, шум уходит ==')

# Значимое — показываем
_keep = [
    '2026-08-30T12:39:40Z INF Registered tunnel connection connIndex=0 '
    'connection=1c6080a3 location=fra10 protocol=http2',
    '2026-08-30T12:39:38Z INF |  SUMMARY: Environment is healthy. '
    "cloudflared will use 'http2' as primary protocol.  |",
    '2026-08-30T12:41:02Z ERR Failed to connect to region: dial tcp: timeout',
    '2026-08-30T12:41:02Z WRN Connection terminated, reconnecting',
    'INF Unregistered tunnel connection connIndex=2',
    'INF Retrying connection in 1s',
    'INF Initiated graceful shutdown',
]
for ln in _keep:
    check(tunnel_line_worth(ln), f'оставляем: {ln[21:60].strip()}…')

# Шум — прячем (реальные строки из продакшн-лога 30.08)
_drop = [
    '2026-08-30T12:39:38Z INF Starting tunnel tunnelID=f8202e6f-24e6-…',
    '2026-08-30T12:39:38Z INF Version 2026.8.2 (Checksum c29eee2…)',
    '2026-08-30T12:39:38Z INF GOOS: windows, GOVersion: go1.26.4, '
    'GoArch: amd64',
    '2026-08-30T12:39:38Z INF Settings: map[config:C:\\Users\\…]',
    '2026-08-30T12:39:38Z INF cloudflared will not automatically update '
    'on Windows systems.',
    '2026-08-30T12:39:38Z INF |  DNS Resolution    region1.v2.argotunnel.com'
    '  PASS    DNS Resolved successfully      |',
    '2026-08-30T12:39:38Z INF |  UDP Connectivity  region1.v2.argotunnel.com'
    '  PASS    QUIC connection successful     |',
    '2026-08-30T12:39:38Z INF |  TCP Connectivity  region1.v2.argotunnel.com'
    '  PASS    HTTP/2 connection successful   |',
    '2026-08-30T12:39:38Z INF Tunnel connection curve preferences: '
    '[X25519MLKEM768 CurveID(65074)…] connIndex=0',
    '2026-08-30T12:39:38Z INF ICMP proxy will use 2.26.49.230 as source '
    'for IPv4',
    '2026-08-30T12:39:38Z INF Starting metrics server on 127.0.0.1:20241',
    '2026-08-30T12:39:38Z INF +-----------------------------------------+',
    '2026-08-30T12:39:38Z INF precheck component="DNS Resolution" '
    'details="DNS Resolved successfully" status=pass',
    '',
    '   ',
]
_noise = 0
for ln in _drop:
    if not tunnel_line_worth(ln):
        _noise += 1
check(_noise == len(_drop),
      f'весь INF-шум скрыт ({_noise}/{len(_drop)} строк)')

# На реальном логе 30.08: из ~60 строк cloudflared остаётся мало
_real = [l for l in (_keep + _drop) if l.strip()]
_kept = sum(1 for l in _real if tunnel_line_worth(l))
check(_kept == len(_keep),
      f'из {len(_real)} строк продакшн-лога показывается только {_kept} '
      'значимых')

print('\n== [ВЕРСИЯ]: какой код работает — видно сразу ==')

check(version_stamp(local_sha='ae9e624ffcacf7310a619315657d9ddd217c479e4')
      .startswith('ae9e624'),
      'sha передан явно -> короткий sha в первой строке')
check(version_stamp(local_sha=None, _local_sha_fn=lambda d: 'deadbee42')
      .startswith('deadbee'),
      'sha из git/маркера (инъекция) -> короткий sha')

_tmp = tempfile.mkdtemp(prefix='hakumo_ver_')
check('НЕИЗВЕСТНА' in version_stamp(bot_dir=_tmp),
      'нет ни git, ни маркера -> честное «НЕИЗВЕСТНА» (а не тишина)')

os.makedirs(os.path.join(_tmp, 'data'), exist_ok=True)
with open(os.path.join(_tmp, 'data', '.update_sha'), 'w',
          encoding='utf-8') as f:
    f.write('1234567890abcdef')
_vs = version_stamp(bot_dir=_tmp)
check(_vs.startswith('1234567') and 'маркер' in _vs,
      'после ZIP-обновления версия читается из data/.update_sha')

# пустой маркер не считается версией
with open(os.path.join(_tmp, 'data', '.update_sha'), 'w',
          encoding='utf-8') as f:
    f.write('   ')
check('НЕИЗВЕСТНА' in version_stamp(bot_dir=_tmp),
      'пустой маркер -> «НЕИЗВЕСТНА» (не путаем владельца)')

print('\n== [ВЕРСИЯ]: git ПРИОРИТЕТНЕЕ устаревшего маркера ==')
# Инцидент 30.08: устаревший data/.update_sha врал о версии. Git HEAD
# каталога должен выигрывать у маркера.
import subprocess as _sp
_gdir = tempfile.mkdtemp(prefix='hakumo_ver_git_')
try:
    _sp.run(['git', 'init', '-q'], cwd=_gdir, check=True,
            capture_output=True)
    _sp.run(['git', 'config', 'user.email', 't@t'], cwd=_gdir, check=True,
            capture_output=True)
    _sp.run(['git', 'config', 'user.name', 't'], cwd=_gdir, check=True,
            capture_output=True)
    open(os.path.join(_gdir, 'f.txt'), 'w').write('x')
    _sp.run(['git', 'add', '.'], cwd=_gdir, check=True, capture_output=True)
    _sp.run(['git', 'commit', '-qm', 'v'], cwd=_gdir, check=True,
            capture_output=True)
    _head = _sp.run(['git', 'rev-parse', 'HEAD'], cwd=_gdir, check=True,
                    capture_output=True, text=True).stdout.strip()
    os.makedirs(os.path.join(_gdir, 'data'), exist_ok=True)
    with open(os.path.join(_gdir, 'data', '.update_sha'), 'w') as f:
        f.write('ffffffffffffff')          # устаревший маркер
    _vs2 = version_stamp(bot_dir=_gdir)
    check(_vs2.startswith(_head[:7]) and 'fffffffff' not in _vs2,
          'git HEAD выигрывает у устаревшего data/.update_sha')
except Exception as _ex:
    check(False, f'git-приоритет (ошибка окружения): {_ex}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
