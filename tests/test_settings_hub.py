# -*- coding: utf-8 -*-
"""Хаб настроек: группа «Настройки», лэйаут меню, /mod-settings, 14 маршрутов.

Проверяем:
- 14 маршрутов хаба каналов + запись/чтение новых шести адаптеров (считалка,
  зала славы, ночной итог, дайджест модерации, смены, призыв тикетов) —
  через те же файлы и хранилища, что читает бот;
- категорию «Настройки» в меню и её 13 страниц в верном порядке;
- сервис лэйаута меню: валидацию, защиту /panel-menu, скрытие и порядок
  (применяется и к владельцу), API лэйаута с валидацией формата;
- страницу /mod-settings и её API: лестницу авто-наказаний (нормализация,
  клампы, кик без длительности) в формате cogs.ladder и исключения временных
  мер (валидация ID) в data/temp_whitelist.json;
- чистоту шаблонов (без эмодзи, запрещённых цветов и localhost; кнопки с
  type=), русский язык /settings, связные ссылки антикраша и CSS-правило
  против стрелок у числовых полей.

Запуск: python3 tests/test_settings_hub.py
"""
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_settings_hub_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

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


GID = 987654321098765432

# ═══ 1. Хаб каналов: 14 маршрутов, новые адаптеры ════════════════════════
print('== хаб каналов: 20 маршрутов ==')
from services import channel_routes as CHR  # noqa: E402
from web.routes.channel_settings import ADAPTERS  # noqa: E402

keys = [s['key'] for s in CHR.ROUTE_SPECS]
check(len(keys) == 20 and len(set(keys)) == 20,
      f'20 уникальных маршрутов — 17 систем + 3 канала заявок ({len(keys)})')
need = {'ban_appeal_channel',
        'proof_channel', 'appeals_channel', 'welcome_channel', 'tagjail_channel',
        'guardian_channel', 'antiraid_channel', 'security_channel',
        'anticrash_channel', 'counting_channel', 'starboard_channel',
        'night_report_channel', 'mod_digest_channel',
        'staff_helper_channel', 'staff_moderator_channel', 'staff_apply_channel', 'shifts_channel',
        'ticket_notify_channel', 'appeal_menu_channel', 'pagerduty_channel'}
check(set(keys) == need, f'все системы на хабе ({len(need)})')
check(set(ADAPTERS) == set(keys), 'у каждого маршрута есть адаптер')

new_6 = {'counting_channel': 2004, 'starboard_channel': 2003,
         'night_report_channel': 1004, 'mod_digest_channel': 4003,
         'shifts_channel': 4002, 'ticket_notify_channel': 4005}
for k, cid in new_6.items():
    get, set_ = ADAPTERS[k]
    check(set_(GID, cid) and get(GID) == cid, f'{k}: запись/чтение = {cid}')

sb = json.load(open(f'data/starboard_settings_{GID}.json', encoding='utf-8'))
check(sb.get('channel_id') == 2003,
      'зала славы: тот же файл, что читает ког starboard')
ns = json.load(open('data/night_summary.json', encoding='utf-8'))
check((ns.get(str(GID)) or {}).get('channel_id') == 1004,
      'ночной итог: data/night_summary.json (файл кога)')
tn = json.load(open(f'data/ticket_notify_{GID}.json', encoding='utf-8'))
check(tn.get('notify_channel_id') == 4005,
      'призыв тикетов: data/ticket_notify_{gid}.json (файл кога)')

from db import GuildData  # noqa: E402

cnt = GuildData('counting').get(GID, 'state', {}) or {}
check(cnt.get('channel_id') == 2004,
      'считалка: GuildData(counting).state.channel_id')
md = GuildData('mod_digest').get(GID, 'settings', {}) or {}
check(md.get('channel_id') == 4003,
      'дайджест модерации: GuildData(mod_digest).settings.channel_id')

# ═══ 2. Меню: категория «Настройки» ══════════════════════════════════════
print('== меню: категория «Настройки» ==')
from services import panel_menu as PM  # noqa: E402

