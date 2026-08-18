# -*- coding: utf-8 -*-
"""Мод-контроль (идеи #34-37).

Проверяем: быстрые причины (CRUD, лимиты, дубли), «на грани» (пороги
steps/thresholds 1:1 с ботом, gap-математику и сортировку), амнистию
(снимок варнов, откат, защиту от новых варнов), радар истечений
(бакеты, прогресс, мусор в файлах), HTTP-права mod+/admin+ и шаблон.

Запуск: python3 tests/test_mod_control.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_modctl_test_')
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


from web.routes import mod_control as MC  # noqa: E402

print('== 1. Быстрые причины (чистые функции) ==')
er = MC.empty_reasons()
check(tuple(er.keys()) == MC.REASON_KINDS and all(v == [] for v in er.values()),
      'пустой набор по всем типам')
check(MC.validate_reason_kind('warn')[0] and not MC.validate_reason_text('ok')[0] is None,
      'валидный тип проходит')
check(MC.validate_reason_kind('nope') == (False, 'Неизвестный тип причины'),
      'неизвестный тип — ошибка')
check(MC.validate_reason_text('  флуд   в  чате  ') == (True, '', 'флуд в чате'),
      'текст нормализуется (схлоп пробелов)')
check(MC.validate_reason_text('   ') == (False, 'Укажите текст причины', ''),
      'пустой текст — ошибка')
long_err = MC.validate_reason_text('x' * (MC.REASON_TEXT_MAX + 1))
check(long_err == (False, f'Причина длиннее {MC.REASON_TEXT_MAX} символов', ''),
      'слишком длинный текст — ошибка')

ok, err, item = MC.add_reason(777, 'warn', ' Флуд ', by='админ')
check(ok and item['id'] == 1 and item['text'] == 'Флуд' and item['by'] == 'админ',
      'первая причина добавлена с id=1')
check(os.path.exists('data/mod_reasons_777.json'), 'файл причин создан')
check(MC.add_reason(777, 'warn', ' фЛУД  ')[1] == 'Такая причина уже есть',
      'дубль (без учёта регистра) отклонён')
check(MC.add_reason(777, 'nope', 'x')[1] == 'Неизвестный тип причины', 'плохой тип в add')
check(MC.add_reason(777, 'warn', '   ')[1] == 'Укажите текст причины', 'пустой текст в add')

for i in range(2, MC.REASONS_PER_KIND + 1):
    ok, err, it = MC.add_reason(777, 'warn', f'Причина {i}')
    if not ok:
        break
check(ok and it['id'] == MC.REASONS_PER_KIND, f'набита упаковка до лимита ({MC.REASONS_PER_KIND})')
check(MC.add_reason(777, 'warn', 'Лишняя')[1].startswith('Лимит:'),
      'сверх лимита — отказ')
reloaded = MC.load_reasons(777)
check(len(reloaded['warn']) == MC.REASONS_PER_KIND and reloaded['mute'] == [],
      'перечитано с диска: полный warn, остальные пустые')

ok, err, removed = MC.remove_reason(777, 'warn', 2)
check(ok and removed['text'] == 'Причина 2', 'удаление возвращает снятую причину')
check(MC.remove_reason(777, 'warn', 2) == (False, 'Причина не найдена', None),
      'повторное удаление — не найдена')
check(MC.remove_reason(777, 'nope', 1)[1] == 'Неизвестный тип причины', 'remove: плохой тип')

jdump('data/mod_reasons_888.json', '{битый')
check(MC.load_reasons(888) == MC.empty_reasons(), 'битый файл — пустой набор, без падения')
jdump('data/mod_reasons_889.json', ['не', 'словарь'])
check(MC.load_reasons(889) == MC.empty_reasons(), 'не-словарь — пустой набор')
mixed = {'warn': [{'id': 1, 'text': '  ок  '}, 'мусор', {'id': 2, 'text': ''},
                  {'id': 'x', 'text': 'тоже ок'}]}
jdump('data/mod_reasons_890.json', mixed)
lm = MC.load_reasons(890)['warn']
check(len(lm) == 2 and lm[0]['text'] == 'ок', 'мусорные записи отфильтрованы, текст обрезан')

print('== 2. На грани авто-наказания ==')
check(MC.load_warns_map(777) == {}, 'без файла — пустая карта')
warns_fixture = {'777': {
    '100': [{'id': 1, 'reason': 'флуд'}, {'id': 2, 'reason': 'спам'}],
    '101': [{'id': 1, 'reason': 'капс'}],
    '102': 'мусор',
    '103': [],
    '104': [{'id': i} for i in range(1, 6)],
}, '888': {'900': [{'id': 1}]}}
jdump('data/warnings.json', warns_fixture)
wm = MC.load_warns_map(777)
check(set(wm.keys()) == {'100', '101', '104'} and len(wm['100']) == 2,
      'карта варнов: пустые и битые записи отброшены')
check(set(MC.load_warns_map(888).keys()) == {'900'}, 'чужой сервер отдельно')

jdump('data/warn_config_777.json', {'steps': [
    {'count': 5, 'action': 'ban'},
    {'count': 3, 'action': 'mute'},
    {'count': 3, 'action': 'kick'},
    {'count': 0, 'action': 'mute'},
    {'count': 'x'},
]})
steps = MC.load_warn_steps(777)
check([(s['count'], s['action']) for s in steps] == [(3, 'mute'), (5, 'ban')],
      'пороги: сортировка, дубль порога свернут, битые отброшены')
check(steps[0]['action_name'] == 'Мут' and steps[1]['action_name'] == 'Бан',
      'русские подписи действий')
jdump('data/warn_config_778.json', {'thresholds': [{'count': 2, 'action': 'timeout'}]})
s2 = MC.load_warn_steps(778)
check(len(s2) == 1 and s2[0]['count'] == 2 and s2[0]['action_name'] == 'Мут',
      "legacy-ключ 'thresholds' тоже читается, timeout = Мут (1:1 с ботом)")
check(MC.load_warn_steps(424242) == [], 'без конфига порогов нет')

rows = MC.at_risk_users(wm, steps, names={'100': 'Хулиган'})
check([(r['user_id'], r['gap']) for r in rows] == [('100', 1), ('101', 2)],
      'сортировка: сначала ближайший к порогу')
check(rows[0]['next_count'] == 3 and rows[0]['action_name'] == 'Мут'
      and rows[0]['warns'] == 2 and rows[0]['name'] == 'Хулиган',
      'строка: следующий порог, действие, имя')
check(all(r['user_id'] != '104' for r in rows), 'у перешагнувшего последний порог — не «на грани»')
check(MC.at_risk_users(wm, [], names={}) == [], 'без порогов — никого')
check(len(MC.at_risk_users(wm, steps, limit=1)) == 1, 'лимит выдачи работает')

print('== 3. Амнистия ==')
check(MC.validate_user_id('500') == (True, '', '500'), 'чистый ID')
check(MC.validate_user_id('<@500>') == (True, '', '500'), 'упоминание <@id>')
check(MC.validate_user_id('<@!500>') == (True, '', '500'), 'упоминание <@!id>')
check(MC.validate_user_id('абырвалг')[1] == 'Некорректный ID пользователя', 'мусорный ID')

jdump('data/warnings.json', {'777': {
    '500': [{'id': 1, 'reason': 'флуд'}, {'id': 2, 'reason': 'спам'}],
    '501': [{'id': 9, 'reason': 'капс'}],
}})
ok, err, entry = MC.amnesty_user(777, '500', by='админский', at='t0')
check(ok and entry['id'] == 1 and entry['count'] == 2 and entry['by'] == 'админский',
      'амнистия проведена, снимок на 2 варна')
after = json.load(open('data/warnings.json', encoding='utf-8'))
check('500' not in after['777'] and '501' in after['777'], 'зеркало очищено, сосед не тронут')
log = MC.load_amnesty_log(777)
check(len(log) == 1 and len(log[0]['warns']) == 2 and log[0]['restored_at'] is None,
      'журнал: варны сохранены для отката')
check(MC.amnesty_user(777, '500')[1] == 'У участника нет варнов', 'повторная — варнов нет')
check(MC.amnesty_user(777, 'xxx')[1] == 'Некорректный ID пользователя', 'мусорный ID в амнистии')
check(MC.undo_amnesty(777, 99) == (False, 'Запись амнистии не найдена', 0),
      'откат несуществующей — честная ошибка')

ok, err, restored = MC.undo_amnesty(777, 1, at='t1')
check(ok and restored == 2, 'откат вернул 2 варна')
back = json.load(open('data/warnings.json', encoding='utf-8'))
check(len(back['777']['500']) == 2, 'варны снова на месте')
check(MC.load_amnesty_log(777)[0]['restored_at'] == 't1', 'в журнале отмечен откат')
check(MC.undo_amnesty(777, 1) == (False, 'Амнистия уже откачена', 0),
      'двойной откат заблокирован')

ok, err, entry2 = MC.amnesty_user(777, '501')
check(ok and entry2['id'] == 2, 'вторая амнистия (следующий id)')
fresh = json.load(open('data/warnings.json', encoding='utf-8'))
fresh['777']['501'] = [{'id': 10, 'reason': 'новый'}]
jdump('data/warnings.json', fresh)
check(MC.undo_amnesty(777, 2)[1] == 'После амнистии появились новые варны',
      'откат не затирает свежие варны')
check(MC.load_warns_map('мусорный-gid') == {}, 'битый gid — пусто без падения')

print('== 4. Радар истечений ==')
NOW = 1_000_000.0
jdump('data/temp_mutes.json', {'777': {
    'u1': {'until': NOW + 3600, 'reason': 'флуд', 'mod_id': '9', 'created_at': NOW - 3600},
    'u2': {'until': NOW - 600, 'reason': '', 'mod_id': '9', 'created_at': NOW - 7200},
    'u3': 'мусор',
    'u4': {'until': 'не-число'},
}})
jdump('data/temp_bans.json', {'777': {
    'u5': {'until': NOW + 2 * 86400, 'reason': 'рейд', 'mod_id': '8', 'created_at': NOW - 86400},
}})
jdump('data/temp_vmutes.json', {'777': {'u6': {'until': NOW + 10 * 86400}}})
# temp_kicks.json намеренно отсутствует
rows = MC.load_temp_actions(777)
check(len(rows) == 4, 'четыре валидных записи, мусор отброшен')
kinds = {r['user_id']: r['kind'] for r in rows}
check(kinds == {'u1': 'mute', 'u2': 'mute', 'u5': 'ban', 'u6': 'vmute'},
      'типы из четырёх файлов')
rad = MC.expiry_radar(rows, now=NOW)
check(rad['counts'] == {'overdue': 1, 'soon': 1, 'week': 1, 'later': 1},
      'бакеты просрочено/24ч/3сут/позже')
check(rad['active_total'] == 4 and len(rad['rows']) == 3, 'в таблицу — только срочные')
check([r['user_id'] for r in rad['rows']] == ['u2', 'u1', 'u5'],
      'сортировка по ближайшему сроку')
by_uid = {r['user_id']: r for r in rad['rows']}
check(abs(by_uid['u1']['frac'] - 0.5) < 1e-9, 'прогресс съеденной половины срока')
check(by_uid['u2']['frac'] == 1.0 and by_uid['u2']['remaining_s'] == -600,
      'просроченный: прогресс капнут в 1.0, остаток отрицательный')
check(abs(by_uid['u5']['frac'] - 86400 / 259200) < 1e-9, 'прогресс трёхсуточного')
check(by_uid['u1']['reason'] == 'флуд' and by_uid['u5']['kind_name'] == 'Бан',
      'причина и русское имя типа сохранены')
empty = MC.expiry_radar([], now=NOW)
check(empty['active_total'] == 0 and empty['counts']['overdue'] == 0 and empty['rows'] == [],
      'пустой радар — нули')

print('== 4b. Последние действия ==')
jdump('data/audit_log.json', {'779': [
    {'category': 'mod', 'action': 'Мут', 'user_id': '1', 'user_name': 'А',
     'mod_name': 'Ст', 'reason': 'флуд', 'timestamp': '2026-08-15T10:00:00'},
    {'category': 'mod', 'action': 'Бан', 'user_id': '2', 'user_name': 'Б',
     'mod_name': 'Ст2', 'timestamp': '2026-08-16T09:00:00'},
    {'category': 'mod', 'action': 'Мут снят', 'user_id': '1', 'user_name': 'А',
     'timestamp': '2026-08-16T12:00:00'},
    {'category': 'member', 'action': 'Мут', 'user_id': '3',
     'timestamp': '2026-08-16T13:00:00'},
    {'category': 'mod', 'action': 'Предупреждение', 'user_id': '4',
     'timestamp': '2026-08-16T14:00:00'},
    {'category': 'mod', 'action': 'Кик', 'user_id': '5', 'timestamp': 'мусор'},
]})
rec = MC.recent_actions(779)
check([r['action'] for r in rec] == ['Мут снят', 'Бан', 'Мут'],
      'новые сверху; только кары и снятия, чужие категории и мусор мимо')
check(rec[0]['kind'] == 'lift' and rec[1]['kind'] == 'punish', 'типы lift/punish')
check(rec[1]['name'] == 'Б' and rec[1]['mod_name'] == 'Ст2' and rec[1]['reason'] == '',
      'имя, модератор и пустая причина сохранены')
check(rec[2]['at'] == '2026-08-15T10:00', 'метка без секунд')
check(len(MC.recent_actions(779, limit=1)) == 1, 'лимит режет список')
check(MC.recent_actions(424242) == [], 'пустой сервер — пусто без падения')

from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
_PULSE_NOW = _dt(2026, 8, 17, 0, 0, tzinfo=_tz.utc)
check(MC.recent_punish_count(779, days=7, now=_PULSE_NOW) == 2,
      'пульс: две кары за 7 дней (снятие не считается)')
check(MC.recent_punish_count(779, days=1, now=_PULSE_NOW) == 1,
      'пульс: за сутки — только бан')

print('== 4c. Варн из панели ==')
jdump('data/warnings.json', {'777': {'600': [{'id': 1, 'reason': 'старый'}]}})
ok, err, res = MC.panel_warn(777, '<@600>', '  флуд   в чате  ', by='Ст', at='t-warn')
check(ok and res['total'] == 2 and res['entry']['id'] == 2, 'варн добавлен, id растёт')
check(res['entry']['reason'] == 'флуд в чате', 'причина нормализована')
check(res['entry']['mod'] == 'Ст (панель)' and res['entry']['mod_id'] == ''
      and res['entry']['timestamp'] == 't-warn',
      'формат записи 1:1 с ботом + панельная пометка мода')
raw = json.load(open('data/warnings.json', encoding='utf-8'))
check(len(raw['777']['600']) == 2, 'зеркало на диске обновлено')
check(MC.panel_warn(777, '600', '   ')[1] == 'Укажите причину варна', 'пустая причина — отказ')
check(MC.panel_warn(777, '600', 'x' * (MC.WARN_REASON_MAX + 1))[1].startswith('Причина длиннее'),
      'длинная причина — отказ')
check(MC.panel_warn(777, 'мусор', 'x')[1] == 'Некорректный ID пользователя',
      'мусорный ID — отказ')
ok, err, res = MC.panel_warn(777, '601', 'первый', at='t2')
check(ok and res['entry']['id'] == 1 and res['total'] == 1, 'новому участнику id=1')

ok, err, res = MC.panel_unwarn(777, '600')
check(ok and res['left'] == 1 and res['removed']['reason'] == 'флуд в чате',
      'снят последний варн')
ok, err, res = MC.panel_unwarn(777, '600')
check(ok and res['left'] == 0, 'второе снятие забрало остаток')
raw = json.load(open('data/warnings.json', encoding='utf-8'))
check('600' not in raw.get('777', {}), 'пустой список не оставляет следа в зеркале')
check(MC.panel_unwarn(777, '600')[1] == 'У участника нет варнов', 'снимать нечего — честный отказ')
check(MC.panel_unwarn(777, 'мусор')[1] == 'Некорректный ID пользователя', 'мусорный ID в unwarn')

print('== 4d. CSV-выгрузки ==')
jdump('data/warnings.json', {'777': {
    '100': [{'id': 1, 'reason': 'капс', 'mod': 'Ст', 'timestamp': '2026-08-10T10:00:00'},
            {'id': 2, 'reason': 'флуд;спам', 'mod': 'Ст2', 'timestamp': '2026-08-12T10:00:00'}],
    '101': [{'id': 1, 'reason': 'спам', 'mod': 'Ст', 'timestamp': '2026-08-11T10:00:00'}],
}})
rows = MC.warns_csv_rows(777)
check([r[0] for r in rows] == ['100', '101'], 'сначала у кого больше варнов')
check(rows[0][2] == 2 and rows[0][3] == 'флуд;спам' and rows[0][4] == 'Ст2'
      and rows[0][5] == '2026-08-12', 'последние причина/мод/дата по участнику')
body = MC.csv_body(MC.WARN_CSV_HEADER, rows)
check(body.startswith('\ufeff' + MC.WARN_CSV_HEADER), 'BOM и шапка — как в других выгрузках')
check('"флуд;спам"' in body, 'ячейка с точкой с запятой экранируется кавычками')
rrows = MC.radar_csv_rows(777, now=NOW)
check(rrows and rrows[0][0] == 'Мут' and rrows[0][1] == 'u2',
      'радар-CSV: сортировка по сроку, просроченный первый')
check('1970' in rrows[0][3], 'дата истечения в читаемом виде')

print('== 4e. Журнал панели ==')
check(MC.panel_log(777) == [], 'журнал пуст, пока операций не было')
if os.path.exists('data/mod_panel_log_777.json'):
    os.remove('data/mod_panel_log_777.json')
check(MC.panel_log(777) == [], 'нет файла — пусто без падения')
e1 = MC.panel_log_add(777, 'warn', '600', 'флуд', by='Ст')
e2 = MC.panel_log_add(777, 'amnesty', '600', 'списано варнов: 2', by='Админ')
check(e1['id'] == 1 and e2['id'] == 2, 'id журнала растут')
log = MC.panel_log(777)
check(log[0]['op'] == 'amnesty' and log[1]['op'] == 'warn', 'новые сверху')
check(log[0]['by'] == 'Админ' and log[0]['detail'] == 'списано варнов: 2'
      and log[0]['user_id'] == '600', 'поля записи на месте')
check(MC.panel_log_add(777, 'левая-операция') is None, 'неизвестная операция не пишется')
for i in range(120):
    MC.panel_log_add(777, 'reason_add', '', f'причина {i}', by='бот')
log_full = MC.panel_log(777, limit=1000)
check(len(log_full) == MC.PANEL_LOG_KEEP, 'журнал обрезан лимитом, не разрастается')
check(log_full[0]['detail'] == 'причина 119', 'голова журнала — свежайшая запись')
check(all(it['op'] != 'warn' for it in log_full), 'старейшие записи вытеснены')
os.remove('data/mod_panel_log_777.json')

print('== 5. Студия удалена: реальные страницы восстановлены ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


check(client.get('/mod-studio').status_code == 404, 'страница Студии удалена (404)')
login('mod')
for path in ('/logs', '/warnings'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} снова рендерится для mod')
login('uye')
check(client.get('/logs').status_code == 403, 'uye /logs закрыт')
check(client.get('/warnings').status_code == 403, 'uye /warnings закрыт')

print('== 6. Меню: Студии нет, разделы модерации отдельно ==')
import services.panel_menu as PM  # noqa: E402
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/mod-studio' not in paths, 'пункта «Студия модерации» в меню больше нет')
check('/mod-control' not in paths and '/mod-insights' not in paths,
      'старых хабов в меню нет')
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
for p_ in ('/logs', '/warnings', '/temp-moderation', '/mod-history', '/autofilter',
           '/antiraid', '/appeals', '/lockdown', '/security', '/antifake', '/ladder',
           '/proofs', '/mod-report'):
    check(p_ in mod_pages, f'раздел {p_} отдельным пунктом меню')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check('mod_studio_panel' not in ext, 'модуль Студии снят с регистрации')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
