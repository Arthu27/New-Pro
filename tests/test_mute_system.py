# -*- coding: utf-8 -*-
"""Муты и варны по заказу владельца 2026-09-05.

1) «Таймаут требует прав — а должен просто дать ОБЕ роли сразу»:
   мут (чат+войс) = роль мута + роль войс-мута + сервер-мут микрофона;
   нативный таймаут НЕ обязателен — без права «Модерация участников»
   действие ВСЁ РАВНО выполняется.
2) Войс-мут = выдать роль войс-мута на срок (без выкида из войса).
3) Снятие войс-мута возвращает микрофон (роль И сервер-мут).
4) «Снять варн» в панели (/modpanel + веб) и в боте (/unwarn без
   Discord-права — права выдаёт владелец через ACL).
Запуск: python3 tests/test_mute_system.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='mute_sys_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


import discord  # noqa: E402
from cogs import moderation as M  # noqa: E402
from cogs import warnings as W  # noqa: E402
from services import punish_roles as PR  # noqa: E402
from services import channel_routes as CR  # noqa: E402

GID = 1484574976580391004


def perms(**kw):
    d = dict(administrator=False, ban_members=True, kick_members=False,
             moderate_members=False, manage_messages=False,
             manage_guild=False, manage_channels=False)
    d.update(kw)
    return types.SimpleNamespace(**d)


class _Overwrite:
    def __init__(self):
        self.deny = 0
        self.speak = None
        self.connect = None
        self.view_channel = None


class _Channel:
    def __init__(self, cid, name='войс'):
        self.id = cid
        self.name = name
        self.overwrites = {}   # target -> _Overwrite
        self.calls = []

    def overwrites_for(self, target):
        return self.overwrites.get(id(target), None) or _Overwrite()

    async def set_permissions(self, target, **kw):
        self.calls.append(kw)
        ow = self.overwrites.setdefault(id(target), _Overwrite())
        for k, v in kw.items():
            if k != 'reason':
                setattr(ow, k, v)


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'
        self.managed = False
        self.permissions = types.SimpleNamespace(
            value=0, speak=True, connect=False)
        self.edits = []

    def is_default(self):
        return False

    async def edit(self, **kw):
        self.edits.append(kw)
        perms = kw.get('permissions')
        if perms is not None:
            self.permissions = perms


class _Voice:
    def __init__(self, channel=None, mute=False):
        self.channel = channel
        self.mute = mute


class _Member:
    def __init__(self, uid, name, roles=(), guild=None):
        self.guild = guild
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.roles = list(roles)
        self.guild_permissions = perms()
        self.voice = _Voice()
        self.timed_out_until = None
        self.edits = []
        self.added = []
        self.removed = []
        self.dms = []
        self.moved_to = 'unset'
        self.display_avatar = types.SimpleNamespace(url='http://a/1')

    async def add_roles(self, role, reason=None):
        self.added.append((role.id, reason))
        if role not in self.roles:
            self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed.append((role.id, reason))

    async def move_to(self, channel, reason=None):
        self.moved_to = channel
        self.voice.channel = channel

    async def edit(self, **kw):
        self.edits.append(kw)
        if 'mute' in kw:
            self.voice.mute = kw['mute']

    async def timeout(self, until, reason=None):
        if not self.guild_permissions.moderate_members_perm:
            raise discord.Forbidden(
                types.SimpleNamespace(status=403, reason='Missing Access'),
                '403 Forbidden (error code: 50001): Missing Access')
        self.timed_out_until = until

    async def send(self, embed=None, **kw):
        self.dms.append(embed)


# разрешение «делать нативный таймаут» — отдельный флаг (у бота его может не быть)
_Member.moderate_members_perm = False


class _Guild:
    def __init__(self, roles, channels=()):
        self.id = GID
        self.name = 'Hakumo'
        self.owner_id = 0
        self.roles = roles
        self.voice_channels = list(channels)
        self.stage_channels = []
        self.members = []
        self.system_channel = None

    def get_channel(self, cid):
        for c in self.voice_channels:
            if c.id == cid:
                return c
        return None

    def get_role(self, rid):
        for r in self.roles:
            if r.id == rid:
                return r
        return None

    def get_member(self, uid):
        for m in self.members:
            if m.id == uid:
                return m
        return None

    async def fetch_member(self, uid):
        return self.get_member(uid)


class _Bot:
    def __init__(self, guild, cogs):
        self._g = guild
        self._cogs = cogs
        self.guilds = [guild]

    def get_guild(self, gid):
        return self._g if int(gid) == GID else None

    def get_cog(self, name):
        return self._cogs.get(name)


def _setup_roles(guild, member):
    PR.set_roles(GID, who='test', mute=5001, vmute=5002, ban=5003)
    r_mute = _Role(5001, 'Мут')
    r_vmute = _Role(5002, 'Войс-мут')
    guild.roles.extend([r_mute, r_vmute])
    return r_mute, r_vmute


class _Resp:
    def __init__(self):
        self.calls = []

    def is_done(self):
        return False

    async def send_message(self, *a, **kw):
        self.calls.append(('send', a, kw))

    async def followup_send(self, *a, **kw):
        self.calls.append(('follow', a, kw))


class _Inter:
    def __init__(self, guild, user, channel=None):
        self.guild = guild
        self.guild_id = GID
        self.user = user
        self.channel = channel
        self.response = _Resp()
        self.followup = types.SimpleNamespace(send=lambda *a, **kw: None)

    async def _respond_stub(self, *a, **kw):
        pass


async def main():
    mod_role_obj = _Role(7001, 'Мод')
    guild = _Guild([_Role(0, '@everyone'), mod_role_obj])
    mod = _Member(2000000000000000200, 'Модератор', roles=[mod_role_obj],
                  guild=guild)
    mod.guild_permissions = perms(manage_messages=True)
    target = _Member(3000000000000000300, 'Виновный', guild=guild)
    guild.members = [mod, target]

    r_mute, r_vmute = _setup_roles(guild, target)

    # owner (бота) — чтобы ACL/лимиты не мешали
    with open('data/config_env_test', 'w') as f:
        f.write('')
    warnings_cog = types.SimpleNamespace()  # подменяется ниже
    import cogs.embed_utils  # noqa: F401

    # настоящий Moderation-ког
    cog = M.Moderation(bot=_Bot(guild, {'Moderation': None}))

    # ── ACL: разрешим модератору всё через action_acl ──
    from services import permission_acl as ACL
    ACL.set_action_rule(GID, 'timeout', [7001])
    ACL.set_action_rule(GID, 'vmute', [7001])
    ACL.set_action_rule(GID, 'mute', [7001])
    ACL.set_action_rule(GID, 'warn', [7001])
    ACL.set_action_rule(GID, 'unwarn', [7001])

    print('== 1. Мут (чат+войс) БЕЗ права moderate_members у бота ==')
    # фейк-член не умеет нативный таймаут без права — сымитируем Forbidden
    class _Tgt(_Member):
        pass
    tgt = target
    ok, text = await cog.apply_panel_action(
        guild, tgt, 'timeout', reason='1.9', amount='60м', actor='Панель')
    check(ok, 'мут выполнен без нативного таймаута', f'→ {text}')
    got_mute = any(rid == 5001 for rid, _ in tgt.added)
    got_vmute = any(rid == 5002 for rid, _ in tgt.added)
    check(got_mute and got_vmute, 'выданы ОБЕ роли (мут + войс-мут)',
          f'→ {tgt.added}')

    print('== 1b. Предпроверка НЕ требует «Модерацию участников» для мута ==')
    # Владелец 2026-09-05: «он просто должен выдать роли — зачем ему права».
    # У бота есть «Управление ролями», НЕТ «Модерации участников» —
    # preflight_reason('timeout') должен молчать (нативный таймаут — бонус).
    class _Me:
        id = 998
        top_role = None
        guild_permissions = types.SimpleNamespace(
            manage_roles=True, moderate_members=False,
            kick_members=False, administrator=False)

    class _GuildMe:
        me = _Me()

    class _G2(_Guild, _GuildMe):
        pass

    g2 = _G2(guild.roles)
    ok_pre = await cog.preflight_reason(g2, tgt, 'timeout')
    check(ok_pre is None,
          'мут без права «Модерация участников» — предпроверка молчит',
          f'→ {ok_pre}')
    ok_pre2 = await cog.preflight_reason(g2, tgt, 'mute_chat')
    check(ok_pre2 is None, 'мут чата — то же (нужно только «Управление ролями»)',
          f'→ {ok_pre2}')

    print('== 2. Войс-мут: только роль на срок ==')
    tgt2 = _Member(3010000000000000301, 'Войс-нарушитель', guild=guild)
    guild.members.append(tgt2)
    ok, text = await cog.apply_panel_action(
        guild, tgt2, 'vmute', reason='1.9', amount='30м', actor='Панель')
    check(ok, 'войс-мут применён', f'→ {text}')
    check(any(rid == 5002 for rid, _ in tgt2.added), 'роль войс-мута выдана')
    vch = _Channel(8001)
    guild.voice_channels.append(vch)
    tgt3 = _Member(3020000000000000302, 'Третий', guild=guild)
    tgt3.voice = _Voice()
    tgt3.voice.channel = vch
    guild.members.append(tgt3)
    ok, text3 = await cog.apply_panel_action(
        guild, tgt3, 'vmute', reason='1.9', amount='30м', actor='Панель')
    check(ok, 'войс-мут с участником в войсе', f'→ {text3}')
    check(any(rid == 5002 for rid, _ in tgt3.added), 'роль выдана третьему')
    check(tgt3.moved_to == 'unset', 'из войса НЕ выкидываем', f'→ {tgt3.moved_to}')
    check(not any(e.get('mute') is True for e in tgt3.edits),
          'сервер-мут НЕ трогаем', f'→ {tgt3.edits}')
    # срок в temps — loop снимет роль сам
    due_now = PR.due(0)
    check(any(int(gid) == GID and int(rid) == 5002 for gid, uid, rid in due_now)
          or any(int(uid) in (tgt2.id, tgt3.id)
                 for gid, uid, rid in PR.due(__import__('time').time() + 3600)),
          'срок войс-мута записан в temps')

    print('== 3. Снятие войс-мута снимает роль ==')
    ok, text = await cog.apply_panel_action(
        guild, tgt2, 'vunmute', reason='1.9', actor='Панель')
    check(ok, 'vunmute выполнен')
    check(any(rid == 5002 for rid, _ in tgt2.removed),
          'роль войс-мута снята', f'→ {tgt2.removed}')

    print('== 5. ПКМ-меню зарегистрировано ==')
    check(hasattr(M, '_CtxMuteModal'), 'модалка ПКМ-мута существует')
    names = [getattr(c, 'name', '') for c in getattr(M, '_CTX_COMMANDS', ())]
    check('🔇 Мут (чат + войс)' in names and '🎙️ Войс-мут' in names
          and '⚠️ Варн' in names and '🔊 Снять муты' in names,
          'ПКМ: мут / войс-мут / варн / снять', f'→ {names}')
    check('_ctx_setup' in open(os.path.join(ROOT, 'cogs/moderation.py'),
                               encoding='utf-8').read(),
          'ПКМ-команды регистрируются вместе с модерацией')

    print('== 6. Снять варн: панель ==')
    wc = W.warnings.__new__(W.warnings)
    wc.db = types.SimpleNamespace(
        set=lambda *a, **k: None)
    wc._warns_cache = {}
    bot2 = _Bot(guild, {'Moderation': cog, 'warnings': wc})
    cog.bot = bot2
    # подсунуть warns: один варн
    wc._get_warns = lambda gid, uid: ([{
        'id': 1, 'reason': 'спам', 'mod': 'X', 'mod_id': '1',
        'timestamp': '2026-09-05T00:00:00+00:00'}]
        if uid == 3000000000000000300 else [])
    wc._save_warns = lambda gid, uid, warns: None
    removed_holder = {}

    async def _fake_sync(g, u, total):
        removed_holder.setdefault('total', total)
    wc._sync_warn_level_roles = _fake_sync
    from cogs.logs import ensure_log_channel as _orig_ensure
    async def _fake_ensure(guild, name):
        return None
    import cogs.logs as _logs_mod
    _logs_mod.ensure_log_channel = _fake_ensure
    ok, text = await cog.apply_panel_action(
        guild, target, 'unwarn', reason='1.9', actor='Панель')
    check(ok and 'Снято' in text, 'панель сняла последний варн', f'→ {text}')
    clean = _Member(9990000000000000999, 'Чистый', guild=guild)
    guild.members.append(clean)
    ok, text = await cog.apply_panel_action(
        guild, clean, 'unwarn', reason='1.9', actor='Панель')
    check(not ok and 'нет предупреждений' in text,
          'без варнов — честный отказ', f'→ {text}')

    print('== 7. /unwarn без Discord-права moderate_members ==')
    src = open(os.path.join(ROOT, 'cogs/warnings.py'),
               encoding='utf-8').read()
    check('has_permissions(moderate_members=True)\n    async def unwarn'
          not in src.replace('\r', ''),
          '/unwarn больше не требует Discord-право moderate_members')
    check("check_action" in src and "'unwarn'" in src,
          '/unwarn проверяет ACL владельца «Снять варн»')

    print('== 8. ACL «unwarn» виден в панели прав ==')
    from services.permission_acl import ACTIONS
    check('unwarn' in ACTIONS and 'Снять варн' in ACTIONS['unwarn'],
          'действие «Снять варн» появилось в «Права команд»')
    check('unwarn' in M.PANEL_ACTIONS and 'unwarn' in M.MODPANEL_ACL_KEYS,
          'панель наказаний знает действие unwarn')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
