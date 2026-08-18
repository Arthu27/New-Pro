# -*- coding: utf-8 -*-
"""Регрессия индивидуального PRO-прохода страницы «Каналы».

Проверяет master-detail layout, режим одной открытой категории,
клавиатурную доступность, диалоги и сохранность API-контрактов.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_channels_pro_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['PANEL_PASSWORD'] = 'ChannelsProTest!2026'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'channels-pro.db')

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


path = os.path.join(ROOT, 'web', 'templates', 'channels.html')
source = open(path, encoding='utf-8').read()

print('== 1. Индивидуальная рабочая область ==')
for marker, label in [
    ('class="ch-workspace"', 'двухпанельный master-detail workspace'),
    ('id="ch-detail-placeholder"', 'понятное состояние без выбора'),
    ('id="ch-detail-content" hidden', 'карточка только одного выбранного канала'),
    ('Структура сервера', 'контекст списка категорий'),
    ('Выбранный канал', 'контекст индивидуальной карточки'),
    ('@media(max-width:1050px)', 'адаптивное переключение в одну колонку'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 2. Одна категория за раз ==')
for marker, label in [
    ("ch_active_cat_", 'активная категория запоминается для сервера'),
    ("item === group", 'при открытии остальные категории сворачиваются'),
    ("item.classList.toggle('collapsed', !active)", 'аккордеон оставляет один раздел'),
    ('aria-expanded=', 'состояние категории доступно screen reader'),
    ('function channelWord', 'корректные русские счётчики каналов'),
    ("name: 'Вне структуры'", 'потерянные категории не скрывают каналы'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 3. Keyboard UX и диалоги ==')
for marker, label in [
    ('role="dialog" aria-modal="true"', 'семантика модальных окон'),
    ('aria-labelledby="createChannelTitle"', 'имя диалога создания'),
    ('aria-labelledby="editChannelTitle"', 'имя диалога редактирования'),
    ("ev.key !== 'Tab'", 'focus trap в открытом диалоге'),
    ("event.key === 'ArrowDown'", 'переход по каналам стрелками'),
    ('role="button" tabindex="0" aria-selected=', 'клавиатурный выбор канала'),
    ('aria-pressed="true"', 'доступный выбор типа канала'),
    ('qualitySetLoading', 'системное состояние загрузки действий'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 4. API и live-refresh не потеряны ==')
for endpoint in (
    '/api/guild/', '/channels/create', '/channels/', '/update', '/delete',
    '/api/guilds',
):
    check(endpoint in source, f'контракт {endpoint} остаётся в шаблоне')
check('lastFingerprint' in source and "fingerprint === lastFingerprint" in source,
      'live-refresh не перерисовывает неизменившийся DOM')
check("document.querySelector('.modal-overlay.open')" in source,
      'live-refresh не вмешивается в редактирование')

print('== 5. Синтаксис и HTTP-рендер ==')
from jinja2 import Environment  # noqa: E402
try:
    Environment().parse(source)
    jinja_ok = True
except Exception as exc:
    jinja_ok = False
    print('  JINJA:', exc)
check(jinja_ok, 'channels.html проходит Jinja parse')

scripts = re.findall(r'<script>(.*?)</script>', source, re.S)
js = scripts[-1] if scripts else ''
js = re.sub(r'\{\{.*?\}\}', 'TEST_VALUE', js, flags=re.S)
js_path = os.path.join(_TMP, 'channels-inline.js')
open(js_path, 'w', encoding='utf-8').write(js)
node = subprocess.run(['node', '--check', js_path], capture_output=True,
                      text=True, timeout=30)
check(bool(scripts) and node.returncode == 0,
      f'inline JS проходит node --check ({node.stderr.strip() or "OK"})')

import web.app as webapp  # noqa: E402
client = webapp.app.test_client()
with client.session_transaction() as session:
    session['logged_in'] = True
    session['username'] = 'ChannelsTester'
    session['role'] = 'owner'
response = client.get('/channels')
body = response.get_data(as_text=True)
check(response.status_code == 200, '/channels возвращает HTTP 200')
check('class="ch-workspace"' in body and 'id="ch-detail-placeholder"' in body,
      'новая рабочая область присутствует в реальном рендере')
check('app.js' in body and 'style.css' in body, 'страница сохраняет глобальный shell')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
