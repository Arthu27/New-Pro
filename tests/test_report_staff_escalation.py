# -*- coding: utf-8 -*-
"""Жалоба на стафф — эскалация вверх по иерархии (владелец 2026-09-21).

«если репорт на модера будет насматривать кураторы и выше, если кураторам
репорт то будут разбираться админы и выше, если админам то будет идти
стафф админ» — обычных модераторов на такую жалобу не зовём (конфликт
интересов: персонал не судит равного/старшего, см. services/staff_hierarchy).

Проверяем НАСТОЯЩИМ кодом (cogs.reports._staff_escalation / _deliver_report):
  • жалоба на модератора → тег кураторов и админов (не модераторов)
  • жалоба на куратора   → тег только админов
  • жалоба на админа     → тег фиксированной роли «Стафф админ» (id из ТЗ)
  • цель без стафф-роли (against=«стафф» по ошибке) → обычный тег модеров
  • карточка красиво объясняет, кто и почему разбирает

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

check(R.STAFF_ESCALATION_ROLE_ID == 1549118975110152263,
      'роль «Стафф админ» = 1549118975110152263 (заказ владельца)')


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
json.dump({str(MOD_ROLE.id): 'mod', str(CURATOR_ROLE.id): 'curator',
          str(ADMIN_ROLE.id): 'admin'},
          open('data/role_map.json', 'w', encoding='utf-8'))
json.dump({'channel_id': '', 'mod_role_id': str(MOD_ROLE.id)},
          open(f'data/reports_{GID}.json', 'w', encoding='utf-8'))


class _Member:
    def __init__(self, uid, roles=None):
        self.id = uid
        self.name = f'u{uid}'
        self.display_name = f'u{uid}'
        self.mention = f'<@{uid}>'
        self.bot = False
        self.roles = roles or []
        self.guild_permissions = NS(administrator=False)


def make_guild(roles):
    all_roles = list(roles)

    def get_role(rid):
        for r in all_roles:
            if r.id == int(rid):
                return r
        return None

    return NS(id=GID, name='Hakumo Test', owner_id=1, roles=all_roles,
             get_role=get_role, get_channel=lambda cid: None,
             get_member=lambda uid: None, members=[], text_channels=[])


mod_target = _Member(301, roles=[MOD_ROLE])
curator_target = _Member(302, roles=[CURATOR_ROLE])
admin_target = _Member(303, roles=[ADMIN_ROLE])
plain_target = _Member(304, roles=[])

print('== 1. _staff_escalation(): тир цели → кого звать ==')
guild_full = make_guild([MOD_ROLE, CURATOR_ROLE, ADMIN_ROLE, STAFF_ADMIN_ROLE])

roles, tier, label = R._staff_escalation(guild_full, mod_target)
check(tier == 'mod', 'цель определена как модератор', f'→ {tier}')
check(set(r.id for r in roles) == {CURATOR_ROLE.id, ADMIN_ROLE.id},
      'на модератора зовут кураторов и админов (не модеров)',
      f'→ {[r.id for r in roles]}')
check(label == 'Кураторы и выше', 'подпись «Кураторы и выше»', f'→ {label!r}')

roles, tier, label = R._staff_escalation(guild_full, curator_target)
check(tier == 'curator', 'цель определена как куратор', f'→ {tier}')
check(set(r.id for r in roles) == {ADMIN_ROLE.id},
      'на куратора зовут только админов', f'→ {[r.id for r in roles]}')
check(label == 'Администраторы и выше', 'подпись «Администраторы и выше»')

roles, tier, label = R._staff_escalation(guild_full, admin_target)
check(tier == 'admin', 'цель определена как админ', f'→ {tier}')
check([r.id for r in roles] == [STAFF_ADMIN_ROLE.id],
      'на админа зовут именно «Стафф админ»', f'→ {[r.id for r in roles]}')
check(label == 'Стафф-админ', 'подпись «Стафф-админ»')

roles, tier, label = R._staff_escalation(guild_full, plain_target)
check(tier == 'uye' and roles == [],
      'цель без стафф-роли — эскалации нет (сработает фолбэк на модеров)',
      f'→ tier={tier} roles={roles}')

print('== 2. Нет кураторских/админских ролей на сервере — фиксированная роль ==')
guild_bare = make_guild([MOD_ROLE, STAFF_ADMIN_ROLE])  # куратора/админа нет
roles, tier, label = R._staff_escalation(guild_bare, mod_target)
check([r.id for r in roles] == [STAFF_ADMIN_ROLE.id],
      'нет кураторов/админов на сервере → фиксированная «Стафф админ»',
      f'→ {[r.id for r in roles]}')


# ── 3. Полный путь через модалку: карточка + тег ────────────────────────────
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
guild_full.text_channels = []  # без совпадения по имени «модерация»


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


# конфиг репортов должен указывать на этот канал, иначе _ensure_mod_channel
# пойдёт искать по имени/умолчанию — используем маршрут явно.
_cfg_before = RC.load_cfg(GID)
RC.save_cfg(GID, dict(_cfg_before, channel_id='', mod_role_id=str(MOD_ROLE.id)))
from services import channel_routes as CR  # noqa: E402
CR.set_route(GID, 'report_channel', 1)
guild_full.get_channel = lambda cid: ch if cid == 1 else None

run.run_until_complete(_submit(mod_target))
check(len(ch.sent) == 2, 'карточка + отдельный пинг ушли одним вызовом',
      f'→ {len(ch.sent)}')
card, ping_msg = ch.sent[0], ch.sent[1]
check(ping_msg.get('content') == CURATOR_ROLE.mention + ' ' + ADMIN_ROLE.mention
      or set(ping_msg.get('content', '').split())
      == {CURATOR_ROLE.mention, ADMIN_ROLE.mention},
      'тег уходит кураторам и админам, БЕЗ модераторской роли',
      f'→ {ping_msg.get("content")!r}')
check(MOD_ROLE.mention not in (ping_msg.get('content') or ''),
      'обычная роль модераторов НЕ тегается на жалобу на модератора')
desc = _card_text(card['view'])
check('Кто разбирает' in desc and 'Кураторы и выше' in desc,
      'в карточке явно написано, кто разбирает')
check('модератор' in desc.lower(), 'в карточке видно, что жалоба на модератора')

print('== 4. /report на админа → тег «Стафф админ» ==')
ch2 = FakeCh()
guild_full.get_channel = lambda cid: ch2 if cid == 1 else None
run.run_until_complete(_submit(admin_target))
card2, ping2 = ch2.sent[0], ch2.sent[1]
check(ping2.get('content') == STAFF_ADMIN_ROLE.mention,
      'тег уходит ровно роли «Стафф админ»', f'→ {ping2.get("content")!r}')
desc2 = _card_text(card2['view'])
check('Стафф-админ' in desc2, 'карточка называет «Стафф-админ» как разборщика')

print('== 5. Жалоба «Стафф», но цель без стафф-роли → обычный тег модеров ==')
ch3 = FakeCh()
guild_full.get_channel = lambda cid: ch3 if cid == 1 else None
run.run_until_complete(_submit(plain_target))
card3, ping3 = ch3.sent[0], ch3.sent[1]
check(ping3.get('content') == MOD_ROLE.mention,
      'без стафф-роли у цели — обычный тег модераторов (фолбэк)',
      f'→ {ping3.get("content")!r}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
