# -*- coding: utf-8 -*-
"""Аудит контрактов: API отдают именно те поля, которые читает фронт.

Три уровня:
1. Контракты API: GET каждого ключевого эндпоинта в демо-режиме → JSON
   с обязательными полями (те самые, что дергают шаблоны).
2. POST-smoke: мутирующие эндпоинты на пустые/битые тела отвечают JSON
   (200/400/404), а не падают 500.
3. Целостность демо-данных data/: структура каналов (категории/позиции),
   xp-файлы, журнал аудита, варны, доска команды, панель-логи.

Запуск: python3 tests/test_contract_audit.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# data/ — gitignored, демо-фикстур в чистом чекауте нет. API каналов в
# демо-режиме читает data/demo_channels.json по абсолютному пути к корню,
# поэтому сеем его заранее (тот же паттерн, что в test_panel_polish.py).
if not os.path.isfile(os.path.join(ROOT, 'data', 'demo_channels.json')):
    # Посев демо бережётся от случайного запуска: тест просит его явно (DEMO_MODE=1)
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'seed_demo_panel.py')],
                   capture_output=True, text=True, timeout=180, cwd=ROOT,
                   env={**os.environ, 'DEMO_MODE': '1'})

_TMP = tempfile.mkdtemp(prefix='hakumo_contract_test_')
os.chdir(_TMP)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

# копируем демо-фикстуры репозитория (если есть), чтобы ветки-демо работали
_src_data = os.path.join(ROOT, 'data')
if os.path.isdir(_src_data):
    for fn in os.listdir(_src_data):
        _s = os.path.join(_src_data, fn)
        _d = os.path.join('data', fn)
        if os.path.isdir(_s):
            shutil.copytree(_s, _d, dirs_exist_ok=True)
        else:
            shutil.copy(_s, _d)

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

GID = '777'

# ── (label, url, required keys) или (label, url, ('list', [item keys])) ──
CONTRACTS = [
    ('статус-публичный', '/api/status-public',
     ['ok', 'online', 'latency_ms', 'guilds', 'users_cached', 'uptime_human']),
    ('общая статистика', '/api/stats', ['guilds', 'users', 'online', 'latency', 'status']),
    ('список серверов', '/api/guilds', ('list', ['id', 'name', 'members'])),
    ('публичные серверы', '/api/public/guilds', ('list', ['id', 'name', 'members'])),
    ('каналы сервера', f'/api/guild/{GID}/channels', ('list', ['id', 'name', 'type', 'position'])),
    ('роли сервера', f'/api/guild/{GID}/roles', ('list', ['id', 'name', 'color', 'members'])),
    ('лидерборд', f'/api/guild/{GID}/leaderboard', ('list', ['name', 'level', 'xp'])),
    ('конфиг левелинга', '/api/leveling/config',
     ['enabled', 'text_xp', 'voice_xp', 'streak_bonus', 'achievements_enabled', 'engagement_dm', 'level_rewards']),
    ('настройки левелинга сервера', f'/api/guild/{GID}/leveling',
     ['enabled', 'notify', 'xp_min', 'xp_max', 'cooldown', 'level_message']),
    ('статистика левелинга', '/api/leveling/stats',
     ['total_users', 'max_level', 'total_xp', 'total_achievements', 'total_ach_available', 'top']),
    ('ачивки', '/api/leveling/achievements', ['catalog', 'unlocked']),
    ('награды уровней', '/api/leveling/rewards', ['rewards']),
    ('конфиг AI-модерации', '/api/ai-mod/config',
     ['enabled', 'auto_actions', 'escalation', 'languages', 'sensitivity']),
    ('статистика AI-модерации', '/api/ai-mod/stats',
     ['total', 'last_24h', 'bans', 'mutes', 'kicks', 'warns']),
    ('здоровье бота', '/api/bot/health', ['current', 'history']),
    ('статистика бота', '/api/bot-stats',
     ['guilds', 'users', 'latency', 'uptime', 'cpu', 'ram', 'history']),
    ('расписание', '/api/schedule/state', ['ok', 'channels', 'items']),
    ('темп-наказания', '/api/temp-mod/active', ['mutes', 'bans', 'kicks', 'scheduled']),
    ('розыгрыши', f'/api/giveaway/{GID}', ('list', ['id', 'prize', 'winners', 'status', 'participants'])),
    ('лента активности', '/api/activity-feed', ['items']),
    ('уведомления', '/api/notifications/poll', ['notifications']),
    ('подсказки логина', '/api/login/suggest?q=eco', ['success', 'suggestions']),
    ('ux-поиск', '/api/ux/search?q=%D0%BA%D0%B0%D0%BD%D0%B0%D0%BB', ['query', 'groups', 'total']),
    ('отчёт модерации', '/api/mod-report?days=7', ['by_action', 'per_day', 'days', 'mods_total']),
    ('пороги варнов', f'/api/warn-config/{GID}', ['thresholds']),
    ('анти-краш обзор', '/api/anticrash/overview',
     ['ok', 'total_errors', 'daily7', 'top_types', 'top_cogs']),
    ('анти-краш конфиг', '/api/anticrash/config', ['ok', 'config', 'order', 'meta']),
    ('карцер', '/api/tagjail/state', ['ok', 'config', 'jailed', 'guild']),
    ('музыка', '/api/music/state', ['success', 'offline', 'connected', 'playing', 'queue']),
    ('счётчики автоматики', '/api/automation/counters-preview', ['success', 'enabled', 'rows']),
    ('доска команды', '/api/team-board', ['columns']),
    ('карма', f'/api/guild/{GID}/karma/overview',
     ['success', 'snapshot', 'feed', 'pairs', 'can_edit']),
    ('карточка 360', f'/api/guild/{GID}/member-card/lookup?user=ecobar', ['success', 'card']),
    ('дежурства', f'/api/duty/{GID}', ['duty', 'points']),
    ('профиль участника', f'/api/member-profile/{GID}/1406597367695806564',
     ['id', 'warnings', 'warn_count', 'cases']),
    ('AFK-список', f'/api/afk/{GID}', ('list', [])),
    ('дни рождения', f'/api/guild/{GID}/birthdays', ('list', [])),
]

print('== 1. Контракты GET-API ==')
_bad = []
for label, url, contract in CONTRACTS:
    r = client.get(url)
    if r.status_code != 200:
        _bad.append(f'{label}: HTTP {r.status_code}')
        continue
    try:
        d = r.get_json()
    except Exception:
        _bad.append(f'{label}: не JSON')
        continue
    if isinstance(contract, tuple) and contract[0] == 'list':
        if not isinstance(d, list):
            _bad.append(f'{label}: ожидали список, получили {type(d).__name__}')
        elif contract[1]:
            for it in d:
                for k in contract[1]:
                    if k not in it:
                        _bad.append(f'{label}: элемент без {k!r}')
                        break
    else:
        for k in contract:
            if k not in d:
                _bad.append(f'{label}: нет поля {k!r}')
check(not _bad, f'{len(CONTRACTS)} контрактов проверено, нарушений: {len(_bad)}')
for b in _bad[:8]:
    print(f'     {b}')

print('== 2. POST-smoke: битые тела не роняют сервер ==')
POSTS = [
    ('конфиг левелинга', '/api/leveling/config', {}),
    ('конфиг AI-модерации', '/api/ai-mod/config', {}),
    ('сохранить анонс (пусто)', '/api/schedule/save', {}),
    ('тоггл анонса (нет id)', '/api/schedule/toggle', {}),
    ('удалить анонс (нет id)', '/api/schedule/delete', {}),
    ('роль с пустым именем', f'/api/guild/{GID}/roles/create', {'name': ''}),
    ('удалить несуществующую роль', f'/api/guild/{GID}/roles/424242/delete', {}),
    ('превью локдауна', f'/api/guild/{GID}/lockdown/preview', {'spec': 'all'}),
    ('локдаун несуществующего', f'/api/guild/{GID}/lockdown/lock', {'spec': '424242'}),
    ('публичная заявка (пусто)', '/api/public/apply', {}),
]
_bad = []
for label, url, body in POSTS:
    r = client.post(url, json=body)
    if r.status_code == 500:
        _bad.append(f'{label}: 500')
        continue
    try:
        r.get_json()
    except Exception:
        _bad.append(f'{label}: не JSON ({r.status_code})')
check(not _bad, f'{len(POSTS)} POST-smoke, падений: {len(_bad)}')
for b in _bad:
    print(f'     {b}')

print('== 3. Целостность демо-данных data/ ==')
_dbad = []


def _load(name):
    p = os.path.join('data', name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return 'broken'


# каналы
ch = _load('demo_channels.json')
if ch is None:
    _dbad.append('demo_channels.json нет')
elif ch == 'broken':
    _dbad.append('demo_channels.json битый')
elif isinstance(ch, list):
    if not ch:
        _dbad.append('demo_channels.json пуст')
    cat_ids = {str(c['id']) for c in ch if c.get('type') == 'category'}
    for c in ch:
        if c.get('type') != 'category' and c.get('category_id') and str(c['category_id']) not in cat_ids:
            _dbad.append(f"канал {c.get('id')} ссылается на несуществующую категорию {c.get('category_id')}")
        if c.get('type') not in ('text', 'voice', 'category'):
            _dbad.append(f"канал {c.get('id')}: неизвестный тип {c.get('type')!r}")
        if not isinstance(c.get('position'), int):
            _dbad.append(f"канал {c.get('id')}: position не число")

# xp
xp_files = [f for f in os.listdir('data') if f.startswith('xp_') and f.endswith('.json')]
for xf in xp_files:
    d = _load(xf)
    if d == 'broken' or not isinstance(d, dict):
        _dbad.append(f'{xf}: битая структура')
        continue
    for uid, u in d.items():
        if not isinstance(u, dict) or 'name' not in u or 'xp' not in u:
            _dbad.append(f'{xf}: участник {uid} без name/xp')

# аудит
au = _load('audit_log.json')
if isinstance(au, dict) and au != 'broken':
    for gid, evs in au.items():
        if not isinstance(evs, list):
            _dbad.append(f'audit_log: {gid} не список')
            continue
        for e in evs:
            if not isinstance(e, dict) or 'action' not in e or 'timestamp' not in e:
                _dbad.append(f'audit_log[{gid}]: событие без action/timestamp')
                break

# варны
w = _load('warnings.json')
if isinstance(w, dict) and w != 'broken':
    for gid, users in w.items():
        if not isinstance(users, dict):
            _dbad.append(f'warnings: {gid} не dict')
            continue
        for uid, warns in users.items():
            if not isinstance(warns, list):
                _dbad.append(f'warnings[{gid}][{uid}] не список')
                continue
            for wr in warns:
                if not isinstance(wr, dict) or 'timestamp' not in wr:
                    _dbad.append(f'warnings[{gid}][{uid}]: варн без timestamp')
                    break

# доска команды
tb = _load('team_board.json')
if isinstance(tb, dict) and tb != 'broken':
    cols = tb.get('columns', {})
    for key, col in cols.items():
        if not isinstance(col, dict) or 'tasks' not in col or not isinstance(col['tasks'], list):
            _dbad.append(f'team_board: колонка {key} без tasks')

# панель-логи
pl = _load('panel_logs.json')
if isinstance(pl, list) and pl:
    for e in pl:
        if not isinstance(e, dict) or 'action' not in e:
            _dbad.append('panel_logs: запись без action')
            break

check(not _dbad, f'данные целы (проблем: {len(_dbad)})')
for b in _dbad[:8]:
    print(f'     {b}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