pages = [p for g in PM.MENU for p in g['pages']]
paths = [p['path'] for p in pages]
check(len(paths) == 124 and len(set(paths)) == 124,
      f'в меню 124 уникальные страницы ({len(paths)})')
groups = {g['key']: g for g in PM.MENU}
check('settings' in groups, 'категория «Настройки» существует')
sg = groups['settings']
check(sg['group'] == 'Настройки' and bool(sg.get('icon')),
      'группа с русским именем и иконкой')
sp = [p['path'] for p in sg['pages']]
want = ['/settings', '/command-switches', '/mod-settings', '/channel-settings',
        '/bot-settings', '/ticket-settings', '/welcome-editor', '/rules-editor',
        '/warn-config', '/automation', '/notifications', '/pagerduty',
        '/theme-settings', '/theme-studio', '/anticrash', '/log-settings']
check(sp == want, f'страницы категории в верном порядке ({len(sp)})')
gkeys = [g['key'] for g in PM.MENU]
check(gkeys.index('settings') == gkeys.index('bot') + 1,
      '«Настройки» сразу после раздела «Бот»')
check(all(p.get('label') and p.get('icon') for p in sg['pages']),
      'у каждой страницы категории русская подпись и иконка')

# ═══ 3. Лэйаут меню: сервис ══════════════════════════════════════════════
print('== лэйаут меню: скрытие и порядок ==')
check(PM.layout_view() == {'hidden_pages': [], 'order': {}, 'group_order': []},
      'по умолчанию лэйаут пуст')

view = PM.save_layout(['/recap', '/panel-menu', '/net-takoy', 42, '/recap'],
                      {'main': ['/bot-stats', '/', '/guilds'],
                       'nope': ['/x'],
                       'mod': ['/warnings', None, '/logs']})
check(view['hidden_pages'] == ['/recap'],
      'скрылась только валидная незащищённая страница')
check(view['order'].get('main') == ['/bot-stats', '/', '/guilds'],
      'свой порядок принят')
check('nope' not in view['order'], 'неизвестный раздел отброшен')
check(view['order'].get('mod') == ['/warnings', '/logs'],
      'мусор внутри порядка отфильтрован')

owner_groups = {g['key']: g for g in PM.panel_groups_for('owner')}
main_paths = [p['path'] for p in owner_groups['main']['pages']]
check('/recap' not in main_paths, 'скрытая страница исчезла даже у владельца')
check(main_paths[:3] == ['/bot-stats', '/', '/guilds'],
      'указанные страницы встали первыми в своём порядке')
check(main_paths[3:] == ['/analytics', '/advanced-analytics',
                         '/server-health', '/ops-center'],
      'остальные страницы остались в исходном порядке (стабильность)')
acc_paths = [p['path'] for p in owner_groups['access']['pages']]
check('/panel-menu' in acc_paths, 'защищённая страница меню скрыться не смогла')

# чистый сброс — дальше по тесту лэйаут должен быть пустым
clean = PM.save_layout([], {})
check(clean == {'hidden_pages': [], 'order': {}, 'group_order': []},
      'лэйаут сброшен до дефолта')
# порядок, совпадающий с исходным, не захламляет файл (UI шлёт полный список)
default_main = [p['path'] for p in groups['main']['pages']]
same = PM.save_layout([], {'main': default_main})
check(same['order'] == {} and 'main' not in same['order'],
      'исходный порядок не сохраняется как «свой»')
again = [p['path'] for g in PM.panel_groups_for('owner')
         for p in g['pages']]
check(again == [p['path'] for g in PM.MENU for p in g['pages']],
      'после сброса меню в точности как MENU')

# ═══ 4. Модуль настроек модерации: нормализация ══════════════════════════
print('== mod-settings: нормализация лестницы и исключений ==')
from web.routes import mod_settings as MS  # noqa: E402

raw = [{'count': 'abc'},                                        # не число
       {'count': 2, 'action': 'mute', 'duration': 30, 'unit': 'minute'},
       {'count': 2, 'action': 'ban', 'duration': 5, 'unit': 'day'},  # дубль
       {'count': 5, 'action': 'yeet'},                          # нет такой меры
       {'count': 7, 'action': 'kick', 'duration': 10, 'unit': 'hour'},
       {'count': 0},                                            # ноль
       {'count': 300, 'action': 'ban', 'duration': 99999, 'unit': 'year'},
       'мусор']                                                 # не словарь
