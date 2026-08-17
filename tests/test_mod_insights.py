# -*- coding: utf-8 -*-
"""Мод-анализ (идеи #38-40).

Проверяем: список «кто чаще наказывается» (веса, сортировка, лимиты),
досье участника (варны + до-порога, таймлайн кар, активные temp-статусы,
амнистии, заметки), эффективность наказаний (рецидив за 7/30 дн., медианы,
флаг «мало данных», окна 7..365), чек-лист готовности (пороги, причины,
автофильтр 1:1 с merge_config бота, анти-рейд, свежесть журнала),
HTTP-права mod+ и шаблон.

Запуск: python3 tests/test_mod_insights.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_modins_test_')
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


def jdump(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)


from web.routes import mod_insights as MI  # noqa: E402

NOW = datetime(2026, 8, 16, 12, 0)
NOW_TS = 1_800_000.0


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat(timespec='seconds')


print('== 1. Кто чаще наказывается ==')
jdump('data/warnings.json', {'777': {
    '100': [{'id': 1}, {'id': 2}],
    '200': [{'id': 1}],
}})
jdump('data/audit_log.json', {'777': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '100', 'user_name': 'Хулиган',
     'mod_name': 'Ст', 'timestamp': iso(1)},
    {'category': 'mod', 'action': 'Бан', 'user_id': '300', 'user_name': 'Рейдер',
     'mod_name': 'Ст', 'timestamp': iso(2)},
    {'category': 'mod', 'action': 'Мут снят', 'user_id': '100', 'user_name': 'Хулиган',
     'timestamp': iso(0)},
    {'category': 'member', 'action': 'Участник вошёл', 'user_id': '400',
     'user_name': 'Тихоня', 'timestamp': iso(0)},
    {'category': 'mod', 'action': 'Мут', 'user_id': '300', 'user_name': 'Рейдер',
     'mod_name': 'Ст2', 'timestamp': iso(3)},
    {'category': 'mod', 'action': 'Мут', 'timestamp': iso(0)},
]})
sub = MI.subjects(777)
check([r['user_id'] for r in sub['items']] == ['100', '300', '200'],
      'сортировка по весу: 3, 2, 1')
check(sub['items'][0]['weight'] == 3 and sub['items'][0]['warns'] == 2
      and sub['items'][0]['punishments'] == 1,
      'вес = варны + кары')
check(sub['items'][0]['name'] == 'Хулиган', 'имя подтянуто из аудита')
check(sub['items'][1]['punishments'] == 2 and sub['items'][1]['last_at'] == iso(2)[:16],
      'у второго две кары, «Мут снят» не засчитан')
check(sub['items'][2]['name'] == '' and sub['items'][2]['punishments'] == 0,
      'варн без аудита: имя пустое, кар ноль')
check(sub['total'] == 3 and sub['warns_open'] == 3, 'итоги: трое под приглядом, 3 варна')
short = MI.subjects(777, limit=2)
check(len(short['items']) == 2 and short['total'] == 3, 'лимит режет список, total честный')
check(MI._norm_days('бред', 90) == 90 and MI._norm_days(3, 90) == 7
      and MI._norm_days(1000, 90) == 365, 'окно: дефолт, минимум 7, максимум 365')

print('== 2. Эффективность наказаний ==')


def pev(uid, action, days_ago):
    return {'category': 'mod', 'action': action, 'user_id': uid,
            'user_name': 'u' + uid, 'mod_name': 'Ст', 'timestamp': iso(days_ago)}


jdump('data/audit_log.json', {'778': [
    pev('1', 'Мут', 60), pev('1', 'Кик', 50),          # рецидив за 10 дн. (только 30)
    pev('2', 'Мут', 40), pev('2', 'Бан', 38),          # рецидив за 2 дн. (оба)
    pev('3', 'Мут', 30),                               # без рецидива
    pev('4', 'Мут', 20), pev('4', 'Мут', 6),           # рецидив за 14 дн. (30)
    pev('5', 'Кик', 25), pev('5', 'Бан', 24),          # рецидив за 1 дн. (оба)
    pev('6', 'Кик', 15), pev('7', 'Кик', 5),           # без рецидива
    pev('8', 'Бан', 10), pev('8', 'Мут', 3),           # рецидив ровно за 7 дн. (оба)
    pev('9', 'Мут', 400), pev('9', 'Кик', 395),        # всё за окном — не считаем
    pev('10', 'Мут', 100), pev('10', 'Кик', 10),       # первое за окном, рецидива нет
    {'category': 'member', 'action': 'Мут', 'user_id': 'zz', 'timestamp': iso(10)},
    {'category': 'mod', 'action': 'Мут', 'user_id': 'zz', 'timestamp': 'мусор'},
]})
eff = MI.punishment_effectiveness(MI.mod_events(778), now=NOW, days=90)
by_action = {r['action']: r for r in eff['types']}
check(eff['days'] == 90 and eff['min_sample'] == MI.EFFECT_MIN_SAMPLE, 'окно и порог выборки')
check(by_action['Мут']['count'] == 4 and by_action['Мут']['repeat7'] == 25
      and by_action['Мут']['repeat30'] == 75, 'мут: 4 наказанных, 25% за 7 дн., 75% за 30')
check(by_action['Мут']['median_days'] == 10.0, 'мут: медиана рецидива 10 дней')
check(by_action['Мут']['thin'] is True, 'мут: выборка 4 < 5 — «мало данных»')
check(by_action['Кик']['count'] == 4 and by_action['Кик']['repeat7'] == 25
      and by_action['Кик']['median_days'] == 1.0, 'кик: 4 человека, рецидив 1 день')
check(by_action['Бан']['count'] == 1 and by_action['Бан']['repeat30'] == 100
      and by_action['Бан']['median_days'] == 7.0, 'бан: один, рецидив ровно на 7-й день')
ov = eff['overall']
check(ov['count'] == 9 and ov['repeat7'] == 33 and ov['repeat30'] == 56,
      'итог: 9 наказанных (u9 за окном не посчитан)')
check(ov['median_days'] == 7.0 and ov['thin'] is False, 'итог: медиана 7, выборки хватает')
clamped = MI.punishment_effectiveness(MI.mod_events(778), now=NOW, days=400)
check(clamped['days'] == 365, 'окно зажато сверху в 365 дней')
empty = MI.punishment_effectiveness([], now=NOW, days=90)
check(empty['overall']['count'] == 0 and empty['overall']['repeat7'] is None
      and empty['overall']['median_days'] is None and empty['overall']['thin'] is True,
      'пустой журнал — нули и «мало данных» без делений на ноль')

print('== 3. Досье участника ==')
jdump('data/warnings.json', {'777': {
    '900': [
        {'id': 1, 'reason': 'флуд', 'timestamp': '2026-08-01T10:00:00', 'mod': 'Ст'},
        {'id': 2, 'reason': 'капс', 'timestamp': '2026-08-03T10:00:00', 'mod': 'Ст'},
        {'id': 3, 'reason': 'ссылки', 'timestamp': '2026-08-05T10:00:00', 'mod': 'Ст2'},
    ],
    '901': [{'id': 9}],
}})
jdump('data/warn_config_777.json', {'steps': [
    {'count': 3, 'action': 'mute'}, {'count': 5, 'action': 'ban'},
]})
jdump('data/audit_log.json', {'777': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '900', 'user_name': 'Смутьен',
     'mod_name': 'Ст', 'reason': 'флуд', 'timestamp': iso(5)},
    {'category': 'mod', 'action': 'Мут снят', 'user_id': '900', 'user_name': 'Смутьен',
     'timestamp': iso(4)},
    {'category': 'mod', 'action': 'Кик', 'user_id': '900', 'user_name': 'Смутьен',
     'mod_name': 'Ст2', 'reason': 'повтор', 'timestamp': iso(1)},
    {'category': 'mod', 'action': 'Мут', 'user_id': '902', 'user_name': 'Сосед',
     'timestamp': iso(2)},
]})
jdump('data/temp_mutes.json', {'777': {
    '900': {'until': NOW_TS + 3600, 'reason': 'свежий', 'mod_id': '9',
            'created_at': NOW_TS - 3600},
    '902': {'until': NOW_TS - 10, 'reason': '', 'mod_id': '9',
            'created_at': NOW_TS - 7200},
}})
jdump('data/member_notes.json', {'900': {'name': 'Смутьен', 'avatar': '', 'notes': [
    {'note': 'переговорили', 'timestamp': '2026-08-10', 'mod': 'Ст'},
    {'note': 'снова флуд', 'timestamp': '2026-08-12', 'mod': 'Ст2'},
]}})
jdump('data/mod_amnesty_777.json', [
    {'id': 1, 'user_id': '900', 'count': 2, 'by': 'Админ', 'at': '2026-08-04T09:00',
     'restored_at': None},
    {'id': 2, 'user_id': '901', 'count': 1, 'by': 'Админ', 'at': '2026-08-06',
     'restored_at': '2026-08-07'},
])

ok, err, ds = MI.dossier(777, '<@!900>', now=NOW, now_ts=NOW_TS)
check(ok and ds['user_id'] == '900' and ds['name'] == 'Смутьен', 'досье по упоминанию, имя из аудита')
check(ds['known'] is True, 'следы есть — досье «известное»')
check(ds['warns']['count'] == 3 and ds['warns']['items'][0]['reason'] == 'ссылки',
      'варны: три, свежий первым')
check(ds['warns']['items'][0]['mod'] == 'Ст2' and ds['warns']['items'][0]['at'] == '2026-08-05',
      'варн: мод и дата сохранены')
check(ds['warns']['gap'] == 2 and ds['warns']['next_count'] == 5
      and ds['warns']['action_name'] == 'Бан', 'до порога бана ещё 2 варна (порог строго выше)')
check(len(ds['temp_active']) == 1 and ds['temp_active'][0]['kind_name'] == 'Мут'
      and ds['temp_active'][0]['reason'] == 'свежий'
      and ds['temp_active'][0]['remaining_s'] == 3600, 'активный temp-мут с остатком')
check(len(ds['timeline']) == 3 and ds['timeline'][0]['action'] == 'Кик'
      and ds['timeline'][1]['kind'] == 'lift', 'таймлайн: кик свежий, снятие отдельным типом')
check(ds['timeline'][0]['reason'] == 'повтор' and ds['timeline'][0]['mod_name'] == 'Ст2',
      'у кары причина и модератор')
check(ds['stats']['punishments'] == 2 and ds['stats']['lifts'] == 1
      and ds['stats']['days_since'] == 1, 'статистика: 2 кары, 1 снятие, тишина 1 день')
check(ds['stats']['last_at'] == iso(1)[:16], 'последняя кара — кик')
check(len(ds['amnesty']) == 1 and ds['amnesty'][0]['count'] == 2
      and ds['amnesty'][0]['restored_at'] is None, 'амнистия участника на месте, чужая не подмешана')
check(len(ds['notes']) == 2 and ds['notes'][0]['note'] == 'снова флуд',
      'заметки команды, свежая первая')

_ok, _e, ds901 = MI.dossier(777, '901', now=NOW, now_ts=NOW_TS)
check(ds901['warns']['gap'] == 2 and ds901['warns']['action_name'] == 'Мут',
      'у 901 до мут-порога ещё 2 варна')
check(ds901['amnesty'][0]['restored_at'] == '2026-08-07', 'откаченная амнистия помечена')
_ok, _e, ds902 = MI.dossier(777, '902', now=NOW, now_ts=NOW_TS)
check(ds902['temp_active'] == [] and len(ds902['timeline']) == 1,
      'просроченный мут не «активен», но виден в таймлайне')
_ok, _e, dsnone = MI.dossier(777, '424242', now=NOW, now_ts=NOW_TS)
check(dsnone['known'] is False and dsnone['warns']['count'] == 0
      and dsnone['timeline'] == [] and dsnone['stats']['days_since'] is None,
      'чистый ID: пустое досье без ошибки')
bad = MI.dossier(777, 'xyz')
check(bad[0] is False and bad[1] == 'Некорректный ID пользователя',
      'мусорный ID — ошибка 1:1 с мод-контролем')
check(MI.load_member_notes('424242') == [], 'заметок нет — пусто без падения')

print('== 4. Чек-лист готовности ==')
for stale in ('data/warn_config_999.json', 'data/mod_reasons_999.json',
              'data/autofilter_999.json', 'data/antiraid_999.json'):
    if os.path.exists(stale):
        os.remove(stale)
cl0 = MI.readiness_checklist(999, now=NOW)
by_key0 = {c['key']: c for c in cl0['items']}
check((cl0['ok'], cl0['warn'], cl0['missing'], cl0['total']) == (0, 2, 3, 5),
      'голый сервер: 2 с заметками, 3 не настроено')
check(by_key0['warn_steps']['status'] == 'missing'
      and by_key0['warn_reasons']['status'] == 'warn', 'нет порогов, нет причин')
check(by_key0['autofilter']['status'] == 'warn'
      and by_key0['autofilter']['detail'] == 'По умолчанию', 'автофильтр на дефолтах — заметка')
check(by_key0['antiraid']['status'] == 'missing'
      and by_key0['audit_fresh']['status'] == 'missing', 'антирейд и журнал отсутствуют')
check(by_key0['warn_steps']['link'] == '/warn-config'
      and by_key0['warn_reasons']['link'] == '/mod-control', 'ссылки ведут на настройку')

jdump('data/autofilter_998.json', {'enabled': False})
cl998 = {c['key']: c for c in MI.readiness_checklist(998, now=NOW)['items']}
check(cl998['autofilter']['status'] == 'missing'
      and cl998['autofilter']['detail'] == 'Выключен', 'фильтр выключен — «не настроено»')

jdump('data/autofilter_997.json', {'enabled': True,
                                   'words': {'enabled': True, 'action': 'warn', 'list': ['фу']}})
jdump('data/antiraid_997.json', {'join_raid': True})
jdump('data/audit_log.json', {'997': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '1', 'user_name': 'x', 'timestamp': iso(1)},
]})
cl997 = {c['key']: c for c in MI.readiness_checklist(997, now=NOW)['items']}
check(cl997['autofilter']['status'] == 'ok' and cl997['autofilter']['detail'] == '1 слов',
      'фильтр включён со словарём — ок (merge_config 1:1 с ботом)')
check(cl997['antiraid']['status'] == 'ok' and cl997['antiraid']['detail'] == '1 из 5',
      'антирейд с одной защитой — ок')
check(cl997['audit_fresh']['status'] == 'ok' and cl997['audit_fresh']['detail'] == 'Вчера',
      'журнал свежий — вчерашнее событие')

jdump('data/audit_log.json', {'996': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '1', 'user_name': 'x', 'timestamp': iso(30)},
]})
cl996 = {c['key']: c for c in MI.readiness_checklist(996, now=NOW)['items']}
check(cl996['audit_fresh']['status'] == 'warn'
      and cl996['audit_fresh']['detail'] == 'Тихо 30 дн.', 'журнал молчит 30 дней — заметка')
jdump('data/audit_log.json', {'995': [
    {'category': 'member', 'action': 'Участник вошёл', 'user_id': '1', 'timestamp': iso(0)},
]})
cl995 = {c['key']: c for c in MI.readiness_checklist(995, now=NOW)['items']}
check(cl995['audit_fresh']['detail'] == 'Сегодня', 'свежее событие любой категории считается')

print('== 5. API: права и потоки ==')
for f in os.listdir('data'):
    if f.startswith(('temp_', 'mod_amnesty_', 'mod_reasons_', 'autofilter_777',
                     'warn_config_777', 'antiraid_777')) or f in ('member_notes.json',):
        os.remove(os.path.join('data', f))
jdump('data/warnings.json', {'777': {
    '100': [{'id': 1, 'reason': 'флуд', 'timestamp': '2026-08-14T10:00', 'mod': 'Ст'}],
}})
jdump('data/warn_config_777.json', {'steps': [{'count': 2, 'action': 'mute'}]})
jdump('data/audit_log.json', {'777': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '100', 'user_name': 'Хулиган',
     'mod_name': 'Ст', 'reason': 'флуд', 'timestamp': iso(1)},
    {'category': 'mod', 'action': 'Бан', 'user_id': '100', 'user_name': 'Хулиган',
     'mod_name': 'Ст', 'timestamp': iso(0)},
]})
jdump('data/member_notes.json', {'100': {'name': 'Хулиган', 'notes': [
    {'note': 'предупреждён', 'timestamp': '2026-08-15', 'mod': 'Ст'},
]}})
jdump('data/mod_reasons_777.json', {'warn': [{'id': 1, 'text': 'флуд', 'by': 'a', 'at': 't'}]})
jdump('data/autofilter_777.json', {'enabled': True,
                                   'words': {'enabled': True, 'action': 'warn', 'list': ['бад']}})
jdump('data/antiraid_777.json', {'join_raid': True})

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/mod-insights/overview'
DS = '/api/guild/777/mod-insights/dossier'
check(client.get('/mod-insights').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
check(client.get(DS + '?user_id=100').status_code in (302, 401, 403), 'гостю досье закрыто')
login('uye')
check(client.get('/mod-insights').status_code == 403, 'uye нельзя на страницу')
check(client.get(OV).status_code == 403, 'uye нельзя в снимок')
login('mod')
page = client.get('/mod-insights')
check(page.status_code == 200 and 'Досье участника' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'страница знает активный сервер')
ovj = client.get(OV).get_json()
check(ovj['success'] and ovj['subjects']['total'] == 1
      and ovj['subjects']['warns_open'] == 1, 'снимок: один под приглядом, один варн')
check(ovj['subjects']['items'][0]['user_id'] == '100'
      and ovj['subjects']['items'][0]['weight'] == 3, 'у участника вес 3 (варн + 2 кары)')
check(ovj['effectiveness']['days'] == 90, 'окно эффективности по умолчанию — 90 дней')
check(client.get(OV + '?days=30').get_json()['effectiveness']['days'] == 30,
      'переключатель окна работает')
check(client.get(OV + '?days=бред').get_json()['effectiveness']['days'] == 90,
      'мусорное окно — дефолт без падения')
clj = ovj['checklist']
check((clj['ok'], clj['warn'], clj['missing']) == (5, 0, 0), 'чек-лист полностью зелёный')
check({c['key'] for c in clj['items']} == {'warn_steps', 'warn_reasons', 'autofilter',
                                           'antiraid', 'audit_fresh'}, 'все пять проверок на месте')
dsj = client.get(DS + '?user_id=<@100>').get_json()
check(dsj['success'] and dsj['dossier']['name'] == 'Хулиган'
      and dsj['dossier']['stats']['punishments'] == 2, 'досье по упоминанию: имя, 2 кары')
check(dsj['dossier']['notes'][0]['note'] == 'предупреждён'
      and dsj['dossier']['known'] is True, 'заметка в досье, следы есть')
bad = client.get(DS + '?user_id=мусор')
check(bad.status_code == 400 and bad.get_json()['error'] == 'Некорректный ID пользователя',
      '400 на мусорный ID')
check(client.get(DS).status_code == 400, '400 без параметра')
clean = client.get(DS + '?user_id=555555').get_json()
check(clean['success'] and clean['dossier']['known'] is False, 'чужой ID — пустое досье, не ошибка')

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/mod_insights.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('miKpis', 'miSubjects', 'miDossier', 'miEffect', 'miCheck',
            'miDaysTabs', 'miDossierId'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check('mod-insights' in tpl, 'API-путь модуля в шаблоне')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/mod-insights' in paths, 'пункт меню «Мод-анализ» есть')
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/mod-insights' in mod_pages, 'пункт в группе «Модерация»')
check('/mod-insights' not in PM.PAGE_COGS, 'файловая страница — не в PAGE_COGS')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('mod_insights') >= 1, 'модуль зарегистрирован в routes_extra (импорт + список)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
