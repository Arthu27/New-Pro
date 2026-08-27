# -*- coding: utf-8 -*-
"""Стоп-правила демо-режима панели: «никакого фейка и чужого сервера в бою».

Проверяем:
  1. web.demo_mode.demo_mode_active — все ветки решения;
  2. web.app._demo_mode() — то же самое в живом приложении;
  3. seed_demo_panel.py — отказывается писать без DEMO_MODE=1,
     сеет в демо и чистит за собой (--clean), не трогая чужие данные;
  4. start_panel.sh/.bat — боевой запуск по умолчанию, посев только
     в явной демо-ветке (--demo / demo).

Запуск: python3 tests/test_demo_mode_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_demo_guard_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ.pop('TOKEN', None)
os.environ.pop('TОКEN', None)
os.environ.pop('DEMO_FORCE', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

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


# ── 1. Чистая функция demo_mode_active ───────────────────────────────────
from web.demo_mode import demo_mode_active, has_real_setup, DEMO_GUILD_PLACEHOLDERS  # noqa: E402

print('== demo_mode_active: ветки решения ==')
check(demo_mode_active({}) is False,
      'без флага DEMO_MODE → не демо')
check(demo_mode_active({'DEMO_MODE': '1'}) is True,
      'DEMO_MODE=1, ничего боевого → демо')
check(demo_mode_active({'DEMO_MODE': '1'}, bot_connected=True) is False,
      'DEMO_MODE=1, но бот подключён → не демо')
check(demo_mode_active({'DEMO_MODE': 'да'}, bot_connected=False) is False,
      'кривое значение флага → не демо')
check(demo_mode_active({'DEMO_MODE': '1', 'TOKEN': 'abc'}) is False,
      'DEMO_MODE=1 + TOKEN в .env → не демо (боевой бот)')
check(demo_mode_active({'DEMO_MODE': '1', 'MAIN_GUILD_ID': '111222333444555666'}) is False,
      'DEMO_MODE=1 + настоящий MAIN_GUILD_ID → не демо (боевой сервер)')
for ph in DEMO_GUILD_PLACEHOLDERS:
    check(demo_mode_active({'DEMO_MODE': '1', 'MAIN_GUILD_ID': ph}) is True,
          f'DEMO_MODE=1 + заглушка {ph} → демо (витрина/тесты)')
check(demo_mode_active({'DEMO_MODE': '1', 'MAIN_GUILD_ID': '111222333444555666',
                        'DEMO_FORCE': '1'}) is True,
      'DEMO_FORCE=1 сознательно включает витрину поверх боевого сервера')
check(demo_mode_active({'DEMO_MODE': '1', 'TOKEN': 'abc', 'DEMO_FORCE': '1'},
                       bot_connected=True) is False,
      'DEMO_FORCE не отменяет живого бота')
check(has_real_setup({}) is False and has_real_setup({'TOKEN': 'x'}) is True
      and has_real_setup({'MAIN_GUILD_ID': '999888777666555444'}) is True
      and has_real_setup({'MAIN_GUILD_ID': '777'}) is False,
      'has_real_setup: токен и настоящий guild — бой, заглушка — нет')

# ── 2. Живой _demo_mode() в web.app ──────────────────────────────────────
print('== web.app._demo_mode: приложение слушается стоп-правил ==')
import web.app as A  # noqa: E402

check(A._demo_mode() is True,
      'витрина (плейсхолдер-сервер, без токена): демо активно')
_saved_mg = os.environ['MAIN_GUILD_ID']
try:
    os.environ['MAIN_GUILD_ID'] = '111222333444555666'
    check(A._demo_mode() is False,
          'боевой MAIN_GUILD_ID + забытый DEMO_MODE=1 → демо НЕ включается')
    os.environ['TOKEN'] = 'real-token'
    check(A._demo_mode() is False,
          'боевой TOKEN → демо НЕ включается')
    os.environ['DEMO_FORCE'] = '1'
    check(A._demo_mode() is True,
          'DEMO_FORCE=1 → витрина поверх боевого .env по явной просьбе')
    os.environ.pop('DEMO_FORCE')
finally:
    os.environ.pop('TOKEN', None)
    os.environ['MAIN_GUILD_ID'] = _saved_mg
check(A._demo_mode() is True, 'окружение восстановлено после проверок')

# API-дымок в «боевом» окружении: панель не сочиняет сервер
try:
    os.environ['MAIN_GUILD_ID'] = '111222333444555666'
    _c = A.app.test_client()
    with _c.session_transaction() as _sess:
        _sess['logged_in'] = True
        _sess['username'] = 't'
        _sess['role'] = 'owner'
    _r = _c.get('/api/guilds')
    check(_r.status_code == 200 and _r.get_json(silent=True) == [],
          '/api/guilds в бою без бота — пустой список, а не сервер-заглушка')
    _r = _c.get('/api/stats')
    check(_r.status_code == 200 and 'error' in (_r.get_json(silent=True) or {}),
          '/api/stats в бою без бота — честная ошибка, а не выдуманные числа')
finally:
    os.environ['MAIN_GUILD_ID'] = _saved_mg

# ── 3. Посев демо-данных: гард, посев, чистка ────────────────────────────
print('== seed_demo_panel: гард и --clean ==')
SEED = os.path.join(ROOT, 'scripts', 'seed_demo_panel.py')


def run_seed(args, env_extra=None, cwd=None):
    env = dict(os.environ)
    env.pop('DEMO_MODE', None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, SEED] + args,
                          cwd=cwd or _TMP, env=env,
                          capture_output=True, text=True, timeout=180)


_sandbox = tempfile.mkdtemp(prefix='hakumo_seed_guard_')
os.makedirs(os.path.join(_sandbox, 'data'), exist_ok=True)

r = run_seed([], cwd=_sandbox)
check(r.returncode != 0 and 'ОТКАЗ' in r.stdout,
      'без DEMO_MODE=1 посев отказывается писать')
check(not os.path.exists(os.path.join(_sandbox, 'data', 'warnings.json')),
      'и data/ остаётся без фейковых варнов')

r = run_seed(['--force'], cwd=_sandbox)
check(r.returncode == 0
      and os.path.exists(os.path.join(_sandbox, 'data', 'warnings.json')),
      '--force (или DEMO_MODE=1) — посев отработал',
      r.stdout[-300:] + r.stderr[-300:])

# примесь «реальных» данных рядом с демо: --clean обязан их пощадить
_warn_path = os.path.join(_sandbox, 'data', 'warnings.json')
with open(_warn_path, 'r', encoding='utf-8') as f:
    _w = json.load(f)
_w['555666777888999000'] = {'42': [{'reason': 'настоящий варн', 'moderator': 'real.mod',
                                    'timestamp': '2026-08-27T10:00:00+00:00'}]}
with open(_warn_path, 'w', encoding='utf-8') as f:
    json.dump(_w, f, ensure_ascii=False)

# канбан: добавляем «реальную» задачу с id ≥ 6
_board_path = os.path.join(_sandbox, 'data', 'team_board.json')
if os.path.exists(_board_path):
    with open(_board_path, 'r', encoding='utf-8') as f:
        _b = json.load(f)
    _b['tasks']['7'] = {'id': 7, 'title': 'реальная задача', 'status': 'todo'}
    _b['next_id'] = 8
    with open(_board_path, 'w', encoding='utf-8') as f:
        json.dump(_b, f, ensure_ascii=False)

# кэш аудита и курсор (пишет бот): демо-GID должен уйти, реальный остаться
for _fn in ('discord_audit_cache.json', 'audit_seen.json'):
    with open(os.path.join(_sandbox, 'data', _fn), 'w', encoding='utf-8') as f:
        json.dump({'987654321098765432': [{'x': 1}] if 'cache' in _fn else '10',
                   '555666777888999000': [{'y': 2}] if 'cache' in _fn else '20'}, f)

r = run_seed(['--clean'], cwd=_sandbox)
with open(_warn_path, 'r', encoding='utf-8') as f:
    _w2 = json.load(f)
_demo_gid = '987654321098765432'
check(r.returncode == 0 and _demo_gid not in _w2
      and '555666777888999000' in _w2,
      '--clean: демо-сервер вырезан, реальный сервер цел')
check(not os.path.exists(os.path.join(_sandbox, 'data', f'modproof_{_demo_gid}.json')),
      '--clean: демо-файлы вида *_{GID}.json удалены')
check(not os.path.exists(os.path.join(_sandbox, 'data', 'demo_channels.json')),
      '--clean: служебные демо-файлы удалены')
if os.path.exists(_board_path):
    with open(_board_path, 'r', encoding='utf-8') as f:
        _b2 = json.load(f)
    check('7' in (_b2.get('tasks') or {}) and '1' not in (_b2.get('tasks') or {}),
          '--clean: реальная задача канбана цела, посевные убраны')
_audit = os.path.join(_sandbox, 'data', 'audit_log.json')
if os.path.exists(_audit):
    with open(_audit, 'r', encoding='utf-8') as f:
        check(_demo_gid not in json.load(f), '--clean: журнал модерации без демо-GID')
_login = os.path.join(_sandbox, 'data', 'login_log.json')
if os.path.exists(_login):
    with open(_login, 'r', encoding='utf-8') as f:
        _ln = json.load(f)
    check(not any(x.get('username') in ('artem.mods', 'sonya.staff') for x in _ln),
          '--clean: демо-входы вырезаны из login_log')
for _fn in ('discord_audit_cache.json', 'audit_seen.json'):
    with open(os.path.join(_sandbox, 'data', _fn), 'r', encoding='utf-8') as f:
        _c = json.load(f)
    check(_demo_gid not in _c and '555666777888999000' in _c,
          f'--clean: {_fn} — демо-GID вырезан, реальный цел')

# ── 4. Стартовые скрипты: бой по умолчанию, посев только в демо-ветке ────
print('== start_panel.sh / .bat: посев не происходит без явного --demo ==')
with open(os.path.join(ROOT, 'start_panel.sh'), 'r', encoding='utf-8') as f:
    sh = f.read()
check('"${1:-}" = "--demo"' in sh and 'if [ "$DEMO" = "1" ]' in sh,
      'start_panel.sh: демо — только по аргументу --demo')
check(sh.index('seed_demo_panel') > sh.index('DEMO=1')
      and '.env не найден' in sh,
      'start_panel.sh: посев внутри демо-ветки; без .env — подсказка про настройку')
check('export MAIN_GUILD_ID=987654321098765432' not in sh
      and 'export PANEL_PASSWORD=preview123' not in sh,
      'start_panel.sh: чужого сервера и паролей в боевой ветке больше нет')
check('DOTENV_PATH=config/panel_preview.env' in sh,
      'start_panel.sh: демо читает свой пресет, боевой .env не трогается')

with open(os.path.join(ROOT, 'start_panel.bat'), 'r', encoding='utf-8') as f:
    bat = f.read()
check('=="demo"' in bat and '=="--demo"' in bat,
      'start_panel.bat: демо — только по аргументу demo/--demo')
check(bat.index('set DEMO_MODE=1') > bat.index('set DEMO=1'),
      'start_panel.bat: DEMO_MODE поднимается только в демо-ветке')
check('set MAIN_GUILD_ID=987654321098765432' not in bat,
      'start_panel.bat: чужого сервера в боевом запуске больше нет')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
