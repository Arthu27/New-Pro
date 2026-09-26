# -*- coding: utf-8 -*-
"""Бан из /modpanel — РОЛЬ бана: каналы бот не закрывает сам.

Заказ владельца 2026-09-08: «боту не нужно закрывать каналы самому —
достаточно просто дать роль бана». Человек остаётся на сервере:
1. бан = выдать роль бана (доступ закрывает сама роль); никаких обходов
   каналов и никакого guild.ban;
2. без выбранной роли бана — вежливый отказ с подсказкой, где настроить;
3. префлайт: нужно manage_roles (выдать роль), право «Бан участников»
   боту НЕ нужно;
4. выбор цели без повторного ника (заказ 2026-09-04);
5. «Взять в работу» в апелляции → в комнату приходит «Вас будет
   обслуживать: …» (владелец 2026-09-08) — см. test_appeals_room_button.

Запуск: python3 tests/test_modpanel_ban_role.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='rb2_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='rb2_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

from cogs import moderation as M

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


print('== 1. Бан = роль бана, каналы бот не трогает ==')
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'cogs', 'moderation.py'), encoding='utf-8').read()
_ban_branch = src[src.index('if action =="ban"'):src.index('elif action =="kick"')]
_compact = _ban_branch.replace(' ', '')
check('guild.ban(' not in _compact,
      'ветка бана НЕ вызывает guild.ban — человек остаётся на сервере')
check('_isolate_member' not in _compact and 'set_permissions' not in _compact,
      'каналы поштучно бот не закрывает (заказ 2026-09-08)')
check('_punish_role' in _compact and 'add_roles' in _compact,
      'бан = выдать роль бана')
check('save_held_roles' not in _compact,
      'роли при бане-ролью не снимаются — снапшот не нужен')
check('Не выбрана роль бана' in _ban_branch and 'Роли наказаний' in _ban_branch,
      'без роли — вежливый отказ с подсказкой, где настроить')

print('== 2. Цель без повторного вопроса ==')
cog = M.Moderation(bot=None)
modal = M.ModActionModal(cog, 'ban', guild=NS(id=777), prefill_target='12345678901234567')
check(modal.fixed_target_id == '12345678901234567',
      'выбранная мышкой цель зафиксирована в модалке')
check(not hasattr(modal, 'target'),
      'поле «Цель» в модалке ОТСУТСТВУЕТ, когда участник выбран мышкой')
modal2 = M.ModActionModal(cog, 'ban', guild=NS(id=777), prefill_target='')
check(hasattr(modal2, 'target'),
      'ручной путь: поле цели на месте (выбор мышкой не обязателен)')
check(modal2.fixed_target_id is None, 'ручной путь: fixed-цели нет')

print('== 3. Префлайт: роли, а не право бана ==')


class _Role:
    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return False


me = NS(top_role=_Role('Бот'), guild_permissions=NS(
    manage_roles=True, ban_members=False, moderate_members=False))
user = NS(id=300, top_role=_Role('Участник'))
guild = NS(id=777, owner_id=42, me=me)
run = asyncio.new_event_loop()
_reason = run.run_until_complete(cog.preflight_reason(guild, user, 'ban'))
check(_reason is None,
      'без ban_members бан проходит предпроверку (нужен только manage_roles)',
      f'→ {_reason}')
me2 = NS(top_role=_Role('Бот'),
         guild_permissions=NS(manage_roles=False, ban_members=True,
                              moderate_members=False))
_reason2 = run.run_until_complete(
    cog.preflight_reason(NS(id=777, owner_id=42, me=me2), user, 'ban'))
check(_reason2 is not None and 'Управление ролями' in _reason2,
      'без manage_roles — подсказка именно про роли',
      f'→ {_reason2}')

print('== 4. Возврат ролей из легаси-снапшота при заходе ==')


class _FakeRole:
    def __init__(self, rid, name, managed=False):
        self.id = rid
        self.name = name
        self.managed = managed


class _FakeMember:
    def __init__(self, roles_given, mid=4242):
        self.id = mid
        self._given = list()
        self.roles = list(roles_given)
        self.guild = None

    async def add_roles(self, *roles, reason=None):
        self._given.extend(roles)
        self._reason = reason


from services import punish_roles as PR

_gid, _uid = 9001, 4242
_kept = [_FakeRole(111, 'Гость'), _FakeRole(222, 'Художник'),
         _FakeRole(333, 'Бот-интеграция', managed=True)]
PR.save_held_roles(_gid, _uid, [r.id for r in _kept])
_ban_role = _FakeRole(999, 'Бан')
_roles_map = {r.id: r for r in (_kept + [_ban_role])}
_guild = NS(id=_gid, default_role=_FakeRole(1, '@everyone'),
            roles=_roles_map, get_role=lambda rid: _roles_map.get(rid))

member = _FakeMember([])
member.guild = _guild
cog2 = M.Moderation(bot=None)
cog2._punish_role = lambda g, kind: (_ban_role if kind == 'ban' else None)
run.run_until_complete(cog2.on_member_join(member))
check([r.id for r in member._given] == [111, 222],
      'on_member_join вернул сохранённые роли (без managed и роли бана)',
      f'→ {[r.id for r in member._given]}')
check(PR.take_held_roles(_gid, _uid) == [],
      'снапшот израсходован — повторный заход ничего не добавляет')

print('== 5. Unban: и роль, и настоящий бан ==')
_unban_branch = src[src.index('elif action =="unban"'):]
_ucompact = _unban_branch.replace(' ', '')[:4000]
check('_unban_role' in _ucompact,
      'разбан снимает роль бана (панельный бан)')
check('guild.unban(' in _ucompact,
      'разбан снимает и настоящий Discord-бан (анти-альт/страж)')

print('== 6. Объявление «Вас будет обслуживать» при «Взять в работу» ==')
_appeals_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'cogs', 'appeals.py'), encoding='utf-8').read()
check('Вас будет обслуживать' in _appeals_src,
      'кнопка «Взять в работу» объявляет в комнате ведущего')
_web_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'web', 'routes', 'appeals_panel.py'), encoding='utf-8').read()
check('Вас будет обслуживать' in _web_src,
      '«Взять в работу» из веб-панели делает то же объявление')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
