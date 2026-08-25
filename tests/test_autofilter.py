# -*- coding: utf-8 -*-
"""Тесты Автофильтра чата: матчинг, флуд-трекер, конфиг, ког, страница панели.

Запуск: python3 tests/test_autofilter.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_autofilter_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs import auto_filter as af  # noqa: E402

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


# ═══ 1. Нормализация и поиск слов ════════════════════════════════════════
print('== normalize/find_bad_word ==')
check(af.normalize_text('ПлоХоООе!!!') == 'плохое!', 'normalize: регистр+повторы схлопываются')
check(af.normalize_text('залгo\u0301 текст') == 'залгo текст', 'normalize: залго/диакритика срезается')
check(af.squash('м у.с.о.р!') == 'mycop', 'squash: пунктуация выкидывается')
check(af.squash('мусор') == 'mycop', 'squash: кириллица складывается в фолд-алфавит')
check(af.squash('мycop') == 'mycop' and af.squash('муcop') == 'mycop', 'squash: омоглифы/латиница сходятся')

words = ['мусор', 'развод']
check(af.find_bad_word('Это просто мусор какой-то', words) == 'мусор', 'матч: простое вхождение')
check(af.find_bad_word('муСООРнический', words) is None, 'нет ложного срабатывания внутри другого слова')
check(af.find_bad_word('архитектура', ['хит']) is None, 'короткое слово не горит внутри длинного (хит ⊄ архитектура)')
check(af.find_bad_word('м у с о р', words) == 'мусор', 'матч: раздельный ввод букв')
check(af.find_bad_word('м-у-с-о-р!!', words) == 'мусор', 'матч: пунктуация между буквами')
check(af.find_bad_word('мусоооооор', words) == 'мусор', 'матч: повторы букв')
check(af.find_bad_word('му50р тут', words) == 'мусор', 'матч: л33т-символы (му50р)')
check(af.find_bad_word('Р@Звод попытка', words) == 'развод', 'матч: регистр + @→a')
check(af.find_bad_word('обычное сообщение без всякого', words) is None, 'чистый текст не матчится')
check(af.find_bad_word('мусор', []) is None, 'пустой список слов — всегда None')
check(af.find_bad_word('', words) is None, 'пустой текст — None')

# ═══ 2. Ссылки и капс ════════════════════════════════════════════════════
print('== links/caps ==')
links = af.extract_links('заходи https://evil.com/steal или www.free-nitro.net и discord.gg/abc123')
check(len(links) == 3, f'extract_links: 3 ссылки пойманы ({len(links)})')
check(af.extract_links('обычный текст без ссылок') == [], 'extract_links: чистый текст → пусто')
check(any('discord.gg' in u for u in links), 'extract_links: инвайт без схемы тоже ловится')
check(af.link_allowed('https://github.com/x', ['github.com']) is True, 'whitelist разрешает свой домен')
check(af.link_allowed('https://evil.com', ['github.com']) is False, 'чужой домен не разрешён')
check(af.link_allowed('https://github.com', []) is False, 'пустой whitelist — всё запрещено')
check(af.caps_ratio('ПРИВЕТ МИР') == 100.0, 'caps_ratio: полный капс = 100%')
check(abs(af.caps_ratio('Привет мир 123') - 100.0 / 9) < 0.01, 'caps_ratio: регистр только букв считается')
check(af.caps_ratio('123 !!!') == 0.0, 'caps_ratio: без букв → 0')

# ═══ 3. classify_message ═════════════════════════════════════════════════
print('== classify_message ==')
cfg = af.merge_config({})
cfg['enabled'] = True  # дефолты opt-in — для теста классификатора включаем явно
cfg['words']['enabled'] = True
cfg['words']['list'] = ['казино']
cfg['links']['enabled'] = True
cfg['caps']['enabled'] = True
cfg['caps']['min_length'] = 10

v = af.classify_message(cfg, 'добро пожаловать в казино онлайн')
check(len(v) == 1 and v[0]['filter'] == 'words' and v[0]['detail'] == 'казино', 'classify: слова срабатывают с деталью')
v = af.classify_message(cfg, 'смотри https://evil.com тут')
check(len(v) == 1 and v[0]['filter'] == 'links', 'classify: ссылка вне whitelist')
cfg['links']['whitelist'] = ['evil.com']
check(af.classify_message(cfg, 'смотри https://evil.com тут') == [], 'classify: whitelist пропускает')
v = af.classify_message(cfg, 'АААА ПРИВЕТ ВСЕМ ТУТ')
check(len(v) == 1 and v[0]['filter'] == 'caps', 'classify: капс выше порога')
check(af.classify_message(cfg, 'ХА ХА') == [], 'classify: короткие сообщения не под капс-фильтром')
cfg['enabled'] = False
check(af.classify_message(cfg, 'казино https://x.com АААААААААА') == [], 'classify: главный выключатель глушит всё')
cfg['enabled'] = True
cfg['words']['enabled'] = False
check(af.classify_message(cfg, 'казино это слово') == [], 'classify: отдельный фильтр глушится')
cfg['words']['enabled'] = True

# ═══ 4. FloodTracker ═════════════════════════════════════════════════════
print('== FloodTracker ==')
tr = af.FloodTracker()
t = 1000.0
res = [tr.hit(1, 10, f'spam {i}', limit=5, seconds=5, dupe_count=3, now=t + i) for i in range(4)]
check(all(r is None for r in res), 'флуд: 4 сообщения подряд ещё не триггер (лимит 5)')
check(tr.hit(1, 10, 'spam 5', limit=5, seconds=5, dupe_count=3, now=t + 4) == 'flood', 'флуд: пятое сообщение → flood')
check(tr.hit(1, 10, 'новое', limit=5, seconds=5, dupe_count=3, now=t + 5) is None, 'флуд: очередь очищается после триггера')

tr2 = af.FloodTracker()
for i in range(6):
    r = tr2.hit(1, 20, 'медленно', limit=5, seconds=5, dupe_count=99, now=t + i * 10)
check(r is None, 'флуд: сообщения вне окна не накапливаются')

tr3 = af.FloodTracker()
res3 = [tr3.hit(1, 30, 'КУПЛЮ ГОЛДУ', limit=9, seconds=8, dupe_count=3, now=t + i) for i in range(2)]
check(all(r is None for r in res3), 'дуп: два одинаковых ещё ок (dupe_count=3)')
check(tr3.hit(1, 30, 'КУПЛЮ ГОЛДУ!', limit=9, seconds=8, dupe_count=3, now=t + 3) == 'dupe',
      'дуп: третье «то же самое» (пунктуация не спасает) → dupe')
tr4 = af.FloodTracker()
for i in range(4):
    tr4.hit(2, 40, f'x{i}', limit=5, seconds=5, dupe_count=99, now=t + i)
for i in range(4):
    r = tr4.hit(2, 41, f'y{i}', limit=5, seconds=5, dupe_count=99, now=t + i)
check(r is None, 'флуд: разные юзеры — независимые очереди')

# ═══ 5. Конфиг: merge / validate / файл ═════════════════════════════════
print('== config ==')
d = af.merge_config(None)
check(d['enabled'] is False and d['words']['action'] == 'warn', 'merge: дефолты при пустом сохранённом (выкл — opt-in)')
check(sorted(d) == sorted(af.DEFAULT_FILTER), 'merge: все ключи дефолта на месте')
c2 = af.merge_config({'caps': {'percent': 999, 'action': 'ban'}, 'unknown': {'x': 1}})
check(c2['caps']['percent'] == 100, 'merge: числа зажаты в диапазон сверху')
check(c2['caps']['action'] == 'delete', 'merge: недопустимое действие отброшено к дефолту')
check('unknown' not in c2, 'merge: неизвестные ключи игнорируются')
c3 = af.merge_config({'words': {'list': ['  фу  ', 'фу', '', '$$$']}})
check(c3['words']['list'] == ['фу'], 'sanitize: strip/дедуп/мусор выкидывается')
cfg_v, errs = af.validate_config({'caps': {'percent': 5}})
check(errs and 'caps.percent' in errs[0], 'validate: процент вне диапазона — ошибка')
cfg_v, errs = af.validate_config({'flood': {'action': 'ban'}})
check(errs and 'flood' in errs[0], 'validate: недопустимое действие — ошибка')
cfg_v, errs = af.validate_config({'flood': {'action': 'timeout', 'limit': 6}})
check(not errs and cfg_v['flood']['action'] == 'timeout' and cfg_v['flood']['limit'] == 6,
      'validate: корректный конфиг проходит')

af.save_config(777, {'enabled': False, 'words': {'list': ['тестово']}})
back = af.load_config(777)
check(back['enabled'] is False and back['words']['list'] == ['тестово'], 'save/load: круг сохранения')
check(os.path.exists(af.cfg_path(777)), 'save: файл на диске')
with open(af.cfg_path(777), 'w', encoding='utf-8') as fp:
    fp.write('{битый json')
check(af.load_config(777)['enabled'] is False, 'load: битый файл → дефолты-выкл, не падаем (opt-in)')
# Тестер ниже ходит по ЖИВОМУ конфигу — включаем явно (дефолты opt-in).
af.save_config(777, {'enabled': True,
                     'words': {'enabled': True, 'action': 'warn', 'list': ['бонус']},
                     'links': {'enabled': True, 'action': 'delete', 'whitelist': ['my.gg']}})
check(af.is_ignored_channel({'ignore_channels': ['123', '456']}, 123) is True, 'ignore: канал в исключениях')
check(af.is_ignored_channel({'ignore_channels': ['123']}, 999, parent_id=123) is True, 'ignore: тред по parent_id')
check(af.is_ignored_channel({'ignore_channels': ['123']}, 999) is False, 'ignore: обычный канал не исключён')

# ═══ 6. Ког: структура и иммунитет ═══════════════════════════════════════
print('== cog ==')
cog = af.AutoFilter(bot=None)
check(isinstance(cog.tracker, af.FloodTracker), 'ког: флуд-трекер инициализирован')
groups = [c for c in af.AutoFilter.__cog_app_commands__ if getattr(c, 'name', '') == 'filter']
check(not groups, 'ког: группа /filter убрана из боевого меню (чистка команд)')
listeners = [m for m in dir(cog) if m.startswith('on_')]
check(any('message' in m for m in listeners) or hasattr(cog, 'on_message'),
      'ког: слушатель автофильтра на месте (сама защита жива)')


class _Perms:
    def __init__(self, manage=False, admin=False):
        self.manage_messages = manage
        self.administrator = admin


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Chan:
    def __init__(self, cid, parent=None):
        self.id = cid
        self.parent_id = parent


class _Author:
    def __init__(self, perms, roles=()):
        self.guild_permissions = perms
        self.roles = list(roles)


class _Msg:
    def __init__(self, author, channel):
        self.author = author
        self.channel = channel


cfg_imm = {'ignore_channels': ['50'], 'immune_roles': ['900']}
check(cog._is_immune(_Msg(_Author(_Perms(manage=True)), _Chan(1)), cfg_imm) is True,
      'иммунитет: manage_messages пропускается')
check(cog._is_immune(_Msg(_Author(_Perms(admin=True)), _Chan(1)), cfg_imm) is True,
      'иммунитет: администратор пропускается')
check(cog._is_immune(_Msg(_Author(_Perms(), [_Role(900)]), _Chan(1)), cfg_imm) is True,
      'иммунитет: иммунная роль пропускается')
check(cog._is_immune(_Msg(_Author(_Perms(), [_Role(901)]), _Chan(55, parent=None)), cfg_imm) is False,
      'иммунитет: обычный юзер вне исключений проверяется')
check(cog._is_immune(_Msg(_Author(_Perms()), _Chan(55, parent=50)), cfg_imm) is True,
      'иммунитет: тред игнорируемого канала пропускается')

# ═══ 7. Панель: страница и API ═══════════════════════════════════════════
print('== панель ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class FakeGuild:
    def __init__(self, gid):
        self.id = gid


class FakePanelBot:
    guilds = [FakeGuild(4242)]
    latency = 0.03
    users = []

    def is_closed(self):
        return False


set_bot_instance(FakePanelBot())
client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelAF'
        s['role'] = role


r = client.get('/autofilter')
check(r.status_code in (302, 401, 403), f'страница без логина закрыта ({r.status_code})')
login_as('uye')
check(client.get('/autofilter').status_code in (302, 403), 'uye не пускают на страницу')
login_as('mod')
r = client.get('/autofilter')
check(r.status_code == 200, 'mod: страница рендерится (200)')
page = r.get_data(as_text=True)

MARKERS = ('id="hero-state"', 'id="hero-chips"', 'id="master-switch"',
           'id="fw-tog"', 'id="fw-action"', 'id="fw-input"', 'id="fw-add"', 'id="fw-chips"',
           'id="fl-tog"', 'id="fl-action"', 'id="wl-input"', 'id="wl-add"', 'id="wl-chips"',
           'id="fc-tog"', 'id="fc-action"', 'id="fc-percent"', 'id="fc-percent-val"', 'id="fc-minlen"',
           'id="ff-tog"', 'id="ff-action"', 'id="ff-limit"', 'id="ff-seconds"', 'id="ff-dupe"', 'id="ff-timeout"',
           'id="af-channels"', 'id="af-roles"', 'id="af-test-text"', 'id="af-test-btn"', 'id="af-test-out"',
           'id="af-note"', 'id="saveBtn"')
missing = [m for m in MARKERS if m not in page]
check(not missing, f'разметка: все {len(MARKERS)} контейнеров на месте ({missing or "ок"})')
check('/api/autofilter/save' in page and '/api/autofilter/test' in page and "'/api/autofilter'" in page,
      'страница: дёргает все три API')
check('{%' not in page and '{{' not in page, 'страница: без сырых Jinja-тегов')

# меню: новый пункт вместо старого
from services.panel_menu import MENU  # noqa: E402
prot_group = next(g for g in MENU if g['key'] == 'protection')
paths = [p['path'] for p in prot_group['pages']]
check('/autofilter' in paths, 'меню: «Автофильтр чата» в категории Защита')
check('/automod-settings' not in paths, 'меню: старая заглушка убрана')

# API
login_as('mod')
r = client.get('/api/autofilter')
d = r.get_json()
check(r.status_code == 200 and d.get('ok') is True, 'API: GET отдаёт конфиг (mod)')
check(d.get('guild_id') == '4242', 'API: guild_id определён по серверу бота')
cfg_keys = set(af.DEFAULT_FILTER)
check(set(d['config']) >= cfg_keys, 'API: все секции конфига в ответе')

# сохранение — права
r = client.post('/api/autofilter/save', json={'enabled': True})
check(r.status_code in (302, 403), 'save: mod не может сохранять (admin+)')
login_as('admin')
r = client.post('/api/autofilter/save',
                json={'enabled': True,  # главный тумблер (дефолты opt-in)
                      'words': {'enabled': True, 'action': 'warn', 'list': ['бонус']},
                      'caps': {'enabled': True, 'action': 'delete', 'percent': 80, 'min_length': 8},
                      'flood': {'action': 'timeout', 'limit': 6, 'seconds': 4,
                                'dupe_count': 4, 'timeout_minutes': 15},
                      'links': {'enabled': True, 'action': 'delete', 'whitelist': ['my.gg']}})
d = r.get_json()
check(r.status_code == 200 and d.get('ok') is True, 'save: валидный конфиг принят (admin)')
save_path = af.cfg_path('4242')
on_disk = json.load(open(save_path, encoding='utf-8')) if os.path.exists(save_path) else {}
check(on_disk.get('words', {}).get('list') == ['бонус'], 'save: слова реально записаны в файл')
r = client.get('/api/autofilter').get_json()
check(r['config']['caps']['percent'] == 80 and r['config']['flood']['timeout_minutes'] == 15,
      'save: GET видит свежий конфиг (кеш сброшен)')

r = client.post('/api/autofilter/save', json={'caps': {'percent': 500}})
check(r.status_code == 400 and 'caps.percent' in (r.get_json().get('errors') or [''])[0],
      'save: невалидный процент → 400 с объяснением')
r = client.post('/api/autofilter/save', json={'flood': {'action': 'nuke'}})
check(r.status_code == 400, 'save: недопустимое действие → 400')

# тестер API отражает живой конфиг («бонус» в списке слов)
login_as('admin')
r = client.post('/api/autofilter/test', json={'text': 'бесплатный бонус ждёт'})
v = r.get_json().get('violations') or []
check(r.status_code == 200 and any(x['filter'] == 'words' and x['detail'] == 'бонус' for x in v),
      'tester: сработка по живому конфигу (words)')
r = client.post('/api/autofilter/test', json={'text': 'всем привет, как дела'})
check(r.get_json().get('violations') == [], 'tester: чистый текст → пусто')
r = client.post('/api/autofilter/test', json={'text': 'https://my.gg/nice'})
check(r.get_json().get('violations') == [], 'tester: whitelist-домен пропускается')
r = client.post('/api/autofilter/test', json={'text': 'https://scam.io/free'})
check(any(x['filter'] == 'links' for x in (r.get_json().get('violations') or [])),
      'tester: чужая ссылка ловится (links)')
login_as('uye')
r = client.post('/api/autofilter/test', json={'text': 'x'})
check(r.status_code in (302, 403), 'tester: uye не пускают в API')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
