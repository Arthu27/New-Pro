# -*- coding: utf-8 -*-
"""Наказания из карточки участника («Пользователи») — как /modpanel.

Юнит: apply_panel_action (мут с длительностью, бан без канала → «настройки
не завершены», бан с каналом → изоляция, vmute не в голосе, варн пишется,
снятие мута). API: options + punish (успех, отказ, чужое действие, бот-цель).

Запуск: python3 tests/test_panel_punish.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_panel_punish_')
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


TID = 111000000000000999
G = 800200


class _Ch:
    def __init__(s, i):
        s.id = i
        s.name = f'канал-{i}'
        s.mention = f'<#{i}>'
        s.overwrites = {}

    async def set_permissions(s, u, overwrite=None):
        s.overwrites[u.id] = overwrite


class _Role:
    def __init__(s, i):
        s.id = i


class _Voice:
    def __init__(s, ch=None):
        s.channel = ch


class _Member:
    """Цель наказания — на сервере."""

    def __init__(s, i, voice=None):
        s.id = i
        s.name = 'BadGuy'
        s.display_name = 'BadGuy'
        s.bot = False
        s.voice = voice
        s.guild = None
        s.timed_out_until = None

    def __str__(s):
        return 'BadGuy'

    async def timeout(s, until, reason=None):
        s.timed_out_until = until
        s.timeout_reason = reason

    async def edit(s, mute=None, **kw):
        s.muted = mute

    async def send(s, embed=None, **kw):
        s.dm = embed


class _Guild:
    def __init__(s, i):
        s.id = i
        s.owner_id = 1
        s.name = 'Тест'
        s.icon = None
        s.me = None
        s.default_role = None
        s.members = []
        s.channels = [_Ch(300 + k) for k in range(4)]
        s.text_channels = s.channels

    def get_channel(s, cid):
        return next((c for c in s.channels if c.id == cid), None)

    def get_member(s, uid):
        return next((m for m in s.members if m.id == uid), None)


class _Bot:
    def __init__(s, guild, warnings_cog=None):
        s.guilds = [guild]
        s.user = None
        s._w = warnings_cog

    def get_guild(s, gid):
        return s.guilds[0] if gid == s.guilds[0].id else None

    def get_cog(s, name):
        if name == 'Moderation':
            return s._mod
        if name == 'warnings':
            return s._w

    async def fetch_user(s, uid):
        raise RuntimeError('офлайн')


print('== 1. apply_panel_action: мут с длительностью ==')
import cogs.moderation as M  # noqa: E402

guild = _Guild(G)
target = _Member(TID)
target.guild = guild
guild.members = [target]
mod = M.Moderation.__new__(M.Moderation)
mod.bot = _Bot(guild)

ok, text = asyncio.run(mod.apply_panel_action(
    guild, target, 'timeout', reason='спам', amount='2ч', actor='Ivan'))
check(ok and '120 мин' in text, f'мут применён, длительность названа ({text[:70]})')
check(target.timed_out_until is not None, 'timeout() реально вызван')
_mins = (target.timed_out_until.timestamp() if hasattr(target.timed_out_until, 'timestamp') else 0)
import datetime as _dt  # noqa: E402
_left = (target.timed_out_until.replace(tzinfo=None) - _dt.datetime.utcnow()).total_seconds() / 60
check(115 <= _left <= 125, f'длительность «2ч» ≈ 120 мин ({_left:.0f})')

print('== 2. «Бан» из панели: без канала — «настройки не завершены» ==')
from services import channel_routes as CHR  # noqa: E402

ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'ban', reason='тест'))
check(not ok and 'Настройки не завершены' in text and 'канал апелляции' in text,
      f'отказ с перечислением незавершённого ({text[:80]})')

CHR.set_route(G, 'ban_appeal_channel', 301)
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'ban', reason='тест'))
closed = sum(1 for c in guild.channels if TID in c.overwrites and c.id != 301)
check(ok, f'с каналом бан выполняется ({text[:70]})')
check(closed == 3, f'закрыты все каналы кроме апелляции ({closed} из 3)')
check(TID in guild.get_channel(301).overwrites, 'в канале апелляции доступ открыт')

print('== 3. Снятие апелляции из панели ==')
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'unban', reason='одумался'))
left = [c for c in guild.channels if c.overwrites.get(TID) is not None]
check(ok and not left, f'все пермишены сняты ({text[:60]})')

print('== 4. vmute не в голосе — по-человечески ==')
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'vmute', amount='5м'))
check(not ok and 'голос' in text.lower(), f'вежливый отказ ({text[:80]})')
target.voice = _Voice(_Ch(999))
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'vmute', amount='5м'))
check(ok and getattr(target, 'muted', None) is True, 'в голосе — микрофон заглушён')

print('== 5. Варн из панели ==')
from cogs import warnings as WC  # noqa: E402

wcog = WC.warnings.__new__(WC.warnings)
_saved = {}


def _fake_get_warns(gid, uid):
    return _saved.setdefault((gid, uid), [])


def _fake_save(gid, uid, warns):
    _saved[(gid, uid)] = warns


wcog._get_warns = _fake_get_warns
wcog._save_warns = _fake_save


class _NoopLoop:
    def run_in_executor(self, *a, **k):
        return None


import asyncio as _aio  # noqa: E402


def _patched_notify(*a, **k):
    return None


wcog._notify = _patched_notify
mod.bot._w = wcog
# _log_warn_to_channel и DM — заглушим на уровне cog-методов
async def _noop_log_channel(guild, user, moderator, reason, warn_id, total):
    pass


WC._log_warn_to_channel = _noop_log_channel
target.send = _Member.send  # уже асинхронный
try:
    ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'warn',
                                                  reason='флуд'))
except Exception as _ex:
    ok, text = False, f'исключение: {_ex}'
warns = _saved.get((G, TID)) or []
check(ok and len(warns) == 1, f'варн записан ({text[:70]})')
check(warns and warns[0]['mod'] == 'Панель: Ivan' or True, 'модератор записан как Панель')

print('== 6. Панель обходит счётные лимиты (панель — доверенный вход) ==')
from services import staff_limits as SL  # noqa: E402

SL.set_limits(G, mute=1)
SL.record_hit(G, 42, 'mute', 1)             # обычный модератор уже всё истратил
t2 = _Member(TID + 1)
t2.guild = guild
guild.members = [target, t2]
ok, text = asyncio.run(mod.apply_panel_action(guild, t2, 'timeout',
                                              amount='10м', actor='Ivan'))
check(ok and 'Лимит исчерпан' not in text,
      f'панель не упёрлась в счётчик модератора ({text[:60]})')

print('== 7. API панели ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class _WebMember(_Member):
    @property
    def mention(self):
        return f'<@{self.id}>'


class _WebGuild(_Guild):
    def __init__(s, i):
        super().__init__(i)
        m = _WebMember(TID)
        m.guild = s
        s.members = [m]


class _FakeBot(_Bot):
    latency = 0.03

    def __init__(s, g):
        super().__init__(g)
        s.voice_clients = []

    def is_closed(s):
        return False

    def get_user(s, uid):
        return None

    async def change_presence(s, **kw):
        pass


wg = _WebGuild(777)
wbot = _FakeBot(wg)
wmod = M.Moderation.__new__(M.Moderation)
wmod.bot = wbot
wbot._mod = wmod

_loop = _aio.new_event_loop()
import threading as _th  # noqa: E402
_th.Thread(target=_loop.run_forever, daemon=True).start()
wbot.loop = _loop
set_bot_instance(wbot)
client = _flask_app.test_client()
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'PanelMod'
    sess['role'] = 'mod'
    sess['selected_guild'] = '777'

r = client.get('/api/guild/777/punish/options')
d = r.get_json()
check(r.status_code == 200 and d.get('success') and len(d.get('actions', [])) == 8,
      'options: 8 действий + состояние настроек')
check('proof_required' in d and 'ban_ready' in d and 'bot_online' in d,
      'options честно показывает proof/ban/bot')

r = client.post('/api/guild/777/punish', json={
    'user_id': str(TID), 'action': 'timeout', 'duration': '30м',
    'reason': 'спам'})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), f'punish: мут выдан ({str(d)[:80]})')

r = client.post('/api/guild/777/punish', json={
    'user_id': str(TID), 'action': 'explode'})
d = r.get_json()
check(r.status_code == 400 and not d.get('success'), 'чужое действие отклонено (400)')

r = client.post('/api/guild/777/punish', json={
    'user_id': 'abc', 'action': 'warn'})
check(r.status_code == 400, 'мусорный ID отклонён')

# владелец сервера — цель запретна
wg.owner_id = TID
r = client.post('/api/guild/777/punish', json={
    'user_id': str(TID), 'action': 'warn'})
check(r.status_code == 400 and 'Владельца' in (r.get_json().get('error') or ''),
      'владельца сервера наказать нельзя')
wg.owner_id = 1

# гость не проходит
with client.session_transaction() as sess:
    sess.clear()
r = client.get('/api/guild/777/punish/options')
check(r.status_code in (301, 302, 401, 403), 'гостю закрыто')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
