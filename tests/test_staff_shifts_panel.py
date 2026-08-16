# -*- coding: utf-8 -*-
"""Редактор дежурств в панели: полный цикл (видно → управляемо).

Виджет дежурств был read-only: поменять расписание — только из Discord
командой /дежурства. Теперь панель умеет назначать/снимать смены и крутить
часовой пояс, и всё это через РОВНО ту же валидацию, что в боте — новая
чистая try_add_shift в коге переиспользована и командой, и панелью
(тексты ошибок и защита от дублей совпадают 1:1).

Проверяем: чистую try_add_shift (ок/ошибки/дубль/added_by), что команда
кога сохранила тексты, API add/remove/settings (права admin-only, коды,
тексты, персистентность, channel_id не затирается), общий payload (форма
GET == форма ответов мутаций), статику редактора в шаблоне.

Запуск: python3 tests/test_staff_shifts_panel.py
"""
import asyncio
import importlib
import os
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_shiftpanel_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


from cogs import staff_shifts as S  # noqa: E402
from db import GuildData  # noqa: E402

print('== 1. try_add_shift (чистая, общая ког+панель) ==')
shifts = {}
sid, err = S.try_add_shift(shifts, 5, 2, '18:00-22:00', added_by='panel:admin')
check(sid and err is None, 'ок: sid выдан')
check(shifts[sid]['start'] == '18:00' and shifts[sid]['end'] == '22:00'
      and shifts[sid]['added_by'] == 'panel:admin', 'поля записи корректны')
sid2, err = S.try_add_shift(shifts, 5, 2, '10:00-14:00')
check(sid2 and shifts[sid2]['start'] == '10:00' and shifts[sid2]['end'] == '14:00',
      'тот же мод+день, но другой СТАРТ — не дубль, ок')
sid3, err = S.try_add_shift(shifts, 5, 2, '18:00-20:00')
check(sid3 is None and 'уже назначена' in (err or ''), f'дубль (тот же старт): «{err}»')
sid4, err = S.try_add_shift(shifts, 5, 9, '18:00-22:00')
check(sid4 is None and 'День недели' in (err or ''), 'weekday=9 — вежливая ошибка')
sid5, err = S.try_add_shift(shifts, 5, 0, '18-22')
check(sid5 is None and 'ЧЧ:ММ' in (err or ''), 'кривое время — текст ровно как у команды')
sid6, err = S.try_add_shift(shifts, 9, 6, '22:00-02:00')
check(sid6 and shifts[sid6]['end'] == '02:00', 'окно через полночь проходит валидацию')
check(len(shifts) == 3, 'словарь не тронут при неудачных попытках')

print('== 2. Команда кога сохранила поведение (рефакторинг прозрачен) ==')
run = asyncio.get_event_loop().run_until_complete


class FakeCtx:
    def __init__(self):
        self.answers = []
        self.guild = SimpleNamespace(id=88001)
        self.author = SimpleNamespace(id=1)

    async def send(self, text, **kw):
        self.answers.append(str(text))


class FakeBot2:
    pass


cog = S.StaffShifts.__new__(S.StaffShifts)
cog.db = GuildData('staff_shifts')
cog.bot = FakeBot2()
ctx = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx, user=SimpleNamespace(id=7), weekday='сб', time_range='10:00-14:00'))
check(any('Смена добавлена' in a and '`10:00–14:00`' in a for a in ctx.answers), 'назначить: текст как раньше')
ctx2 = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx2, user=SimpleNamespace(id=7), weekday='сб', time_range='10:00-14:00'))
check(any('уже назначена' in a for a in ctx2.answers), 'дубль: текст как раньше')
ctx3 = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx3, user=SimpleNamespace(id=7), weekday='сб', time_range='18-22'))
check(any('ЧЧ:ММ' in a for a in ctx3.answers), 'кривое время: текст как раньше')

