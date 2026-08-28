# -*- coding: utf-8 -*-
"""UX-пакет панели: глобальный поиск + личные prefs + навигационная статика.

Покрываем: чистые функции prefs (валидация/merge/атомарность), поисковые
источники (страницы по роли 1:1 с меню, участники через ms_search_members,
транскрипты через filter_records+snippets — те же функции, что у страницы,
триггеры из хранилища кога, объявления из ленты web.app), API-эндпоинты
(права, границы, коды), монтаж base.html (крошки, ux-kit, чистка старого
Ctrl+K), статика ux-kit.js/polish.css.

Запуск: python3 tests/test_panel_ux.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_ux_test_')
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
from services import transcript_store  # noqa: E402
from web.routes import ux  # noqa: E402

print('== 1. Prefs: валидация ==')
clean, err = ux.validate_prefs_patch({'theme': 'light', 'accent': '#A1B2C3', 'compact': True})
check(err is None and clean['theme'] == 'light' and clean['accent'] == '#a1b2c3'
      and clean['compact'] is True, 'валидный патч: акцент приведён к #hex lowercase')
clean, err = ux.validate_prefs_patch({'theme': 'neon'})
check(clean is None and 'тема' in err, 'неизвестная тема — отказ со словами')
clean, err = ux.validate_prefs_patch({'accent': 'red'})
check(clean is None and '#rrggbb' in err, 'кривой акцент — отказ с форматом')
clean, err = ux.validate_prefs_patch({'unknown_key': 1})
check(clean is None and 'пустой патч' in err, 'лишние ключи игнорируются, пусто — отказ')
clean, err = ux.validate_prefs_patch('строка')
check(clean is None, 'не-объект — отказ')

print('== 2. Prefs: merge/persist/изоляция ==')
prefs, err = ux.merge_user_prefs('admin', {'theme': 'light'})
check(err is None and prefs['theme'] == 'light', 'admin: тема сохранена')
prefs, err = ux.merge_user_prefs('admin', {'compact': True})
check(err is None and prefs['theme'] == 'light' and prefs['compact'] is True,
      'второй патч не затирает первый (merge)')
prefs, err = ux.merge_user_prefs('moder', {'theme': 'dark'})
check(err is None and ux.load_prefs()['moder']['theme'] == 'dark'
      and ux.load_prefs()['admin']['theme'] == 'light', 'учётки изолированы')
check(os.path.exists(ux.PREFS_PATH) and not os.path.exists(ux.PREFS_PATH + '.tmp'),
      'запись атомарна: tmp убран')
bad, err = ux.merge_user_prefs('admin', {'theme': 'blue'})
check(bad is None and ux.load_prefs()['admin']['theme'] == 'light',
      'невалидный патч ничего не записывает')

print('== 3. Поиск: страницы по роли ==')
owner_hits = ux.search_pages('owner', 'транск')
check(any(h['href'] == '/transcripts' and h['sub'] for h in owner_hits),
      'owner видит Транскрипты с группой в подписи')
mod_hits = ux.search_pages('mod', 'эконом')
check(all(h['href'] != '/economy' for h in mod_hits), 'mod не видит скрытые группы (1:1 с меню)')
check(len(ux.search_pages('owner', 'и')) <= ux.SEARCH_LIMIT, 'лимит группы соблюдён')
check(ux.search_pages('owner', '') == [], 'пустой запрос — пусто')

print('== 4. Поиск: участники через ms_ (та же выдача, что member-search) ==')
members = [SimpleNamespace(id=101, name='artyom', display_name='Артём', global_name=None, nick=None,
                           bot=False, status='online', display_avatar=None),
           SimpleNamespace(id=102, name='mod-help', display_name='МодПомощник', global_name=None,
                           nick=None, bot=False, status='online', display_avatar=None)]


class FakeGuild:
    def __init__(self):
        self.id = 777
        self.members = members


class FakeBot:
    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None


hits = ux.search_members(FakeBot(), '777', 'артём')
check(len(hits) == 1 and hits[0]['title'] == 'Артём' and hits[0]['sub'] == 'ID 101',
      'кириллица, регистр не важен; подпись — ID')
check(hits[0]['href'].startswith('/member-search?q='), 'хит ведёт на страницу поиска с запросом')
check(ux.search_members(FakeBot(), '777', 'zzz') == [], 'нет совпадений — пусто')
check(ux.search_members(None, '777', 'арт') == [], 'бот офлайн — тихо пусто, не падаем')
check(ux.search_members(FakeBot(), '999', 'арт') == [], 'чужой guild — пусто')

print('== 5. Поиск: транскрипты (глубокий, 1:1 со страницей) ==')
transcript_store.record(guild_id=777, channel_id=55, channel_name='ticket-sasha',
                        user_name='Саша', category='teknik', closed_by='МодПомощник',
                        messages=[{'author': 'Саша', 'content': 'не работает кнопка оплаты'},
                                  {'author': 'Мод', 'content': 'проверьте кэш браузера'}])
hits = ux.search_transcripts('оплаты')
check(len(hits) == 1 and hits[0]['title'] == 'ticket-sasha · 55', 'глубокий хит по тексту сообщений')
check(isinstance(hits[0]['sub'], str) and 'оплаты' in hits[0]['sub'],
      'подпись — строка-сниппет (не dict), с искомой фразой')
check(hits[0]['href'] == '/transcripts?text=%D0%BE%D0%BF%D0%BB%D0%B0%D1%82%D1%8B',
      'href — глубокая ссылка с urlencoded запросом')
hits2 = ux.search_transcripts('sasha')
check(len(hits2) == 1 and hits2[0]['sub'] == 'Техническая проблема', 'хит по имени канала: подпись — категория')

print('== 6. Поиск: триггеры и объявления ==')
GuildData('triggers').set(777, 'state', {'next_id': 2, 'cooldown': 30, 'items': [
    {'id': 1, 'trigger': 'правила', 'response': 'Читай #правила', 'exact': False,
     'uses': 3, 'created_at': 'x'}]})
hits = ux.search_triggers('777', 'правил')
check(len(hits) == 1 and 'правила' in hits[0]['title'] and '№1' in hits[0]['sub'],
      'триггер найден, подпись с номером')
check(hits[0]['href'] == '/automation#triggers-sec', 'ссылка на якорь редактора триггеров')
with open('data/announcements.json', 'w', encoding='utf-8') as f:
    json.dump([{'id': 'ann-1', 'title': 'Вайп экономики', 'message': 'завтра в 18:00',
                'channel_id': '5', 'channel_name': 'news', 'delivered': True}], f, ensure_ascii=False)
import web.app as appmod  # noqa: E402
hits = ux.search_announcements('вайп')
check(len(hits) == 1 and hits[0]['title'] == 'Вайп экономики' and 'доставлено' in hits[0]['sub'],
      'анонс найден из живой ленты web.app')

print('== 7. API: права и границы ==')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()
appmod.bot_instance = FakeBot()


def login(role='owner', username='admin'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = username
        s['role'] = role


r = client.get('/api/ux/search?q=тест')
check(r.status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/ux/search?q=тест').status_code == 403, 'uye нельзя (403)')
login('mod')
r = client.get('/api/ux/search?q=а')
check(r.status_code == 200 and r.get_json()['groups'] == [], 'запрос короче 2 — 200 с пусто (не шумим)')
r = client.get('/api/ux/search')
check(r.status_code == 200 and r.get_json()['total'] == 0, 'без q — 200 пусто')
r = client.get('/api/ux/search?q=логи')
check(r.status_code == 200, 'mod может искать (200)')
check('pages' in [g['key'] for g in r.get_json()['groups']],
      'mod: группа Страницы наполнена из его меню')
login('owner')
r = client.get('/api/ux/search?q=правил')
body = r.get_json()
keys = [g['key'] for g in body['groups']]
check('triggers' in keys and 'pages' in keys, 'owner: страницы + триггеры в одной выдаче')
check(body['total'] == sum(len(g['items']) for g in body['groups']) and body['total'] > 0,
      'total сходится с группами')
login('owner')  # member-группа: бот выдаёт FakeGuild 777
r = client.get('/api/ux/search?q=модпомощник')
mb = [i for g in r.get_json()['groups'] if g['key'] == 'members' for i in g['items']]
check(len(mb) == 1 and mb[0]['title'] == 'МодПомощник', 'API: участник найден через бота')

print('== 8. API: prefs ==')
r = client.get('/api/ux/prefs')
check(r.status_code == 200 and r.get_json()['prefs']['theme'] == 'light',
      'GET prefs: тема admin из хранилища (следует за учёткой)')
r = client.post('/api/ux/prefs', data=json.dumps({'accent': '#12AB34'}),
                content_type='application/json')
check(r.status_code == 200 and r.get_json()['prefs']['accent'] == '#12ab34', 'POST prefs: акцент')
r = client.post('/api/ux/prefs', data=json.dumps({'accent': 'zzz'}),
                content_type='application/json')
check(r.status_code == 400 and '#rrggbb' in r.get_json()['error'], 'кривой акцент — 400 с форматом')
login('mod', username='moder')
r = client.get('/api/ux/prefs')
check(r.get_json()['prefs']['theme'] == 'dark' and 'accent' not in r.get_json()['prefs'],
      'другая учётка — свои prefs, чужих нет')

print('== 9. Монтаж base.html ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
for token in ('class="crumbs"', 'crumb-home', '/static/app.js', 'id="palette-data"',
              'Фильтр меню'):
    assert token in src, token
check(True, 'крошки, данные палитры и единый кит подключены')
check('__hakumoGPressed' not in src, 'старый g-код удалён (нет дублей хоткеев)')
check("e.key === 'k'" not in src, 'старый Ctrl+K-фокус сайдбара убран (палитра одна)')
check('panel_menu|default([], true)' in src, 'крошки строятся из panel_menu (1:1 с сайдбаром)')
login('owner')
r = client.get('/transcripts')
check(r.status_code == 200 and 'crumb-here' in r.get_data(as_text=True)
      and 'Транскрипты' in r.get_data(as_text=True), 'крошки рендерятся на живой странице')

print('== 10. app.js / style.css ==')
js = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
for token in ('paletteOpen', 'guardSilent' if 'guardSilent' in js else 'fetchCachedJSON',
              'uxUndo', 'confirmAction', 'qualitySetLoading', 'showToast'):
    assert token in js, token
check(True, 'палитра, undo, подтверждения, тосты и live-кит на месте')
check('markMatch(p.label, q)' in js and 'function markMatch' in js
      and 'esc(text.slice' in js and 'innerHTML' in js,
      'выдача палитры экранируется esc() через markMatch')
css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
for token in ('.crumbs', '.kbd-palette', '.nav-link.active', '.toast',
              '.user-menu a:hover', '.page-hero'):
    assert token in css, token
check(True, 'стили палитры, крошек и тостов на месте')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(js) and not EMOJI.search(open(os.path.join(
    ROOT, 'web', 'routes', 'ux.py'), encoding='utf-8').read()), 'эмодзи в новых файлах нет')

print('== 11. Глубокие ссылки на страницах ==')
trx = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
ms = open(os.path.join(ROOT, 'web', 'templates', 'member_search.html'), encoding='utf-8').read()
auto = open(os.path.join(ROOT, 'web', 'templates', 'automation.html'), encoding='utf-8').read()
check("get('text')" in trx and 'URLSearchParams' in trx, 'транскрипты читают ?text=')
check("get('q')" in ms and 'searchNow()' in ms, 'поиск участников читает ?q=')
check('id="triggers-sec"' in auto, 'якорь редактора триггеров существует')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
