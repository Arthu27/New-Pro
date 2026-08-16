# -*- coding: utf-8 -*-
"""Панель «Апелляции» (идеи #116-120).

Валидация и решения 1:1 с cogs/appeals.py (тексты create/resolve), очередь
как в /апелляции список, история с фильтрами, офлайн-разбор без побочки,
канал карточек, CSV, права, шаблон, меню.

Запуск: python3 tests/test_appeals_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_appeals_test_')
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


from db import GuildData  # noqa: E402
from cogs import appeals as AP  # noqa: E402
from web.routes import appeals_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
T = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)

print('== 1. Чистые функции кога уважены ==')
st = AP.empty_state()
item, err = AP.create_appeal(st, 1, 'Короткий', 'мало', T)
check(item is None and err == 'слишком коротко — напишите подробнее (минимум 10 символов)',
      'короткий текст — слова кога')
item, err = AP.create_appeal(st, 1, 'Длинный', 'х' * 501, T)
check(item is None and err == 'максимум 500 символов', 'перебор — слова кога')
st = AP.empty_state()
for i in range(3):
    AP.create_appeal(st, 1, 'Настырный', f'апелляция номер {i} прошу разбана', T)
item, err = AP.create_appeal(st, 1, 'Настырный', 'ещё одна просьба о разбане', T)
check(item is None and err == 'уже есть 3 открытых — дождитесь решения',
      'не больше трёх открытых')
check(st['next_id'] == 4 and len(AP.pending_items(st)) == 3, 'конвейер цел')

print('== 2. Фикстура журнала ==')
st = AP.empty_state()
AP.create_appeal(st, 111, 'АннаПро', 'прошу разбанить, бан навесили по ошибке', T)
AP.create_appeal(st, 222, 'Борис', 'обещаю вести себя хорошо; и не флудить',
                 T.replace(day=12, hour=11))
old3, _ = AP.create_appeal(st, 333, 'Вера', 'старое дело хочу закрыть', T.replace(day=9))
AP.resolve_appeal(st, old3['id'], True, 'МодАдмин', T.replace(day=13, hour=9), reply='исправился')
old4, _ = AP.create_appeal(st, 444, 'Гриша', 'просил пощады за капс', T.replace(day=8))
AP.resolve_appeal(st, old4['id'], False, 'МодАдмин', T.replace(day=14, hour=9),
                  reply='приходите через месяц')
GuildData('appeals').set('777', 'state', st)

stats = SP.overview_stats(st)
check(stats['pending'] == 2 and stats['accepted'] == 1 and stats['rejected'] == 1
      and stats['total'] == 4, 'сводка по статусам')
check(stats['last_resolved']['id'] == 4 and stats['last_resolved']['status_label'] == 'отклонена',
      'последнее решение — #4')
pend = SP.pending_view(st)
check([p['id'] for p in pend] == [1, 2], 'очередь в порядке подачи')
check(pend[0]['card_text'] == AP.fmt_card_text(st['items'][0]),
      'текст карточки — как у кога')
check(pend[0]['created_at'] == '2026-08-10 10:00', 'дата читаемая')

print('== 3. История и фильтры ==')
hist = SP.history_view(st)
check([h['id'] for h in hist] == [2, 1, 3, 4], 'свежие по подаче сверху')
check([h['id'] for h in SP.history_view(st, status='accepted')] == [3], 'только принятые')
check([h['id'] for h in SP.history_view(st, query='месяц')] == [4], 'поиск по комментарию')
check([h['id'] for h in SP.history_view(st, query='444')] == [4], 'поиск по ID')
check([h['id'] for h in SP.history_view(st, query='бан')] == [1], 'поиск по тексту')
check([h['id'] for h in SP.history_view(st, status='rejected', query='капс')] == [4],
      'фильтры складываются')
check(SP.history_view(st, status='мимо') == hist, 'кривой статус игнорируется')

print('== 4. Разбор офлайн-режима ==')
eff = SP.apply_side_effects(None, '777', {'id': 9, 'user_id': 1}, True)
check(eff == {'offline': True, 'unbanned': None, 'dm_attempted': False},
      'бот офлайн — побочка честно не сделана')
ok, err, code, payload = SP.resolve_panel(None, '777', 1, True, 'Панелька',
                                          now=T.replace(day=15))
check(ok and payload['status_text'] == 'принята', 'принята офлайн (без «разбанен»)')
check(payload['effects']['offline'] is True, 'эффекты подписаны')
check(payload['item']['reviewed_by'] == 'Панелька', 'кто решил — записан')
ok, err, code, _ = SP.resolve_panel(None, '777', 1, True, 'Панелька', now=T)
check(not ok and code == 409 and err == 'апелляция #1 уже рассмотрена (accepted)',
      'повтор — текст и 409')
ok, err, code, _ = SP.resolve_panel(None, '777', 99, False, 'Панелька', now=T)
check(not ok and code == 404 and err == 'апелляция #99 не найдена', 'нет такой — 404')
ok, err, code, payload = SP.resolve_panel(None, '777', 2, False, 'Панелька',
                                          reply='  пока рано  ', now=T)
check(ok and payload['status_text'] == 'отклонена'
      and payload['item']['reply'] == 'пока рано', 'отказ с комментарием (обрезан)')
saved = GuildData('appeals').get('777', 'state', {})
check(saved['items'][0]['status'] == 'accepted' and saved['items'][1]['status'] == 'rejected',
      'решения сохранились в общее хранилище')

print('== 5. Канал и CSV ==')
ok, err, cid = SP.set_log_channel(AP.empty_state(), 'abc')
check(not ok and err == 'Некорректный ID канала', 'буквы — текст панели')
ok, err, cid = SP.set_log_channel(AP.empty_state(), '-5')
check(not ok and err == 'Некорректный ID канала', 'минус — туда же')
st2 = AP.empty_state()
ok, _, cid = SP.set_log_channel(st2, ' 555 ')
check(ok and st2['log_channel_id'] == 555, 'ID сохранён числом, как у кога')
rows = SP.appeals_csv_rows(GuildData('appeals').get('777', 'state', {}))
check(len(rows) == 4 and rows[0][3] == 'принята' and rows[1][3] == 'отклонена'
      and rows[2][3] == 'принята' and rows[3][3] == 'отклонена', 'статусы словами')
check(rows[0][6] == '2026-08-15 10:00' and rows[0][5] == 'Панелька', 'решения в выгрузке')

print('== 6. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


OV = '/api/guild/777/appeals/overview'
check(client.get('/appeals').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/appeals')
check(page.status_code == 200 and 'Апелляции' in page.get_data(as_text=True),
      'mod открывает страницу')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod без права решений')
check(ov['stats']['pending'] == 0 and ov['pending'] == [],
      'после разборов очередь чиста')
check(ov['readiness'] == {'log_channel_id': 0, 'channel_name': '', 'falls_to': ''},
      'офлайн: канал не подтверждён')
check([p['id'] for p in ov['pending']] == [], 'очередь в JSON — пустой список')
r = client.get('/api/guild/777/appeals/history?status=rejected')
check(len(r.get_json()['items']) == 2, 'история по API с фильтром')
r = client.post('/api/guild/777/appeals/resolve', json={'appeal_id': '3', 'accept': True})
check(r.status_code == 403, 'mod не решает')
login('admin')
r = client.post('/api/guild/777/appeals/resolve', json={'appeal_id': 'ку', 'accept': True})
check(r.status_code == 400 and r.get_json()['error'] == 'Некорректный номер апелляции', 'битый ID')
r = client.post('/api/guild/777/appeals/resolve', json={'appeal_id': '4', 'accept': 'да'})
check(r.status_code == 400 and 'true или false' in r.get_json()['error'], 'accept строгий')
r = client.post('/api/guild/777/appeals/resolve', json={'appeal_id': '99', 'accept': True})
check(r.status_code == 404, 'нет такой через API')
r = client.post('/api/guild/777/appeals/channel', json={'channel_id': '777555'})
check(r.get_json()['success'] and 'бот офлайн' in r.get_json()['message'],
      'канал сохранён с честной оговоркой')
ov = client.get(OV).get_json()
check(ov['readiness']['log_channel_id'] == 777555, 'канал виден в обзоре')

csv_r = client.get('/api/guild/777/appeals/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'appeals_777.csv' in csv_r.headers.get('Content-Disposition', ''), 'имя файла')
check(body.startswith('\ufeffid;user_id'), 'BOM + шапка')
check('обещаю вести себя хорошо, и не флудить' in body, 'разделитель в тексте заменён')
lines = body.strip().split('\n')
check(len(lines) == 5, f'шапка + 4 записи (пришло {len(lines)})')
login('uye')
check(client.get('/api/guild/777/appeals/export.csv').status_code == 403, 'uye не выгружает')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/appeals.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('apQueue', 'apHistory', 'apReady', 'apCsv', 'apChanSave', 'apKpis'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/resolve'" in tpl and "'/channel'" in tpl
      and '/export.csv' in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/appeals' in mod_pages, 'пункт меню «Апелляции» в «Модерации»')
check(PM.PAGE_COGS.get('/appeals') == ('appeals',), 'appeals-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('appeals_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