# ═══ Панель ═══════════════════════════════════════════════════════════════
print('== 3. API: права ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(path, payload):
    import json as _json
    r = client.post(path, data=_json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


ADD = '/api/guild/777/staff-shifts/add'
REM = '/api/guild/777/staff-shifts/remove'
SET = '/api/guild/777/staff-shifts/settings'

with client.session_transaction() as s:
    s.clear()
check(post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})[0] in (302, 401, 403),
      'гостю закрыто')
login('uye')
check(post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})[0] == 403, 'uye нельзя (403)')
login('mod')
check(post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})[0] == 403,
      'mod нельзя — запись admin-only (403)')
code, body = client.get('/api/guild/777/staff-shifts').status_code, None
login('mod')
check(client.get('/api/guild/777/staff-shifts').status_code == 200, 'чтение по-прежнему mod+')

print('== 4. API: валидация 1:1 с когом ==')
login('owner')
code, body = post(ADD, {'user_id': 'xx', 'weekday': 2, 'start': '18:00', 'end': '22:00'})
check(code == 400 and 'user_id' in (body.get('error') or ''), 'user_id не число — 400')
code, body = post(ADD, {'user_id': '5', 'weekday': 9, 'start': '18:00', 'end': '22:00'})
_, cog_wd_err = S.try_add_shift({}, 5, 9, '18:00-22:00')
check(code == 400 and body.get('error') == cog_wd_err, 'weekday=9: текст ровно из кога')
code, body = post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18-00', 'end': '22:00'})
_, cog_tm_err = S.try_add_shift({}, 5, 2, '18-00-22:00')
check(code == 400 and body.get('error') == cog_tm_err, 'кривое время: текст ровно из кога')

print('== 5. API: цикл добавить → убрать ==')
code, body = post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})
check(code == 200 and body.get('success'), 'назначено (200)')
check({'current', 'next', 'today', 'all', 'tz_offset', 'weekday'} <= set(body),
      'ответ мутации — тот же payload, что у GET')
check(len(body['all']) == 1 and body['all'][0]['user_id'] == 5 and body['all'][0]['weekday_ru'] == 'ср',
      'all содержит новую смену с русским днем')
new_sid = body['all'][0]['id']
stored = GuildData('staff_shifts').get(777, 'shifts', {})
check(stored.get(new_sid, {}).get('added_by') == 'panel:admin', 'в БД видно, что назначено из панели')
code, body = post(ADD, {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})
check(code == 400 and 'уже назначена' in (body.get('error') or ''), 'дубль через панель — 400 словами бота')
code, body = post(REM, {'shift_id': 'nope'})
check(code == 404, 'снятие несуществующей — 404')
code, body = post(REM, {'shift_id': new_sid})
check(code == 200 and body.get('all') == [], 'снята; all снова пуст')

print('== 6. API: часовой пояс ==')
GuildData('staff_shifts').set(777, 'settings', {'channel_id': 42, 'tz_offset': 3})
code, body = post(SET, {'tz_offset': 'abc'})
check(code == 400, 'пояс не число — 400')
code, body = post(SET, {'tz_offset': 99})
check(code == 400 and 'Пояс' in (body.get('error') or ''), 'пояс 99 — границы как у /дежурства пояс')
code, body = post(SET, {'tz_offset': -5})
check(code == 200 and body.get('tz_offset') == -5 and body.get('weekday'), 'пояс -5 применён, payload пересчитан')
stored = GuildData('staff_shifts').get(777, 'settings', {})
check(stored.get('channel_id') == 42 and stored.get('tz_offset') == -5,
      'channel_id не затёрт при смене пояса')

print('== 7. Редактор в шаблоне ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
for token in ('shiftManage', 'shMemberList', 'shiftAdd()', 'shiftRemove', 'shiftTzSave',
              '/staff-shifts/add', '/staff-shifts/remove', '/staff-shifts/settings',
              "role == 'admin' or role == 'owner'", 'renderShiftEditor', 'bindShiftEditor'):
    assert token in src, token
check(True, 'DOM, хендлеры и гейтинг admin/owner на месте')
check('/api/member-search/' in src, 'подсказки участников через существующий member-search API')
check("esc(s.name)" in src and "esc(m.display_name)" in src, 'имена через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (FA-иконки только)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
