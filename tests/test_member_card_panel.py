# -*- coding: utf-8 -*-
"""Карточка участника 360° (идеи #106-110).

Активность/ранги 1:1 с ProfileCog._data (уровень из gamification, сообщения/войс
из leaderboard + voice_stats, баланс/ранги по таблицам кога), карма через чистые
функции кога, варны из зеркала, ДР — по num-формуле schedule, автодополнение
из аудита+ДР, CSV с BOM, права. Отдельной страницы больше нет: досье живёт
перетаскиваемым окном в «Пользователях» (users.html + static/member_card.*),
в меню и PAGE_COGS путь отвязан, модуль API зарегистрирован.

Запуск: python3 tests/test_member_card_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_mcard_test_')
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


NOW = datetime.now(timezone.utc)
TODAY_MD = f'{NOW.month:02d}-{NOW.day:02d}'
# та же грубая формула кога, что в schedule: num = m*100+d, минус -> +1200
DD_NUM = 101 - (NOW.month * 100 + NOW.day)
if DD_NUM < 0:
    DD_NUM += 1200

# ── файловые фикстуры (читаются на каждый вызов, как у бота) ─────────────────
json.dump({'messages': {'111': 100, '222': 50}, 'voice_minutes': {'111': 2}},
          open('data/leaderboard_777.json', 'w', encoding='utf-8'))
json.dump({'111': {'date': TODAY_MD, 'name': 'Алиса'},
           '333': {'date': '01-01', 'name': 'Вика'}},
          open('data/birthdays_777.json', 'w', encoding='utf-8'))
json.dump({'777': {'111': [
    {'id': 1, 'reason': 'спам;флуд', 'mod': 'ModOne', 'timestamp': '2026-08-01T10:00:00+00:00'},
    {'id': 2, 'reason': 'капс', 'mod': 'ModTwo', 'timestamp': '2026-08-05T11:00:00+00:00'},
    {'id': 3, 'reason': 'реклама', 'mod': 'ModOne', 'timestamp': '2026-08-12T12:00:00+00:00'}]}},
    open('data/warnings.json', 'w', encoding='utf-8'))
audit = [{'user_id': '111', 'user_name': 'Алиса Мод'},
         {'user_id': '222', 'user_name': 'Борис'}]
audit += [{'user_id': str(900 + i), 'user_name': f'тест {i:02d}'} for i in range(1, 11)]
json.dump({'777': audit}, open('data/audit_log.json', 'w', encoding='utf-8'))

from db import GuildData, UserData  # noqa: E402
from cogs import karma as KC  # noqa: E402
from services.gamification import points_system  # noqa: E402
from web.routes import member_card_panel as MC  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

# войс первичного пути (GuildData) + экономика + очки + карма — всё API бота
GuildData('voice_stats').set(777, '222',
                             {'name': 'Борис', 'avatar': '', 'total_seconds': 600, 'daily': {}})
UserData('economy').set(111, {'balance': 300, 'bank': 200})
UserData('economy').set(222, {'balance': 100})
points_system.add_points('111', 250, 'тест')
kstate = KC.empty_state()
KC.thank(kstate, 222, 111, NOW, 'за помощь')
KC.thank(kstate, 333, 111, NOW)
KC.thank(kstate, 111, 222, NOW)
GuildData('karma').set('777', 'state', kstate)

print('== 1. Активность 1:1 с /profile ==')
a = MC.activity_view(None, '777', '111')
check(a['level'] == 2 and a['xp'] == 250 and a['xp_needed'] == 300,
      'уровень 2 (250 очков), xp_needed = 100 + 2^2*50')
check(a['messages'] == 100, 'сообщения из leaderboard')
check(a['voice_seconds'] == 120, 'войс: нет в трекере — fallback leaderbord *60')
check(a['balance'] == 500, 'баланс кошелёк+банк')
check(a['rank_messages'] == 1 and a['rank_balance'] == 1, 'первый по сообщениям и богатству')
check(a['rank_voice'] == 2, 'вне голосового топа = len+1 (как _rank кога)')
b = MC.activity_view(None, '777', '222')
check(b['voice_seconds'] == 600 and b['rank_voice'] == 1, 'B: войс из трекера, топ-1')
check(b['level'] == 1 and b['xp_needed'] == 150, 'B без очков — новичок')
c = MC.activity_view(None, '777', '333')
check(c['rank_messages'] == 3 and c['rank_voice'] == 2 and c['rank_balance'] == 3,
      '333 везде вне списков = len+1')
check(c['balance'] == 0 and c['messages'] == 0, '333 голые нули')

print('== 2. Карма / варны / ДР ==')
km = MC.karma_view('777', '111')
check(km['score'] == 2 and km['rank'] == 1, 'две благодарности — первое место')
check(km['received'] == 2 and km['given'] == 1, 'журнал: получил 2, отдал 1')
km2 = MC.karma_view('777', '222')
check(km2['score'] == 1 and km2['rank'] == 2, 'B второй')
check(MC.karma_view('777', '333')['rank'] is None, '0 очков — вне топа')
w = MC.warns_view('777', '111')
check(w['count'] == 3 and [x['id'] for x in w['recent']] == [3, 2, 1],
      'варны хвостом, свежие сверху')
check(w['recent'][0]['reason'] == 'реклама' and w['recent'][0]['date'] == '2026-08-12',
      'метки как в /warnings бота')
check(MC.warns_view('777', '222')['count'] == 0, 'B чист')
bd = MC.birthday_view('777', '111')
check(bd['today'] is True and bd['days_until'] == 0, 'ДР сегодня')
bd3 = MC.birthday_view('777', '333')
check(bd3['days_until'] == DD_NUM and bd3['name'] == 'Вика', 'перенос года +1200 как у кога')
check(MC.birthday_view('777', '222') is None, 'у B ДР нет')

print('== 3. Сборка карточки и имена ==')
card = MC.card_view(None, '777', '111')
check(card['member'] is None, 'бот офлайн — live-блока нет')
check(card['name'] == 'Алиса Мод' and card['name_source'] == 'audit',
      'имя из аудита бьёт запись ДР')
check(card['economy'] == {'balance': 300, 'bank': 200, 'total': 500}, 'экономика раздельно')
card3 = MC.card_view(None, '777', '333')
check(card3['name'] == 'Вика' and card3['name_source'] == 'birthday', 'имя из календаря ДР')
card9 = MC.card_view(None, '777', '999')
check(card9['name'] == '' and card9['name_source'] == '' and card9['birthday'] is None,
      'незнакомец — честные пустые поля')
check(card9['karma']['score'] == 0 and card9['warns']['count'] == 0, 'нули без данных')
check(len(card['links']) == 6 and card['links'][0]['path'] == '/karma?user=111',
      'быстрые переходы: карма с фильтром первой')

print('== 4. Автодополнение ==')
s = MC.suggest('777', 'али')
check(len(s) == 1 and s[0] == {'user_id': '111', 'name': 'Алиса Мод'}, 'по имени из аудита')
check(MC.suggest('777', 'вика')[0]['user_id'] == '333', 'по имени из календаря ДР')
check(MC.suggest('777', '222')[0]['user_id'] == '222', 'по ID')
check(MC.suggest('777', '') == [], 'пустой запрос — пустой ответ')
s = MC.suggest('777', 'тест')
check(len(s) == MC.SUGGEST_LIMIT and s[0]['name'] == 'тест 01' and s[-1]['name'] == 'тест 08',
      'лимит 8, сорт по имени')

print('== 4b. @-поиск (стиль Discord-упоминаний) ==')
check(MC.suggest('777', '@али') == MC.suggest('777', 'али'),
      '@-запрос эквивалентен обычному')
at_pool = MC.suggest('777', '@')
check(len(at_pool) >= 1 and all('@' not in (h['name'] or '') for h in at_pool),
      'голый @ показывает людей из пула (получено %d)' % len(at_pool))
uid, err = MC.resolve_user_ref('777', '@Алиса Мод')
check(uid == '111' and err is None, '@Имя резолвится в ID')
uid2, err2 = MC.resolve_user_ref('777', '  @222 ')
check(uid2 == '222' and err2 is None, '@ID с пробелами резолвится')

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


LK = '/api/guild/777/member-card/lookup'
check(client.get(LK + '?user=111').status_code in (302, 401, 403), 'гостю API закрыт')
login('uye')
check(client.get(LK + '?user=111').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/member-card').status_code == 404,
      'отдельной страницы больше нет — досье перетаскиваемым окном в «Пользователях»')
r = client.get(LK)
check(r.status_code == 400 and 'Введите ID или имя' in r.get_json()['error'],
      'без user — просим ID или имя участника')
r = client.get(LK + '?user=куку')
check(r.status_code == 400 and 'не найден ни по ID, ни по имени' in r.get_json()['error'],
      'незнакомое имя — честная ошибка 400')
r = client.get(LK + '?user=Алиса')
check(r.status_code == 200 and r.get_json()['card']['user_id'] == '111',
      'карточка ищется ПО ИМЕНИ (не только ID)')
r = client.get(LK + '?user=<@!111>')
d = r.get_json()
check(r.status_code == 200 and d['card']['user_id'] == '111', 'упоминание распарсено')
check(d['card']['activity']['xp'] == 250 and d['card']['karma']['score'] == 2,
      'API собирает те же числа, что чистые вызовы')
check(d['card']['member'] is None and d['card']['name'] == 'Алиса Мод',
      'офлайн: без live-полей, имя из аудита')
r = client.get('/api/guild/777/member-card/suggest?q=али')
check(r.status_code == 200 and r.get_json()['items'][0]['user_id'] == '111',
      'подсказки через API')
r = client.get(LK + '?user=112')
check(r.get_json()['card']['warns']['recent'] == [], 'чужой ID — пустые варны')

print('== 6. Выгрузка CSV ==')
csv_r = client.get('/api/guild/777/member-card/export?user=111')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'member_card_111_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'имя файла с uid и gid')
check(body.startswith('\ufeffРаздел;Показатель;Значение'), 'BOM + шапка')
lines = body.strip().split('\n')
check(len(lines) == 23, f'шапка + 22 строки данных (пришло {len(lines)})')
check('Профиль;Уровень;2' in body and 'Активность;Голос (сек);120' in body,
      'числа активности в выгрузке')
check('Карма;Место в топе;1' in body and 'Карма;Благодарностей получено;2' in body,
      'карма в выгрузке')
check('Модерация;Варнов;3' in body and '2026-08-01 · спам,флуд · ModOne' in body,
      'варны в выгрузке, точка с запятой в тексте заменена')
check('День рождения;Через (дней, по формуле бота);0' in body, 'ДР в выгрузке')
check('Discord;' not in body, 'офлайн — Discord-секции нет')
check(client.get('/api/guild/777/member-card/export?user=qq').status_code == 400,
      'битый user в выгрузке — 400')
login('uye')
check(client.get('/api/guild/777/member-card/export?user=111').status_code == 403,
      'uye не выгружает')

print('== 7. Страница удалена: окно в «Пользователях», меню, регистрация ==')
check(not os.path.exists(os.path.join(ROOT, 'web/templates/member_card.html')),
      'member_card.html удалён — отдельной страницы больше нет')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
mcjs = open(os.path.join(ROOT, 'web/static/member_card.js'), encoding='utf-8').read()
mccss = open(os.path.join(ROOT, 'web/static/member_card.css'), encoding='utf-8').read()
check(not EMOJI_RE.search(mcjs + mccss), 'в ассетах карточки нет эмодзи')
check('window.MemberCard' in mcjs and 'renderCard' in mcjs, 'общий рендер досье на месте')
check('.mcf-win' in mccss and '.mc-panel' in mccss, 'стили карточки и окна в общем css')
check('localhost' not in mcjs and '127.0.0.1' not in mcjs, 'без локальных адресов')
utpl = open(os.path.join(ROOT, 'web/templates/users.html'), encoding='utf-8').read()
check('mcf-win' in utpl and 'mcWinHead' in utpl, 'в «Пользователях» перетаскиваемое окно')
check('pointerdown' in utpl, 'окно таскает за шапку (pointer-события)')
for fid in ('mcKpis', 'mcProfile', 'mcWarns', 'mcLinks'):
    check(('id="' + fid + '"') in utpl, f'блок {fid} на месте в окне')
check('/member-card/lookup?user=' in utpl and '/member-card/export?user=' in utpl,
      'окно грузит досье и CSV через API карточки')
check('member_card.js' in utpl and 'member_card.css' in utpl, 'общие ассеты подключены')
ktpl = open(os.path.join(ROOT, 'web/templates/karma.html'), encoding='utf-8').read()
check("URLSearchParams(location.search).get('user')" in ktpl,
      'карма читает ?user= из адреса — переход из карточки рабочий')
import services.panel_menu as PM
mem_pages = [pg['path'] for g in PM.MENU if g['key'] == 'members' for pg in g['pages']]
check('/member-card' not in mem_pages, 'пункта «Карточка 360°» в меню больше нет')
check(PM.PAGE_COGS.get('/member-card') is None, 'коги страницы отвязаны')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('member_card_panel') >= 1, 'модуль API зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
