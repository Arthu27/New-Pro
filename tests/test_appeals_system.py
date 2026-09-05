# -*- coding: utf-8 -*-
"""Система апелляций — обход находок 2026-09-05 (полная проверка).

1) Принятие апелляции = разбан, расходка «unban»: лимит проверяется ДО
   решения у кнопки кога (раньше блок стоял внутри except ACL и в
   нормальном пути не работал вовсе; отклонение лимит не тратит).
2) Панель при принятии снимает муты тем же вызовом, что кнопка кога
   (роль чат-мута, роль войс-мута, server-mute, нативный таймаут).
3) Решение из панели — гейт «mod»: право всё равно решает ACL «Бан»,
   панель не должна быть строже кнопок под карточкой.
Плюс живой POST решения, повторное решение (409), страница /appeals.

Запуск: python3 tests/test_appeals_system.py
"""
import asyncio
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_sys_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
os.environ['MAIN_GUILD_ID'] = '511000'   # активный сервер панели = gid теста

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


GID = 511000
UID = 777000000000000731
ROLE_ID = 6101

from datetime import datetime, UTC  # noqa: E402
from cogs import appeals as AP  # noqa: E402
from cogs.appeals import AppealView  # noqa: E402
from services import staff_limits as SL  # noqa: E402
from services.permission_acl import (set_action_rule,  # noqa: E402
                                     clear_action_rules)


class _Role:
    def __init__(s, rid):
        s.id = rid


class _User:
    def __init__(s, uid, roles=()):
        s.id = uid
        s.roles = list(roles)
        s.bot = False
        s.display_name = 'Модератор'


class _Resp:
    def __init__(s):
        s.msg = None
        s.edited = 0

    async def send_message(s, content=None, **kw):
        s.msg = str(content or '')

    async def edit_message(s, **kw):
        s.edited += 1


class _Embed:
    def __init__(s):
        s.title = 'Апелляция #1'
        s.color = None
        s.footer = None

    def set_footer(s, text=None, **kw):
        s.footer = text


class _Msg:
    def __init__(s):
        s.embeds = [_Embed()]


class _Inter:
    def __init__(s, user):
        s.user = user
        s.response = _Resp()
        s.message = _Msg()


class _Guild:
    def __init__(s, gid):
        s.id = gid
        s.owner_id = 1
        s.unbans = []

    def get_member(s, uid):
        return None

    async def unban(s, obj, reason=None):
        s.unbans.append(getattr(obj, 'id', None))


class _Bot:
    def __init__(s, guild):
        s.guilds = [guild]

    def get_guild(s, gid):
        return s.guilds[0] if gid == s.guilds[0].id else None

    def get_cog(s, name):
        return None


def _cog_with(state):
    cog = AP.Appeals.__new__(AP.Appeals)
    guild = _Guild(GID)
    cog.bot = _Bot(guild)
    cog._load = lambda gid: state
    cog._save = lambda gid, st: None

    async def _noop(*a, **k):
        return None

    cog._notify_user = _noop
    cog._make_return_invite = _noop
    return cog, guild


print('== 1. Кнопка «Принять»: лимит «unban» действует ДО решения ==')
state = {'items': [], 'next_id': 1, 'settings': {}}
item, err = AP.create_appeal(state, UID, 'Нарушитель',
                             'Прошу снять бан, это была ошибка',
                             datetime.now(UTC))
check(err is None and item['status'] == 'pending', 'апелляция создана', err or '')
cog, guild = _cog_with(state)
view = AppealView(cog, GID, item['id'])

set_action_rule(GID, 'ban', [ROLE_ID])
mod_ok = _User(UID, [_Role(ROLE_ID)])
mod_no = _User(999000000000000999, [])

# ACL: без роли — отказ ещё до лимитов
in0 = _Inter(mod_no)
asyncio.new_event_loop().run_until_complete(view._resolve(in0, True))
check('не дал владелец' in in0.response.msg, 'без права «Бан» — отказ ACL',
      in0.response.msg[:80])
check(item['status'] == 'pending', 'апелляция не решена')

