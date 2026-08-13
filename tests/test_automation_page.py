# -*- coding: utf-8 -*-
"""Тесты страницы «Автоматика»: API настроек, валидация, рендер, меню.

Панель и коги пишут/читают одни и те же нейспейсы GuildData — тест
проверяет это сквозное соглашение и безопасность полей.

Запуск: python3 tests/test_automation_page.py
"""
import ast
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_auto_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


from web.app import app as panel, set_bot_instance  # noqa: E402
from services import panel_menu as pm  # noqa: E402
from db import GuildData  # noqa: E402
from web.routes import automation as au  # noqa: E402


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Demo'


class FakeBot:
    guilds = [FakeGuild(1)]
    latency = 0.01
    users = []

    def is_closed(self):
        return False


set_bot_instance(FakeBot())
client = panel.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'Arthur'
    s['role'] = 'owner'

print('== 1. страница рендерится ==')
r = client.get('/automation')
html = r.get_data(as_text=True)
check(r.status_code == 200, 'GET /automation -> 200')
check('{%' not in html, 'чистый Jinja (нет нерешённых блоков)')
check('/api/automation' in html, 'страница ходит в API настроек')
EMOJI = re.compile('[\U0001F000-\U0001FAFF⺀-⻿\u2B00-\u2BFF\uFE0F]|[☀-➿]')
junk = [l.strip()[:60] for l in html.splitlines() if EMOJI.search(l)]
check(not junk, f'эмодзи на странице нет (FA-иконки вместо них) {junk[:2]}')

print('== 2. API: индекс и сохранение ==')
r = client.get('/api/automation')
data = r.get_json()
check(data['success'] and set(data['modules']) == {'night_mode', 'anti_alt',
                                                   'welcome_pro', 'mod_digest'},
      'индекс отдаёт 4 модуля')
nm = data['modules']['night_mode']
check(nm['values']['enabled'] is False and nm['values']['start_hour'] == 23,
      'дефолты ночного режима на месте')

# сохранение: ночной режим вкл + окно 22-6
r = client.post('/api/automation/night_mode', json={
    'enabled': True, 'start_hour': 22, 'end_hour': 6, 'slowmode_seconds': 10,
    'lock_channels': True, 'report_channel_id': 0})
back = r.get_json()
check(back['success'] and back['values']['enabled'] is True
      and back['values']['start_hour'] == 22, 'POST сохраняет настройки')

# проверка сквозного чтения: то, что сохранила панель, читает ког
from cogs import night_mode as nm_cog  # noqa: E402
gid = 1
got = nm_cog.merge_settings(GuildData('night_mode').get(gid, 'settings', {}))
check(got['enabled'] is True and got['slowmode_seconds'] == 10,
      'ког читает то, что записала панель (общая SQLite-точка)')

print('== 3. валидация: белые списки полей и типы ==')
r = client.post('/api/automation/anti_alt', json={
    'enabled': True, 'min_age_days': 14, 'action': 'kick',
    'log_channel_id': 0, 'hack_key': 'root', 'templates': [1]})
vals = r.get_json()['values']
check('hack_key' not in vals and 'templates' not in vals,
      'чужие ключи отбрасываются')
check(vals['action'] == 'kick' and vals['min_age_days'] == 14, 'разрешённые применены')
r = client.post('/api/automation/anti_alt', json={'action': 'взорвать сервер'})
vals = r.get_json()['values']
check(vals['action'] == 'kick', 'невалидный select игнорируется (остаётся прошлое)')
r = client.post('/api/automation/night_mode', json={'slowmode_seconds': 999999})
check(r.get_json()['values']['slowmode_seconds'] == 21600, 'int зажимается в лимит')

r = client.post('/api/automation/несуществующий', json={'x': 1})
check(r.status_code == 404, 'неизвестный модуль -> 404')
r = client.post('/api/automation/night_mode', data='не json',
                content_type='text/plain')
check(r.status_code == 400, 'не-JSON -> 400')

print('== 4. welcome_pro: список шаблонов из textarea ==')
r = client.post('/api/automation/welcome_pro', json={
    'enabled': True, 'channel_id': 0, 'dm_enabled': False,
    'templates': '{mention} добро пожаловать!\n\n{user} с нами!\n'})
vals = r.get_json()['values']
check(vals['enabled'] is True and '\n' in vals['templates']
      and 'добро пожаловать' in vals['templates'],
      'шаблоны уходят строками и возвращаются textarea-текстом')
from cogs import welcome_pro as wp_cog  # noqa: E402
saved = wp_cog.merge_settings(GuildData('welcome_pro').get(1, 'settings', {}))
check(len(saved['templates']) == 2, 'пустые строки-пустышки вычищены')

print('== 5. меню и карта модулей ==')
paths = {p['path'] for g in pm.MENU for p in g['pages']}
check('/automation' in paths, 'пункт «Автоматика» в меню')
check('/automation' in pm.PAGE_COGS, 'карта PAGE_COGS покрывает страницу')
# в classic-режиме страница не гаснет (её коги загружены)
for k in ('MOD_ONLY', 'DISABLED_COGS', 'EXTRA_COGS'):
    os.environ.pop(k, None)
check('/automation' not in pm.module_off_paths(), 'classic: страница активна')

print('== 6. линт модуля маршрутов ==')
src = open(os.path.join(ROOT, 'web', 'routes', 'automation.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')
facade = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
check(facade.count('automation') == 2, 'automation зарегистрирован в фасаде')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
