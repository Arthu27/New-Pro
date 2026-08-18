# -*- coding: utf-8 -*-
"""SLA-контроль (идеи #161-165).

Багфикс сервиса: SLACalculator.calculate_sla (именно его зовёт команда
/sla-status — метода не было); id политик за максимальным номером, чтобы
удаление в середине не дало дубликат. Форматтер интервалов, рабочие часы,
условия политик. Панельные флоу на тех же синглтонах, что у кога: создание
sla-create, лимиты через update_policy (пусто — не трогай, 0 — сними),
статус тикета словами /sla-status («Тикет не найден!», «Нарушён», «В рамках
SLA», «Нет дедлайнов», «Нет политики»), лента нарушений /sla-breaches со
сводкой, перепроверка детектором (битые даты честно пропускаются), отчёт
о соответствии за период, CSV. API, права, шаблон, меню.

Запуск: python3 tests/test_sla_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_sla_test_')
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


# ── Фикстуры тикетов (читаются живьём при каждом вызове, кэша нет) ──────
NOW = datetime.now().replace(microsecond=0)
C1 = NOW - timedelta(days=10)          # T-1: оба дедлайна давно сорваны
C2 = NOW - timedelta(minutes=30)       # T-2: отвечен, решение ещё горит
C3 = NOW - timedelta(hours=1)          # T-3: закрыт, medium без лимитов
C4 = NOW - timedelta(hours=2)          # T-4: ни одна политика не подходит
C5 = NOW - timedelta(days=2)           # T-5: aware-дата — сервис её не стерпит
json.dump([
    {'id': 'T-1', 'category': 'support', 'priority': 'high',
     'status': 'open', 'created_at': C1.isoformat()},
    {'id': 'T-2', 'category': 'billing', 'priority': 'high',
     'status': 'open', 'created_at': C2.isoformat(),
     'first_response_at': (NOW - timedelta(minutes=10)).isoformat()},
    {'id': 'T-3', 'category': 'support', 'priority': 'medium',
     'status': 'closed', 'created_at': C3.isoformat()},
    {'id': 'T-4', 'category': 'other', 'priority': 'high',
     'status': 'open', 'created_at': C4.isoformat()},
    {'id': 'T-5', 'category': 'support', 'priority': 'high',
     'status': 'open', 'created_at': C5.isoformat() + '+00:00'},
], open('data/customer_tickets.json', 'w', encoding='utf-8'), ensure_ascii=False)

from services.sla_management import (  # noqa: E402
    SLAManager, SLACalculator, SLAPolicy, sla_manager, sla_reporter,
)
from web.routes import sla_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 1. Багфикс сервиса: calculate_sla, которого ждёт /sla-status ==')
import cogs.sla_cog as SC  # noqa: E402
check(hasattr(SC.sla_calculator, 'calculate_sla'), 'у синглтона кога метод на месте')

m3 = SLAManager()  # файла политик ещё нет — память пустая
p1 = SLAPolicy('sla_1', 'Базовый SLA', 'поддержка')
p1.add_condition('category', 'equals', 'support')
p1.set_response_time('high', 60)
p1.set_resolution_time('high', 240)
m3.policies['sla_1'] = p1
calc = SLACalculator(m3)

t_open = {'id': 'X-1', 'category': 'support', 'priority': 'high',
          'status': 'open', 'created_at': C1.isoformat()}
info = calc.calculate_sla(t_open)
need = {'policy_name', 'policy_id', 'priority', 'status', 'response_deadline',
        'resolution_deadline', 'response_breached', 'resolution_breached',
        'time_remaining'}
check(need <= set(info), 'все ключи, что читает ког, выданы')
check(info['status'] == 'Нарушён' and info['response_breached']
      and info['resolution_breached'], 'два срыва — «Нарушён»')
check(info['time_remaining'] == 'просрочено на 9 д 23 ч',
      'просрочка словами, детерминированно')
check(info['response_deadline'] == (C1 + timedelta(minutes=60)).isoformat()
      and info['response_deadline'][:16] and info['priority'] == 'high',
      'дедлайн ответа — iso, ког его режет [:16]')

t_ans = {'id': 'X-2', 'category': 'support', 'priority': 'high',
         'status': 'open', 'created_at': C2.isoformat(),
         'first_response_at': (NOW - timedelta(minutes=10)).isoformat()}
info = calc.calculate_sla(t_ans)
check(info['status'] == 'В рамках SLA' and info['response_breached'] is False
      and re.match(r'^3 ч (29|30) мин$', info['time_remaining'] or ''),
      'отвечен: ответ не карается, горит решение')

t_med = {'id': 'X-3', 'category': 'support', 'priority': 'medium',
         'status': 'closed', 'created_at': C3.isoformat()}
check(calc.calculate_sla(t_med)['status'] == 'Нет дедлайнов',
      'приоритет без лимитов — «Нет дедлайнов»')
t_none = {'id': 'X-4', 'category': 'other', 'priority': 'high',
          'status': 'open', 'created_at': C4.isoformat()}
info = calc.calculate_sla(t_none)
check(info['status'] == 'Нет политики' and info['policy_id'] is None
      and info['policy_name'] == 'Нет политики', 'без политики — её слова')
t_cl = {'id': 'X-5', 'category': 'support', 'priority': 'high',
        'status': 'closed', 'created_at': C2.isoformat()}
check(calc.calculate_sla(t_cl)['status'] == 'Закрыт в срок',
      'закрытый без срыва — «Закрыт в срок»')

check(SLACalculator._fmt_duration(timedelta(hours=2, minutes=15)) == '2 ч 15 мин'
      and SLACalculator._fmt_duration(timedelta(minutes=45)) == '45 мин'
      and SLACalculator._fmt_duration(timedelta(hours=26)) == '1 д 2 ч',
      'форматтер интервалов')

pb = SLAPolicy('sla_b', 'Офисные часы')
pb.set_response_time('high', 120)
pb.set_business_hours(9, 18)
fri = NOW.replace(hour=17, minute=0, second=0, microsecond=0)
fri += timedelta(days=(4 - fri.weekday()) % 7)
got = calc.calculate_response_deadline(
    {'priority': 'high', 'created_at': fri.isoformat()}, pb)
check(got == (fri + timedelta(days=3)).replace(hour=10),
      'рабочие часы: пт 17:00 + 120 мин = пн 10:00')

check(p1.matches_ticket({'category': 'support'}) is True
      and p1.matches_ticket({'category': 'billing'}) is False, 'equals')
q = SLAPolicy('q', 'Q')
q.add_condition('status', 'not_equals', 'closed')
q.add_condition('priority', 'in', ['high', 'critical'])
q.add_condition('subject', 'contains', 'оплат')
check(q.matches_ticket({'status': 'open', 'priority': 'high',
                        'subject': 'вопрос про оплату'}) is True,
      'not_equals + in + contains — все трое')
check(q.matches_ticket({'status': 'closed', 'priority': 'high',
                        'subject': 'оплата'}) is False
      and q.matches_ticket({'status': 'open', 'priority': 'low',
                            'subject': 'оплата'}) is False,
      'каждое условие заворачивает')

print('== 2. id политик за максимальным номером ==')
m2 = SLAManager()  # файл пустой — пишет только свою память
a = m2.create_policy('A')
b = m2.create_policy('B')
m2.delete_policy(a.policy_id)
c = m2.create_policy('C')
check((a.policy_id, b.policy_id, c.policy_id) == ('sla_1', 'sla_2', 'sla_3'),
      'после удаления нового дубликата нет')
m2.policies.clear()
m2._save_policies()  # вернуть файл в «{}» до старта синглтонных флоу

print('== 3. Флоу политик на синглтоне кога ==')
ok, err, _ = SP.create_flow('', 'x')
check(not ok and err == SP.ERR_NAME, 'пустое название — отказ')
ok, err, p = SP.create_flow('Базовый SLA', 'поддержка')
check(ok and p['message'] == 'Политика «Базовый SLA» создана. ID: sla_1.',
      'создание — как /sla-create')
ok, err, p = SP.create_flow('Биллинг', 'деньги')
check(ok and p['message'].endswith('ID: sla_2.'), 'вторая политика')
sla_manager.update_policy('sla_1', conditions=[
    {'field': 'category', 'operator': 'equals', 'value': 'support'}])
sla_manager.update_policy('sla_2', conditions=[
    {'field': 'category', 'operator': 'equals', 'value': 'billing'}])
stored = json.load(open('data/sla_policies.json', encoding='utf-8'))
check('sla_1' in stored and stored['sla_1']['conditions'][0]['value'] == 'support',
      'файл общий — условия сохранены')
ok, err, _ = SP.configure_flow('sla_99', 'high', '60', '240')
check(not ok and err == SP.ERR_POLICY, 'чужая политика — слова /sla-info')
ok, err, _ = SP.configure_flow('sla_1', 'high', 'мусор', '')
check(not ok and err == SP.ERR_MINUTES, 'мусорные минуты — отказ')
ok, err, _ = SP.configure_flow('sla_1', 'high', '', '')
check(not ok and err == SP.ERR_LIMITS, 'два пустых поля — нечего менять')
ok, err, p = SP.configure_flow('sla_1', 'high', '60', '240')
check(ok and p['message'] == 'Политика «Базовый SLA»: high — ответ 60 мин, '
                             'решение 240 мин.', 'лимиты выставлены')
ok, err, p = SP.configure_flow('sla_2', 'high', '45', '180')
check(ok and sla_manager.get_policy('sla_2').resolution_times['high'] == 180,
      'вторая политика тоже')
ok, err, p = SP.create_flow('Времянка', '')
check(ok and p['message'].endswith('ID: sla_3.'), 'времянка — sla_3')
ok, err, p = SP.configure_flow('sla_3', 'low', '30', '0')
check(ok and p['message'] == 'Политика «Времянка»: low — ответ 30 мин, '
                             'решение снят.'
      and sla_manager.get_policy('sla_3').response_times == {'low': 30}
      and sla_manager.get_policy('sla_3').resolution_times == {},
      '0 — снять лимит, пусто — не тронуть')
ok, err, p = SP.delete_flow('sla_3')
check(ok and p['message'] == 'Политика «Времянка» удалена. Всего политик: 2.',
      'удаление — со счётчиком')
ok, err, _ = SP.delete_flow('sla_3')
check(not ok and err == SP.ERR_POLICY, 'повторное удаление — слова команды')
check(SP._minutes(None) == (None, None) and SP._minutes(' 45 ') == (45, None)
      and SP._minutes('x') == (None, SP.ERR_MINUTES), 'парсер минут')

print('== 4. Статус тикета — /sla-status ==')
ok, err, _ = SP.status_flow('')
check(not ok and err == SP.ERR_TICKET, 'пустой id — слова команды')
ok, err, _ = SP.status_flow('ZZZ')
check(not ok and err == SP.ERR_TICKET, 'нет такого — слова команды')
ok, err, v = SP.status_flow('T-1')
check(ok and v['status'] == 'Нарушён' and v['policy_name'] == 'Базовый SLA'
      and v['ticket_status'] == 'open', 'T-1 сорван целиком')
check(v['response_deadline'] == (C1 + timedelta(minutes=60)).isoformat(),
      'дедлайн ответа пересчитан руками')
ok, err, v = SP.status_flow('T-2')
check(ok and v['status'] == 'В рамках SLA'
      and re.match(r'^2 ч (29|30) мин$', v['time_remaining'])
      and v['response_deadline'] == (C2 + timedelta(minutes=45)).isoformat(),
      'T-2: биллинг-политика, отвечен, решение горит')
ok, err, v = SP.status_flow('T-3')
check(ok and v['status'] == 'Нет дедлайнов'
      and v['response_deadline'] is None, 'T-3: medium без лимитов')
ok, err, v = SP.status_flow('T-4')
check(ok and v['status'] == 'Нет политики', 'T-4: политика не подошла')
ok, err, _ = SP.status_flow('T-5')
check(not ok and err == SP.ERR_CALC, 'T-5: aware-дата честно поймана')

print('== 5. Лента нарушений и перепроверка ==')
v0 = SP.breaches_view()
check(v0['rows'] == [] and v0['summary']['total_breaches'] == 0
      and v0['empty_note'] == 'Нарушение SLA не найдено!',
      'пустая лента — слова /sla-breaches')
scan = SP.scan_flow()
check(scan['checked'] == 5 and scan['skipped'] == 1 and scan['found'] == 2,
      'перепроверка: 5 тикетов, 1 битый, 2 нарушения')
saved = json.load(open('data/sla_breaches.json', encoding='utf-8'))
check('T-1' in saved and len(saved['T-1']) == 2, 'нарушения дописаны в общий файл')
v = SP.breaches_view()
check(len(v['rows']) == 2
      and {r['type_label'] for r in v['rows']} == {'время ответа', 'время решения'}
      and all(r['ticket_id'] == 'T-1' and r['policy_name'] == 'Базовый SLA'
              for r in v['rows']), 'строки ленты')
s = v['summary']
check(s['total_breaches'] == 2 and s['response_breaches'] == 1
      and s['resolution_breaches'] == 1 and s['by_policy'] == {'sla_1': 2},
      'сводка reporter-а')

print('== 6. Отчёт о соответствии за период ==')
ok, err, rep = SP.report_flow('abc')
check(ok and rep['days'] == 30, 'мусорные дни — дефолт 30')
check(rep['total_tickets'] == 4 and rep['response_met'] == 3
      and rep['resolution_met'] == 3, 'из 5 тикетов один битый отброшен')
check(rep['response_compliance'] == 75.0 and rep['resolution_compliance'] == 75.0
      and rep['breached_tickets'] == 1 and rep['breach_rate'] == 25.0,
      'проценты пересчитаны руками')
check(rep['period']['start'].startswith((NOW - timedelta(days=30))
                                        .strftime('%Y-%m-%d')),
      'период эхом — как в сервисе')
ok, err, rep7 = SP.report_flow('7')
check(ok and rep7['total_tickets'] == 3 and rep7['response_compliance'] == 100.0
      and rep7['breached_tickets'] == 0 and rep7['breach_rate'] == 0.0,
      'за неделю — без нарушений')
rep0 = sla_reporter.generate_compliance_report(
    [], NOW - timedelta(days=1), NOW)
check(rep0['total_tickets'] == 0 and rep0['response_compliance'] == 100
      and 'breach_rate' not in rep0, 'пустой вход сервиса — 100%, без rate')
ok, err, rep_c = SP.report_flow('99999')
check(ok and rep_c['days'] == 3650, 'потолок периода — 3650 дней')

print('== 7. Строки CSV ==')
rows = SP.policies_csv_rows()
check(rows == [('sla_1', 'Базовый SLA', 'поддержка', 'high', 60, 240),
               ('sla_2', 'Биллинг', 'деньги', 'high', 45, 180)],
      'политики: строка на приоритет')
brows = SP.breaches_csv_rows()
check(len(brows) == 2 and brows[0][0] == 'T-1'
      and brows[0][5] == 'Базовый SLA', 'нарушения: две строки T-1')
check(SP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 8. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


VW = '/api/guild/777/sla/view'
check(client.get('/sla').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(VW).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(VW).status_code == 403, 'uye не смотрит')
check(client.get('/api/guild/777/sla/policies.csv').status_code == 403,
      'uye не выгружает')
login('mod')
page = client.get('/sla')
check(page.status_code == 200 and 'SLA-контроль' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(VW).get_json()
check(d['success'] and d['kpi'] == {'policies': 2, 'tickets': 5, 'breaches': 2}
      and len(d['policies']) == 2 and len(d['breaches']['rows']) == 2
      and d['can_edit'] is False, 'вид для mod — все цифры руками')
d = client.get('/api/guild/777/sla/ticket?tid=T-1').get_json()
check(d['success'] and d['status'] == 'Нарушён', 'статус тикета через API')
r = client.get('/api/guild/777/sla/ticket?tid=мусор')
check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_TICKET,
      'мусорный тикет — 400 с текстом команды')
r = client.get('/api/guild/777/sla/ticket?tid=T-5')
check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_CALC,
      'битая дата — 400, честная ошибка')
d = client.get('/api/guild/777/sla/report?days=30').get_json()
check(d['success'] and d['total_tickets'] == 4 and d['breach_rate'] == 25.0,
      'отчёт через API')
check(client.post('/api/guild/777/sla/create', json={'name': 'x'}).status_code == 403,
      'mod не создаёт политики')
check(client.post('/api/guild/777/sla/scan', json={}).status_code == 403,
      'mod не гоняет перепроверку')
login('admin')
r = client.post('/api/guild/777/sla/create', json={'name': 'АИ-политика',
                                                   'description': 'x'})
check(r.status_code == 200 and 'создана. ID: sla_3.' in r.get_json()['message'],
      'admin создал — id за максимумом')
r = client.post('/api/guild/777/sla/configure',
                json={'policy_id': 'sla_3', 'priority': 'medium',
                      'response_minutes': '15', 'resolution_minutes': ''})
check(r.status_code == 200
      and 'medium — ответ 15 мин.' in r.get_json()['message'],
      'admin настроил, пустое поле не тронуто')
r = client.post('/api/guild/777/sla/delete', json={'policy_id': 'sla_3'})
check(r.status_code == 200 and 'Всего политик: 2.' in r.get_json()['message'],
      'admin убрал')
r = client.post('/api/guild/777/sla/delete', json={'policy_id': 'sla_3'})
check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_POLICY,
      'повторное — 400 словами команды')
r = client.post('/api/guild/777/sla/scan', json={})
check(r.status_code == 200 and r.get_json()['found'] == 2,
      'admin перепроверил — столько же нарушений')
ex = client.get('/api/guild/777/sla/policies.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200
      and ex.headers['Content-Disposition'].endswith('sla_policies_777.csv'),
      'CSV политик: имя файла')
check(body.startswith('\ufeffpolicy_id;name;description;priority;'
                      'response_min;resolution_min'),
      'CSV политик: BOM и шапка')
check(len(body.strip().split('\n')) == 3, 'CSV политик: 2 строки + шапка')
ex = client.get('/api/guild/777/sla/breaches.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200
      and ex.headers['Content-Disposition'].endswith('sla_breaches_777.csv')
      and len(body.strip().split('\n')) == 3, 'CSV нарушений: имя и 2 строки')
login('mod')

print('== 9. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/sla.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/sla_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('slKpis', 'slNew', 'slName', 'slDesc', 'slCreate', 'slNewMsg',
            'slCfg', 'slCfgPolicy', 'slCfgPrio', 'slCfgResp', 'slCfgRes',
            'slCfgGo', 'slCfgMsg', 'slPolicies', 'slBreaches', 'slScanRow',
            'slScan', 'slScanMsg', 'slTid', 'slTicketGo', 'slTicket',
            'slTicketMsg', 'slDays', 'slReportGo', 'slReport', 'slRepMsg',
            'slCsvP', 'slCsvB'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/view'", "'/ticket?tid='", "'/report?days='", "'/create'",
             "'/configure'", "'/delete'", "'/scan'", "'/policies.csv'",
             "'/breaches.csv'"):
    check(path in tpl, f'путь {path} в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
tick_pages = [pg['path'] for g in PM.MENU if g['key'] == 'tickets'
              for pg in g['pages']]
check('/sla' in tick_pages, 'пункт меню «SLA-контроль» в «Тикетах»')
check(PM.PAGE_COGS.get('/sla') == ('sla_cog',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('sla_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
