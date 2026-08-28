# -*- coding: utf-8 -*-
"""Журнал панели: человеческие ярлыки действий.

/api/panel-logs обогащает записи меткой/иконкой/ссылкой из _ACTION_MAP
(«POST /api/…/appeals/resolve» → «Решение по апелляции»), сырой путь
остаётся рядом; страница журнала показывает метку жирным + быструю ссылку.

Запуск: python3 tests/test_panel_logs_humanize.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_plog_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'

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


appmod = importlib.import_module('web.app')

print('== 1. словарь действий ==')
label, icon, link = appmod._human_panel_action(
    'POST /api/guild/777/appeals/resolve')
check(label == 'Решение по апелляции' and icon == 'fa-scale-balanced'
      and link == '/appeals', f'апелляция: {label} / {icon} / {link}')
label, icon, link = appmod._human_panel_action(
    'POST /api/guild/777/mod-schedule/create')
check('Запланировали наказание' == label and link == '/mod-schedule',
      'отложенное наказание НЕ принимает за расписание анонсов')
label, icon, _ = appmod._human_panel_action('POST /api/guild/777/schedule/ban')
check(label == 'Расписание анонсов', 'базовые расписания на месте')
label, icon, link = appmod._human_panel_action('POST /api/guild/777/punish')
check(label == 'Наказание из панели', 'форма наказания карточки')
label, icon, _ = appmod._human_panel_action('POST /api/neym/lodku')
check(label.startswith('Изменили:') and icon == 'fa-sliders',
      'неизвестный путь — честный фолбэк с последним сегментом')

print('== 2. API обогащает записи ==')
json.dump([
    {'time': '28.08 12:00', 'user': 'owner', 'role': 'owner',
     'ip': '127.0.0.1', 'action': 'POST /api/guild/777/appeals/claim'},
    {'time': '28.08 12:01', 'user': 'owner', 'role': 'owner',
     'ip': '127.0.0.1', 'action': 'report_new', 'broadcast': True},
], open('data/panel_logs.json', 'w', encoding='utf-8'))

client = appmod.app.test_client()
with client.session_transaction() as sess:
    sess['logged_in'] = True
    sess['username'] = 'CQ-a.png'
    sess['role'] = 'owner'
rows = client.get('/api/panel-logs').get_json()
check(isinstance(rows, list) and len(rows) == 2, 'журнал отдан')
hit = [r for r in rows if r.get('action', '').endswith('appeals/claim')]
check(bool(hit) and hit[0].get('label') == 'Взяли апелляцию в работу'
      and hit[0].get('icon') and hit[0].get('link') == '/appeals',
      'запись обогащена ярлыком/иконкой/ссылкой')
rows2 = client.get('/api/panel-logs').get_json()
raw = [r for r in rows2 if r.get('action') == 'report_new']
check(bool(raw) and not raw[0].get('label'),
      'broadcast-записи не трогаем')

print('== 3. шаблон журнала ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'panel_logs.html'),
           encoding='utf-8').read()
check('l.label || l.action' in tpl, 'метка жирным, сырой путь рядом')
check("fa-arrow-right" in tpl and 'l.link' in tpl, 'быстрая ссылка на раздел')
check('l.icon ||' in tpl, 'иконка действия из словаря')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
