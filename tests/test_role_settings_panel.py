# -*- coding: utf-8 -*-
"""Страница «Роли наказаний» (Настройки → Роли наказаний).

Только интерактивные селекты (ручной ввод ID исключён — требование
владельца): все виды наказаний (мут/войс-мут/«бан») и уровни варнов
warn_1..warn_10 собираются одним POST; чужие/удалённые роли отклоняются;
бот офлайн → бережный отказ сохранения.

Запуск: python3 tests/test_role_settings_panel.py
"""
import importlib
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_rset_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


# ── фейк-бот с ролями сервера ───────────────────────────────────────────
class _Role:
    def __init__(self, rid, name, pos=1, managed=False):
        self.id = rid
        self.name = name
        self.position = pos
        self.managed = managed
        self.color = None

    def is_default(self):
        return self.name == '@everyone'


class _Guild:
    def __init__(self, gid, roles):
        self.id = gid
        self.name = 'Тестовый сервер'
        self.roles = roles


class _Bot:
    def __init__(self, guild):
        self.guilds = [guild]

    def get_guild(self, gid):
        return self.guilds[0] if gid == self.guilds[0].id else None


GUILD = _Guild(777, [
    _Role(777, '@everyone', 0),
    _Role(555001, 'Уровень 1', 5),
    _Role(555003, 'Уровень 3', 8),
    _Role(555010, 'Изолирован', 12),
    _Role(555020, 'запрещён-бот-роль', 9, managed=True),
])

appmod = importlib.import_module('web.app')
appmod.set_bot_instance(_Bot(GUILD))
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


from services import punish_roles as PR  # noqa: E402


print('== 1. страница и доступ ==')
r = client.get('/role-settings')
check(r.status_code in (302, 401), 'гость уходит на логин')
login('mod')
r = client.get('/role-settings')
check(r.status_code in (302, 401, 403), 'модератору страница закрыта (admin+)')
login('owner')
r = client.get('/role-settings')
check(r.status_code == 200, 'админ/владелец заходит')

print('== 2. API: форма как у бота ==')
login('owner')
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('success'), 'успешный ответ')
check([k['key'] for k in d['kinds']] == ['mute', 'vmute', 'ban'],
      'базовые виды: мут, войс-мут, бан')
check(all(k.get('icon', '').startswith('fa-') and k.get('hint')
          for k in d['kinds']), 'у видов иконки и подсказки')
levels = [l['key'] for l in d['levels']]
check(levels == [f'warn_{i}' for i in range(1, 11)],
      'уровни warn_1..warn_10 в порядке роста')
check(all(l['icon'] == 'fa-triangle-exclamation' for l in d['levels']),
      'у уровней своя иконка')
rid = {r['id'] for r in d['roles']}
check('555001' in rid and '555010' in rid and '@everyone' not in [r['name'] for r in d['roles']],
      'список ролей сервера (без @everyone)')
check('555020' not in rid, 'управляемые бот-роли не предлагаем')
check(d['roles_count'] == len(d['roles']) and d['bot_online'], 'бот онлайн')

print('== 3. сохранение ==')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'mute': '555010', 'warn_1': '555001', 'warn_3': '555003', 'ban': '0'}})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), f'сохранение: {d.get("error", "")}')
got = PR.get('777')
check(got.get('mute') == 555010 and got.get('warn_1') == 555001
      and got.get('warn_3') == 555003 and 'ban' not in got,
      'выбор лёг в хранилище (общий с «Настройками модерации»)')

print('== 4. отсев мусора ==')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'mute': '999999999999999999'}})
check(r.status_code == 400 and not r.get_json().get('success'),
      'роль не с этого сервера — 400 и ничего не сохранили')
check(PR.get('777').get('mute') == 555010, 'прошлый выбор не пострадал')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'hack': '555001', 'warn_99': '555003'}})
check(r.status_code == 400, 'неизвестные ключи — 400')
r = client.post('/api/guild/777/role-settings', data='не json',
                content_type='application/json')
check(r.status_code == 400, 'битый JSON — 400')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'warn_2': 'не-id'}})
check(r.status_code == 400, 'не-ID (ручной ввод) — отклонено')
login('mod')
r = client.post('/api/guild/777/role-settings', json={'mapping': {'mute': '555010'}})
check(r.status_code in (302, 401, 403), 'сохраняет только admin+')
login('owner')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'mute': '0', 'warn_1': '0', 'warn_3': '0'}})
check(r.get_json().get('success') and PR.get('777') == {},
      '«не выдавать» по всем — чистое хранилище')

print('== 5. шаблон: никаких ручных ID ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'role_settings.html'),
           encoding='utf-8').read()
check('type="number"' not in tpl and 'type="text"' not in tpl,
      'в шаблоне нет полей ручного ввода — только селекты')
check('/api/guild/' in tpl and '/role-settings' in tpl, 'шаблон ходит в свой API')
check('data-k=' in tpl and 'rs-role-grid' in tpl, 'карточки селектов на месте')
check('breadcrumbs' not in tpl and 'fa-save' in tpl, 'кнопка «Сохранить всё»')

print('== 6. в меню «Настройки» ==')
from services import panel_menu  # noqa: E402
grp = next(g for g in panel_menu.MENU if g['key'] == 'settings')
paths = [p['path'] for p in grp['pages']]
check('/role-settings' in paths, 'страница в категории «Настройки»')
it = next(p for p in grp['pages'] if p['path'] == '/role-settings')
check(it['label'] == 'Роли наказаний' and it['icon'].startswith('fa-'),
      'метка и FA-иконка')
check(len(paths) == len(set(paths)), 'URL-ов дублей нет')

print('== 7. бот офлайн — бережный отказ ==')
appmod.set_bot_instance(None)
ok, err, saved = __import__('web.routes.role_settings_panel',
                            fromlist=['save_settings']).save_settings(
    777, {'mute': '555010'}, who='test')
check(not ok and err and saved is None, f'офлайн: {err}')
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('success') and d['roles'] == [] and not d['bot_online'],
      'офлайн-обзор пуст, но не падает')
appmod.set_bot_instance(_Bot(GUILD))

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
