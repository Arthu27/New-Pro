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

_TMP = tempfile.mkdtemp(prefix='hakumo_modctl_test_')
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

print('== 5. API: права и потоки ==')
# Свежие фикстуры с известным состоянием
jdump('data/warnings.json', {'777': {
    '100': [{'id': 1}, {'id': 2}],
    '101': [{'id': 1}],
    '104': [{'id': i} for i in range(1, 6)],
}})
jdump('data/audit_log.json', {'777': [
    {'category': 'mod', 'action': 'Мут', 'mod_name': 'Ст',
     'user_id': '100', 'user_name': 'Хулиган', 'timestamp': 't'},
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


OV = '/api/guild/777/mod-control/overview'
check(client.get('/mod-control').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/mod-control').status_code == 302, 'uye нельзя')
check(client.get(OV).status_code == 403, 'uye нельзя API')
login('mod')
page = client.get('/mod-control')
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

check(client.post('/api/guild/777/mod-control/reasons', json={'kind': 'warn', 'text': 'x'}).status_code == 403,
      'mod не добавляет причины')
login('admin')
check(client.get(OV).get_json()['can_edit'] is True, 'admin с правом правки')
bad = client.post('/api/guild/777/mod-control/reasons', json={'kind': 'nope', 'text': 'x'})
check(bad.status_code == 400 and bad.get_json()['error'] == 'Неизвестный тип причины',
      '400 на плохой тип')
bad2 = client.post('/api/guild/777/mod-control/reasons', json={'kind': 'mute', 'text': '  '})
check(bad2.status_code == 400 and bad2.get_json()['error'] == 'Укажите текст причины',
      '400 на пустой текст')
good = client.post('/api/guild/777/mod-control/reasons', json={'kind': 'mute', 'text': ' Флуд в голосе '})
check(good.status_code == 200 and good.get_json()['item']['text'] == 'Флуд в голосе',
      'причина добавлена (нормализация)')
check(len(client.get(OV).get_json()['reasons']['mute']) == 1, 'причина видна в снимке')
rm = client.post('/api/guild/777/mod-control/reasons/mute/1/delete')
check(rm.status_code == 200 and rm.get_json()['removed']['text'] == 'Флуд в голосе', 'удалена')
check(client.post('/api/guild/777/mod-control/reasons/mute/1/delete').status_code == 404,
      'повторное удаление — 404')

am = client.post('/api/guild/777/mod-control/amnesty', json={'user_id': '<@100>'})
check(am.status_code == 200 and am.get_json()['amnesty']['count'] == 2,
      'амнистия по упоминанию: 2 варна')
aid = am.get_json()['amnesty']['id']
ov2 = client.get(OV).get_json()
check(len(ov2['risk']['items']) == 1 and ov2['risk']['edge'] == 0,
      'после амнистии «на грани» пересчитан')
check(ov2['amnesty'][0]['count'] == 2 and ov2['amnesty_total'] == 1, 'журнал амнистий в снимке')
un = client.post(f'/api/guild/777/mod-control/amnesty/{aid}/undo')
check(un.status_code == 200 and un.get_json()['restored'] == 2, 'откат вернул варны')
check(client.post(f'/api/guild/777/mod-control/amnesty/{aid}/undo').status_code == 400,
      'двойной откат — 400')
check(client.post('/api/guild/777/mod-control/amnesty/999/undo').status_code == 404,
      'откат несуществующей — 404')
no_warns = client.post('/api/guild/777/mod-control/amnesty', json={'user_id': '424242'})
check(no_warns.status_code == 400 and no_warns.get_json()['error'] == 'У участника нет варнов',
      'честный отказ без варнов')
check(len(client.get(OV).get_json()['risk']['items']) == 2, 'после отката картина восстановлена')

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/mod_control.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('mcKpis', 'mcRisk', 'mcRadar', 'mcReasons', 'mcAmnesty', 'mcTabs', 'mcAmnestyId'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check('/warn-config' in tpl, 'ссылка на настройку порогов')
check('uxUndo' in tpl, 'амнистия с 6.5-секундным откатом через uxUndo')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/mod-control' in paths, 'пункт меню «Мод-контроль» есть')
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/mod-control' in mod_pages, 'пункт в группе «Модерация»')
check('/mod-control' not in PM.PAGE_COGS, 'файловая страница — не в PAGE_COGS')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('mod_control') >= 1, 'модуль зарегистрирован в routes_extra (импорт + список)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
