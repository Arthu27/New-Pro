# -*- coding: utf-8 -*-
"""Единый источник роли модераторов (services/mod_role).

Заказ владельца: роль модераторов должна браться из ОДНОГО места, а не
размазываться по reports / ticket_notify / ticket_permissions / staff_roles.
"""
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modrole_')
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
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


from services import mod_role as MR  # noqa: E402

print('== 1. Пустое состояние ==')
check(MR.get_mod_role_id(777) == '', 'без настроек роль не задана')

print('== 2. set пишет канон + зеркала ==')
MR.set_mod_role_id(777, 555)
check(MR.get_mod_role_id(777) == '555', 'канон reports_777 отдаёт роль')
rep = json.load(open('data/reports_777.json', encoding='utf-8'))
check(rep.get('mod_role_id') == '555', 'reports конфиг записан')
tn = json.load(open('data/ticket_notify_777.json', encoding='utf-8'))
check(tn.get('mod_role_id') == '555', 'ticket_notify зеркалирован (призыв модеров)')
sr = json.load(open('data/staff_roles.json', encoding='utf-8'))
check(sr.get('777', {}).get('moderator_role') == '555', 'staff_roles зеркалирован (заявки)')

print('== 3. Легаси-фолбэки (настройка с любой старой страницы не теряется) ==')
shutil.rmtree('data', ignore_errors=True)
os.makedirs('data', exist_ok=True)
json.dump({'888': {'moderator_role': '111'}}, open('data/staff_roles.json', 'w', encoding='utf-8'))
check(MR.get_mod_role_id(888) == '111', 'фолбэк на staff_roles')

json.dump({'mod_roles': ['222', '333']}, open('data/ticket_permissions_999.json', 'w', encoding='utf-8'))
check(MR.get_mod_role_id(999) == '222', 'фолбэк на ticket_permissions (первая роль)')

json.dump({'mod_role_id': '444'}, open('data/ticket_notify_555.json', 'w', encoding='utf-8'))
check(MR.get_mod_role_id(555) == '444', 'фолбэк на ticket_notify')

print('== 4. Канон приоритетнее легаси ==')
json.dump({'mod_role_id': '100'}, open('data/reports_700.json', 'w', encoding='utf-8'))
json.dump({'mod_role_id': '200'}, open('data/ticket_notify_700.json', 'w', encoding='utf-8'))
check(MR.get_mod_role_id(700) == '100', 'reports-конфиг главнее легаси')

print('== 5. Валидация ==')
check(MR.set_mod_role_id(777, 'не-число') == '', 'мусорный ID не пишется')
check(MR.get_mod_role_id('') == '' and MR.get_mod_role_id(None) == '', 'пустой gid безопасен')

print('== 6. member_is_mod: права Discord + настроенная роль ==')
class FakePerms:
    def __init__(self, **kw):
        self.administrator = kw.get('administrator', False)
        self.manage_guild = kw.get('manage_guild', False)
        self.manage_messages = kw.get('manage_messages', False)
        self.moderate_members = kw.get('moderate_members', False)
        self.ban_members = kw.get('ban_members', False)
        self.kick_members = kw.get('kick_members', False)
class FakeRole:
    def __init__(self, rid): self.id = rid
class FakeMember:
    def __init__(self, roles=(), perms=None):
        self.roles = [FakeRole(int(r)) for r in roles]
        self.guild_permissions = perms or FakePerms()
    guild = None
# роль совпадает
m_role = FakeMember(roles=('111',), perms=FakePerms())
check(MR.member_is_mod(m_role) is False, 'без guild роль 111 не матчится (нет gid)')
# с правами
m_admin = FakeMember(perms=FakePerms(administrator=True))
check(MR.member_is_mod(m_admin) is True, 'администратор — модератор')
m_ban = FakeMember(perms=FakePerms(ban_members=True))
check(MR.member_is_mod(m_ban) is True, 'право бана — модератор')
m_user = FakeMember(perms=FakePerms())
check(MR.member_is_mod(m_user) is False, 'без прав и роли — не модератор')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
