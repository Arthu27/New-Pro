# -*- coding: utf-8 -*-
"""Лента инцидентов (идеи #136-140).

Выборка окна 1:1 с /replay (кламп 5..1440, дефолт 30; метки без TZ = UTC;
битые пропускаем; uid ищется подстрокой в JSON-блобе; сортировка; хвост 14),
детали строк через RP._detail_text, подписи категорий — CATEGORIES логов,
пульс окна, CSV, тихий текст словами бота, API, права, шаблон, меню.

Запуск: python3 tests/test_replay_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_replay_test_')
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


from cogs import replay as RP  # noqa: E402
from web.routes import replay_panel as PL  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
UTC = timezone.utc
NOW = datetime.now(UTC)


def iso(minutes_ago, naive=False):
    ts = NOW - timedelta(minutes=minutes_ago)
    if naive:
        ts = ts.replace(tzinfo=None)
    return ts.isoformat()


audit = {
    '777': [
        {'category': 'member', 'action': 'Участник зашёл',
         'user_name': 'Катя', 'user_id': 111, 'timestamp': iso(25)},
        {'category': 'mod', 'action': 'Блокировка',
         'user_name': 'Вредный', 'user_id': 222, 'mod_name': 'Админ',
         'reason': 'спам', 'until': '2026-08-17T12:00:00+00:00',
         'timestamp': iso(20)},
        {'category': 'message', 'action': 'Сообщение удалено',
         'user_name': 'Катя', 'user_id': 111, 'channel_name': 'общий',
         'content': 'а' * 100, 'timestamp': iso(15)},
        {'category': 'role', 'action': 'Роли изменены',
         'user_name': 'Иван', 'user_id': 333, 'added_roles': ['Модер'],
         'removed_roles': ['Новенький'], 'timestamp': iso(10)},
        {'category': 'channel', 'action': 'Канал создан',
         'channel_name': 'новый-канал', 'name': 'Админ', 'timestamp': iso(5)},
        {'category': 'mod', 'action': 'Битая метка', 'timestamp': 'не-дата'},
        {'category': 'member', 'action': 'Участник вышел',
         'user_name': 'Древний', 'user_id': 444, 'timestamp': iso(200)},
        {'category': 'voice', 'action': 'Зашёл в голос',
         'user_name': 'Катя', 'user_id': 111, 'channel_name': 'Голосовой',
         'timestamp': iso(8, naive=True)},
        {'category': 'mod', 'action': 'Предупреждение',
         'user_name': 'Иван', 'user_id': 333, 'mod_name': '—',
         'reason': '—', 'timestamp': iso(3)},
        {'category': 'guild', 'timestamp': iso(2)},
    ],
    '888': [
        {'category': 'mod', 'action': f'Действие {i:02d}', 'user_id': 500 + i,
         'timestamp': iso(21 - i)}
        for i in range(1, 21)
    ],
}
json.dump(audit, open('data/audit_log.json', 'w', encoding='utf-8'),
          ensure_ascii=False)

print('== 1. Выборка окна 1:1 с /replay ==')
rows30, m = PL.load_rows('777', 30)
check(m == 30 and len(rows30) == 8, f'окно 30 мин: 8 свежих из 10 (пришло {len(rows30)})')
acts = [ev.get('action', 'Событие') for _ts, ev in rows30]
check('Участник вышел' not in acts and 'Битая метка' not in acts,
      'старое и битая метка отсеяны')
check('Зашёл в голос' in acts, 'метка без TZ посчитана как UTC')
tss = [ts for ts, _ev in rows30]
check(tss == sorted(tss), 'сортировка по времени')
rows300, _m = PL.load_rows('777', 300)
check(len(rows300) == 9, f'окно 300 мин: старое вернулось (пришло {len(rows300)})')
for raw, want in ((0, 30), (-10, 5), (9999, 1440), ('мусор', 30), (None, 30)):
    _r, got = PL.load_rows('777', raw)
    check(got == want, f'кламп окна: {raw!r} -> {got}')
rows_uid, _m = PL.load_rows('777', 30, uid='111')
check(len(rows_uid) == 3, f'фильтр по участнику: 3 следа Кати (пришло {len(rows_uid)})')
rows_none, _m = PL.load_rows('777', 30, uid='999')
check(len(rows_none) == 0, 'чужой ID — пусто')

print('== 2. Лента и детали строк ==')
feed = PL.feed_view(rows30)
check(len(feed) == 8, 'лента отдала все 8')
by_action = {e['label']: e for e in feed}
check(by_action['Блокировка']['detail'] ==
      'Вредный · Мод: Админ · Причина: спам · до 2026-08-17 12:00',
      'детали бана через _detail_text')
check(by_action['Сообщение удалено']['detail'] ==
      'Катя · #общий · «' + 'а' * 70 + '»', 'контент обрезан до 70, канал с #')
check(by_action['Роли изменены']['detail'] == 'Иван · + Модер · − Новенький',
      'роли с + и −')
check(by_action['Канал создан']['detail'] == 'Админ · #новый-канал',
      'имя из name-fallback')
check(by_action['Предупреждение']['detail'] == 'Иван',
      'прочерк-поля («—») пропущены')
check(by_action['Событие']['detail'] == '' and by_action['Событие']['cat'] == 'guild',
      'пустое событие: экшен по умолчанию, деталей нет')
check(by_action['Блокировка']['cat_label'] == 'Модерация'
      and by_action['Зашёл в голос']['cat_label'] == 'Голос',
      'подписи категорий из CATEGORIES логов')
check(by_action['Событие']['cat_label'] == 'Guild',
      'неизвестная категория — capitalize')
check(re.match(r'^\d{2}:\d{2}$', feed[0]['time']) is not None, 'время %H:%M')
rows888, _m = PL.load_rows('888', 60)
feed888 = PL.feed_view(rows888)
check(len(rows888) == 20 and len(feed888) == 14, 'хвост ленты — 14 как в карточке')
check(feed888[0]['label'] == 'Действие 07' and feed888[-1]['label'] == 'Действие 20',
      'хвост — самые свежие')

print('== 3. Пульс окна ==')
p = PL.pulse(rows30, 30)
check(p['total'] == 8 and p['per_hour'] == 16.0, f'8 событий, темп 16/час (пришло {p})')
check(p['by_category'][0] == {'cat': 'mod', 'label': 'Модерация', 'count': 2},
      'топ-категория — модерация')
check(len(p['top_actions']) == 5, 'топ действий ограничен пятью')
check(PL.pulse([], 30)['per_hour'] == 0.0 and PL.pulse([], 30)['by_category'] == [],
      'пустое окно — нули')

print('== 4. CSV ==')
check(PL._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся от ; и переносов')
rows_csv = PL.csv_rows(rows888)
check(len(rows_csv) == 20, 'в CSV всё окно, не хвост')
check(rows_csv[0][1] == 'mod' and rows_csv[0][2] == 'Действие 01',
      'сырые ключи категорий в CSV')

print('== 5. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


FEED = '/api/guild/777/replay/feed'
check(client.get('/replay').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(FEED).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/replay').status_code == 403, 'uye не видит страницу')
check(client.get(FEED).status_code == 403, 'uye не видит API')
login('mod')
page = client.get('/replay')
check(page.status_code == 200 and 'Лента инцидентов' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(FEED).get_json()
check(d['success'] and d['minutes'] == 30 and d['quiet'] is False,
      'дефолтное окно 30 мин')
check(len(d['feed']) == 8 and d['pulse']['total'] == 8, 'лента и пульс через API')
d5 = client.get(FEED + '?minutes=2').get_json()
check(d5['minutes'] == 5, 'API клампит окно снизу')
du = client.get(FEED + '?user=111').get_json()
check(du['pulse']['total'] == 3, 'API фильтрует по участнику')
dbad = client.get(FEED + '?user=абракадабра').get_json()
check(dbad['success'] and dbad['pulse']['total'] == 8,
      'битый ID участника мягко игнорируется')
dq = client.get('/api/guild/555/replay/feed').get_json()
want_quiet = ('За последние 30 мин событий нет. Бот ведёт летопись, '
              'пока он в сети — старые окна могут быть пустыми.')
check(dq['quiet'] is True and dq['quiet_text'] == want_quiet,
      'тихий текст — слова команды без разметки')
ex = client.get('/api/guild/777/replay/export.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and ex.headers['Content-Disposition'].endswith(
      'replay_30m_777.csv'), 'имя файла с окном и гильдией')
check(body.startswith('\ufefftimestamp;category;action;detail'), 'BOM и шапка')
check(len(body.strip().split('\n')) == 9, f'шапка + 8 строк (пришло {len(body.strip().splitlines())})')
ex5 = client.get('/api/guild/777/replay/export.csv?minutes=2')
check(ex5.headers['Content-Disposition'].endswith('replay_5m_777.csv'),
      'имя файла после клампа окна')
login('uye')
check(client.get('/api/guild/777/replay/export.csv').status_code == 403,
      'uye не выгружает')
login('mod')

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/replay.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/replay_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('rpPulse', 'rpPreset', 'rpMin', 'rpUser', 'rpGo', 'rpCsv',
            'rpChips', 'rpFeed', 'rpTop'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/feed?'" in tpl and "'/export.csv?'" in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
logs_pages = [pg['path'] for g in PM.MENU if g['key'] == 'logs' for pg in g['pages']]
check('/replay' in logs_pages, 'пункт меню «Инцидент-лента» в «Логах»')
check(PM.PAGE_COGS.get('/replay') == ('replay',), 'replay-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('replay_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
