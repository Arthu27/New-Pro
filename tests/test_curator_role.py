# -*- coding: utf-8 -*-
"""Роль «Куратор» — везде: лестница ролей, маппинг Discord-ролей,
доступ к меню, видимость уведомлений, страницы настройки и база знаний ИИ.

Куратор — старший модератор (между модератором и администратором):
видит всё модерское + тикеты/сообщество, настраивается владельцем так же,
как модератор и администратор.

Запуск: python3 tests/test_curator_role.py
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_curator_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


print('== 1. Лестница ролей и подписи ==')
import web.app as wa  # noqa: E402

ROLES = wa.ROLES
check(ROLES.get('uye', 0) < ROLES['mod'] < ROLES['curator'] < ROLES['admin'] < ROLES['owner'],
      f'лестница ролей uye<mod<curator<admin<owner ({ROLES})')
check(wa.ROLE_LABELS.get('curator') == 'Куратор'
      and wa.ROLE_LABELS.get('mod') == 'Модератор'
      and wa.ROLE_LABELS.get('admin') == 'Администратор'
      and wa.ROLE_LABELS.get('owner') == 'Владелец'
      and wa.ROLE_LABELS.get('uye') == 'Участник',
      'русские подписи всех ролей (Куратор на месте)')


print('== 2. Маппинг Discord-ролей → роль панели ==')
class FakeRole:
    def __init__(self, rid):
        self.id = rid
        self.name = f'role-{rid}'


class FakePerms:
    administrator = False
    ban_members = False
    kick_members = False
    manage_guild = False
    manage_messages = False
    manage_channels = False


class FakeMember:
    def __init__(self, roles, admin=False):
        self.roles = [FakeRole(r) for r in roles]
        self.guild_permissions = FakePerms()
        self.guild_permissions.administrator = admin


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Куратор-тест'
        self.icon = None
        self.member_count = 1
        self.members = []
        self.channels = []
        self.text_channels = []
        self.roles = []

    def get_member(self, _id):
        return None

    def get_channel(self, _id):
        return None

    def get_role(self, _id):
        return None


class FakeBot:
    def __init__(self):
        self.guilds = [FakeGuild(1)]
        self.latency = 0.01
        self.users = []

    def is_closed(self):
        return False

    def is_ready(self):
        return True

    def get_guild(self, _id):
        for g in self.guilds:
            if str(g.id) == str(_id):
                return g
        return None

    def get_user(self, _id):
        return None


_saved_bot = wa.bot_instance
_saved_map = dict(wa.DISCORD_ROLE_MAP)
_saved_gid = wa.MAIN_GUILD_ID
try:
    wa.set_bot_instance(FakeBot())
    wa.MAIN_GUILD_ID = '1'

    wa.DISCORD_ROLE_MAP = {'55': 'curator', '66': 'admin', '77': 'mod'}
    check(wa._get_role_from_discord('999') == 'uye',
          'без маппинга — участник (uye)')

    def _member_with(roles, admin=False):
        m = FakeMember(roles, admin=admin)
        wa._resolve_guild_member = lambda guild, uid: m
        return m

    _member_with(['55', '77'])
    check(wa._get_role_from_discord('999') == 'curator',
          'роль, привязанная к curator, даёт панель куратора')

    _member_with(['77', '66'])
    check(wa._get_role_from_discord('999') == 'admin',
          'при curator+admin выше — admin')

    _member_with(['77'])
    check(wa._get_role_from_discord('999') == 'mod',
          'привязанная mod-роль даёт модератора')

    _member_with([], admin=True)
    check(wa._get_role_from_discord('999') == 'admin',
          'права администратора Discord — admin')
finally:
    wa.bot_instance = _saved_bot
    wa.DISCORD_ROLE_MAP = _saved_map
    wa.MAIN_GUILD_ID = _saved_gid


print('== 3. API ролей и меню ==')
app = wa.app


def make_client(role):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'CUR'
        s['role'] = role
        s['_role_checked'] = time.time()
    return c


# 3.1 /api/role-map принимает curator
c = make_client('admin')
r = c.post('/api/role-map', json={'role_id': '424242', 'panel_role': 'curator'})
check(r.status_code == 200 and r.get_json().get('success')
      and wa.DISCORD_ROLE_MAP.get('424242') == 'curator',
      'POST /api/role-map принимает panel_role=curator')
r = c.post('/api/role-map', json={'role_id': '424242', 'panel_role': 'куратор'})
check(r.status_code == 400, 'неизвестная роль — 400 (только латинские ключи)')
r = c.delete('/api/role-map/424242')
check(r.status_code == 200 and '424242' not in wa.DISCORD_ROLE_MAP,
      'сопоставление куратора удаляется через DELETE')

# 3.2 /api/panel-menu: куратор — настраиваемая панель
c = make_client('owner')
r = c.get('/api/panel-menu')
d = r.get_json(silent=True)
check(r.status_code == 200 and d and 'curator' in (d.get('configurable') or []),
      'куратор в списке настраиваемых панелей')
r = c.post('/api/panel-menu', json={'role': 'curator',
                                    'groups': ['main', 'mod'],
                                    'items': ['/', '/warnings']})
check(r.status_code == 200 and r.get_json().get('success'),
      'владелец сохраняет конфигурацию панели куратора')
r = c.post('/api/panel-menu', json={'role': 'boss',
                                    'groups': [], 'items': []})
check(r.status_code == 400, 'неизвестная панель — 400')

# 3.3 Видимость уведомлений: min-роль «куратор»
c = make_client('owner')
r = c.post('/api/panel/visibility', json={'notifications_min_role': 'curator',
                                          'activity_min_role': 'curator'})
check(r.status_code == 200
      and r.get_json()['visibility']['notifications_min_role'] == 'curator',
      'владелец ставит видимость уведомлений «кураторы и выше»')

c = make_client('mod')
r = c.get('/')
body = r.get_data(as_text=True)
check(r.status_code == 200 and 'id="notifBtn"' not in body,
      'модератор: уведомления скрыты при min-роли curator')

c = make_client('curator')
r = c.get('/')
body = r.get_data(as_text=True)
check(r.status_code == 200 and 'id="notifBtn"' in body,
      'куратор: уведомления видны при min-роли curator')

# вернуть дефолт
c = make_client('owner')
c.post('/api/panel/visibility', json={'notifications_min_role': 'mod',
                                      'activity_min_role': 'mod'})


print('== 4. Страницы и шаблоны ==')
# 4.1 Доступ к страницам по уровню
c = make_client('curator')
r = c.get('/warnings')
check(r.status_code == 200, 'куратор открывает модерскую страницу /warnings')
c = make_client('curator')
r = c.get('/panel-access')
check(r.status_code == 302, 'куратор НЕ открывает /panel-access (только admin+)')

# 4.2 Шапка: русская подпись роли + штабное меню
c = make_client('curator')
r = c.get('/')
body = r.get_data(as_text=True)
check(r.status_code == 200 and 'Куратор' in body,
      'в шапке панели куратора показана подпись «Куратор»')
check('nav-group' in body, 'куратор видит штабное меню (сайдбар)')

# 4.3 Шаблон «Панели и роли»: куратор в легенде/опциях/статистике
c = make_client('owner')
r = c.get('/panel-access')
pa = r.get_data(as_text=True)
check('p-curator' in pa and 'fa-graduation-cap' in pa
      and 'Куратор' in pa, 'страница «Панели и роли» знает куратора')
check(pa.count('value="curator"') >= 2,
      'оба селекта видимости предлагают «Кураторы и выше»')
check('cnt-curator' in pa and "v:'curator'" in pa,
      'статистика и опции маппинга включают куратора')

# 4.4 Шаблон «Меню панели»: вкладка Куратора
r = c.get('/panel-menu')
pm = r.get_data(as_text=True)
check('tab-curator' in pm and "selectPanel('curator')" in pm,
      'страница «Меню панели» имеет вкладку «Куратор»')


print('== 5. База знаний ИИ ==')
from web.ai_knowledge import (build_panel_knowledge, build_panel_faq,  # noqa: E402
                              ROLE_LABELS, ROLE_ORDER)
kb = build_panel_knowledge()
check('Куратор' in kb and 'curator' in kb
      and '/warnings' in kb and '/panel-access' in kb and '/panel-menu' in kb,
      'справка ИИ описывает куратора и страницы настройки')
check(ROLE_ORDER == ('uye', 'mod', 'curator', 'admin', 'owner'),
      'порядок ролей в справке ИИ правильный')
faq = build_panel_faq()
check('Куратор' in faq and 'Панели и роли' in faq and 'Меню панели' in faq,
      'человекочитаемая справка упоминает куратора и страницы настройки')
kb_compact = build_panel_knowledge(compact=True, full_menu=False)
check('Куратор' in kb_compact and 'РАЗДЕЛЫ' in kb_compact,
      'компактная справка для чата тоже знает куратора')

from web.ai_helper import _bot_knowledge_base  # noqa: E402
base = _bot_knowledge_base()
check('curator' in base and 'Куратор' in base,
      'база знаний тикет-ИИ дополнена панелью и куратором')


print('== 6. Меню куратора по умолчанию ==')
# сбросить конфиг, сохранённый проверкой 3.2 (тест пишет в свой tmp-каталог)
_pmf = 'data/panel_menu.json'
if os.path.exists(_pmf):
    os.remove(_pmf)
from services.panel_menu import panel_groups_for, DEFAULT_GROUPS  # noqa: E402
cg = DEFAULT_GROUPS.get('curator') or []
check('tickets' in cg and 'community' in cg and 'mod' in cg,
      f'дефолт куратора: модерация + тикеты + сообщество ({cg})')
visible = panel_groups_for('curator')
keys = [g['key'] for g in visible]
check(set(['main', 'mod', 'members', 'tickets', 'community', 'logs', 'ai']) <= set(keys),
      'куратор видит все свои дефолтные группы')
mod_paths = [p['path'] for g in visible for p in g['pages'] if g['key'] == 'mod']
check('/bulk-actions' not in mod_paths and '/tagjail' not in mod_paths,
      'админские страницы в мод-группе скрыты от куратора (403 не светится в меню)')

c = make_client('curator')
for path in ('/ai-tickets', '/reports-queue', '/warnings'):
    r = c.get(path)
    check(r.status_code == 200, f'куратор открывает {path}')
r = c.get('/panel-menu')
check(r.status_code == 302, 'куратор НЕ открывает /panel-menu (настройка — только владелец)')


print('== 7. Демо-ветка /api/role-map ==')
_saved_demo = os.environ.get('DEMO_MODE')
_saved_bot2 = wa.bot_instance
try:
    os.environ['DEMO_MODE'] = '1'
    wa.set_bot_instance(None)
    c = make_client('admin')
    r = c.get('/api/role-map')
    d = r.get_json(silent=True)
    names = [g.get('name') for g in (d or {}).get('guild_roles', [])]
    check(r.status_code == 200 and 'Куратор' in names,
          'демо-список ролей сервера включает Куратора')
    check((d or {}).get('role_map', {}).get('9013') == 'curator',
          'демо-маппинг привязывает роль 9013 к куратору')
finally:
    wa.set_bot_instance(_saved_bot2)
    if _saved_demo is None:
        os.environ.pop('DEMO_MODE', None)
    else:
        os.environ['DEMO_MODE'] = _saved_demo


print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
