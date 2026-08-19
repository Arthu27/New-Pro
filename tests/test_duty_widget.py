# -*- coding: utf-8 -*-
"""Виджет дежурств на дашборде: /api/guild/<gid>/staff-shifts + плашка в dashboard.

Ког /дежурства хранил расписание только для Discord: кто сейчас на смене —
видно лишь по команде. Виджет читает то же хранилище (GuildData
'staff_shifts') из панели и показывает текущее дежурство, ближайшую смену
и чипы сегодняшнего дня прямо на дашборде (mod+, автообновление 30 с).

Проверяем: форму ответа (current/next/today/tz), активную смену «по живым
часам», фолбэк имён при офлайн-боте, пустое расписание, валидацию и права,
гейтинг виджета от участников, auto-refresh обоими механизмами.

Запуск: python3 tests/test_duty_widget.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_shiftwgt_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'

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


from db import GuildData  # noqa: E402

appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()

TZ3 = timezone(timedelta(hours=3))


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def get(gid):
    r = client.get(f'/api/guild/{gid}/staff-shifts')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


def fmt(dt):
    return dt.strftime('%H:%M')


# ── Сид: «живая» активная смена (вокруг текущего момента в UTC+3) ─────────
local_now = datetime.now(timezone.utc).astimezone(TZ3)
active_start = local_now - timedelta(minutes=30)
active_end = local_now + timedelta(minutes=30)
# при пересечении полночи смена принадлежит дню СВОЕГО начала,
# а не сегодняшнему (перенос через полночь в active_shift)
active_wd = active_start.weekday()
future_start = local_now + timedelta(hours=2)
future_end = local_now + timedelta(hours=3)

db = GuildData('staff_shifts')
db.set(777, 'shifts', {
    'aaaa': {'user_id': 5, 'weekday': active_wd,
             'start': fmt(active_start), 'end': fmt(active_end),
             'added_by': '1', 'added_at': local_now.isoformat()},
    'bbbb': {'user_id': 7, 'weekday': future_start.weekday(),
             'start': fmt(future_start), 'end': fmt(future_end),
             'added_by': '1', 'added_at': local_now.isoformat()},
})
db.set(777, 'settings', {'tz_offset': 3, 'channel_id': None})
db.set(778, 'shifts', {
    'cccc': {'user_id': 9, 'weekday': future_start.weekday(),
             'start': fmt(future_start), 'end': fmt(future_end)},
})
db.set(778, 'settings', {'tz_offset': 3})


class FakeBot:
    def __init__(self):
        m5 = SimpleNamespace(display_name='Мод Великий')
        guild = SimpleNamespace(get_member=lambda uid: m5 if int(uid) == 5 else None)
        self._g = {777: guild}

    def get_guild(self, gid):
        return self._g.get(gid)


print('== 1. Доступ и валидация ==')
with client.session_transaction() as s:
    s.clear()
code, body = get(777)
check(code in (302, 401, 403), f'гостю закрыто ({code})')
login('uye')
code, body = get(777)
check(code == 403, 'uye нельзя (403)')
login('mod')
code, body = get('abc')
check(code == 400 and body.get('error'), f'кривой id сервера — 400: {body}')

print('== 2. Активная смена и форма ответа ==')
appmod.set_bot_instance(FakeBot())
code, body = get(777)
check(code == 200 and body.get('success'), 'mod: 200 + success')
check({'tz_offset', 'current', 'next', 'today', 'weekday'} <= set(body), 'полный набор ключей')
cur = body['current']
check(cur is not None and cur['user_id'] == 5, 'активная смена определена')
check(cur['name'] == 'Мод Великий', 'имя резолвится из кэша бота')
check(cur['ends_at'].endswith('+00:00'), 'ends_at в aware-ISO UTC')
check(body['tz_offset'] == 3 and body['weekday'], 'часовой пояс и день недели в ответе')
act = [t for t in body['today'] if t['active']]
check(len(act) == 1 and act[0]['user_id'] == 5, 'сегодняшний чип активной смены помечен')
check(all({'user_id', 'name', 'start', 'end', 'active'} <= set(t) for t in body['today']),
      'у всех чипов полный набор полей')

print('== 3. Ближайшая смена ==')
nxt = body['next']
check(nxt is not None and nxt['user_id'] == 7, 'next — будущая смена другого мода')
check(nxt['name'] == 'ID 7', 'мод вне кэша — честный фолбэк на ID')
check(nxt['weekday'] and nxt['starts_at'].endswith('+00:00'), 'weekday по-русски + aware starts_at')

print('== 4. Бот офлайн — имена деградируют, виджет не падает ==')
appmod.set_bot_instance(None)
code, body = get(777)
check(code == 200 and body['current']['name'] == 'ID 5', 'без бота current живёт с ID-фолбэком')
appmod.set_bot_instance(FakeBot())

print('== 5. Пустое и «только будущее» расписания ==')
code, body = get(778)
check(body['current'] is None and body['next'] is not None,
      '778: сейчас пусто, но next есть')
check(all(not t['active'] for t in body['today']), '778: активных чипов нет')
code, body = get(779)
check(body['success'] and body['current'] is None and body['next'] is None and body['today'] == [],
      '779 (без расписания): честные null и пустой список')

print('== 6. Виджет в дашборде ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
for token in ('id="shiftNow"', 'id="shiftToday"', 'loadShifts', '/staff-shifts',
              "role != 'uye'", 'shift-dot on', '/дежурства'):
    assert token in src, token
check(True, 'DOM-якоря, загрузчик, гейтинг от uye, подсказка про /дежурства')
check('setLiveRefresh(loadShifts, 30000)' in src and 'setInterval(loadShifts, 30000)' in src,
      'автообновление 30 с в обоих механизмах рефреша')
check("esc(s.name)" in src and "esc(d.current.name)" in src, 'имена рендерятся через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи в дашборде нет (FA-иконки только)')

route_src = open(os.path.join(ROOT, 'web', 'routes', 'community.py'), encoding='utf-8').read()
check("'/api/guild/<guild_id>/staff-shifts'" in route_src and 'active_shift' in route_src,
      'эндпоинт в community.py использует чистые функции кога')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
