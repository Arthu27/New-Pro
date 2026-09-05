# -*- coding: utf-8 -*-
"""Потолок длительности мута: парсер «1ч/2д/90», лимиты-потолки (глоб+роль),
текст отказа, «обновится через», API панели.
Запуск: python3 tests/test_mute_caps.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_mutecaps_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

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


print('== 1. Парсер длительностей ==')
from cogs.moderation import parse_duration_minutes as pdm, human_duration as hd  # noqa: E402

check(pdm('90') == 90, "'90' → 90 минут")
check(pdm('60') == 60, "'60' → 60 минут")
check(pdm('1ч') == 60, "'1ч' → 60")
check(pdm('2 часа') == 120, "'2 часа' → 120")
check(pdm('1h') == 60, "'1h' → 60")
check(pdm('30м') == 30, "'30м' → 30")
check(pdm('45 мин') == 45, "'45 мин' → 45")
check(pdm('1д') == 1440, "'1д' → 1440")
check(pdm('3 дня') == 4320, "'3 дня' → 4320")
check(pdm('2d') == 2880, "'2d' → 2880")
check(pdm('1н') == 10080, "'1н' → 10080")
check(pdm('1 нед') == 10080, "'1 нед' → 10080")
check(pdm('мусор', 5) == 5, 'мусор → дефолт')
check(pdm('') == 5, 'пусто → дефолт 5')
check(hd(30) == '30 мин' and hd(60) == '1 ч' and hd(90) == '90 мин',
      'human: 30 мин / 1 ч / 90 мин')
check(hd(1440) == '1 дн' and hd(4320) == '3 дн' and hd(10080) == '7 дн',
      'human: дни')

print('== 2. Потолки: глобальный ==')
from services import staff_limits as SL  # noqa: E402

G = 900100
check(SL.get_durations(G) == {}, 'из коробки потолка нет')
SL.set_durations(G, who='t', mute=3600)
check(SL.get_durations(G).get('mute') == 3600, 'set 3600 → get 3600')
SL.set_durations(G, who='t', mute=10)
check(SL.get_durations(G).get('mute') == 60, 'клэмп снизу: 10 → 60 сек')
SL.set_durations(G, who='t', mute=10**9)
check(SL.get_durations(G).get('mute') == 28 * 86400, 'клэмп сверху: 28 дней')
SL.set_durations(G, who='t', mute=0)
check(SL.get_durations(G) == {}, '0 = потолок снят')
SL.set_durations(G, who='t', ban=3600)
check('ban' not in SL.get_durations(G), 'чужой ключ (ban) не принимается')

print('== 3. Потолки: роль главнее глобального ==')
SL.set_durations(G, who='t', mute=3600)
check(SL.effective_max_duration(G, 'mute', ()) == 3600, 'без ролей — глобальный')
check(SL.effective_max_duration(G, 'mute', (501,)) == 3600,
      'роль без своего потолка — глобальный')
SL.set_role_durations(G, 501, who='t', role_name='Мод', mute=300)
check(SL.effective_max_duration(G, 'mute', (501,)) == 300,
      'свой потолок роли (300) перекрывает глобальный (3600)')
SL.set_role_durations(G, 502, who='t', role_name='Старший', mute=86400)
check(SL.effective_max_duration(G, 'mute', (501, 502)) == 86400,
      'две роли с потолками — мягчайший (86400)')
SL.set_role_durations(G, 501, who='t', role_name='Мод', mute=0)
check(SL.effective_max_duration(G, 'mute', (501,)) == 3600,
      '0 у роли = свой потолок снят → глобальный')
SL.set_durations(G, who='t', mute=0)
check(SL.effective_max_duration(G, 'mute', (502,)) == 86400 and
      SL.effective_max_duration(G, 'mute', ()) == SL.DEFAULT_MUTE_DURATION_CAP,
      'глобальный снят — роль живёт своим; без роли — дефолт 7 дней '
      '(потолок 100000 минут больше невозможен)')

print('== 4. «Обновится через» ==')
M = 555
SL.set_limits(G, ban=2, clear=0)
SL.set_windows(G, ban=3600)          # окно 1 час
txt0 = SL.refresh_in_text(G, M, 'ban')
check(txt0 is None, 'без трат — текста нет')
SL.record_hit(G, M, 'ban', 1)
txt1 = SL.refresh_in_text(G, M, 'ban')
check(txt1 is not None and ('мин' in txt1 or 'меньше минуты' in txt1),
      f'полчаса до обновления… вернулся текст ({txt1})')
ok, used, limit = SL.check_limit(G, M, 'ban', 1)
check(ok and used == 1, 'вторая трата разрешена (1/2)')
SL.record_hit(G, M, 'ban', 1)
ok2, used2, limit2 = SL.check_limit(G, M, 'ban', 1)
check(not ok2 and used2 == 2 and limit2 == 2, 'третья заблокирована (2/2)')
txt2 = SL.refresh_in_text(G, M, 'ban')
check(txt2 is not None and txt2 != '', f'«обновится через» есть ({txt2})')

print('== 5. Текст отказа по потолку ==')
cap = SL.effective_max_duration(G, 'mute', (502,))
check(hd(max(1, cap // 60)) == '1 дн', 'потолок 86400 в отказе звучит «1 дн»')
req = pdm('2д')
check(req * 60 > cap and hd(req) == '2 дн',
      'просит 2 дня при потолке 1 день → отказ, длительность названа')
cap300 = 300
check(hd(max(1, cap300 // 60)) == '5 мин', 'потолок 300 сек звучит «5 мин», не «1 ч»')

print('== 6. API панели ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class _FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.color = 0x99AAB5
        self.position = 1
        self.members = []


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.roles = [_FakeRole(9001, 'Модератор'), _FakeRole(9002, 'Стажёр')]


class FakeBot:
    guilds = [FakeGuild(777)]
    latency = 0.03
    users = []

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None

    def is_closed(self):
        return False

    def get_user(self, uid):
        return None

    async def change_presence(self, **kw):
        pass


import asyncio as _aio
import threading as _th

_loop = _aio.new_event_loop()
_th.Thread(target=_loop.run_forever, daemon=True).start()
FakeBot.loop = _loop
set_bot_instance(FakeBot())
client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'CapsTester'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

r = client.get('/api/guild/777/staff-limits')
d = r.get_json()
check(r.status_code == 200 and d.get('success') and 'durations' in d,
      'GET отдаёт durations')
check(isinstance(d.get('durations'), dict), 'durations — словарь')

r = client.post('/api/guild/777/staff-limits',
                json={'durations': {'mute': 3600}})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and
      d.get('durations', {}).get('mute') == 3600,
      'POST ставит глобальный потолок 1 час')
r = client.get('/api/guild/777/staff-limits')
check(r.get_json().get('durations', {}).get('mute') == 3600,
      'GET подтверждает сохранение')

r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '9001', 'durations': {'mute': 600}})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and
      d.get('durations', {}).get('mute') == 600,
      'POST роли ставит свой потолок 10 мин')
roles = {str(x['id']): x for x in client.get('/api/guild/777/staff-limits')
         .get_json().get('roles', [])}
check(roles.get('9001', {}).get('durations', {}).get('mute') == 600,
      'роль в GET несёт свой durations')

r = client.post('/api/guild/777/staff-limits',
                json={'durations': {'mute': 0}})
d = r.get_json()
check(d.get('success') and not d.get('durations'),
      'POST 0 снимает глобальный потолок')

# модера не пускают к чужим настройкам лимитов? (владелец-only уже правилами роута)
with client.session_transaction() as s:
    s['role'] = 'moderator'
r = client.post('/api/guild/777/staff-limits', json={'durations': {'mute': 60}})
check(r.status_code >= 400 or not r.get_json().get('success'),
      'не-владелец не может менять потолки')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
