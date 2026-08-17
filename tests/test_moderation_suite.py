# -*- coding: utf-8 -*-
"""PRO-навигация всех 18 страниц модерации.

Проверяет структуру workflow, ролевую фильтрацию, общий UI на каждой странице
и целостность отдельных CSS/JS-ресурсов.

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
check(len(raw_pages) == 18, f'в полном центре ровно 18 инструментов ({len(raw_pages)})')
check(len({page['path'] for page in raw_pages}) == 18, 'URL всех инструментов уникальны')
required = {'path', 'label', 'icon', 'section', 'description', 'access', 'tone'}
missing = [(page.get('path'), sorted(required - set(page))) for page in raw_pages
           if not required <= set(page)]
check(not missing, f'у каждой страницы есть PRO-метаданные ({missing or "полный комплект"})')
check(all(page['icon'].startswith('fa-') for page in raw_pages), 'только Font Awesome, без декоративных эмодзи')
check({page['section'] for page in raw_pages} ==
      {section['key'] for section in pm.MODERATION_SECTIONS},
      'каждый инструмент входит в известный рабочий раздел')

profiles = pm.MODERATION_PAGE_PROFILES
check(set(profiles) == {page['path'] for page in raw_pages},
      'индивидуальный профиль существует у каждой из 18 комнат')
profile_required = {'code', 'accent', 'name', 'headline', 'mission', 'features'}
check(all(profile_required <= set(profile) for profile in profiles.values()),
      'все профили содержат полный визуальный и смысловой контракт')
check(len({profile['code'] for profile in profiles.values()}) == 18 and
      len({profile['name'] for profile in profiles.values()}) == 18,
      'коды и продуктовые имена всех комнат уникальны')
check(all(len(profile['features']) == 3 for profile in profiles.values()),
      'у каждой комнаты ровно три собственные опорные возможности')
check([pm.moderation_profile_for(page['path'])['position'] for page in raw_pages] == list(range(1, 19)),
      'профили знают точную позицию в маршруте 01–18')

admin_group = next(group for group in pm.panel_groups_for('admin') if group['key'] == 'mod')
section_counts = [len(section['pages']) for section in admin_group['sections']]
check(section_counts == [6, 4, 4, 4], f'workflow разбит 6/4/4/4 ({section_counts})')
check([section['key'] for section in admin_group['sections']] ==
      ['response', 'investigation', 'protection', 'management'],
      'порядок: операции -> инциденты -> защита -> контроль')

print('== 2. Роли: ни одной ссылки, ведущей в гарантированный 403 ==')
mod_group = next(group for group in pm.panel_groups_for('mod') if group['key'] == 'mod')
mod_paths = {page['path'] for page in mod_group['pages']}
admin_only = {'/bulk-actions', '/tagjail', '/antiraid'}
check(len(mod_group['pages']) == 15, f'модератор видит 15 доступных инструментов ({len(mod_group["pages"])})')
check(not (mod_paths & admin_only), 'админские операции скрыты от роли mod')
check(admin_only <= {page['path'] for page in admin_group['pages']},
      'администратор видит все рискованные операции')
owner_group = next(group for group in pm.panel_groups_for('owner') if group['key'] == 'mod')
check(len(owner_group['pages']) == 18, 'owner видит полный набор из 18 инструментов')

print('== 3. Общий UI подключён ко всем страницам ==')
base_path = os.path.join(ROOT, 'web', 'templates', 'base.html')
base = open(base_path, encoding='utf-8').read()
for marker, label in [
    ('moderation-suite.css?v=3', 'новая версия shell без старого browser-cache'),
    ('moderation-rooms.css?v=3', 'полная дизайн-система 18 новых рабочих комнат'),
    ('moderation-suite.js?v=2', 'отдельный JS-контроллер без старого browser-cache'),
    ('data-mod-suite', 'контекстная панель'),
    ('mod-command-room', 'полноценная командная комната'),
    ('data-mod-workspace', 'единая рабочая поверхность'),
    ('mod-command-features', 'индивидуальные возможности страницы'),
    ('mod-command-rail', 'маршрут четырёх контуров'),
    ('data-mod-enter', 'переход к рабочей области'),
    ('data-mod-overlay', 'полноэкранный центр'),
    ('data-mod-search', 'поиск инструментов'),
    ('data-mod-prev', 'переход назад'),
    ('data-mod-next', 'переход вперёд'),
    ('grp.sections', 'вложенные секции sidebar'),
]:
    check(marker in base, f'base.html содержит: {label}')

css_path = os.path.join(ROOT, 'web', 'static', 'moderation-suite.css')
rooms_css_path = os.path.join(ROOT, 'web', 'static', 'moderation-rooms.css')
js_path = os.path.join(ROOT, 'web', 'static', 'moderation-suite.js')
check(os.path.isfile(css_path) and os.path.isfile(rooms_css_path) and os.path.isfile(js_path),
      'shell CSS, room CSS и JS существуют')
css = open(css_path, encoding='utf-8').read()
rooms_css = open(rooms_css_path, encoding='utf-8').read()
js = open(js_path, encoding='utf-8').read()
check(css.count('{') == css.count('}') and css.count('{') >= 100,
      f'CSS целый и содержательный ({css.count("{")} блоков)')
for marker in ('.nav-subgroup', '.mod-suite-bar', '.mod-suite-dialog',
               '.mod-suite-grid', '.mod-command-room', '.mod-command-rail',
               '.mod-page-workspace', '[data-mod-accent="crimson"]',
               '@media (max-width:760px)', 'prefers-reduced-motion'):
    check(marker in css, f'CSS содержит {marker}')
check(rooms_css.count('{') == rooms_css.count('}') and rooms_css.count('{') >= 250,
      f'дизайн-система комнат целая и глубокая ({rooms_css.count("{")} блоков)')
for marker in ('.ops-caseboard', '.ops-time-control', '.ops-field-kit',
               '.ops-bulk-command', '.ops-lockdown-core', '.ops-tag-isolation',
               '.ops-evidence-stream', '.ops-decision-timeline', '.ops-proof-vault',
               '.ops-review-chamber', '.ops-security-radar', '.ops-content-shield',
               '.ops-raid-sentinel', '.ops-identity-guard', '.ops-team-desk',
               '.ops-performance-brief', '.ops-risk-intelligence',
               '.ops-escalation-map', '[data-theme="light"]',
               '@media (max-width:720px)', 'prefers-reduced-motion'):
    check(marker in rooms_css, f'room CSS содержит {marker}')
for marker in ('Alt+M', 'RECENT_KEY', 'filterCards', 'focusable',
               'data-mod-section', 'sidebarSearch', 'enterWorkspace',
               'prefers-reduced-motion: reduce'):
    check(marker in js, f'JS содержит {marker}')

room_templates = {
    '/warnings': 'warnings', '/temp-moderation': 'temp_moderation',
    '/mod-tools': 'mod_tools', '/bulk-actions': 'bulk_actions',
    '/lockdown': 'lockdown', '/tagjail': 'tagjail', '/logs': 'logs',
    '/mod-history': 'modhistory', '/proofs': 'proofs', '/appeals': 'appeals',
    '/security': 'security', '/autofilter': 'autofilter',
    '/antiraid': 'antiraid', '/antifake': 'antifake',
    '/mod-control': 'mod_control', '/mod-report': 'mod_report',
    '/mod-insights': 'mod_insights', '/ladder': 'ladder',
}
room_kinds = []
legacy_surfaces = ('page-hero', 'pw-card', 'ba-card', 'tj-box', 'logs-box',
                   'mh-box', 'ap-panel', 'sc-panel', 'mc-panel', 'mr-panel',
                   'mi-panel')
for page in raw_pages:
    source = open(os.path.join(ROOT, 'web', 'templates', room_templates[page['path']] + '.html'),
                  encoding='utf-8').read()
    visible = source.split('<script>', 1)[0]
    match = re.search(r'data-room-kind="([^"]+)"', visible)
    if match:
        room_kinds.append(match.group(1))
    check('data-room-version="3"' in visible and not any(old in visible for old in legacy_surfaces),
          f'{page["path"]}: старая рабочая поверхность удалена полностью')
check(len(room_kinds) == 18 and len(set(room_kinds)) == 18,
      'все 18 шаблонов имеют собственную уникальную композицию')

node = subprocess.run(['node', '--check', js_path], capture_output=True, text=True, timeout=30)
check(node.returncode == 0, f'JS проходит node --check ({node.stderr.strip() or "OK"})')

print('== 4. Рендер всех 18 страниц ==')
import web.app as wa  # noqa: E402

client = wa.app.test_client()


def login(role):
    with client.session_transaction() as session:
        session.clear()
        session['logged_in'] = True
        session['username'] = 'SuiteTester'
        session['role'] = role


login('owner')
rendered = 0
for page in raw_pages:
    response = client.get(page['path'])
    html = response.get_data(as_text=True)
    profile = pm.moderation_profile_for(page['path'])
    ok = (response.status_code == 200
          and f'data-current-path="{page["path"]}"' in html
          and 'class="mod-suite-bar mod-command-room"' in html
          and f'data-mod-profile="{profile["code"]}"' in html
          and f'data-mod-workspace="{profile["code"]}"' in html
          and f'data-mod-accent="{profile["accent"]}"' in html
          and profile['headline'] in html
          and 'data-room-version="3"' in html
          and f'data-room-kind="{room_kinds[raw_pages.index(page)]}"' in html
          and 'moderation-rooms.css?v=3' in html
          and len(re.findall(r'<a[^>]+data-mod-card(?:\s|=)', html)) == 18)
    if ok:
        rendered += 1
    check(ok, f'{page["path"]}: уникальная комната {profile["code"]} и 18 карточек')
check(rendered == 18, 'все 18 страниц получили единый PRO-интерфейс')

login('mod')
response = client.get('/logs')
html = response.get_data(as_text=True)
check(response.status_code == 200, 'роль mod открывает журнал')
check(len(re.findall(r'<a[^>]+data-mod-card(?:\s|=)', html)) == 15,
      'навигатор роли mod содержит только 15 доступных карточек')
check('data-mod-card-path="/bulk-actions"' not in html
      and 'data-mod-card-path="/tagjail"' not in html
      and 'data-mod-card-path="/antiraid"' not in html,
      'в мод-навигатор не протекли админские ссылки')
check(client.get('/bulk-actions').status_code == 403,
      'серверная защита /bulk-actions по-прежнему действует')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