norm = MS.normalize_steps(raw)
check(norm == [{'count': 2, 'action': 'mute', 'duration': 30, 'unit': 'minute'},
               {'count': 5, 'action': 'mute', 'duration': 0, 'unit': 'minute'},
               {'count': 7, 'action': 'kick', 'duration': 0, 'unit': 'hour'},
               {'count': 100, 'action': 'ban', 'duration': 10000,
                'unit': 'minute'}],
      f'клампы, дедуп, сортировка, кик без срока ({len(norm)} ступени)')
big = [{'count': i, 'action': 'mute'} for i in range(1, 40)]
check(len(MS.normalize_steps(big)) == MS.MAX_STEPS,
      f'лимит ступеней ({MS.MAX_STEPS})')
check(MS.temp_whitelist(GID) == [], 'исключения пусты по умолчанию')
saved_wl = MS.save_temp_whitelist(GID, ['823456789012345678',
                                        '823456789012345678', 'bad',
                                        '123', 723456789012345678])
check(saved_wl == ['823456789012345678', '723456789012345678'],
      f'ID проверены и дедуплицированы ({saved_wl})')
check(MS.temp_whitelist(GID) == saved_wl, 'исключения перечитываются из файла')

# ═══ 5. Панель: страницы, доступы, API ═══════════════════════════════════
print('== панель: /mod-settings, /settings, лэйаут API ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'hub-T'
        s['role'] = role


r = client.get('/mod-settings')
check(r.status_code == 200, f'в демо /mod-settings открыта ({r.status_code})')
body = r.get_data(as_text=True)
check('Настройки модерации' in body and 'Лестница авто-наказаний' in body
      and 'Исключения временных мер' in body
      and 'msSaveSteps' in body and 'msSaveWl' in body,
      'страница собрана: лестница + исключения + две кнопки сохранения')
check('/channel-settings' in body and '/guardian' in body,
      'панель связей настроек модерации на месте')
login_as('mod')
r = client.get('/mod-settings')
check(r.status_code == 302, f'настройка модерации — Админ+ ({r.status_code})')
r = client.get(f'/api/guild/{GID}/mod-settings')
check(r.status_code == 403, 'модератор не читает API настроек модерации')
login_as('owner')

r = client.get(f'/api/guild/{GID}/mod-settings')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True
      and isinstance(d.get('cfg'), dict), 'API GET: конфиг отдан')
cfg = d['cfg']
check(cfg.get('max_steps') == MS.MAX_STEPS
      and [a['key'] for a in cfg['actions']] == ['mute', 'kick', 'ban']
      and [u['key'] for u in cfg['units']] == ['minute', 'hour', 'day'],
      'API GET: меры и единицы с русскими подписями')
check(cfg.get('temp_whitelist') == saved_wl,
      'API GET: исключения из того же файла, что читает бот')

bad = client.post(f'/api/guild/{GID}/mod-settings', data='{oops',
                  content_type='application/json')
check(bad.status_code == 400, 'битый JSON отклонён')

ok = client.post(f'/api/guild/{GID}/mod-settings', json={
    'steps': [{'count': 3, 'action': 'mute', 'duration': 15, 'unit': 'minute'},
              {'count': 5, 'action': 'kick'},
              {'count': 8, 'action': 'ban', 'duration': 1, 'unit': 'day'}],
    'temp_whitelist': ['823456789012345678']})
check(ok.status_code == 200 and ok.get_json().get('success') is True,
      f'POST принят ({ok.status_code})')
wc = json.load(open(f'data/warn_config_{GID}.json', encoding='utf-8'))
check(wc.get('steps') == [
        {'count': 3, 'action': 'mute', 'duration': 15, 'unit': 'minute'},
        {'count': 5, 'action': 'kick', 'duration': 0, 'unit': 'minute'},
        {'count': 8, 'action': 'ban', 'duration': 1, 'unit': 'day'}],
      'лестница записалась в файл бота в командном формате')
