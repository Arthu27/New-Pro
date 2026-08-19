# -*- coding: utf-8 -*-
"""Навигация раздела модерации панели (Light Edition).

Проверяет структуру 18 инструментов, ролевую фильтрацию, новый светлый
каркас страниц и целостность общего клиентского кита (app.js).

Запуск: python3 tests/test_moderation_suite.py
"""
import os
import re
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_mod_suite_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['PANEL_PASSWORD'] = 'ModSuiteTest!2026'
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


print('== 1. Карта 18 инструментов ==')
from services import panel_menu as pm  # noqa: E402

raw_group = next(group for group in pm.MENU if group['key'] == 'mod')
raw_pages = raw_group['pages']
check(len(raw_pages) == 19, f'в разделе модерации ровно 19 инструментов ({len(raw_pages)})')
check(len({page['path'] for page in raw_pages}) == 19, 'URL всех инструментов уникальны')
required = {'path', 'label', 'icon', 'section', 'description', 'access', 'tone'}
missing = [(page.get('path'), sorted(required - set(page))) for page in raw_pages
           if not required <= set(page)]
check(not missing, f'у каждой страницы есть полные метаданные ({missing or "полный комплект"})')
check(all(page['icon'].startswith('fa-') for page in raw_pages),
      'только Font Awesome, без декоративных эмодзи')
check({page['section'] for page in raw_pages} ==
      {section['key'] for section in pm.MODERATION_SECTIONS},
      'каждый инструмент входит в известный рабочий раздел')

sections = {s['key']: s for s in pm.MODERATION_SECTIONS}
check([s['key'] for s in pm.MODERATION_SECTIONS] ==
      ['response', 'investigation', 'protection', 'management'],
      'порядок: реагирование -> расследование -> защита -> команда')
check(all(sections[k]['label'] and sections[k]['short'] and sections[k]['icon'].startswith('fa-')
          for k in sections), 'у всех разделов есть имя, короткое имя и иконка')
check(not any(re.search(r'[A-Z]{2,}', page['label'] + page['description'])
              for page in raw_pages),
      'заголовки и описания — без латинских аббревиатур, только русский')
check(all(not re.search(r'\b(RSP|INV|PRT|MGT|MODERATION OS|CASE SIGNAL|TIME CONTROL)\b',
                        page['label'] + page['description'], re.I)
          for page in raw_pages),
      'старая «Moderation OS» с кодами комнат полностью удалена из метаданных')
check(not hasattr(pm, 'MODERATION_PAGE_PROFILES') and not hasattr(pm, 'MODERATION_QUICK_ACTIONS'),
      'старые профили комнат и quick-actions удалены из сервиса')
check(not hasattr(pm, 'moderation_profile_for'),
      'старый moderation_profile_for удалён из сервиса')

admin_group = next(group for group in pm.panel_groups_for('admin') if group['key'] == 'mod')
section_counts = [len(section['pages']) for section in admin_group['sections']]
check(section_counts == [7, 4, 4, 4], f'workflow разбит 7/4/4/4 ({section_counts})')
check([section['key'] for section in admin_group['sections']] ==
      ['response', 'investigation', 'protection', 'management'],
      'подгруппы сайдбара следуют рабочему сценарию')

print('== 2. Роли: ни одной ссылки, ведущей в гарантированный 403 ==')
mod_group = next(group for group in pm.panel_groups_for('mod') if group['key'] == 'mod')
mod_paths = {page['path'] for page in mod_group['pages']}
admin_only = {'/bulk-actions', '/tagjail', '/antiraid'}
check(len(mod_group['pages']) == 16, f'модератор видит 16 доступных инструментов ({len(mod_group["pages"])})')
check(not (mod_paths & admin_only), 'админские операции скрыты от роли mod')
check(admin_only <= {page['path'] for page in admin_group['pages']},
      'администратор видит все рискованные операции')
owner_group = next(group for group in pm.panel_groups_for('owner') if group['key'] == 'mod')
check(len(owner_group['pages']) == 19, 'owner видит полный набор из 19 инструментов')

print('== 3. Общий каркас: светлый shell + единый кит ==')
base_path = os.path.join(ROOT, 'web', 'templates', 'base.html')
base = open(base_path, encoding='utf-8').read()
for marker, label in [
    ('class="app-shell"', 'единая оболочка приложения'),
    ('class="sidebar"', 'сайдбар навигации'),
    ('id="sidebarSearch"', 'фильтр меню'),
    ('grp.sections', 'вложенные подгруппы раздела модерации'),
    ('id="palette-data"', 'данные палитры Ctrl+K'),
    ('/static/app.js', 'единый клиентский кит'),
    ('/static/style.css', 'дизайн-система'),
    ('id="main-content"', 'цель keyboard-навигации'),
    ('class="skip-link"', 'skip-link к содержимому'),
    ('data-theme="light"', 'светлая тема по умолчанию'),
]:
    check(marker in base, f'base.html содержит: {label}')
