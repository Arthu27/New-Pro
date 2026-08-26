# -*- coding: utf-8 -*-
"""Живая проверка заявок в команду и AFK (заказ 2026-08-27):

1) /afk и /afk-remove отвечают ТОЛЬКО самому пользователю (ephemeral);
2) чат-контроля больше нет: в select-меню и в обеих формах заявки
   остались только Хелпер и Модератор;
3) после одобрения бот выдаёт роль ПО ДОЛЖНОСТИ заявки:
   Хелпер → «Хелпер», Модератор → «Модератор»
   (env → data/staff_roles.json → имя роли на сервере);
4) отказ по-человечески: подсказка, какую роль создать / где задать ID.

Запуск: python3 tests/test_staff_apply_roles.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DEMO_MODE', '1')

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


TMP = tempfile.mkdtemp(prefix='hakumo_staff_roles_')
os.chdir(TMP)
os.makedirs('data', exist_ok=True)

# ── 1. AFK: ответы видит только сам пользователь ─────────────────────
print('== /afk: ответы только пользователю (ephemeral) ==')
from cogs.afk import AFK


class FakeResp:
    def __init__(self):
        self.kw = None

    async def send_message(self, content=None, **kw):
        self.kw = {'content': content, **kw}

    async def defer(self, **kw):
        pass


class FakeUser:
    display_name = 'Тест'
    id = 42

    class _Av:
        url = 'https://cdn.discordapp.com/x.png'
    display_avatar = _Av()

    async def edit(self, *a, **kw):
        pass


class FakeInter:
    guild_id = 777
    user = FakeUser()

    def __init__(self):
        self.response = FakeResp()


cog = AFK(bot=None)
loop = asyncio.new_event_loop()

async def _call_afk(icog, iinter, reason='AFK'):
    # app_commands.Command хранит сырой колбэк в _callback (binding = cog)
    return await icog.afk._callback(icog, iinter, причина=reason)


inter = FakeInter()
loop.run_until_complete(_call_afk(cog, inter, 'обед'))
kw = inter.response.kw
check(kw is not None and kw.get('ephemeral') is True,
      '/afk отвечает ephemeral — видит только сам пользователь')
check('обед' in str(kw.get('embed').description) if kw.get('embed') else True,
      '/afk карточка с причиной на месте')

inter2 = FakeInter()
loop.run_until_complete(cog.afk_remove._callback(cog, inter2))
check(inter2.response.kw is not None and inter2.response.kw.get('ephemeral') is True,
      '/afk-remove (без упоминаний) — ephemeral')

from cogs import afk as afk_mod
afk_mod._pending_mentions[42] = [{
    'from': 'Кто-то', 'guild': 'G', 'channel': 'general', 'msg': 'ты где?'}]
cog._set(777, 42, 'обед')
inter3 = FakeInter()
loop.run_until_complete(cog.afk_remove._callback(cog, inter3))
check(inter3.response.kw is not None and inter3.response.kw.get('ephemeral') is True,
      '/afk-remove (со списком упоминаний) — ephemeral')

# ── 2. Чат-контроля нет, должности две ───────────────────────────────
print('== Должности: только Хелпер и Модератор ==')
from cogs.staff_apply import RoleSelect, StaffReviewView

opts = RoleSelect().options
labels = [o.label for o in opts]
values = [o.value for o in opts]
check('Chat Control' not in values and 'Чат-контроль' not in labels,
      'select-меню: чат-контроля нет')
check(set(values) == {'Helper', 'Moderator'}, f'select-меню: ровно две должности {values}')
check('Хелпер' in labels and 'Модератор' in labels, 'select-меню: подписи по-русски')

repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for tpl in ('web/templates/member_apply.html', 'web/templates/public_apply.html'):
    html = open(os.path.join(repo, tpl), encoding='utf-8').read()
    check('Чат-контроль' not in html and 'Chat Control' not in html,
          f'{tpl.split("/")[-1]}: карточки чат-контроля нет')
    check(html.count('name="apply-role"') >= 2,
          f'{tpl.split("/")[-1]}: выбор Хелпер/Модератор на месте')

# ── 3. Роль по должности: поиск и выдача ─────────────────────────────
print('== Роль по должности: откуда берётся ==')
from services import staff_roles as SR


class FakeRole:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class FakeMember:
    def __init__(self, mid):
        self.id = mid
        self.added = []

    async def add_roles(self, role, **kw):
        self.added.append(role.name)


class FakeGuild:
    def __init__(self, roles, members):
        self.roles = roles
        self._members = members

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_member(self, mid):
        return self._members.get(mid)


g = FakeGuild([FakeRole(10, 'Хелпер'), FakeRole(20, 'Модератор')], {})

check(SR.normalize_position('Helper') == 'helper'
      and SR.normalize_position('Хелпер') == 'helper'
      and SR.normalize_position('Moderator') == 'moderator'
      and SR.normalize_position('Модератор') == 'moderator',
      'должности нормализуются (ru/en)')
check(SR.normalize_position('Chat Control') == 'moderator'
      and SR.normalize_position('Чат-контроль') == 'moderator',
      'легаси-заявки с чат-контролем ведём как модераторские')

r, _ = SR.resolve_staff_role(g, 'helper')
check(r is not None and r.name == 'Хелпер', 'поиск по имени: хелпер найден')
r, _ = SR.resolve_staff_role(g, 'moderator')
check(r is not None and r.name == 'Модератор', 'поиск по имени: модератор найден')
r, searched = SR.resolve_staff_role(FakeGuild([], {}), 'helper')
check(r is None and searched, 'роли нет — возвращаем, что искали (для подсказки)')

from config import Config
prev = Config.STAFF_HELPER_ROLE_ID
Config.STAFF_HELPER_ROLE_ID = 7777
g2 = FakeGuild([FakeRole(7777, 'Staff Helper')], {})
r, _ = SR.resolve_staff_role(g2, 'helper')
check(r is not None and r.name == 'Staff Helper', 'приоритет: явный ID из .env')
Config.STAFF_HELPER_ROLE_ID = prev

m = FakeMember(42)
g3 = FakeGuild([FakeRole(10, 'Хелпер')], {42: m})
res = loop.run_until_complete(SR.grant_staff_role(g3, 42, 'Хелпер'))
check(res['role_name'] == 'Хелпер' and m.added == ['Хелпер'],
      'grant: хелперу выдана роль «Хелпер»')
res = loop.run_until_complete(SR.grant_staff_role(g3, 99, 'Модератор'))
check(res['role_name'] is None and res['reason'] == 'member_left',
      'grant: участник ушёл — понятно почему не выдано')
res = loop.run_until_complete(SR.grant_staff_role(FakeGuild([], {42: FakeMember(42)}), 42, 'Хелпер'))
hint = SR.role_hint(res)
check('STAFF_HELPER_ROLE_ID' in hint and 'хелпер' in hint.lower(),
      f'подсказка человеку: {hint}')

# ── 3.5 Ветки заявок: хелперы — своим кураторам, модераторы — своим ──
print('== Ветки заявок: своя на каждую должность ==')
from cogs.staff_apply import apply_target
from config import Config


class FakeChan:
    def __init__(self, cid): self.id = cid


class FakeGuildCh:
    def __init__(self, chans): self._ch = {c.id: c for c in chans}

    def get_channel(self, cid):
        return self._ch.get(cid)


_p = (Config.STAFF_HELPER_CHANNEL_ID, Config.STAFF_MODERATOR_CHANNEL_ID,
      Config.STAFF_HELPER_CURATOR_ROLE_ID, Config.STAFF_MODERATOR_CURATOR_ROLE_ID)
(_ph, _pm, _ch, _cm) = _p
try:
    Config.STAFF_HELPER_CHANNEL_ID = 501
    Config.STAFF_MODERATOR_CHANNEL_ID = 502
    Config.STAFF_HELPER_CURATOR_ROLE_ID = 601
    Config.STAFF_MODERATOR_CURATOR_ROLE_ID = 602
    gch = FakeGuildCh([FakeChan(501), FakeChan(502), FakeChan(500)])

    ch, ping = apply_target('Хелпер', gch)
    check(ch is not None and ch.id == 501 and ping == '<@&601>',
          'заявка хелпера → ветка хелперов (501) + пинг кураторов хелперов',
          f'→ канал {getattr(ch, "id", None)}, пинг {ping}')
    ch, ping = apply_target('Модератор', gch)
    check(ch is not None and ch.id == 502 and ping == '<@&602>',
          'заявка модератора → ветка модераторов (502) + пинг своих кураторов')
    ch, ping = apply_target('Chat Control', gch)
    check(ch.id == 502, 'легаси чат-контроль ведётся в ветку модераторов')

    Config.STAFF_HELPER_CHANNEL_ID = 0  # ветки нет → общий канал
    from cogs import staff_apply as _sa
    _saved_apply_ch, _sa.APPLY_CHANNEL_ID = _sa.APPLY_CHANNEL_ID, 500
    try:
        ch, ping = apply_target('Хелпер', gch)
        check(ch is not None and ch.id == 500,
              'без своей ветки — общий канал заявок')
    finally:
        _sa.APPLY_CHANNEL_ID = _saved_apply_ch
    ch, ping = apply_target('Хелпер', None)
    check(ch is None and ping == '', 'без гильдии — ничего не отправляем')
finally:
    (Config.STAFF_HELPER_CHANNEL_ID, Config.STAFF_MODERATOR_CHANNEL_ID,
     Config.STAFF_HELPER_CURATOR_ROLE_ID, Config.STAFF_MODERATOR_CURATOR_ROLE_ID) = _p

src_cog = open(os.path.join(repo, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
src_web = open(os.path.join(repo, 'web', 'app.py'), encoding='utf-8').read()
check('apply_target(self.role_name, interaction.guild)' in src_cog,
      'Discord-заявка уходит в ветку по должности')
check('apply_target (data .get' in src_web or 'apply_target(data' in src_web,
      'веб-заявка уходит в ту же ветку по должности')

# ── 4. Кнопки в Discord: одобрение выдаёт роль ───────────────────────
print('== Кнопки «Одобрить» в Discord ==')
apps = {'42': {
    'user_id': '42', 'username': 'cand', 'display_name': 'cand', 'avatar': None,
    'role': 'Helper', 'age': '18', 'experience': '-', 'reason': '-', 'activity': '-',
    'status': 'pending', 'submitted_at': '2026-08-27T00:00:00',
    'timestamp': '2026-08-27T00:00:00', 'message_id': '555', 'guild_id': '777',
}}
with open('data/staff_apps.json', 'w', encoding='utf-8') as f:
    json.dump(apps, f, ensure_ascii=False, indent=2)


class FakeMsg:
    id = 555
    embeds = []


class FakeClient:
    def __init__(self, guild):
        self._g = guild
        self.fetched = []

    def get_guild(self, gid):
        return self._g if gid == 777 else None

    async def fetch_user(self, uid):
        self.fetched.append(uid)
        u = FakeUser()
        u.sent = []
        u.send = (lambda uu: (lambda *a, **k: uu.sent.append(a or k) or asyncio.sleep(0)))(u)
        return u


class _GP:
    manage_guild = True
    administrator = True


class FakeInter2:
    user = type('U', (), {'guild_permissions': _GP(), 'display_name': 'Главный'})()
    display_name = 'Главный'
    message = FakeMsg()
    guild = None

    def __init__(self, client):
        self.client = client
        self.response = FakeResp()
        self.followups = []

    async def defer(self, **kw):
        pass


g4 = FakeGuild([FakeRole(10, 'Хелпер')], {42: FakeMember(42)})
cl = FakeClient(g4)
inter4 = FakeInter2(cl)
inter4.followup = type('F', (), {
    'send': (lambda s, *a, **k: s.msgs.append(a[0] if a else k) or asyncio.sleep(0))})()
inter4.followup.msgs = []

loop.run_until_complete(StaffReviewView()._review(inter4, 'approve'))
data = json.load(open('data/staff_apps.json', encoding='utf-8'))
check(data['42']['status'] == 'approved', 'заявка одобрена (статус в базе)')
check(data['42'].get('granted_role') == 'Хелпер', 'в заявке записана выданная роль')
check(g4._members[42].added == ['Хелпер'], 'участнику реально добавлена роль «Хелпер»')
check(any('Роль выдана' in str(m) and 'Хелпер' in str(m) for m in inter4.followup.msgs),
      'нажавшему видно: роль выдана — какая')
check(cl.fetched == [42], 'заявителю отправлено ЛС')

# отказ — роль не трогаем
apps['42']['status'] = 'pending'
apps['42'].pop('granted_role', None)
with open('data/staff_apps.json', 'w', encoding='utf-8') as f:
    json.dump(apps, f, ensure_ascii=False)
g5 = FakeGuild([FakeRole(10, 'Хелпер')], {42: FakeMember(42)})
inter5 = FakeInter2(FakeClient(g5))
inter5.followup = type('F', (), {
    'send': (lambda s, *a, **k: s.msgs.append(a[0] if a else k) or asyncio.sleep(0))})()
inter5.followup.msgs = []
loop.run_until_complete(StaffReviewView()._review(inter5, 'reject'))
data = json.load(open('data/staff_apps.json', encoding='utf-8'))
check(data['42']['status'] == 'rejected'
      and g5._members[42].added == [],
      'отклонение: роль не выдаётся')

# ── 5. Панель: одобрение в «Заявках в команду» ──────────────────────
print('== Панель: одобрение заявки ==')
bg_loop = asyncio.new_event_loop()
threading.Thread(target=bg_loop.run_forever, daemon=True).start()

import web.app as A

apps['42'] = dict(apps['42'], status='pending')
with open('data/staff_apps.json', 'w', encoding='utf-8') as f:
    json.dump(apps, f, ensure_ascii=False)

g6 = FakeGuild([FakeRole(10, 'Хелпер'), FakeRole(20, 'Модератор')], {42: FakeMember(42)})


class FakeBot:
    def __init__(self, guild, loop_):
        self.guilds = [guild]
        self.loop = loop_
        self.user = FakeUser()

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None

    async def fetch_user(self, uid):
        u = FakeUser()
        u.send = lambda *a, **k: asyncio.sleep(0)
        return u


A.bot_instance = FakeBot(g6, bg_loop)
A.MAIN_GUILD_ID = '777'
c = A.app.test_client()
with c.session_transaction() as s:
    s.update(logged_in=True, role='mod', username='tester')

r = c.post('/api/staff-apps/42/review', json={'action': 'approve', 'note': 'ок'})
d = r.get_json() or {}
check(r.status_code == 200 and d.get('role_assigned') == 'Хелпер',
      f'панель: одобрена, выдана «Хелпер» → {d.get("role_assigned")}')
check(g6._members[42].added == ['Хелпер'], 'панель: роль реально добавлена участнику')
check(d.get('dm_sent') is True, 'панель: ЛС заявителю ушло')
data = json.load(open('data/staff_apps.json', encoding='utf-8'))
check(data['42']['status'] == 'approved', 'панель: статус в базе обновлён')

# роль не найдена — панель отвечает по-человечески
apps['42'] = dict(apps['42'], status='pending')
apps['43'] = dict(apps['42'], user_id='43', role='Модератор')
with open('data/staff_apps.json', 'w', encoding='utf-8') as f:
    json.dump(apps, f, ensure_ascii=False)
A.bot_instance = FakeBot(FakeGuild([], {43: FakeMember(43)}), bg_loop)
r = c.post('/api/staff-apps/43/review', json={'action': 'approve'})
d = r.get_json() or {}
check(not d.get('role_assigned') and 'модератор' in str(d.get('role_note', '')).lower(),
      f'панель без роли: подсказка вместо «no_mapped_role» → {d.get("role_note")}')

bg_loop.call_soon_threadsafe(bg_loop.stop)
loop.close()

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