tw = json.load(open('data/temp_whitelist.json', encoding='utf-8'))
check(tw.get(str(GID)) == ['823456789012345678'],
      'исключения записались в файл бота')
cfg2 = client.get(f'/api/guild/{GID}/mod-settings').get_json()['cfg']
labels = [s['label'] for s in cfg2['steps']]
check(len(cfg2['steps']) == 3
      and labels == ['мут на 15 мин', 'кик', 'бан на 1 дн'],
      f'подписи ступеней — как в команде бота ({labels})')
from cogs import ladder as LD  # noqa: E402
check(cfg2['steps'][0]['label'] == LD._fmt_step(wc['steps'][0]),
      'подпись панели посимвольно совпадает с подписью кога')

# ── Лэйаут через API ──
r = client.get('/api/panel-menu')
d = r.get_json()
check('layout' in d and d['layout'] == {'hidden_pages': [], 'order': {}, 'group_order': []},
      'GET /api/panel-menu отдаёт блок лэйаута')
login_as('mod')
r = client.post('/api/panel-menu/layout', json={'hidden_pages': ['/recap']})
check(r.status_code == 403, f'лэйаут меняет только владелец ({r.status_code})')
login_as('owner')
bad = client.post('/api/panel-menu/layout', json={'hidden_pages': 'нет',
                                                  'order': []})
check(bad.status_code == 400, 'лэйаут с битым форматом отклонён')
ok = client.post('/api/panel-menu/layout',
                 json={'hidden_pages': ['/recap', '/panel-menu'],
                       'order': {'main': ['/bot-stats', '/'],
                                 'hakerstvo': ['/x']}})
lay = ok.get_json().get('layout') or {}
check(ok.status_code == 200 and lay.get('hidden_pages') == ['/recap']
      and lay.get('order', {}).get('main') == ['/bot-stats', '/']
      and 'hakerstvo' not in lay.get('order', {}),
      'лэйаут сохранён с валидацией')
r = client.get('/api/panel-menu')
check(r.get_json()['layout'].get('hidden_pages') == ['/recap'],
      'GET /api/panel-menu видит сохранённый лэйаут')
ok = client.post('/api/panel-menu/layout',
                 json={'hidden_pages': [], 'order': {}})
check(ok.get_json()['layout'] == {'hidden_pages': [], 'order': {}, 'group_order': []},
      'лэйаут сброшен через API')

# ── /settings: русская и связная ──
r = client.get('/settings')
check(r.status_code == 200, f'/settings открыта ({r.status_code})')
body = r.get_data(as_text=True)
check('Статус бота' in body and 'Защита сервера' in body
      and 'Туннель' in body and 'Синхронизировать' in body,
      'карточки настроек сервера на русском')
check('/guardian' in body and '/security' in body,
      'из настроек есть переходы в Щит и Центр безопасности')

# ═══ 6. Шаблоны и CSS: чистота ═══════════════════════════════════════════
print('== шаблоны: аудит чистоты ==')
EMOJI = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FF]')
FORBIDDEN = ('#0a0907', '#1a1a20', '#e2e8f0', '#d4a843', '#2ecc71', '#e74c3c',
             '212,175,55', '#e8c96a', '#d4af37', 'rgba(0,0,0,0.3)',
             '86efac', 'fca5a5', 'a5f3fc')
for name in ('mod_settings.html', 'settings.html'):
    tpl = open(os.path.join(ROOT, 'web', 'templates', name), encoding='utf-8').read()
    check(not EMOJI.search(tpl), f'{name}: без эмодзи')
    check('localhost' not in tpl and '127.0.0.1' not in tpl,
          f'{name}: без localhost')
    check(not any(bad in tpl for bad in FORBIDDEN),
          f'{name}: без запрещённых цветов')
    btns = re.findall(r'<button\b[^>]*>', tpl)
    check(btns and all('type=' in b for b in btns),
          f'{name}: кнопки с явным type ({len(btns)})')
    check('{% extends "base.html" %}' in tpl
          and '{% block content %}' in tpl,
          f'{name}: встроена в общий каркас')

