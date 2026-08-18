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

print('== 5. API: права и потоки ==')
# Свежие фикстуры с известным состоянием
jdump('data/warnings.json', {'777': {
    '100': [{'id': 1}, {'id': 2}],
    '101': [{'id': 1}],
    '104': [{'id': i} for i in range(1, 6)],
}})
_pulse_now = _dt.now(_tz.utc)


def _iso_h(hours_ago):
    return (_pulse_now - _td(hours=hours_ago)).isoformat()


jdump('data/audit_log.json', {'777': [
    {'category': 'mod', 'action': 'Мут', 'mod_name': 'Ст',
     'user_id': '100', 'user_name': 'Хулиган', 'timestamp': 't'},
    {'category': 'mod', 'action': 'Бан', 'mod_name': 'Ст',
     'user_id': '300', 'user_name': 'Рейдер', 'reason': 'рейд',
     'timestamp': _iso_h(3)},
    {'category': 'mod', 'action': 'Кик', 'mod_name': 'Ст2',
     'user_id': '301', 'user_name': 'Флудер', 'timestamp': _iso_h(1)},
    {'category': 'mod', 'action': 'Мут снят', 'mod_name': 'Ст',
     'user_id': '300', 'user_name': 'Рейдер', 'timestamp': _iso_h(0.2)},
]})
if os.path.exists('data/mod_reasons_777.json'):
    os.remove('data/mod_reasons_777.json')
