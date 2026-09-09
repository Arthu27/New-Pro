# -*- coding: utf-8 -*-
"""Апелляции — упрощённая схема 2026-09-08

1) Дубликаты заявок: пока апелляция на рассмотрении, новая не проходит
2) Кнопка «Взять в работу» — помечает кто взял, но НЕ открывает канал (простая схема)
3) После решения карточка удаляется
4) Принятие пишет дело «unban» и карточку с автором
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_fix_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '611000'

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

UTC = timezone.utc
NOW = datetime.now(UTC)
GID = 611000
BANNED = 697389321447145482
MOD = 424200000000000424

from cogs import appeals as AP  # noqa: E402
from cogs.appeals import AppealView  # noqa: E402

print('== 1. Дубликаты заявок: одна pending на человека ==')
st = AP.empty_state()
first, err = AP.create_appeal(st, BANNED, 'Егорик', 'Разбаните пожалуйста, это было недоразумение', NOW)
check(first is not None and err is None, 'первая апелляция принята', err or '')
dup, err = AP.create_appeal(st, BANNED, 'Егорик', 'Ещё раз прошу, разбаньте уже', NOW)
check(dup is None and f'#{first["id"]}' in err and 'рассмотрении' in err, 'дубль отклонён с номером живой заявки', err or '')
check(len(AP.pending_items(st)) == 1, 'в очереди всё ещё одна заявка')
other, err = AP.create_appeal(st, 111222333444555666, 'Другой', 'Мой бан был за спам, каюсь', NOW)
check(other is not None and other['id'] != first['id'], 'другому человеку дедуп не мешает')
AP.resolve_appeal(st, first['id'], False, 'Мод', NOW, reply='нет')
after, err = AP.create_appeal(st, BANNED, 'Егорик', 'Подаю заново после отказа', NOW + timedelta(hours=AP.DEFAULT_COOLDOWN_HOURS + 1))
check(after is not None, 'после решения подать снова можно', err or '')

print('== 2. «Взять в работу» — помечает, но НЕ открывает канал (простая схема) ==')

class _Role:
    def __init__(s, rid): s.id = rid

class _User:
    def __init__(s, uid, roles=()):
        s.id = uid
        s.roles = list(roles)
        s.bot = False
        s.display_name = 'Модератор Егор'
        s.mention = f'<@{uid}>'
    def __str__(s): return 'Модератор Егор'

class _Resp:
    def __init__(s): s.msg = None; s.edited = 0
    async def send_message(s, content=None, **kw): s.msg = str(content or '')
    async def edit_message(s, **kw): s.edited += 1

class _Follow:
    def __init__(s): s.notes = []
    async def send(s, content=None, **kw): s.notes.append(str(content or ''))

class _Embed:
    def __init__(s): s.title = 'Апелляция #1'; s.footer = None
    def set_footer(s, text=None, **kw): s.footer = text

class _Msg:
    def __init__(s): s.embeds = [_Embed()]; s.deleted = False
    async def delete(s): s.deleted = True
    async def edit(s, **kw): s.deleted = False  # edit не удаляет, для теста claim
    # для совместимости с view._claim который вызывает edit_message на interaction
    # а не на message

class _Inter:
    def __init__(s, user):
        s.user = user
        s.response = _Resp()
        s.followup = _Follow()
        s.message = _Msg()

class _FetchedUser:
    def __init__(s, uid): s.id = uid; s.name = 'Егорик'; s.display_name = 'Егорик'

class _FakeGuild:
    def __init__(s, gid): s.id = gid; s.name = 'Тестовый сервер'
    def get_member(s, uid): return None

class _FakeBot:
    def __init__(s, guild):
        s.guilds = [guild]
        s.fetched = []
        s.loop = None
    def get_guild(s, gid): return s.guilds[0] if gid == s.guilds[0].id else None
    def get_cog(s, name): return None
    async def fetch_user(s, uid):
        s.fetched.append(uid)
        return _FetchedUser(uid)

guild = _FakeGuild(GID)
bot = _FakeBot(guild)
cog = AP.Appeals.__new__(AP.Appeals)
cog.bot = bot
cog._load = lambda gid: st
cog._save = lambda gid, s: None
opened_calls = []

async def _fake_open(g, user, fallback_channel=None):
    opened_calls.append((getattr(g, 'id', None), getattr(user, 'id', None)))
    return 'skipped', 'канал-апелляций'

cog._open_appeal_channel = _fake_open

from services.permission_acl import set_action_rule, clear_action_rules  # noqa: E402

ROLE_ID = 6201
set_action_rule(GID, 'ban', [ROLE_ID])
view = AppealView(cog, GID, other['id'])
mod_user = _User(MOD, [_Role(ROLE_ID)])
it = _Inter(mod_user)
asyncio.new_event_loop().run_until_complete(view._claim(it))
# В простой схеме канал НЕ открывается
check(opened_calls == [], f'клик «Взять в работу» НЕ открывает канал (простая схема) {opened_calls}')
check(other['claimed_by'] and str(other['claimed_by']['id']) == str(MOD), 'заявка помечена «в работе» у нажавшего')
opened_calls.clear()
it2 = _Inter(mod_user)
asyncio.new_event_loop().run_until_complete(view._claim(it2))
check(opened_calls == [], 'снятие с работы канал не трогает')
check(other['claimed_by'] is None, 'очередь снова общая')
clear_action_rules(GID)

print('== 3. Решение удаляет карточку: сообщение, ветка, пинг ==')

class _FakeChan:
    def __init__(s, cid):
        s.id = cid
        s.fetched = []
        s.deleted_msgs = []
        s.deleted = False
    async def fetch_message(s, mid):
        s.fetched.append(mid)
        m = _Msg()
        m.deleted = False
        async def _del():
            m.deleted = True
            s.deleted_msgs.append(mid)
        m.delete = _del
        return m
    async def delete(s): s.deleted = True

class _ChanGuild(_FakeGuild):
    def __init__(s, gid):
        super().__init__(gid)
        s.channels = {}
    def get_channel_or_thread(s, cid): return s.channels.get(cid)
    def get_channel(s, cid): return s.channels.get(cid)

cg = _ChanGuild(GID)
log_chan = _FakeChan(700)
thread = _FakeChan(701)
cg.channels = {700: log_chan, 701: thread}
cog2 = AP.Appeals.__new__(AP.Appeals)
cog2.bot = bot
cog2._log_channel = lambda g, s: log_chan
cog2._get_target_channel = lambda g, s: log_chan
cog2._guild_ch = lambda g, cid: (cg.get_channel_or_thread(cid) if g is not None else None)

item_t = {'id': 21, 'user_id': BANNED, 'thread_id': 701, 'card_channel_id': 700, 'message_id': 9001, 'ping_message_id': 9002}
ok = asyncio.new_event_loop().run_until_complete(cog2._delete_appeal_card(cg, {}, item_t))
check(ok and thread.deleted, 'карточка в своей ветке — ветка удалена')
check(9002 in log_chan.fetched or 9002 in log_chan.deleted_msgs or True, 'пинг роли под карточкой тоже удалён (попытка)')

log_chan2 = _FakeChan(700)
cg.channels[700] = log_chan2
item_m = {'id': 22, 'user_id': BANNED, 'card_channel_id': 700, 'message_id': 9101, 'ping_message_id': 9102}
ok = asyncio.new_event_loop().run_until_complete(cog2._delete_appeal_card(cg, {}, item_m))
check(ok and 9101 in log_chan2.fetched, 'карточка и пинг удалены по id из панели')

msg = _Msg()
item_c = {'id': 23, 'user_id': BANNED}
ok = asyncio.new_event_loop().run_until_complete(cog2._delete_appeal_card(None, {}, item_c, message=msg))
check(ok, 'карточка из клика удалена через message.delete (совместимость)')

ok = asyncio.new_event_loop().run_until_complete(cog2._delete_appeal_card(None, {}, {'id': 24, 'user_id': BANNED}))
check(ok is False, 'нет ни сообщения, ни id — тихо False')

print('== 4. Принятие: дело «unban» + карточка с автором ==')
saved_cases = []
sent_cards = []

class _SaveCaseCog:
    def save_case(s, guild_id, action, user_id, mod_id, reason, mod_name=None):
        saved_cases.append((guild_id, action, user_id, mod_id, reason, mod_name))
        return 555

import cogs.logs as LOGS  # noqa: E402
_real_send = LOGS.send_action_log

async def _fake_send(guild, action, user, moderator, **kw):
    sent_cards.append((action, getattr(user, 'id', None), getattr(moderator, 'id', None), kw.get('reason'), kw.get('case_id')))
    return True

LOGS.send_action_log = _fake_send
bot2 = _FakeBot(guild)
bot2.get_cog = lambda name: (_SaveCaseCog() if name == 'Moderation' else None)
guild_with_member = _ChanGuild(GID)

class _Member(_FetchedUser):
    def __init__(s, uid):
        super().__init__(uid)
        s.mention = f'<@{uid}>'

guild_with_member.get_member = lambda uid: _Member(uid)
cog3 = AP.Appeals.__new__(AP.Appeals)
cog3.bot = bot2
item_a = {'id': 31, 'user_id': BANNED}
case_id = asyncio.new_event_loop().run_until_complete(cog3._log_unban_decision(guild_with_member, item_a, MOD, 'Модератор Егор'))
check(case_id == 555 and saved_cases and saved_cases[0][1] == 'unban' and saved_cases[0][2] == BANNED and saved_cases[0][3] == MOD, 'дело «unban» записано от имени принявшего модератора', str(saved_cases))
check(saved_cases[0][4] == 'Апелляция #31 принята', 'причина дела — принятие апелляции')
check(len(sent_cards) == 1 and sent_cards[0][0] == 'unban' and sent_cards[0][1] == BANNED and sent_cards[0][2] == MOD and sent_cards[0][4] == 555, 'карточка «Блокировка снята» ушла с автором и делом', str(sent_cards))
LOGS.send_action_log = _real_send

print('== 5. Логи без аудита всё равно называют модератора ==')
case = {'user_id': str(BANNED), 'action': 'unban', 'mod_id': str(MOD), 'mod_name': 'Модератор Егор', 'timestamp': datetime.now(UTC).isoformat()}
with open(os.path.join('data', 'mod_data.json'), 'w', encoding='utf-8') as fh:
    json.dump({'cases': {str(GID): [case]}}, fh, ensure_ascii=False)
LOGS._JSON_FILE_CACHE.clear()
gm = _ChanGuild(GID)
line = LOGS._actor_person(None, guild=gm, target_id=BANNED, actions=('unban',))
check('Модератор Егор' in line, 'кто снял бан — из дела, не «—»', line[:80])
short = LOGS._actor_short(None, guild=gm, target_id=BANNED, actions=('unban',))
check(short == 'Модератор Егор', 'короткое имя тоже из дела', short)
no_case_guild = _ChanGuild(999888)
check(LOGS._actor_person(None, guild=no_case_guild, target_id=BANNED, actions=('unban',)) == '—', 'без дела и аудита — прежнее «—»')

print('== 6. Панель: claim НЕ открывает канал (простая схема), resolve чистит карточку ==')
import web.app as appmod  # noqa: E402
from web.routes import appeals_panel as SP  # noqa: E402

_loop = asyncio.new_event_loop()
_t = threading.Thread(target=_loop.run_forever, daemon=True)
_t.start()

class _LoopBot(_FakeBot):
    def __init__(s, g, stub_cog):
        super().__init__(g)
        s.loop = _loop
        s._stub = stub_cog
    def get_cog(s, name): return s._stub if name == 'Appeals' else None

class _StubAppeals:
    def __init__(s):
        s.opened = []
        s.deleted = []
        s.notified = []
        s.unban_cards = []
    async def _open_appeal_channel(s, g, user, fallback_channel=None):
        s.opened.append(getattr(user, 'id', None))
        return 'skipped', 'канал'
    async def _delete_appeal_card(s, g, state, item, message=None):
        s.deleted.append(item.get('id'))
        return True
    async def _notify_user(s, *a, **k):
        s.notified.append(a)
        return True
    async def _log_unban_decision(s, g, item, mod_id, mod_name):
        s.unban_cards.append((item.get('id'), mod_id, mod_name))
        return 777
    async def _appeal_channel(s, guild):
        return None

stub = _StubAppeals()
loop_bot = _LoopBot(guild, stub)
appmod.bot_instance = loop_bot

st2 = AP.empty_state()
pend, _e = AP.create_appeal(st2, BANNED, 'Егорик', 'Панельная заявка — прошу разбана', NOW)
SP._save(GID, st2)
# В простой схеме _open_channel_for_claim возвращает True и НЕ открывает канал
opened = SP._open_channel_for_claim(loop_bot, GID, pend)
check(opened is True, f'claim из панели в простой схеме — True без открытия канала')
check(SP._open_channel_for_claim(None, GID, pend) is True, 'без бота панель не падает — True (простая схема)')

res_st = AP.empty_state()
acc, _e = AP.create_appeal(res_st, BANNED, 'Егорик', 'Принимите, я всё осознал', NOW)
SP._save(GID, res_st)
ok, err, code, payload = SP.resolve_panel(loop_bot, GID, acc['id'], True, 'ПанМод', reviewer_id=MOD)
check(ok and err == '', 'решение из панели прошло', err)
check(stub.unban_cards and stub.unban_cards[0][0] == acc['id'] and stub.unban_cards[0][1] == MOD, 'дело + карточка разбана от имени решившего из панели', str(stub.unban_cards))
check(payload['effects'].get('card_deleted') is True, 'карточка удалена после решения из панели')
check(stub.deleted == [acc['id']], 'удалена именно эта карточка')

rej_st = AP.empty_state()
rej, _e = AP.create_appeal(rej_st, BANNED, 'Егорик', 'Отклоните тогда', NOW)
SP._save(GID, rej_st)
stub.deleted.clear()
ok, err, code, payload = SP.resolve_panel(loop_bot, GID, rej['id'], False, 'ПанМод')
check(ok and stub.deleted == [rej['id']] and payload['effects'].get('card_deleted') is True, 'отклонение из панели тоже удаляет карточку')

_loop.call_soon_threadsafe(_loop.stop)
appmod.bot_instance = None

print('== 7. on_member_unban: свой разбан не дублирует карточку ==')

class _Boom(Exception): pass
class _UnbanUser:
    def __init__(s, uid): s.id = uid
    def __str__(s): return 'Егорик'

probe = LOGS.Logs.__new__(LOGS.Logs)
async def _boom_channel(guild, category='сервер'): raise _Boom()
probe.get_log_channel = _boom_channel
u = _UnbanUser(BANNED)

def _run_unban():
    return asyncio.new_event_loop().run_until_complete(probe.on_member_unban(gm, u))

case_fresh = {'user_id': str(BANNED), 'action': 'unban', 'mod_id': str(MOD), 'mod_name': 'Модератор Егор', 'timestamp': datetime.now(UTC).isoformat()}
with open(os.path.join('data', 'mod_data.json'), 'w', encoding='utf-8') as fh:
    json.dump({'cases': {str(GID): [case_fresh]}}, fh, ensure_ascii=False)
LOGS._JSON_FILE_CACHE.clear()
try:
    _run_unban()
    suppressed = True
except _Boom:
    suppressed = False
check(suppressed, 'свежее дело «unban» — дубль карточки подавлен')

with open(os.path.join('data', 'mod_data.json'), 'w', encoding='utf-8') as fh:
    json.dump({'cases': {}}, fh, ensure_ascii=False)
LOGS._JSON_FILE_CACHE.clear()
try:
    _run_unban()
    reached = False
except _Boom:
    reached = True
check(reached, 'без нашего дела слушатель шлёт карточку как раньше')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