stpl = open(os.path.join(ROOT, 'web', 'templates', 'settings.html'),
            encoding='utf-8').read()
check('Tehlike' not in stpl and 'Aktif' not in stpl,
      'settings: турецкий язык вычищен')
check('Настройки сервера' in stpl and 'set-grid' in stpl,
      'settings: русский заголовок и сетка карточек')

atpl = open(os.path.join(ROOT, 'web', 'templates', 'anticrash.html'),
            encoding='utf-8').read()
check('ac-links' in atpl and '/channel-settings' in atpl
      and '/guardian' in atpl,
      'антикраш связан с хабом каналов и Щитом')

ptpl = open(os.path.join(ROOT, 'web', 'templates', 'panel_menu.html'),
            encoding='utf-8').read()
check('tab-layout' in ptpl and 'Порядок и скрытие' in ptpl
      and '/api/panel-menu/layout' in ptpl,
      'у меню панели есть вкладка «Порядок и скрытие»')
check('layoutHide' in ptpl and 'layoutMove' in ptpl and 'saveLayout' in ptpl,
      'JS лэйаута: скрытие, стрелки перемещения, сохранение')

css = open(os.path.join(ROOT, 'web', 'static', 'style.css'),
           encoding='utf-8').read()
check('input[type="number"]' in css and '-webkit-inner-spin-button' in css,
      'CSS: стрелки числовых полей убраны глобально')

from web import routes_extra as _re  # noqa: E402
check(any(m.__name__ == 'web.routes.mod_settings' for m in _re._MODULES)
      and any(m.__name__ == 'web.routes.channel_settings' for m in _re._MODULES),
      'маршруты настроек модерации и хаба каналов зарегистрированы')

# ═══ 7. Демо-витрина: всё включено, кнопки живые ══════════════════════════
print('== демо-режим: без «выкл», кнопки работают ==')
check(os.environ.get('DEMO_MODE') == '1', 'тест бежит в демо-режиме')
check(PM.module_off_paths() == frozenset(),
      'в демо ни одна страница не приглушена (всё включено)')
body = client.get('/').get_data(as_text=True)
check('nav-off-chip' not in body, 'в меню нет чипов «выкл»')

r = client.get('/api/cogs')
cogs = r.get_json()
check(r.status_code == 200 and len(cogs) > 50,
      f'менеджер модулей видит все модули ({len(cogs)})')
check(all(c['loaded'] for c in cogs), 'в демо все модули «загружены»')

r = client.post('/api/cogs/unload', json={'name': 'economy_cog'})
check(r.status_code == 200 and r.get_json().get('ok') is True,
      'выключение модуля в демо — успех, а не «Бот офлайн»')
loaded_now = {c['name']: c['loaded'] for c in client.get('/api/cogs').get_json()}
check(loaded_now.get('economy_cog') is False,
      'выключенный модуль честно показывается выключенным')
check('/economy' in PM.module_off_paths(),
      'выключенный модуль даёт чип «выкл» в меню')
r = client.post('/api/cogs/load', json={'name': 'economy_cog'})
loaded_now = {c['name']: c['loaded'] for c in client.get('/api/cogs').get_json()}
check(r.get_json().get('ok') is True and loaded_now.get('economy_cog') is True,
      'включение обратно тоже работает')
check(PM.module_off_paths() == frozenset(),
      'после включения меню снова без «выкл»')

r = client.post('/api/cogs/reload', json={'name': 'level_cog'})
check(r.status_code == 200 and r.get_json().get('ok') is True,
      'перезагрузка модуля в демо — успех')
r = client.post('/api/cogs/reload-all')
check(r.status_code == 200 and r.get_json().get('ok') is True,
      '«обновить все модули» в демо — успех')

r = client.post('/api/bot/sync', json={})
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True and d.get('demo') is True,
      'кнопка «Синхронизировать» в демо — успех')
r = client.post('/api/bot/restart')
check(r.status_code == 200 and r.get_json().get('success') is True,
      'кнопка «Перезапуск» в демо — успех')

from services import demo_cogs as DC  # noqa: E402
check(DC.load_states() == {}, 'после reload-all демо-состояния сброшены (всё вкл)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