for dead in ('moderation-suite.css', 'moderation-rooms.css', 'quality-suite.css',
             'polish.css', 'moderation-suite.js', 'moderation-rooms.js',
             'quality-suite.js', 'ux-kit.js', 'welcomeScreen', 'mod-suite',
             'MODERATION OS', 'bg-ambient'):
    check(dead not in base, f'старый ассет/элемент удалён из base.html: {dead}')

css_path = os.path.join(ROOT, 'web', 'static', 'style.css')
js_path = os.path.join(ROOT, 'web', 'static', 'app.js')
check(os.path.isfile(css_path) and os.path.isfile(js_path),
      'дизайн-система и клиентский кит существуют')
css = open(css_path, encoding='utf-8').read()
js = open(js_path, encoding='utf-8').read()
check(css.count('{') == css.count('}') and css.count('{') >= 200,
      f'CSS целый и содержательный ({css.count("{{")} блоков)')
for marker in ('.nav-subgroup', '.page-head', '.kpi', '.panel', '.data-table',
               '.kbd-palette', '.drawer', '.toolbar', '.chip',
               'prefers-reduced-motion'):
    check(marker in css, f'CSS содержит {marker}')
for dead in ('.ops-canvas', '.mod-suite', '.ops-room-label', '.tm-tab',
             '.mod-command-room', '.ops-time-control'):
    check(dead not in css, f'старый терминальный стиль удалён из CSS: {dead}')
for marker in ('fetchCachedJSON', 'setLiveRefresh', 'showToast', 'confirmAction',
               'drawDonut', 'paletteOpen', 'uxUndo', 'qualitySetLoading'):
    check(marker in js, f'app.js реализует {marker}')
for dead in ('moderation:live-resume', 'data-room-jump', 'LIVE_KEY', 'DENSITY_KEY'):
    check(dead not in js, f'старый комнатный протокол удалён из JS: {dead}')

print('== 4. Страницы модерации: новая композиция без наследия ==')
room_templates = {
    '/mod-center': 'mod_center',
    '/warnings': 'warnings', '/temp-moderation': 'temp_moderation',
    '/mod-tools': 'mod_tools', '/bulk-actions': 'bulk_actions',
    '/lockdown': 'lockdown', '/tagjail': 'tagjail', '/logs': 'logs',
    '/mod-history': 'modhistory', '/proofs': 'proofs', '/appeals': 'appeals',
    '/security': 'security', '/autofilter': 'autofilter',
    '/antiraid': 'antiraid', '/antifake': 'antifake',
    '/mod-control': 'mod_control', '/mod-report': 'mod_report',
    '/mod-insights': 'mod_insights', '/ladder': 'ladder',
}
legacy_surfaces = ('ops-canvas', 'ops-room-label', 'ops-kicker', 'data-room-kind',
                   'data-room-version', 'mod-suite', 'tm-tab', 'ap-kpi', 'ld-kpi')
for page in raw_pages:
    source = open(os.path.join(ROOT, 'web', 'templates', room_templates[page['path']] + '.html'),
                  encoding='utf-8').read()
    check('class="page-head"' in source and ('<h1>' + page['label']) in source,
          f'{page["path"]}: светлый заголовок страницы с русским названием')
    check(not any(old in source for old in legacy_surfaces),
          f'{page["path"]}: старая рабочая поверхность удалена полностью')
    check('extends "base.html"' in source, f'{page["path"]}: наследует общий каркас')

temp_source = open(os.path.join(ROOT, 'web', 'templates', 'temp_moderation.html'),
                   encoding='utf-8').read()
check('container.dataset.signature' in temp_source
      and 'el.textContent = fmtRem(until)' in temp_source
      and "padStart(2, '0')" in temp_source
      and 'data-until="' in temp_source,
      'live-таймеры фиксированы и не пересобирают экран каждую секунду')
check('window.confirmAction' in temp_source and 'window.showToast' in temp_source,
      'страницы используют единый кит подтверждений и тостов')

node = subprocess.run(['node', '--check', js_path], capture_output=True, text=True, timeout=30)
check(node.returncode == 0,
      f'app.js проходит node --check ({node.stderr.strip() or "OK"})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
os.chdir(ROOT)
for leftover in os.listdir(_TMP):
    pass
import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
