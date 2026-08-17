# -*- coding: utf-8 -*-
"""Единый стиль категории «Модерация» (modskin).

Вся группа «Модерация» выглядит одним фасом: body.mz-skin +
web/static/modskin.css на каждой странице. Тест держит это в сборе:
файл скина жив, base.html даёт блоки, все шаблоны категории подключены,
страницы реально рендерятся со скином.

Запуск: python3 tests/test_mod_skin.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_modskin_test_')
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


# Страницы группы «Модерация» (menu) + warn-config как инструмент модерации.
SKIN_TEMPLATES = (
    'logs.html', 'temp_moderation.html', 'warnings.html', 'modhistory.html',
    'autofilter.html', 'antiraid.html', 'tagjail.html', 'mod_tools.html',
    'proofs.html', 'bulk_actions.html', 'mod_report.html', 'appeals.html',
    'lockdown.html', 'security.html', 'antifake.html', 'ladder.html',
    'warn_config.html', 'mod_center.html',
)

print('== 1. Файл скина ==')
skin_path = os.path.join(ROOT, 'web/static/modskin.css')
check(os.path.exists(skin_path), 'modskin.css существует')
skin = open(skin_path, encoding='utf-8').read()
check('body.mz-skin' in skin, 'скин скоупится на body.mz-skin')
check(skin.count('body.mz-skin') >= 10, 'переопределений много — стиль цельный')
check('[data-theme="light"]' in skin, 'светлая тема учтена')
emoji = re.compile('[\U0001F000-\U0001FAFF\u2B00-\u2BFF\uFE0F]|[\u2600-\u27BF]')
check(not emoji.search(skin), 'в скине нет эмодзи (только FA-глифы)')

print('== 2. base.html даёт точки подключения ==')
base = open(os.path.join(ROOT, 'web/templates/base.html'), encoding='utf-8').read()
check('{% block head_extra %}' in base, 'блок head_extra в <head>')
check('body_class' in base and '<body class=' in base, 'блок body_class на <body>')

print('== 3. Все шаблоны категории подключены ==')
for t in SKIN_TEMPLATES:
    src = open(os.path.join(ROOT, 'web/templates', t), encoding='utf-8').read()
    ok = ('{% block body_class %}mz-skin{% endblock %}' in src
          and 'modskin.css' in src)
    check(ok, f'{t} носит mz-skin и подключает скин')

print('== 4. Страницы рендерятся со скином ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
for path in ('/mod-center', '/warnings', '/mod-history', '/bulk-actions'):
    r = client.get(path)
    body = r.get_data(as_text=True)
    check(r.status_code == 200 and 'mz-skin' in body and 'modskin.css' in body,
          f'{path} отдаётся со скином')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
