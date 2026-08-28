# -*- coding: utf-8 -*-
"""Видимость /modpanel по «категории доступа» (Классические разрешения).

Заказ владельца: «в /modpanel должны быть только те наказания, что я в
категории доступа ключу. Не ключу бан — бан не отображается».

Классическое разрешение (панель → Доступ → Права команд → Классические
разрешения) хранится в permission_acl (action_acl, SQLite). Проверяем:
1) пункт /modpanel ↔ ключ действия (бан → ban+unban, мут → mute_chat/
   vmute/vunmute, таймаут → timeout/untimeout, варн, очистка);
2) нет правила — модератор видит всё (ничего не ломаем);
3) правило на действие — пункт исчезает у чужих ролей и остаётся у
   назначенных (владелец сервера/бота и админ видят всё);
4) фильтры работают вместе с «Лимитами команды» (staff_limits);
5) защита на исполнении: выбор меню и отправка модалки отказывают, если
   доступ сняли, пока меню было открыто; веб-панель (PanelActor) НЕ
   режется ролевым ACL — у неё своя авторизация.

Запуск: /tmp/venv/bin/python tests/test_modpanel_acl.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modpanel_acl_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')  # изолированный sqlite

from services.permission_acl import (ACTIONS, check_action, save_action_acl,  # noqa: E402
                                     set_action_rule, load_action_acl)
from cogs.moderation import (actions_for_member, MODPANEL_ACTIONS,  # noqa: E402
                             MODPANEL_ACL_KEYS, ModActionModal,
                             ModActionSelect, Moderation, PanelActor,
                             MODPANEL_EMOJI)

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


class Role:
    def __init__(self, rid):
        self.id = rid


class Perms:
    def __init__(self, administrator=False):
        self.administrator = administrator


class Member:
    def __init__(self, uid, roles=(), administrator=False):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.guild_permissions = Perms(administrator)
        self.bot = False


class Guild:
    def __init__(self, gid, owner=1):
        self.id = gid
        self.owner_id = owner


GID = 424243
OWNER = 10
BOT_OWNER = 11
save_action_acl(GID, {})
os.environ['OWNER_ID'] = str(BOT_OWNER)  # владелец бота — обходит правила

BASE = [a[0] for a in MODPANEL_ACTIONS]
m = Member(100, [601])
m_owner = Member(OWNER, [])
m_bot_owner = Member(BOT_OWNER, [])
m_admin = Member(102, [602], administrator=True)

print('== 1. Пункт /modpanel ↔ «классическое» разрешение ==')
_expected = {
    'warn': 'warn',
    'ban': 'ban',
    'unban': 'ban',
    'timeout': 'timeout',
    'untimeout': 'timeout',
    'mute_chat': 'mute',
    'vmute': 'mute',
    'vunmute': 'mute',
    'clear': 'purge',
}
for act, key in _expected.items():
    check(MODPANEL_ACL_KEYS.get(act) == key, f'{act} -> действие {key}')
for act in BASE:
    check(act in MODPANEL_ACL_KEYS, f'{act} из меню имеет маппинг ACL')
for key in set(MODPANEL_ACL_KEYS.values()):
    check(key in ACTIONS, f'{key} существует в Классических разрешениях панели')
check(MODPANEL_ACL_KEYS.get('warn') == 'warn' and MODPANEL_ACL_KEYS.get('clear') == 'purge',
      'варн и очистка тоже управляются категорией доступа')

print('== 2. Правил нет — видно всё (ничего не сломали) ==')
check([a[0] for a in actions_for_member(Guild(GID), m)] == BASE,
      'модератор без правил видит все пункты')
g_own = Guild(GID, owner=OWNER)
check([a[0] for a in actions_for_member(g_own, m_owner)] == BASE,
      'владелец сервера видит все пункты')
check([a[0] for a in actions_for_member(Guild(GID), m_admin)] == BASE,
      'админ видит все пункты')
check([a[0] for a in actions_for_member(Guild(GID), m_bot_owner)] == BASE,
      'владелец бота видит все пункты')

print('== 3. Не ключил «Бан» — бана нет в /modpanel ==')
set_action_rule(GID, 'ban', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check('ban' not in got and 'unban' not in got,
      f'без роли 601 бана/разбана нет: {got}')
check('timeout' in got and 'mute_chat' in got and 'clear' in got,
      'остальные наказания на месте')
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [601]))]
check('ban' in got and 'unban' in got, 'роль с «Бан» видит бан и разбан')
check([a[0] for a in actions_for_member(g_own, m_owner)] == BASE,
      'владельца правило бана не касается')
check([a[0] for a in actions_for_member(Guild(GID), m_admin)] == BASE,
      'админа правило бана не касается')
check([a[0] for a in actions_for_member(Guild(GID), m_bot_owner)] == BASE,
      'владельца бота правило бана не касается')
set_action_rule(GID, 'ban', [])

print('== 4. Отдельные тумблеры: мут, таймаут, варн, очистка ==')
set_action_rule(GID, 'mute', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check('mute_chat' not in got and 'vmute' not in got and 'vunmute' not in got,
      f'без «Мут» нет мутов чата/войса и снятий: {got}')
check('timeout' in got and 'untimeout' in got,
      '«Таймаут» — отдельный тумблер, муты его не глушат')
set_action_rule(GID, 'timeout', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check('timeout' not in got and 'untimeout' not in got,
      f'без «Таймаут» нет таймаута и снятия: {got}')
check('ban' in got and 'warn' in got and 'clear' in got,
      'остальные наказания на месте (муты и таймауты — скрыты своими тумблерами)')
set_action_rule(GID, 'warn', ['601'])
set_action_rule(GID, 'purge', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check('warn' not in got and 'clear' not in got,
      f'без «Варн»/«Очистка» их нет: {got}')
set_action_rule(GID, 'mute', [])
set_action_rule(GID, 'timeout', [])
set_action_rule(GID, 'warn', [])
set_action_rule(GID, 'purge', [])

print('== 5. Фильтры вместе: Лимиты команды + категория доступа ==')
from services import staff_limits as SL  # noqa: E402

SL.set_role_limits(GID, 602, who='t', role_name='Мут-роль', mute=5)
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check(set(got) == {'timeout', 'mute_chat', 'vmute'},
      f'лимит мута оставил только муты: {got}')
set_action_rule(GID, 'ban', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [602]))]
check(set(got) == {'timeout', 'mute_chat', 'vmute'},
      'оба фильтра вместе: мут-лимит и без бана — муты на месте')
set_action_rule(GID, 'mute', ['601'])
got = [a[0] for a in actions_for_member(Guild(GID), Member(100, [601, 602]))]
check(set(got) == {'timeout', 'mute_chat', 'vmute'},
      'роль с «Мут» в категории доступа всё равно ограничена лимитом мута')
set_action_rule(GID, 'ban', [])
set_action_rule(GID, 'mute', [])
SL.clear_role_limits(GID, 602, who='t')

print('== 6. Защита на исполнении (меню открыто до смены прав) ==')
cog = Moderation.__new__(Moderation)


class _Resp:
    def __init__(self):
        self.done = False
        self.sent = []
        self.modal = []
        self.deferred = False

    def is_done(self):
        return self.done

    async def send_message(self, embed=None, ephemeral=False, **kw):
        self.sent.append(embed)
        self.done = True

    async def send_modal(self, modal):
        self.modal.append(modal)

    async def defer(self, ephemeral=False):
        self.deferred = True


class _Inter:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.response = _Resp()


g = Guild(GID)
set_action_rule(GID, 'ban', ['601'])

# выбор пункта в меню: чужой роли модалка не откроется
i = _Inter(Member(100, [602]), g)
sel = ModActionSelect(cog, member=Member(100, [602]), allowed=[a for a in MODPANEL_ACTIONS])
sel._values = ['ban']  # как discord проставляет выбранное значение
asyncio.run(sel.callback(i))
check(not i.response.modal, 'выбор «Бан» без разрешения → модалка не открылась')
check(i.response.sent and 'Классические разрешения' in str(getattr(i.response.sent[0], 'description', '')),
      'отказ объясняет, где включить доступ')

# своя роль — модалка открывается
i2 = _Inter(Member(100, [601]), g)
sel2 = ModActionSelect(cog, member=Member(100, [601]), allowed=[a for a in MODPANEL_ACTIONS])
sel2._values = ['ban']
asyncio.run(sel2.callback(i2))
check(bool(i2.response.modal) and not i2.response.sent,
      'с ролью «Бан» модалка открывается')

# отправка модалки: даже если меню старое — без права не исполняем
i3 = _Inter(Member(100, [602]), g)
modal = ModActionModal(cog, 'ban', guild=g)
asyncio.run(modal.on_submit(i3))
check(not i3.response.deferred and not getattr(i3, 'ran', False),
      'on_submit без разрешения: до исполнения не дошло, отработан отказ')
check(i3.response.sent and 'Классические разрешения' in str(getattr(i3.response.sent[-1], 'description', '')),
      'отказ в модалке говорит, откуда включить доступ')

# с правами — исполнение идёт дальше. Дальше цепочка демки/канала апелляции
# (не тема этого теста) — важно, что ACL пропустил и defer сделался.
i4 = _Inter(Member(100, [601]), g)
i4.channel = None
modal4 = ModActionModal(cog, 'ban', guild=g)
try:
    asyncio.run(modal4.on_submit(i4))
except Exception:
    pass  # дальше пути — доказательства/изоляция
check(i4.response.deferred, 'с ролью «Бан» путь исполнения запускается (defer сделан)')

set_action_rule(GID, 'ban', [])
SL.clear_role_limits(GID, 602, who='t')

print('== 7. Веб-панель (PanelActor) не режется ролевым ACL ==')
set_action_rule(GID, 'ban', ['601'])
check(check_action(GID, PanelActor('admin'), 'ban'),
      'PanelActor обходит классические разрешения (у панели своя авторизация)')
check(load_action_acl(GID).get('ban') == ['601'], 'правило в БД, откат чистый')
set_action_rule(GID, 'ban', [])
save_action_acl(GID, {})

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