# лимит unban исчерпан → принятие запрещено, апелляция ждёт
SL.set_limits(GID, unban=1)
SL.record_hit(GID, UID, 'unban', 1)
it1 = _Inter(mod_ok)
asyncio.new_event_loop().run_until_complete(view._resolve(it1, True))
check('Лимит' in it1.response.msg, f'принятие упёрлось в лимит unban',
      it1.response.msg[:80])
check(item['status'] == 'pending', 'исчерпавший лимит НЕ решил апелляцию')

print('== 2. «Отклонить»: лимит unban расходки не несёт ==')
it2 = _Inter(mod_ok)
asyncio.new_event_loop().run_until_complete(view._resolve(it2, False))
check(it2.response.edited == 1 and 'Лимит' not in (it2.response.msg or ''),
      'отклонение прошло без вопроса о лимите', (it2.response.msg or '')[:60])
check(item['status'] == 'rejected', 'апелляция отклонена')

print('== 3. Принятие без лимита: решение + расходка «unban» в счётчик ==')
state2 = {'items': [], 'next_id': 1, 'settings': {}}
item2, _e = AP.create_appeal(state2, UID, 'Нарушитель',
                             'Второе прошение — проверка принятия',
                             datetime.now(UTC))
cog2, guild2 = _cog_with(state2)
view2 = AppealView(cog2, GID, item2['id'])
# лимит unban=1 ещё висит, но у ДРУГОГО модератора квота свободна
mod_ok2 = _User(777000000000000732, [_Role(ROLE_ID)])
it3 = _Inter(mod_ok2)
asyncio.new_event_loop().run_until_complete(view2._resolve(it3, True))
check(it3.response.edited == 1 and item2['status'] == 'accepted',
      'принятие выполнилось')
check(guild2.unbans == [UID], 'настоящий разбан вызван')
_ok, used, lim = SL.check_limit(GID, mod_ok2.id, 'unban', 1)
check(used == 1, f'расходка «unban» записана (used={used})')

print('== 4. Панель: гейт «mod», offline-решение, повтор — 409 ==')
src = open(os.path.join(ROOT, 'web', 'routes', 'appeals_panel.py'),
           encoding='utf-8').read()
i0 = src.index("def api_appeals_resolve")
_head = src[max(0, i0 - 200):i0]
check("@role_required('mod')" in _head,
      'resolve из панели открыт «mod+» (право решает ACL «Бан»)')
i1 = src.index('def apply_side_effects')
i2 = src.index('def resolve_panel')
check('clear_all_mutes' in src[i1:i2],
      'панель снимает муты тем же вызовом, что кнопка кога')

import web.app as appmod  # noqa: E402
from web.routes import appeals_panel as WAP  # noqa: E402
from cogs import appeals as APc  # noqa: E402

appmod.bot_instance = None             # офлайн-бот — панель всё равно решает
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'ПанМод'
    sess['role'] = 'mod'
    sess['selected_guild'] = str(GID)

st = WAP._state(GID)
new_item, _err = APc.create_appeal(st, 555000000000000555, 'Изолянт',
                                   'Панельное прошение — вернуть в строй',
                                   datetime.now(UTC))
WAP._save(GID, st)

r = client.get('/appeals')
check(r.status_code == 200, f'страница «Апелляции» отдаётся ({r.status_code})')
r = client.post(f'/api/guild/{GID}/appeals/resolve', json={})
check(r.status_code == 400, 'пустой запрос — валидация, а не 403 прав')

r = client.post(f'/api/guild/{GID}/appeals/resolve',
                json={'appeal_id': str(new_item['id']), 'accept': True})
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success'),
      f'POST решения от «mod» — успех ({str(d)[:80]})')
check(d.get('status_text') == 'принята', f'статус: {d.get("status_text")}')
check((d.get('effects') or {}).get('offline') is True,
      'офлайн-бот честно помечен effects.offline')

r = client.post(f'/api/guild/{GID}/appeals/resolve',
                json={'appeal_id': str(new_item['id']), 'accept': False})
check(r.status_code == 409, 'повторное решение — 409 (уже рассмотрена)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
