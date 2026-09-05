# -*- coding: utf-8 -*-
"""Размут в /modpanel: один пункт → выбор чат / войс. Без авто-срока.

Запуск: python3 tests/test_modpanel_unmute.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_unmute_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
os.environ['OWNER_ID'] = '11'

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from cogs import moderation as M  # noqa: E402
from services.permission_acl import set_action_rule, save_action_acl  # noqa: E402
from services import punish_roles as PR  # noqa: E402

print('== 1. В меню один пункт «Снять мут», не два размута ==')
names = [a[0] for a in M.MODPANEL_ACTIONS]
check('unmute' in names, 'пункт unmute в меню')
check('untimeout' not in names and 'vunmute' not in names,
      'отдельные размут чат/войс из главного меню убраны')
check('class UnmuteKindSelect' in open(os.path.join(ROOT, 'cogs/moderation.py'),
                                       encoding='utf-8').read(),
      'второй селект чат/войс на месте')

print('== 2. Виды размута по разрешениям ==')


class Role:
    def __init__(self, rid):
        self.id = rid


class Member:
    def __init__(self, uid, roles=()):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.bot = False


GID = 424280
save_action_acl(GID, {})
set_action_rule(GID, 'mute', [601])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['unmute_chat'],
      f'только чат-мут → только «Чат»: {[k[0] for k in kinds]}')
set_action_rule(GID, 'vmute', [601])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['unmute_chat', 'vunmute', 'untimeout'],
      f'чат+войс → три варианта: {[k[0] for k in kinds]}')
set_action_rule(GID, 'mute', [])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['vunmute'],
      f'только войс → только «Войс»: {[k[0] for k in kinds]}')

print('== 3. unmute_chat не трогает микрофон ==')


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Voice:
    mute = True
    channel = object()


class _Tgt:
    def __init__(self):
        self.id = 3000000000000000300
        self.name = 'T'
        self.display_name = 'T'
        self.mention = '<@3000000000000000300>'
        self.bot = False
        self.roles = []
        self.voice = _Voice()
        self.timed_out_until = object()
        self.edits = []
        self.removed = []
        self.added = []
        self.dms = []
        self.display_avatar = types.SimpleNamespace(url='http://a')

    async def add_roles(self, role, reason=None):
        self.added.append(role.id)

    async def remove_roles(self, role, reason=None):
        self.removed.append(role.id)

    async def edit(self, **kw):
        self.edits.append(kw)

    async def timeout(self, until, reason=None):
        self.timed_out_until = until

    async def send(self, embed=None, **kw):
        self.dms.append(embed)


class _Guild:
    id = GID
    name = 'G'
    owner_id = 1
    icon = None
    me = None
    members = []
    roles = []
    channels = []
    text_channels = []
    voice_channels = []

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid):
        return None


class _Resp:
    def is_done(self):
        return True

    async def defer(self, ephemeral=False):
        pass

    async def send_message(self, **kw):
        self.kw = kw


class _Inter:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = _Resp()
        self.followup = types.SimpleNamespace(send=lambda **k: None)
        self.channel = None


PR.set_roles(GID, who='t', mute=5001, vmute=5002, ban=5003)
g = _Guild()
r_mute, r_vmute = _Role(5001, 'Мут'), _Role(5002, 'Войс')
g.roles = [r_mute, r_vmute]
tgt = _Tgt()
tgt.roles = [r_mute, r_vmute]
mod = Member(200, [601])
mod.display_name = 'Мод'
g.members = [tgt]
cog = M.Moderation.__new__(M.Moderation)
cog.bot = types.SimpleNamespace(get_cog=lambda n: None, user=types.SimpleNamespace(id=1))

ok, text = asyncio.run(cog.apply_panel_action(
    g, tgt, 'unmute_chat', reason='тест', actor='Панель'))
check(ok, 'unmute_chat выполнен', f'→ {text}')
check(5001 in tgt.removed, 'роль чат-мута снята')
check(not any(e.get('mute') is False for e in tgt.edits),
      'микрофон не открывали (это войс-размут)')

print('== 4. Владельца бота нельзя замьютить ==')
owner = _Tgt()
owner.id = 11
owner.bot = False
check(M._is_untouchable(g, owner), 'владелец бота в неприкасаемых')
check(not M._is_untouchable(g, tgt), 'обычный участник — можно наказывать')

print('== 5. Модалка мута без авто-срока ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check("placeholder=\"30, 60, 2ч\"" in src and 'default="60"' not in src
      and "default='60м'" not in src and "default='60'" not in src,
      'в поле срока нет заранее стоящих 60 минут')
check("placeholder='30, 60, 2ч'" in src,
      'ПКМ-мут тоже без авто-срока, только подсказка')

print('== 6. Бан: роль есть — комнаты не обходим по одной ==')
check('Semaphore' in src and "_punish_role(guild,'ban')" in src.replace(' ', ''),
      'изоляция комнат: параллельно, и пропускается если есть роль бана')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