if os.path.exists('data/mod_amnesty_777.json'):
    os.remove('data/mod_amnesty_777.json')

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/mod-studio/overview'
check(client.get('/mod-studio').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/mod-studio').status_code == 403, 'uye нельзя')
check(client.get(OV).status_code == 403, 'uye нельзя API')
login('mod')
page = client.get('/mod-studio')
check(page.status_code == 200 and 'На грани авто-наказания' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'страница знает активный сервер')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает снимок без права правки')
check(len(ov['risk']['items']) == 2 and ov['risk']['edge'] == 1, 'снимок: двое на грани, один на волоске')
check(ov['risk']['items'][0]['name'] == 'Хулиган', 'имя подтянуто из журнала аудита')
check(ov['radar']['counts']['overdue'] >= 0 and 'rows' in ov['radar'], 'радар в снимке')
check(ov['reasons']['warn'] == [] and ov['amnesty'] == [], 'причины и амнистии пусты')
check(ov['risk']['tuned'] is True, 'пороги настроены (фикстура warn_config_777)')
check(len(ov['recent']) == 3 and ov['recent'][0]['action'] == 'Мут снят',
      'последние действия в снимке: снятие самым свежим, битые метки не в счёт')
check(ov['recent7'] == 2, 'пульс: две кары за последние 7 дней')

check(client.post('/api/guild/777/mod-studio/reasons', json={'kind': 'warn', 'text': 'x'}).status_code == 403,
      'mod не добавляет причины')
login('admin')
check(client.get(OV).get_json()['can_edit'] is True, 'admin с правом правки')
bad = client.post('/api/guild/777/mod-studio/reasons', json={'kind': 'nope', 'text': 'x'})
check(bad.status_code == 400 and bad.get_json()['error'] == 'Неизвестный тип причины',
      '400 на плохой тип')
bad2 = client.post('/api/guild/777/mod-studio/reasons', json={'kind': 'mute', 'text': '  '})
check(bad2.status_code == 400 and bad2.get_json()['error'] == 'Укажите текст причины',
      '400 на пустой текст')
good = client.post('/api/guild/777/mod-studio/reasons', json={'kind': 'mute', 'text': ' Флуд в голосе '})
check(good.status_code == 200 and good.get_json()['item']['text'] == 'Флуд в голосе',
      'причина добавлена (нормализация)')
check(len(client.get(OV).get_json()['reasons']['mute']) == 1, 'причина видна в снимке')
rm = client.post('/api/guild/777/mod-studio/reasons/mute/1/delete')
check(rm.status_code == 200 and rm.get_json()['removed']['text'] == 'Флуд в голосе', 'удалена')
check(client.post('/api/guild/777/mod-studio/reasons/mute/1/delete').status_code == 404,
      'повторное удаление — 404')

am = client.post('/api/guild/777/mod-studio/amnesty', json={'user_id': '<@100>'})
check(am.status_code == 200 and am.get_json()['amnesty']['count'] == 2,
      'амнистия по упоминанию: 2 варна')
aid = am.get_json()['amnesty']['id']
ov2 = client.get(OV).get_json()
check(len(ov2['risk']['items']) == 1 and ov2['risk']['edge'] == 0,
      'после амнистии «на грани» пересчитан')
check(ov2['amnesty'][0]['count'] == 2 and ov2['amnesty_total'] == 1, 'журнал амнистий в снимке')
un = client.post(f'/api/guild/777/mod-studio/amnesty/{aid}/undo')
check(un.status_code == 200 and un.get_json()['restored'] == 2, 'откат вернул варны')
check(client.post(f'/api/guild/777/mod-studio/amnesty/{aid}/undo').status_code == 400,
      'двойной откат — 400')
check(client.post('/api/guild/777/mod-studio/amnesty/999/undo').status_code == 404,
      'откат несуществующей — 404')
no_warns = client.post('/api/guild/777/mod-studio/amnesty', json={'user_id': '424242'})
check(no_warns.status_code == 400 and no_warns.get_json()['error'] == 'У участника нет варнов',
      'честный отказ без варнов')
check(len(client.get(OV).get_json()['risk']['items']) == 2, 'после отката картина восстановлена')

login('mod')
check(client.post('/api/guild/777/mod-studio/warn',
                   json={'user_id': '100', 'reason': 'флуд'}).status_code == 403,
      'mod не выдаёт варны из панели')
check(client.post('/api/guild/777/mod-studio/unwarn',
                   json={'user_id': '100'}).status_code == 403,
      'mod не снимает варны из панели')
login('admin')
bad = client.post('/api/guild/777/mod-studio/warn', json={'user_id': '100', 'reason': '   '})
check(bad.status_code == 400 and bad.get_json()['error'] == 'Укажите причину варна',
      'warn: 400 на пустую причину')
bad = client.post('/api/guild/777/mod-studio/warn', json={'user_id': 'мусор', 'reason': 'флуд'})
check(bad.status_code == 400 and bad.get_json()['error'] == 'Некорректный ID пользователя',
      'warn: 400 на мусорный ID')
warned = client.post('/api/guild/777/mod-studio/warn', json={'user_id': '100', 'reason': ' флуд '})
check(warned.status_code == 200 and warned.get_json()['total'] == 3,
      'warn: у участника теперь 3 варна')
ov3 = client.get(OV).get_json()
check(ov3['risk']['edge'] == 0, 'warn: после третьего варна участник ушёл с волоска (порог 3)')
unw = client.post('/api/guild/777/mod-studio/unwarn', json={'user_id': '<@100>'})
check(unw.status_code == 200 and unw.get_json()['left'] == 2,
      'unwarn: по упоминанию, осталось 2')
check(client.post('/api/guild/777/mod-studio/unwarn',
                   json={'user_id': '424242'}).get_json()['error'] == 'У участника нет варнов',
      'unwarn: честный отказ без варнов')
check(client.get(OV).get_json()['risk']['edge'] == 1, 'unwarn: картина на грани восстановлена')

ovlog = client.get(OV).get_json()
ops = [e['op'] for e in ovlog['panel_log']]
check(ops and ops[0] == 'unwarn' and 'warn' in ops and 'amnesty' in ops
      and 'amnesty_undo' in ops and 'reason_add' in ops and 'reason_del' in ops,
      f'журнал панели записал все операции (сверху: {ops[0]})')
check(all(e['by'] == 'admin' for e in ovlog['panel_log']),
      'в журнале видно, кто действовал')

login('mod')
csv_r = client.get('/api/guild/777/mod-studio/warns.csv')
check(csv_r.status_code == 200 and 'text/csv' in (csv_r.headers.get('Content-Type') or ''),
      'CSV варнов отдаётся моду')
check(csv_r.headers.get('Content-Disposition') == 'attachment; filename=modcenter_warns_777.csv',
      'CSV варнов: заголовок вложения')
csv_body = csv_r.get_data(as_text=True)
check(csv_body.startswith('\ufeff' + MC.WARN_CSV_HEADER), 'CSV варнов: BOM + шапка')
check('100' in csv_body and '104' in csv_body, 'CSV варнов: участники на месте')
radar_r = client.get('/api/guild/777/mod-studio/radar.csv')
check(radar_r.status_code == 200
      and radar_r.headers.get('Content-Disposition') == 'attachment; filename=modcenter_radar_777.csv',
      'CSV радара отдаётся с правильным именем')
login('uye')
check(client.get('/api/guild/777/mod-studio/warns.csv').status_code == 403,
      'uye CSV закрыт')

print('== 5b. Консоль: вкладки Журнал/Варны/Временные/История ==')
login('mod')
jr = client.get('/api/guild/777/mod-studio/journal').get_json()
check(jr['success'] and jr['total'] == 3, 'журнал: три разборчивых события')
check([r['action'] for r in jr['rows']] == ['Мут снят', 'Кик', 'Бан'],
      'журнал: новые сверху')
check(jr['categories'] == {'mod': 3}, 'журнал: счётчики категорий')
jr2 = client.get('/api/guild/777/mod-studio/journal?query=рейд').get_json()
check(jr2['total'] == 2 and jr2['rows'][0]['action'] == 'Мут снят',
      'журнал: поиск цепляет и причину («рейд»), и имя (Рейдер)')
jr3 = client.get('/api/guild/777/mod-studio/journal?mod=ст2').get_json()
check(jr3['total'] == 1 and jr3['rows'][0]['action'] == 'Кик',
      'журнал: фильтр по модератору подстрокой')

tf = client.get('/api/guild/777/mod-studio/temp-full').get_json()
check(tf['success'] and len(tf['rows']) == 4, 'временные: все четыре активных')
check([r['user_id'] for r in tf['rows']] == ['u2', 'u1', 'u5', 'u6'],
      'временные: сортировка по сроку')
check(tf['counts']['overdue'] == 4 and tf['counts']['later'] == 0,
      'временные: фикстура 1970 года просрочена целиком — сводка честная')

wl = client.get('/api/guild/777/mod-studio/warns-list').get_json()
check(wl['success'] and wl['total_warns'] == 8, 'варны: всего восемь')
check([r['user_id'] for r in wl['rows']] == ['104', '100', '101'],
      'варны: сначала у кого больше')
check(len(wl['rows'][0]['items']) == 5, 'варны: последние пять причин')
check([(s['count'], s['action']) for s in wl['steps']] == [(3, 'mute'), (5, 'ban')],
      'варны: пороги в выдаче')

hs = client.get('/api/guild/777/mod-studio/history').get_json()
check(hs['success'] and [r['action'] for r in hs['rows']] == ['Мут снят', 'Кик', 'Бан'],
      'история: кары и снятия, новые сверху')
check(hs['rows'][1]['kind'] == 'punish' and hs['rows'][0]['kind'] == 'lift',
      'история: типы punish/lift')

check(client.get('/api/guild/777/mod-studio/journal').status_code == 200,
      'журнал доступен моду')
login('uye')
check(client.get('/api/guild/777/mod-studio/journal').status_code == 403,
      'uye журнал закрыт')
check(client.get('/api/guild/777/mod-studio/history').status_code == 403,
      'uye история закрыта')

print('== 5d. Консоль забрал Щит, Демки и Апелляции ==')
login('mod')
jdump('data/antiraid_777.json', {'join_raid': True, 'bot_protection': True})
jdump('data/autofilter_777.json', {'enabled': True,
                                    'words': {'enabled': True, 'action': 'warn', 'list': ['фу']}})
sh = client.get('/api/guild/777/mod-studio/shield').get_json()
check(sh['success'] and sh['autofilter']['status'] == 'ok'
      and '1 слов' in sh['autofilter']['detail'], 'щит: автофильтр включён со словарём')
check(sh['antiraid']['status'] == 'ok' and '2 из 5' in sh['antiraid']['detail'],
      'щит: анти-рейд с двумя защитами')
check(sh['lockdown']['active'] is False, 'щит: локдаун не активен')
check(sh['security']['tuned'] is False, 'щит: безопасность не настроена')
jdump('data/security_777.json', {'panel_login_guard': True})
sh2 = client.get('/api/guild/777/mod-studio/shield').get_json()
check(sh2['security']['tuned'] is True, 'щит: безопасность появилась после настройки')

jdump('data/modproof_777.json', {'next': 3, 'items': {
    '1': {'id': 1, 'user_id': '100', 'user_name': 'Хулиган', 'mod_id': '7',
          'mod_name': 'Ст', 'action': 'бан', 'reason': 'рейд',
          'link': 'https://example.com/p1', 'set_at': '2026-08-15T10:00:00'},
    '2': {'id': 2, 'user_id': '101', 'user_name': 'Флудер', 'mod_id': '8',
          'mod_name': 'Ст2', 'action': 'мут', 'reason': 'флуд',
          'link': '', 'set_at': '2026-08-16T09:00:00'},
    'x': 'мусор',
}})
pr = client.get('/api/guild/777/mod-studio/proofs').get_json()
check(pr['success'] and pr['total'] == 2, 'демки: два доказательства, мусор мимо')
check(pr['rows'][0]['user_name'] == 'Флудер', 'демки: свежие сверху')
check(pr['rows'][1]['action'] == 'бан' and pr['rows'][1]['link'], 'демки: поля на месте')

from db import GuildData  # noqa: E402
GuildData('appeals').set('777', 'state', {'items': [
    {'id': 1, 'status': 'pending', 'user_name': 'Хулиган', 'reason': 'бан за рейд',
     'created_at': '2026-08-16T10:00:00', 'reviewed_at': None},
    {'id': 2, 'status': 'accepted', 'user_name': 'Флудер', 'reason': 'мут',
     'created_at': '2026-08-15T09:00:00', 'reviewed_at': '2026-08-15T12:00:00',
     'reviewed_by': 'admin'},
]})
ap = client.get('/api/guild/777/mod-studio/appeals').get_json()
check(ap['success'] and ap['stats']['pending'] == 1 and ap['stats']['accepted'] == 1,
      'апелляции: счётчики очереди верны')
check(ap['rows'][0]['user'] == 'Хулиган' and ap['rows'][0]['status'] == 'pending',
      'апелляции: свежие сверху, статусы на месте')
login('uye')
check(client.get('/api/guild/777/mod-studio/shield').status_code == 403,
      'uye щит закрыт')
check(client.get('/api/guild/777/mod-studio/proofs').status_code == 403,
      'uye демки закрыты')

print('== 5c. Старые страницы ведут в консоль ==')
login('mod')
for path, tab in (('/logs', 'journal'), ('/warnings', 'warns'),
                  ('/temp-moderation', 'temp'), ('/mod-history', 'history')):
    r = client.get(path)
    check(r.status_code in (301, 302)
          and ('/mod-studio?tab=' + tab) in (r.headers.get('Location') or ''),
          f'{path} -> Центр, вкладка {tab}')

print('== 5e. Закладки студии ==')
login('mod')
pins = client.get('/api/guild/777/mod-studio/pins').get_json()
check(pins['success'] and pins['pins'] == [], 'закладки изначально пусты')
t1 = client.post('/api/guild/777/mod-studio/pins/toggle', json={'user_id': '100'}).get_json()
check(t1['success'] and t1['pinned'] is True and len(t1['pins']) == 1,
      'закладка добавлена')
check(t1['pins'][0]['name'] == 'Хулиган', 'имя в закладке подтянуто из аудита')
t2 = client.post('/api/guild/777/mod-studio/pins/toggle', json={'user_id': '<@100>'}).get_json()
check(t2['success'] and t2['pinned'] is False and t2['pins'] == [],
      'повторный клик убирает закладку (по упоминанию)')
bad = client.post('/api/guild/777/mod-studio/pins/toggle', json={'user_id': 'мусор'})
check(bad.status_code == 400, 'мусорный ID в закладках — 400')
login('uye')
check(client.get('/api/guild/777/mod-studio/pins').status_code == 403,
      'uye закладки закрыты')

print('== 6. Шаблон Студии, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/mod_studio.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('sdFeed', 'sdStats', 'sdFind', 'sdRisk', 'sdWarnId', 'sdWarnText',
            'sdReasons', 'sdAmnesty', 'sdPanelLog', 'sdNotes', 'sdDossier',
            'sdJournal', 'sdWarnsList', 'sdTempFull', 'sdHistory',
            'sdShield', 'sdLockdown', 'sdProofs', 'sdAppeals', 'sdSubjects',
            'sdPins', 'sdDigest', 'sdDigestQuick', 'sdReportTotals'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check('/warn-config' in tpl, 'ссылка на настройку порогов')
check('sdNotify' in tpl and 'sd-ncard' in tpl,
      'действия отзываются карточками-уведомлениями, а не тостами')
check('/mod-studio/warns.csv' in tpl and '/mod-studio/radar.csv' in tpl,
      'CSV-кнопки варнов и радара в шаблоне')
check('sdWarnAsk' in tpl and 'sdUnwarnAsk' in tpl and 'sdAmnestyAsk' in tpl,
      'варн/анварн/амнистия на кнопках')
check("get('uid')" in tpl, 'префилл по ?uid= из досье')
check('SD_TAB_KEYS' in tpl, 'горячие клавиши 1-0 переключают вкладки')
check('sdTogglePin' in tpl and 'sdCopyDigest' in tpl,
      'закладки и копирование отчёта на месте')
check("get('tab')" in tpl, 'deep-link по ?tab= из меню и редиректов')
check(not os.path.exists(os.path.join(ROOT, 'web/templates/mod_control.html'))
      and not os.path.exists(os.path.join(ROOT, 'web/templates/mod_insights.html')),
      'старые страницы удалены без следа')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/mod-studio' in paths, 'пункт меню «Студия модерации» есть')
check('/mod-control' not in paths and '/mod-insights' not in paths,
      'старых пунктов в меню больше нет')
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check(mod_pages == ['/mod-studio'],
      'группа «Модерация» — одна Студия, всё в одном месте')
check('/antiraid' not in paths and '/autofilter' not in paths
      and '/appeals' not in paths and '/proofs' not in paths,
      'легаси-страницы убраны из меню (живут внутри Студии)')
check(mod_pages[0] == '/mod-studio', 'Центр — первый пункт группы «Модерация»')
check('/mod-studio' not in PM.PAGE_COGS, 'файловая страница — не в PAGE_COGS')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check('mod_studio_panel' in ext, 'модуль Студии зарегистрирован в routes_extra')
check('mod_control,' not in ext and 'mod_insights,' not in ext,
      'старые страницы сняты с регистрации (логика осталась модулям)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
