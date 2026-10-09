# -*- coding: utf-8 -*-
"""Жалоба на стафф — эскалация вверх + нельзя разбирать себя.

Схема (2026-10-08):
  • модер/хелпер/мастер → кураторы и выше
  • куратор/ассистент   → администраторы и выше
  • админ               → роль «Стафф админ»
  • стафф-админ         → Owner (владелец сервера/бота)
  • цель не может принять/отклонить жалобу на себя
  • равный/младший тир тоже не может

Запуск: python3 tests/test_report_staff_escalation.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='esc_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='esc_ws_'))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from cogs import reports as R           # noqa: E402
from services import reports_core as RC  # noqa: E402
from services.staff_roles import KNOWN_STAFF_ADMIN_ROLE_ID  # noqa: E402

check(R.STAFF_ESCALATION_ROLE_ID == int(KNOWN_STAFF_ADMIN_ROLE_ID),
      'роль «Стафф админ» = известный id')


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'
        self.managed = False

    def is_default(self):
        return False


MOD_ROLE = _Role(9001, 'Модератор')
CURATOR_ROLE = _Role(9002, 'Куратор')
ADMIN_ROLE = _Role(9003, 'Админ')
STAFF_ADMIN_ROLE = _Role(R.STAFF_ESCALATION_ROLE_ID, 'Стафф админ')

GID = 8080808
OWNER_ID = 42
json.dump({str(MOD_ROLE.id): 'mod', str(CURATOR_ROLE.id): 'curator',
           str(ADMIN_ROLE.id): 'admin',
           str(STAFF_ADMIN_ROLE.id): 'staff_admin'},
          open('data/role_map.json', 'w', encoding='utf-8'))
json.dump({'channel_id': '', 'mod_role_id': str(MOD_ROLE.id)},
          open(f'data/reports_{GID}.json', 'w', encoding='utf-8'))


class _Member:
    def __init__(self, uid, roles=None, *, admin_perm=False):
        self.id = uid
        self.name = f'u{uid}'
        self.display_name = f'u{uid}'
        self.mention = f'<@{uid}>'
        self.bot = False
        self.roles = roles or []
        self.guild_permissions = NS(
            administrator=admin_perm, manage_messages=admin_perm or bool(roles),
            ban_members=False, manage_guild=False)


def make_guild(roles, members=None):
    all_roles = list(roles)
    mem = list(members or [])

    def get_role(rid):
        for r in all_roles:
            if r.id == int(rid):
                return r
        return None

    def get_member(uid):
        for m in mem:
            if int(m.id) == int(uid):
                return m
        return None

    return NS(id=GID, name='Hakumo Test', owner_id=OWNER_ID, roles=all_roles,
              get_role=get_role, get_channel=lambda cid: None,
              get_member=get_member, members=mem, text_channels=[])


owner_member = _Member(OWNER_ID, roles=[], admin_perm=True)
mod_target = _Member(301, roles=[MOD_ROLE])
curator_target = _Member(302, roles=[CURATOR_ROLE])
admin_target = _Member(303, roles=[ADMIN_ROLE])
staff_admin_target = _Member(305, roles=[STAFF_ADMIN_ROLE], admin_perm=True)
plain_target = _Member(304, roles=[])

print('== 1. _staff_escalation(): тир цели → кого звать ==')
guild_full = make_guild(
    [MOD_ROLE, CURATOR_ROLE, ADMIN_ROLE, STAFF_ADMIN_ROLE],
    members=[owner_member, mod_target, curator_target, admin_target,
             staff_admin_target, plain_target])

roles, users, tier, label = R._staff_escalation(guild_full, mod_target)
check(tier == 'mod', 'цель определена как модератор', f'→ {tier}')
check(set(r.id for r in roles) >= {CURATOR_ROLE.id, ADMIN_ROLE.id},
      'на модератора зовут кураторов и админов (не модеров)',
      f'→ {[r.id for r in roles]}')
check(label == 'Кураторы и выше', 'подпись «Кураторы и выше»', f'→ {label!r}')

roles, users, tier, label = R._staff_escalation(guild_full, curator_target)
check(tier == 'curator', 'цель определена как куратор', f'→ {tier}')
check(ADMIN_ROLE.id in {r.id for r in roles},
      'на куратора зовут админов', f'→ {[r.id for r in roles]}')
check(label == 'Администраторы и выше', 'подпись «Администраторы и выше»')

roles, users, tier, label = R._staff_escalation(guild_full, admin_target)
check(tier == 'admin', 'цель определена как админ', f'→ {tier}')
check([r.id for r in roles] == [STAFF_ADMIN_ROLE.id],
      'на админа зовут именно «Стафф админ»', f'→ {[r.id for r in roles]}')
check(label == 'Стафф-админ', 'подпись «Стафф-админ»')

roles, users, tier, label = R._staff_escalation(guild_full, staff_admin_target)
check(tier == 'staff_admin', 'цель определена как стафф-админ', f'→ {tier}')
check(roles == [], 'на стафф-админа роли не тегаем — только Owner',
      f'→ {[r.id for r in roles]}')
check([u.id for u in users] == [OWNER_ID],
      'на стафф-админа зовут Owner', f'→ {[u.id for u in users]}')
check(label == 'Owner', 'подпись «Owner»', f'→ {label!r}')

roles, users, tier, label = R._staff_escalation(guild_full, plain_target)
check(tier == 'uye' and roles == [] and users == [],
      'цель без стафф-роли — эскалации нет',
      f'→ tier={tier} roles={roles} users={users}')

print('== 2. Нет кураторских/админских ролей на сервере — фиксированная роль ==')
guild_bare = make_guild([MOD_ROLE, STAFF_ADMIN_ROLE], members=[mod_target])
roles, users, tier, label = R._staff_escalation(guild_bare, mod_target)
check([r.id for r in roles] == [STAFF_ADMIN_ROLE.id],
      'нет кураторов/админов на сервере → фиксированная «Стафф админ»',
      f'→ {[r.id for r in roles]}')


print('== 3. /report на модератора → тег кураторов, не модеров ==')


class FakeCh:
    def __init__(self):
        self.sent = []
        self.mention = '<#1>'

    async def send(self, **kw):
        self.sent.append(kw)
        return NS(id=len(self.sent) + 5000)


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *a, **kw):
        self.sent.append((a, kw))


class FakeResp:
    def __init__(self):
        self.modal = None
        self._done = False

    def is_done(self):
        return self._done

    async def defer(self, *a, **kw):
        self._done = True

    async def send_modal(self, modal):
        self._done = True
        self.modal = modal


def _walk(item, out):
    out.append(item)
    for child in (getattr(item, 'children', None) or []):
        _walk(child, out)
    return out


def _card_text(view):
    return '\n'.join(getattr(it, 'content', '') or '' for it in _walk(view, [])
                     if type(it).__name__ == 'TextDisplay')


reporter = _Member(200)
ch = FakeCh()
guild_full.get_channel = lambda cid: ch if cid else None
guild_full.text_channels = []


def make_interaction():
    return NS(guild=guild_full, user=reporter, response=FakeResp(),
              followup=FakeFollowup(), channel=NS(id=1, mention='<#1>'),
              client=None)


cog = R.Reports(bot=NS(get_cog=lambda n: None))
run = asyncio.new_event_loop()


async def _submit(target, against='staff', location='chat'):
    inter = make_interaction()
    await cog.report_slash.callback(cog, inter)
    modal = inter.response.modal
    modal.target_select._values = [target]
    modal.against_select._values = [against]
    modal.location_select._values = [location]
    modal.reason_input._value = 'грубит и злоупотребляет'
    inter2 = make_interaction()
    await modal.on_submit(inter2)
    return inter2


_cfg_before = RC.load_cfg(GID)
RC.save_cfg(GID, dict(_cfg_before, channel_id='', mod_role_id=str(MOD_ROLE.id)))
from services import channel_routes as CR  # noqa: E402
CR.set_route(GID, 'report_channel', 1)
guild_full.get_channel = lambda cid: ch if cid == 1 else None

run.run_until_complete(_submit(mod_target))
check(len(ch.sent) == 2, 'карточка + отдельный пинг ушли одним вызовом',
      f'→ {len(ch.sent)}')
card, ping_msg = ch.sent[0], ch.sent[1]
check(MOD_ROLE.mention not in (ping_msg.get('content') or ''),
      'обычная роль модераторов НЕ тегается на жалобу на модератора')
desc = _card_text(card['view'])
check('Кто разбирает' in desc and 'Кураторы и выше' in desc,
      'в карточке явно написано, кто разбирает')

print('== 4. /report на админа → тег «Стафф админ» ==')
ch2 = FakeCh()
guild_full.get_channel = lambda cid: ch2 if cid == 1 else None
run.run_until_complete(_submit(admin_target))
card2, ping2 = ch2.sent[0], ch2.sent[1]
check(ping2.get('content') == STAFF_ADMIN_ROLE.mention,
      'тег уходит ровно роли «Стафф админ»', f'→ {ping2.get("content")!r}')
desc2 = _card_text(card2['view'])
check('Стафф-админ' in desc2, 'карточка называет «Стафф-админ» как разборщика')

print('== 5. /report на стафф-админа → Owner ==')
ch5 = FakeCh()
guild_full.get_channel = lambda cid: ch5 if cid == 1 else None
run.run_until_complete(_submit(staff_admin_target))
card5, ping5 = ch5.sent[0], ch5.sent[1]
check(owner_member.mention in (ping5.get('content') or ''),
      'тег уходит Owner', f'→ {ping5.get("content")!r}')
check(STAFF_ADMIN_ROLE.mention not in (ping5.get('content') or ''),
      'роль Staff Admin НЕ тегается на жалобу на Staff Admin')
desc5 = _card_text(card5['view'])
check('Owner' in desc5, 'карточка называет Owner', f'→ {desc5!r}')

print('== 6. Жалоба «Стафф», но цель без стафф-роли → обычный тег модеров ==')
ch3 = FakeCh()
guild_full.get_channel = lambda cid: ch3 if cid == 1 else None
run.run_until_complete(_submit(plain_target))
card3, ping3 = ch3.sent[0], ch3.sent[1]
check(ping3.get('content') == MOD_ROLE.mention,
      'без стафф-роли у цели — обычный тег модераторов (фолбэк)',
      f'→ {ping3.get("content")!r}')

print('== 7. Нельзя принять/отклонить жалобу на себя / равного ==')
ticket_sa = {'accused_id': str(staff_admin_target.id), 'reporter_id': '200'}
ok, deny = R._can_resolve_report(guild_full, staff_admin_target, ticket_sa)
check(not ok and 'себя' in (deny or ''),
      'Staff Admin не может разобрать жалобу на себя', f'→ {deny!r}')

ok, deny = R._can_resolve_report(guild_full, admin_target, ticket_sa)
check(not ok and 'старший' in (deny or '').lower(),
      'обычный Admin не может разобрать жалобу на Staff Admin',
      f'→ {deny!r}')

ok, deny = R._can_resolve_report(guild_full, owner_member, ticket_sa)
check(ok, 'Owner может разобрать жалобу на Staff Admin', f'→ {deny!r}')

ticket_mod = {'accused_id': str(mod_target.id), 'reporter_id': '200'}
peer_mod = _Member(399, roles=[MOD_ROLE])
guild_full.members.append(peer_mod)
ok, deny = R._can_resolve_report(guild_full, peer_mod, ticket_mod)
check(not ok, 'модер не разбирает жалобу на другого модера', f'→ {deny!r}')

ok, deny = R._can_resolve_report(guild_full, curator_target, ticket_mod)
check(ok, 'куратор разбирает жалобу на модера', f'→ {deny!r}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
