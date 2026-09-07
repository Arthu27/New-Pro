# -*- coding: utf-8 -*-
"""Бан из /modpanel — НАСТОЯЩИЙ серверный бан + возврат ролей после разбана.

Заказ владельца 2026-09-07: «так жёстко и банить не нужно — зачем он-то на
сервере должен быть, просто в бане самого сервера». Раньше «бан» был
изоляцией (роль бана + закрытые каналы, человек оставался на сервере —
решение от 2026-09-04). Теперь:
1. бан = guild.ban(...) — человек вылетает с сервера, попадает в список
   банов; сообщения НЕ удаляются (delete_message_seconds=0);
2. перед баном роли сохраняются в снапшот (punish_roles.save_held_roles),
   а при возврате после разбана on_member_join возвращает их сам;
3. изоляция/роль бана в бан-действии больше НЕТ (право — ban_members,
   не manage_roles);
4. выбор цели без повторного ника (заказ 2026-09-04, не зависит от типа бана).

Запуск: python3 tests/test_modpanel_ban_role.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='rb_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='rb_ws_'))
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


print('== 1. Бан = настоящий Discord-бан ==')
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'cogs', 'moderation.py'), encoding='utf-8').read()
_ban_branch = src[src.index('if action =="ban"'):src.index('elif action =="kick"')]
_compact = _ban_branch.replace(' ', '')
check('guild.ban(' in _compact,
      'ветка бана вызывает guild.ban — человек вылетает с сервера')
check('delete_message_seconds=0' in _compact,
      'бан НЕ удаляет сообщения (delete_message_seconds=0)')
check('_isolate_member' not in _compact,
      'изоляция в бан-действии больше не вызывается')
check('add_roles' not in _compact and '_punish_role' not in _compact,
      'роль бана в бан-действии больше не выдаётся')
check('save_held_roles' in _compact,
      'перед баном роли сохраняются в снапшот (для возврата после разбана)')
_snap_at = _compact.index('save_held_roles')
_ban_at = _compact.index('guild.ban(')
check(_snap_at < _ban_at,
      'снапшот ролей делается ДО вызова guild.ban')
check('error_embed' not in _ban_branch and 'не выбран' not in _ban_branch
      and 'return ' not in _ban_branch,
      'жёсткой блокировки «канал апелляции не настроен» в бан-ветке больше нет')

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

print('== 3. Префлайт: настоящему бану нужны права бана ==')


class _Role:
    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return False


me = NS(top_role=_Role('Бот'), guild_permissions=NS(
    manage_roles=True, ban_members=True, moderate_members=False))
user = NS(id=300, top_role=_Role('Участник'))
guild = NS(id=777, owner_id=42, me=me)
run = asyncio.new_event_loop()
_reason = run.run_until_complete(cog.preflight_reason(guild, user, 'ban'))
check(_reason is None,
      'с ban_members бан проходит предпроверку', f'→ {_reason}')
me2 = NS(top_role=_Role('Бот'),
         guild_permissions=NS(manage_roles=True, ban_members=False,
                              moderate_members=False))
_reason2 = run.run_until_complete(
    cog.preflight_reason(NS(id=777, owner_id=42, me=me2), user, 'ban'))
check(_reason2 is not None and 'Бан участников' in _reason2,
      'без ban_members — понятная подсказка именно про право бана',
      f'→ {_reason2}')

print('== 4. Возврат после разбана: роли возвращаются сами ==')


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
# managed-роль и роль бана вернуть нельзя — фильтруются
_ban_role = _FakeRole(999, 'Бан')
_guild = NS(id=_gid, default_role=_FakeRole(1, '@everyone'),
            roles={r.id: r for r in (_kept + [_ban_role])},
            get_role=lambda rid: {r.id: r for r in (_kept + [_ban_role])}.get(rid))


class _CogNS(NS):
    pass


member = _FakeMember([])
member.guild = _guild
cog2 = M.Moderation(bot=None)
# подменим _punish_role, чтобы вернул «роль бана» — её возвращать нельзя
cog2._punish_role = lambda g, kind: (_ban_role if kind == 'ban' else None)
run.run_until_complete(cog2.on_member_join(member))
check([r.id for r in member._given] == [111, 222],
      'on_member_join вернул сохранённые роли (без managed и роли бана)',
      f'→ {[r.id for r in member._given]}')
check(PR.take_held_roles(_gid, _uid) == [],
      'снапшот израсходован — повторный заход ничего не добавляет')

print('== 5. Unban: ссылка-возврат при настоящем бане ==')
check('_make_return_invite' in src and 'Ссылка-возврат отправлена в ЛС' in src,
      'разбан из панели отправляет ссылку-возврат, если инвайты включены')
_unban_branch = src[src.index('elif action =="unban"'):]
_ucompact = _unban_branch.replace(' ', '')[:4000]
check('guild.unban(' in _ucompact,
      'разбан снимает настоящий бан (guild.unban), а не только изоляцию')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
