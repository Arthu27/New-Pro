# -*- coding: utf-8 -*-
"""Полный сброс данных (reset_server_data.py): «удали все данные о серверах».

Скрипт считает базу от своего расположения, поэтому тест копирует его в
песочницу с фикстурой data/ и проверяет: сносится всё (включая вложенные
папки, логи, tunnel_url.txt), повторный запуск честно говорит «чисто»,
--keep-auth сохраняет доступ к панели, .env не трогается.

Запуск: python3 tests/test_reset_server_data.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'reset_server_data.py')

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


def make_sandbox():
    box = tempfile.mkdtemp(prefix='hakumo_reset_')
    data = os.path.join(box, 'data')
    os.makedirs(os.path.join(data, 'uploads', 'proofs'))
    os.makedirs(os.path.join(data, 'flask_sessions'))
    # журналы «всех серверов» — то, что просили снести целиком
    with open(os.path.join(data, 'audit_log.json'), 'w', encoding='utf-8') as f:
        json.dump({'111': [{'action': 'Бан'}], '222': [{'action': 'bot_add'}]}, f)
    for name in ('discord_audit_cache.json', 'warnings.json', 'mod_data.json'):
        with open(os.path.join(data, name), 'w', encoding='utf-8') as f:
            json.dump({'222': []}, f)
    with open(os.path.join(data, 'uploads', 'proofs', '222_1.png'), 'w') as f:
        f.write('png')
    with open(os.path.join(data, 'panel_credentials.json'), 'w', encoding='utf-8') as f:
        json.dump({'user': 'owner', 'password_hash': 'x'}, f)
    with open(os.path.join(data, 'members.json'), 'w', encoding='utf-8') as f:
        json.dump({}, f)
    os.makedirs(os.path.join(box, 'logs'))
    with open(os.path.join(box, 'logs', 'bot.log'), 'w') as f:
        f.write('log')
    with open(os.path.join(box, 'tunnel_url.txt'), 'w') as f:
        f.write('https://x.trycloudflare.com')
    os.makedirs(os.path.join(box, 'cogs', '__pycache__'))
    with open(os.path.join(box, 'cogs', '__pycache__', 'logs.cpython-311.pyc'), 'w') as f:
        f.write('pyc')
    with open(os.path.join(box, '.env'), 'w', encoding='utf-8') as f:
        f.write('TOKEN=abc\nMAIN_GUILD_ID=111\n')
    shutil.copy(SCRIPT, os.path.join(box, 'reset_server_data.py'))
    return box


def run(box, *args):
    return subprocess.run([sys.executable, os.path.join(box, 'reset_server_data.py')] + list(args),
                          capture_output=True, text=True, timeout=120,
                          input='yes\n')


print('== полный снос: data/, логи, туннель, кэш — всё ==')
box = make_sandbox()
r = run(box, '--yes')
data = os.path.join(box, 'data')
check(r.returncode == 0, f'сброс отработал (rc={r.returncode})', r.stderr[-300:])
check(not os.path.exists(os.path.join(data, 'audit_log.json'))
      and not os.path.exists(os.path.join(data, 'discord_audit_cache.json'))
      and not os.path.exists(os.path.join(data, 'mod_data.json')),
      'журналы всех серверов стёрты')
check(not os.path.exists(os.path.join(data, 'uploads')),
      'вложенные папки (uploads/proofs) стёрты тоже')
check(not os.path.exists(os.path.join(data, 'panel_credentials.json')),
      'без --keep-auth доступ к панели тоже стирается')
check(not os.path.exists(os.path.join(box, 'logs', 'bot.log'))
      and not os.path.exists(os.path.join(box, 'tunnel_url.txt'))
      and not os.path.exists(os.path.join(box, 'cogs', '__pycache__')),
      'логи, tunnel_url.txt и кэш Python стёрты')
check(open(os.path.join(box, '.env'), encoding='utf-8').read().startswith('TOKEN=abc'),
      '.env не тронут (TOKEN и MAIN_GUILD_ID на месте)')

r = run(box, '--yes')
check('нечего' in r.stdout.lower(), 'повторный запуск: честно «удалять нечего»')

print('== --keep-auth: сносим данные, доступ к панели остаётся ==')
box2 = make_sandbox()
r = run(box2, '--yes', '--keep-auth')
data2 = os.path.join(box2, 'data')
check(os.path.exists(os.path.join(data2, 'panel_credentials.json'))
      and os.path.exists(os.path.join(data2, 'members.json')),
      'файлы доступа сохранились')
check(not os.path.exists(os.path.join(data2, 'audit_log.json'))
      and not os.path.exists(os.path.join(data2, 'warnings.json')),
      'а серверные данные стёрты')

print('== --dry-run: только показывает, ничего не удаляет ==')
box3 = make_sandbox()
r = run(box3, '--dry-run')
check(os.path.exists(os.path.join(box3, 'data', 'audit_log.json'))
      and '--dry-run' in r.stdout,
      'сухой прогон ничего не тронул')

print('== обёртка для Windows на месте и зовёт сброс корректно ==')
with open(os.path.join(ROOT, 'reset_server_data.bat'), encoding='utf-8') as f:
    bat = f.read()
check('reset_server_data.py --yes --keep-auth' in bat
      and 'закрой окно бота' in bat.lower(),
      'reset_server_data.bat: полный сброс с --keep-auth + предупреждение про бота')

for b in (box, box2, box3):
    shutil.rmtree(b, ignore_errors=True)

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
