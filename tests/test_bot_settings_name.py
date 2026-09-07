# -*- coding: utf-8 -*-
"""«Настройки бота»: имя бота видно на странице.

Жалоба владельца: «настройки бота — проблема с именем, его не видно».
Имя подключённого бота не показывалось нигде: карточка «Информация» шла
сразу с префикса, а API не отдавал имя вовсе. Отдельный процесс панели
(start_panel / gunicorn) имени не знал и знать не мог — его нет в пульсе.

Проверяем:
  1. bot_bridge.write_state пишет identity (имя/ID/аватар) в пульс,
     state_identity читает его обратно;
  2. старт до логина (identity пуст) НЕ затирает последнее известное имя;
  3. /api/bot-settings отдаёт bot_name/bot_username/bot_id/bot_avatar:
     из живого bot_instance → из пульса → демо-заглушка;
  4. шаблон страницы содержит блок «кто такой бот» (аватар + имя + ID).

Запуск: python3 tests/test_bot_settings_name.py
"""
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_botname_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ.pop('TOKEN', None)

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


print('== bot_bridge: имя бота в пульсе ==')
from services import bot_bridge as bb  # noqa: E402

STATE = os.path.join(_TMP, 'data', 'bot_state.json')
if os.path.exists(STATE):
    os.remove(STATE)

IDENT = {'id': '111222333444555666', 'name': 'hakumo_guard',
         'display_name': 'Хакумо · Страж', 'avatar': 'https://cdn.example/av.png'}
bb.write_state('online', guilds=[{'id': '777', 'name': 'Сервер'}],
               force=True, identity=IDENT)
with open(STATE, encoding='utf-8') as f:
    pulse = json.load(f)
check(isinstance(pulse.get('identity'), dict)
      and pulse['identity'].get('display_name') == 'Хакумо · Страж',
      'write_state пишет identity в пульс', str(pulse.get('identity')))
got = bb.state_identity()
check(got.get('name') == 'hakumo_guard' and got.get('id') == '111222333444555666'
      and got.get('avatar') == 'https://cdn.example/av.png',
      'state_identity читает имя/ID/аватар', str(got))

# старт до логина: бота видели, user ещё не пришёл — имя не теряем
bb.write_state('starting', guilds=[], force=True, identity=None)
with open(STATE, encoding='utf-8') as f:
    pulse2 = json.load(f)
check(pulse2.get('identity', {}).get('name') == 'hakumo_guard',
      'пульс без identity сохраняет последнее известное имя',
      str(pulse2.get('identity')))

# старый пульс без identity вовсе (легаси-файл) — читатель честно пустой
with open(STATE, 'w', encoding='utf-8') as f:
    json.dump({'status': 'online', 'ts': 0, 'guilds': []}, f)
check(bb.state_identity() == {},
      'легаси-пульс без identity → пусто, без падения')
# восстанавливаем нормальный пульс для API-тестов ниже
bb.write_state('online', guilds=[{'id': '777', 'name': 'Сервер'}],
               force=True, identity=IDENT)

print('== /api/bot-settings: имя бота в ответе ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

# ── 1. Живой бот в процессе панели ──
_prev_bot = appmod.bot_instance
try:
    appmod.bot_instance = SimpleNamespace(
        is_closed=lambda: False, guilds=[SimpleNamespace(id=777)],
        user=SimpleNamespace(
            id=111222333444555666, name='hakumo_guard',
            display_name='Хакумо · Страж',
            display_avatar=SimpleNamespace(url='https://cdn.example/av.png')))
    r = client.get('/api/bot-settings')
    d = r.get_json(silent=True) or {}
    check(r.status_code == 200 and d.get('ok')
          and d.get('bot_name') == 'Хакумо · Страж'
          and d.get('bot_username') == 'hakumo_guard'
          and d.get('bot_id') == '111222333444555666'
          and d.get('bot_avatar') == 'https://cdn.example/av.png',
          'живой бот: имя/@username/ID/аватар в ответе',
          str({k: d.get(k) for k in ('bot_name', 'bot_username', 'bot_id', 'bot_avatar')}))
finally:
    appmod.bot_instance = _prev_bot

# ── 2. Панель отдельным процессом: имя из пульса ──
r = client.get('/api/bot-settings')
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('bot_name') == 'Хакумо · Страж',
      'отдельный процесс: имя взято из пульса data/bot_state.json',
      f'bot_name={d.get("bot_name")!r}')
check(d.get('bot_online') is True,
      'отдельный процесс: онлайн по-прежнему определяется пульсом')

# ── 3. Ничего не известно (нет бота, нет живого пульса) ──
bb.write_state('offline', guilds=[], force=True, identity=None)
with open(STATE, encoding='utf-8') as f:
    _p = json.load(f)
_p.pop('identity', None)
_p['ts'] = 0                      # протухший пульс = офлайн
with open(STATE, 'w', encoding='utf-8') as f:
    json.dump(_p, f)
r = client.get('/api/bot-settings')
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and not d.get('bot_name')
      and d.get('bot_online') is False,
      'бота нет и пульс протух: имя пустое, статус офлайн — без 500',
      str({k: d.get(k) for k in ('bot_name', 'bot_online')}))

print('== Шаблон страницы: блок «кто такой бот» ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'bot_settings.html'),
           encoding='utf-8').read()
for marker, label in [
    ('id="bs-bot-name"', 'элемент имени бота'),
    ('id="bs-bot-avatar"', 'аватар бота'),
    ('id="bs-bot-dot"', 'индикатор онлайн/офлайн'),
    ('d.bot_name', 'JS читает bot_name из API'),
    ('d.bot_avatar', 'JS подставляет аватар из API'),
]:
    check(marker in tpl, f'шаблон: {label}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
os.chdir(ROOT)
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
