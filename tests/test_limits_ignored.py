# -*- coding: utf-8 -*-
"""Лимиты длительности + игнорируемые роли (владелец, 2026-09-05).

1) «Модер дал 100000 минут мута» — теперь потолок действует ВСЕГДА:
   по умолчанию 7 дней, настраивается в Щите сервера → Лимиты; работает
   в боте (/modpanel, ПКМ) и в панели (карточка участника).
2) «Облачная» роль 1192970051821772890 НЕ учитывается никак: с правами
   на ней человек не становится модератором/админом; модератор с ней —
   обычный модератор. Список настраивается в панели (Доступ).
3) Выбор участника в /modpanel — молча, без «вы выбрали этого».
Запуск: python3 tests/test_limits_ignored.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='lim_ign_'))
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
from services import staff_limits as SL  # noqa: E402
from services import ignored_roles as IR  # noqa: E402
from services import staff_hierarchy as SH  # noqa: E402

GID = 1484574976580391004
CLOUD_ROLE = 1192970051821772890

print('== 1. Потолок длительности: дефолт 7 дней ==')
cap = SL.effective_max_duration(GID, 'mute', [])
check(cap == 7 * 86400,
      f'без настройки потолок = 7 дней ({cap // 86400} дн)', f'→ {cap}')
check(SL.effective_max_duration(GID, 'warn', []) == 0,
      'у варнов потолка длительности нет (не мут)')

print('== 2. Модер просит 100000 минут — отказ ==')
import time as _t
from cogs import moderation as M  # noqa: E402
check(M.parse_duration_minutes('100000', 5) == 100000,
      'ввод «100000» парсится как 100000 минут')


def perms(**kw):
    d = dict(administrator=False, ban_members=True, moderate_members=False,
             manage_messages=False, manage_guild=False)
    d.update(kw)
    return types.SimpleNamespace(**d)


class _Role:
    def __init__(self, rid, name, admin_perm=False):
        self.id = rid
        self.name = name
        self.managed = False
        self.permissions = perms(administrator=admin_perm)

    def is_default(self):
        return False


class _Member:
    def __init__(self, uid, name, roles=()):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.roles = list(roles)
        self.guild_permissions = perms()
        self.voice = types.SimpleNamespace(channel=None, mute=False)
        self.timed_out_until = None
        self.added = []
        self.edits = []
        self.dms = []
        self.display_avatar = types.SimpleNamespace(url='http://a/1')

    async def add_roles(self, role, reason=None):
        self.added.append(role.id)
        if role not in self.roles:
            self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        if role in self.roles:
            self.roles.remove(role)

    async def edit(self, **kw):
        self.edits.append(kw)

    async def send(self, embed=None, **kw):
        self.dms.append(embed)


class _Guild:
    def __init__(self, roles):
        self.id = GID
        self.name = 'Hakumo'
        self.owner_id = 0
        self.roles = roles
        self.voice_channels = []
        self.members = []

    def get_role(self, rid):
        for r in self.roles:
            if r.id == rid:
                return r
        return None

    def get_member(self, uid):
        return None


class _PanelActor:
    is_panel = True
    bot = False
    id = 0

    def __init__(self, name='Панель'):
        self._name = name

    @property
    def display_name(self):
        return f'Панель: {self._name}'

    mention = display_name

    def __str__(self):
        return self.display_name


async def cap_test():
    guild = _Guild([_Role(0, '@everyone'), _Role(7001, 'Мут'),
                    _Role(7002, 'Вмут')])
    PR = __import__('services.punish_roles', fromlist=['punish_roles'])
    PR.set_roles(GID, who='t', mute=7001, vmute=7002)
    cog = M.Moderation(bot=types.SimpleNamespace(
        get_guild=lambda gid: guild, get_cog=lambda n: None))
    target = _Member(3000000000000000300, 'Жертва')
    guild.members.append(target)
    ok, text = await cog.apply_panel_action(
        guild, target, 'timeout', reason='тест', amount='100000',
        actor='Модер', duration_cap=None)
    check(not ok and 'дольше разрешённого' in text,
          '100000 минут — отказ с потолком (7 дней)', f'→ {text[:90]}')
    check(not target.added, 'роли не выданы')
    ok, text = await cog.apply_panel_action(
        guild, target, 'timeout', reason='тест', amount='3д',
        actor='Модер', duration_cap=None)
    check(ok, '3 дня — в пределах потолка, мут выдан', f'→ {text[:80]}')
    check(7001 in target.added and 7002 in target.added,
          'выданы обе мут-роли')
    # потолок от панели (с ролями зрителя): админ-роли разрешили 28 дней
    ok, text = await cog.apply_panel_action(
        guild, target, 'timeout', reason='тест', amount='28д',
        actor='Модер', duration_cap=28 * 86400)
    check(ok, 'потолок с панели (28 дней) пропускает 28д')

asyncio.run(cap_test())

print('== 3. Игнорируемая роль: дефолт — «облачная» роль владельца ==')
check(CLOUD_ROLE in IR.get_ignored(GID),
      'роль 1192970051821772890 в игноре по умолчанию')

cloud = _Role(CLOUD_ROLE, 'Облако', admin_perm=True)  # права есть — игнор!
mod_role = _Role(7001, 'Модерация')
guild2 = _Guild([_Role(0, '@everyone'), cloud, mod_role])
guild2.owner_id = 1111000000000000111
with open(f'data/reports_{GID}.json', 'w') as f:
    json.dump({'mod_role_id': '7001'}, f)

holder = _Member(5000000000000000500, 'Облачный', roles=[cloud])
holder.guild_permissions = perms(administrator=True)  # агрегат Discord
guild2.members = [holder]
tr = SH.target_panel_role(guild2, holder)
check(tr == 'uye',
      'носитель «облачной» роли с admin-правом — просто УЧАСТНИК', f'→ {tr}')
ok, deny, ar, trr = SH.check(guild2, holder,
    _Member(6000000000000000600, 'Мод', roles=[mod_role]),
    'timeout', session_role='uye')
check(not ok, 'облачный НЕ может наказать модератора')

print('== 4. Модератор с «облачной» ролью — обычный модератор ==')
mod_with_cloud = _Member(2100000000000000210, 'МодерОбл', roles=[mod_role, cloud])
mod_with_cloud.guild_permissions = perms(administrator=True)
guild2.members.append(mod_with_cloud)
tr = SH.target_panel_role(guild2, mod_with_cloud)
check(tr == 'mod',
      'модератор с «облачной» ролью — МОДЕР (не админ, не выше других)',
      f'→ {tr}')
# panel-role через web.app логику не проверяем здесь — та же функция IR

print('== 5. Панель управляет списком ==')
IR.add(1234567890123456789, GID)
check(1234567890123456789 in IR.get_ignored(GID), 'роль добавлена через панель-API')
IR.remove(1234567890123456789, GID)
check(1234567890123456789 not in IR.get_ignored(GID), 'роль убрана из игнора')
check(IR.is_ignored_role(CLOUD_ROLE, GID), 'is_ignored_role работает')

print('== 6. Выбор участника в /modpanel — молча ==')
src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
i = src.find('class ModTargetSelect')
block = src[i:i + 1800]
check('send_message' not in block,
      'при выборе цели НЕТ сообщений «Цель: … выберите действие»')
check('defer(ephemeral=True)' in block,
      'клик подтверждается тихо (ephemeral defer, на экране ничего)')

print('== 7. Команды не ограничены каналами в коде ==')
import re as _re
srcs = ''
for root in ('cogs',):
    for fn in os.listdir(os.path.join(ROOT, root)):
        if fn.endswith('.py'):
            srcs += open(os.path.join(ROOT, root, fn), encoding='utf-8').read()
check('channel_id in' not in srcs or not _re.search(
    r'if\s+\w*\.?channel_id\s+(==|in)\s', srcs),
      'в коде нет запретов «команда только в канале X» (режет Discord, не бот)')
check('guild_ids' not in srcs,
      'команды не привязаны к списку каналов/гильдий в коде')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
