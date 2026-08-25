# -*- coding: utf-8 -*-
"""AntiFake (идеи #191-195).

Панель работает через живой ког: set_cfg/cfg — та же память и те же файлы
(data/antifake*.json), что слушают on_member_join/on_message. Тексты —
словами команд /antifake без маркдауна. Детекция 1:1 find_impersonation и
find_stolen_avatar: кириллица-хамелеон даёт совпадение 100%, чужой аватар
с тем же ключом — находка. Страйки: окно 7 дней / лимит 3 — константы кога.
Offline — честные 409; чтение mod+, мутации и сухой прогон admin+.

Запуск: python3 tests/test_antifake_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='aether_antifake_test_')
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


from cogs import impersonation as IM  # noqa: E402
from web.routes import antifake_panel as AF  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')


class FakePerms:
    def __init__(self, administrator=False, manage_guild=False,
                 moderate_members=False):
        self.administrator = administrator
        self.manage_guild = manage_guild
        self.moderate_members = moderate_members


class FakeAvatar:
    def __init__(self, key):
        self.key = key


class FakeMember:
    def __init__(self, name, mid, guild=None, perms=None, avatar=None,
                 nick=None, global_name=None, bot=False, display=None):
        self.name = name
        self.id = mid
        self.guild = guild
        self.guild_permissions = perms or FakePerms()
        self.avatar = avatar
        self.nick = nick
        self.global_name = global_name
        self.bot = bot
        self.display_name = (display if display is not None
                             else (nick or global_name or name))


class FakeChannel:
    def __init__(self, name, cid):
        self.name = name
        self.id = cid


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.members = []
        self.owner = None
        self.channels = {}

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return self.channels.get(cid)


class FakeBot:
    def __init__(self, guilds, cogs=None):
        self.guilds = list(guilds)
        self.cogs_map = dict(cogs or {})

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)

    def get_cog(self, name):
        return self.cogs_map.get(name)


G = FakeGuild(777)
OWNER = FakeMember('Владелец', 1, guild=G)
ADMIN = FakeMember('moder_admin', 2, guild=G,
                   perms=FakePerms(administrator=True),
                   avatar=FakeAvatar('av-1'), display='Модератор')
IMP = FakeMember('mоder_admin', 3, guild=G)       # кириллическая «о»
THIEF = FakeMember('Петя', 4, guild=G, avatar=FakeAvatar('av-1'))
PLAIN = FakeMember('Участник', 5, guild=G, avatar=FakeAvatar('av-9'))
G.members = [OWNER, ADMIN, IMP, THIEF, PLAIN]
G.owner = OWNER
G.channels[555] = FakeChannel('мод-логи', 555)

for f in (IM.CFG_PATH, IM.STRIKES_PATH):
    if os.path.exists(f):
        os.remove(f)
COG = IM.AntiFake(None)
FB2 = FakeBot([G], {'AntiFake': COG})

print('== 1. Чистые функции кога ==')
check(IM.normalize('Аdm1n') == 'admln', 'хамелеоны в латиницу: А→a, 1→l')
check(IM.normalize('mоder_admin') == 'moderadmin',
      'кириллическая «о» склеивается с латиницей')
check(IM.has_confusables('mоder_admin') is True
      and IM.has_confusables('moderadmin') is False,
      'has_confusables видит подмену')
check(IM.similarity('admin', 'admin') == 1.0, 'одинаковые — 1.0')
check(round(IM.similarity('admin', 'admin2'), 2) == 0.92,
      'вложенность длинных — бонус 0.92')
check(round(IM.similarity('admin', 'admln'), 1) == 0.8,
      'одна замена — ниже порога')
check([c.value for c in IM.ACTION_CHOICES] == ['strip', 'jail', 'kick', 'alert']
      and IM.ACTION_CHOICES[2].name == 'Кикнуть',
      'ACTION_CHOICES — те самые Choice команды')

print('== 2. Доступ к когу (_ctx) ==')
ok, err, code, cog, guild = AF._ctx(lambda: None, '777')
check(not ok and code == 409 and err == 'Бот не работает', 'без бота — 409')
ok, err, code, cog, guild = AF._ctx(lambda: FB2, '999')
check(not ok and code == 404 and err == 'Сервер не найден', 'чужой сервер — 404')
ok, err, code, cog, guild = AF._ctx(lambda: FakeBot([G]), '777')
check(not ok and code == 409 and err == AF.ERR_COG,
      'бот без кога — честный 409')
ok, err, code, cog, guild = AF._ctx(lambda: FB2, '777')
check(ok and cog is COG and guild is G, 'живой ког и гильдия')

print('== 3. Статус 1:1 _cfg_embed ==')
ok, err, code, p = AF.status_flow(lambda: FB2, '777')
check(ok and p['enabled'] is False and p['action'] == 'strip'
      and p['action_label'] == 'Снять ник' and p['threshold_pct'] == 85,
      'дефолты: ВЫКЛ (opt-in), strip «Снять ник», 85%')
check([(t['key'], t['on']) for t in p['toggles'] if t['key'] == 'enabled']
      == [('enabled', False)] and len(p['toggles']) == 7,
      'все семь флагов конфига на месте')
check(p['log_auto'] is True and p['log_channel_name'] is None
      and p['protected_count'] == 0,
      'лог-канал «авто», своих строк нет — как в эмбеде')
check(p['strike_limit'] == 3 and p['strike_window_days'] == 7,
      'лимит и окно — константы кога')
COG.set_cfg(777, 'log_channel_id', 555)
ok, err, code, p = AF.status_flow(lambda: FB2, '777')
check(p['log_channel_name'] == 'мод-логи' and p['log_auto'] is False,
      'заданный лог-канал подхвачен из кэша')

print('== 4. Переключатели, действие, порог ==')
ok, err, code, p = AF.toggle_flow(lambda: FB2, '777', 'enabled')
check(ok and p['message'] == 'Система: вкл' and p['on'] is True,
      'toggle enabled == /antifake on (дефолт был выкл)')
check(IM.AntiFake(None).cfg(777)['enabled'] is True,
      'запись дошла до файла — её увидит и свежий ког')
ok, err, code, p = AF.toggle_flow(lambda: FB2, '777', 'enabled')
check(ok and p['on'] is False, 'выключение назад')
ok, err, code, p = AF.toggle_flow(lambda: FB2, '777', 'check_ads')
check(ok and p['message'] == 'Анти-реклама: выкл', 'флаг рекламы переключён')
ok, err, code, p = AF.toggle_flow(lambda: FB2, '777', 'погода')
check(not ok and code == 400 and err == AF.ERR_KEY, 'чужой ключ — 400')
ok, err, code, p = AF.action_flow(lambda: FB2, '777', 'kick')
check(ok and p['message'] == 'Действие при подделке: Кикнуть'
      and p['action'] == 'kick' and p['status']['action_label'] == 'Кикнуть',
      'действие — словами команды без маркдауна')
ok, err, code, p = AF.action_flow(lambda: FB2, '777', 'ban')
check(not ok and code == 400 and err == AF.ERR_ACTION, 'чужое действие — 400')
AF.action_flow(lambda: FB2, '777', 'strip')
ok, err, code, p = AF.threshold_flow(lambda: FB2, '777', 90)
check(ok and p['message'] == 'Порог похожести: 90%'
      and abs(COG.cfg(777)['threshold'] - 0.9) < 1e-9,
      'порог — словами команды, в конфиге доля')
for bad in (59, 101, 'х'):
    ok, err, code, p = AF.threshold_flow(lambda: FB2, '777', bad)
    check(not ok and code == 400 and err == AF.ERR_THRESHOLD,
          f'порог {bad!r} — 400')
AF.threshold_flow(lambda: FB2, '777', 85)

print('== 5. Защищаемые строки ==')
ok, err, code, p = AF.protect_flow(lambda: FB2, '777', 'AetherBank')
check(ok and p['message'] == 'Защищаемые строки (1): AetherBank',
      'protect — словами команды')
ok, err, code, p = AF.protect_flow(lambda: FB2, '777', 'AetherBank')
check(ok and p['protected_names'] == ['AetherBank'], 'дубль не добавляется')
ok, err, code, p = AF.protect_flow(lambda: FB2, '777', '   ')
check(ok and p['protected_names'] == ['AetherBank'], 'пустая строка мимо — как в команде')
ok, err, code, p = AF.unprotect_flow(lambda: FB2, '777', 'AetherBank')
check(ok and p['message'] == 'Осталось строк: 0'
      and p['protected_names'] == [], 'unprotect — словами команды')

print('== 6. Сухой прогон 1:1 /antifake test ==')
ok, err, code, p = AF.test_member_flow(lambda: FB2, '777', 3)
check(ok and p['clean'] is False
      and p['findings'] == [{'kind': 'name',
                             'text': 'Имя похоже на moder_admin (совпадение 100%)'}],
      'хамелеон пойман — строка команды без эмодзи')
ok, err, code, p = AF.test_member_flow(lambda: FB2, '777', 4)
check(ok and p['clean'] is False
      and p['findings'] == [{'kind': 'avatar',
                             'text': 'Аватар скопирован с Модератор'}],
      'украденный аватар — строка команды')
check(COG.find_stolen_avatar(THIEF) is ADMIN, 'find_stolen_avatar кога сам находит')
ok, err, code, p = AF.test_member_flow(lambda: FB2, '777', 5)
check(ok and p['clean'] is True
      and p['verdict'] == 'Чисто — подделки не найдено',
      'чистый — вердикт команды без эмодзи')
ok, err, code, p = AF.test_member_flow(lambda: FB2, '777', 'х')
check(not ok and code == 400 and err == AF.ERR_NUMBER, 'битый ID — 400')
ok, err, code, p = AF.test_member_flow(lambda: FB2, '777', 424242)
check(not ok and code == 404 and err == 'Участник не найден!',
      'нет такого — словами поисковых команд')

print('== 7. Лаборатория строки ==')
ok, err, code, p = AF.lab_flow(lambda: FB2, '777', 'mоder_admin')
check(ok and p['catch'] is True and p['norm'] == 'moderadmin'
      and p['confusables'] is True and p['threshold_pct'] == 85,
      'разбор хамелеона: канон, флаг, вердикт')
check(p['matches'][0]['name'] == 'moder_admin'
      and p['matches'][0]['score_pct'] == 100
      and p['matches'][0]['catch'] is True,
      'ближайшее защищаемое имя — 100%')
AF.protect_flow(lambda: FB2, '777', 'AetherBank')
ok, err, code, p = AF.lab_flow(lambda: FB2, '777', 'АetherBank')
row = next((r for r in p['matches'] if r['name'] == 'AetherBank'), None)
check(row is not None and row['source'] == 'string'
      and row['score_pct'] == 100 and row['catch'] is True,
      'защищаемая строка ловит свою подделку')
ok, err, code, p = AF.lab_flow(lambda: FB2, '777', 'совсем другой текст')
check(ok and p['catch'] is False and p['confusables'] is True,
      'хамелеоны без похожести — вердикт честный «мимо»')
ok, err, code, p = AF.lab_flow(lambda: FB2, '777', '###')
check(ok and p['norm'] == '' and p['catch'] is False,
      'пустая каноническая форма не паникует')
ok, err, code, p = AF.lab_flow(lambda: FB2, '777', '   ')
check(not ok and code == 400 and err == AF.ERR_TEXT, 'пустой текст — 400')
AF.unprotect_flow(lambda: FB2, '777', 'AetherBank')

print('== 8. Страйки рекламы ==')
now = time.time()
_strike_data = {'5': [now - 100, now - 3600, now - 9 * 86400],
                '9': [now - 50]}
# файл-первый контракт: панель читает тот же файл, что пишет ког
import json as _json
with open(IM.STRIKES_PATH, 'w', encoding='utf-8') as _f:
    _json.dump({'777': _strike_data}, _f)
COG._strikes['777'] = {k: list(v) for k, v in _strike_data.items()}
ok, err, code, p = AF.strikes_flow(lambda: FB2, '777')
check(ok and p['limit'] == 3 and p['window_days'] == 7,
      'лимит и окно — из кога')
check([e['user_id'] for e in p['entries']] == ['5', '9'],
      'сортировка по активным')
e5 = p['entries'][0]
check(e5['name'] == 'Участник' and e5['total'] == 3 and e5['active'] == 2
      and re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', e5['last_at']),
      'имя из кэша, старый страйк вне окна, дата читаемая')
check(p['entries'][1]['name'] is None, 'ушедший — без имени (честно)')
ok, err, code, p = AF.clear_strikes_flow(lambda: FB2, '777', 5)
check(ok and p['message'] == 'Снято страйков: 3.' and p['removed'] == 3
      and p['member'] == 'Участник' and len(p['strikes']['entries']) == 1,
      'обнуление через хелпер кога')
check(COG.strike_view(777) == {'9': COG.strike_view(777)['9']},
      'в памяти кога тоже чисто')
ok, err, code, p = AF.clear_strikes_flow(lambda: FB2, '777', 5)
check(not ok and code == 404 and err == AF.NO_STRIKES,
      'повторное обнуление — честный 404')
COG._strikes.pop('777', None)

print('== 9. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


for f in (IM.CFG_PATH, IM.STRIKES_PATH):
    if os.path.exists(f):
        os.remove(f)
COG2 = IM.AntiFake(None)
COG2.set_cfg(777, 'log_channel_id', 555)
FB3 = FakeBot([G], {'AntiFake': COG2})
appmod.bot_instance = FB3
try:
    check(client.get('/antifake').status_code in (302, 401, 403),
          'гостю страница закрыта')
    check(client.get('/api/guild/777/antifake/status').status_code
          in (302, 401, 403), 'гостю API закрыто')
    login('uye')
    check(client.get('/antifake').status_code == 403, 'uye не видит')
    login('mod')
    page = client.get('/antifake')
    body = page.get_data(as_text=True)
    check(page.status_code == 200 and 'Антифейк' in body
          and 'CAN_EDIT = false' in body, 'mod открывает страницу на чтение')
    d = client.get('/api/guild/777/antifake/status').get_json()
    check(d['success'] and d['threshold_pct'] == 85
          and d['log_channel_name'] == 'мод-логи', 'статус через API')
    check(client.post('/api/guild/777/antifake/toggle',
                      json={'key': 'enabled'}).status_code == 403,
          'mod не щёлкает флагами')
    check(client.post('/api/guild/777/antifake/test',
                      json={'user_id': 3}).status_code == 403,
          'mod не гоняет сухой прогон — как и в боте (admin)')
    r = client.post('/api/guild/777/antifake/lab',
                    json={'text': 'mоder_admin'})
    check(r.status_code == 200 and r.get_json()['catch'] is True,
          'mod держит лабораторию')
    login('admin')
    body = client.get('/antifake').get_data(as_text=True)
    check('CAN_EDIT = true' in body, 'admin видит формы')
    r = client.post('/api/guild/777/antifake/action', json={'action': 'jail'})
    check(r.status_code == 200
          and r.get_json()['message'] == 'Действие при подделке: В джейл (Tag Jail)',
          'действие через API 1:1')
    r = client.post('/api/guild/777/antifake/threshold', json={'percent': 55})
    check(r.status_code == 400 and r.get_json()['error'] == AF.ERR_THRESHOLD,
          'низкий порог — 400 через API')
    r = client.post('/api/guild/777/antifake/protect', json={'text': 'AetherBank'})
    check(r.status_code == 200
          and r.get_json()['protected_names'] == ['AetherBank'],
          'protect через API')
    check(IM.AntiFake(None).cfg(777)['protected_names'] == ['AetherBank'],
          'строка дошла до файла кога')
    COG2._strikes['777'] = {'5': [time.time() - 42]}
    with open(IM.STRIKES_PATH, 'w', encoding='utf-8') as _f:
        _json.dump({'777': {'5': [time.time() - 42]}}, _f)
    d = client.get('/api/guild/777/antifake/strikes').get_json()
    check(d['success'] and d['entries'][0]['active'] == 1,
          'страйки через API (файл-первый)')
    r = client.get('/api/guild/777/antifake/strikes.csv')
    body = r.get_data(as_text=True)
    check(r.headers['Content-Disposition']
          .endswith('antifake_strikes_777.csv'), 'CSV: имя файла')
    check(body.startswith('\ufeffuser_id;name;active;total;last_at')
          and '5;Участник;1;1;' in body, 'CSV: BOM, шапка, строка')
    r = client.post('/api/guild/777/antifake/strikes/clear',
                    json={'user_id': 5})
    check(r.status_code == 200 and r.get_json()['removed'] == 1,
          'обнуление через API')
    appmod.bot_instance = None
    check(client.get('/api/guild/777/antifake/status').status_code == 200,
          'статус без бота — 200 (файл-первый, панель живёт отдельным процессом)')
    check(client.post('/api/guild/777/antifake/lab',
                      json={'text': 'x'}).status_code == 200,
          'лаборатория без бота — 200 (чистые функции кога)')
finally:
    appmod.bot_instance = None

print('== 10. Шаблон, ког, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/antifake.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/antifake_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле панели нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
check('confirmAction(' in tpl or 'askConfirm(' in tpl, 'опасные действия через confirmAction')
for fid in ('afAction', 'afThr', 'afThrGo', 'afReload', 'afLogPill',
            'afProtPill', 'afStrikePill', 'afStatMsg', 'afToggles',
            'afProtIn', 'afProtGo', 'afProtList', 'afProtMsg', 'afTestPanel',
            'afTestUid', 'afTestGo', 'afTestMsg', 'afTestRes', 'afLabText',
            'afLabGo', 'afLabMsg', 'afLabRes', 'afStrikesBox',
            'afStrikesReload', 'afStrikesCsv', 'afStMsg'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/status'", "'/toggle'", "'/action'", "'/threshold'",
             "'/protect'", "'/unprotect'", "'/test'", "'/lab'", "'/strikes'",
             "'/strikes/clear'", "'/strikes.csv'"):
    check(path in tpl, f'путь {path} в шаблоне')
check(hasattr(IM, 'AntiFake') and callable(IM.setup), 'ког impersonation цел')
check(hasattr(IM.AntiFake, 'strike_view')
      and hasattr(IM.AntiFake, 'clear_strikes'),
      'хелперы страйков в коге')
check(AF.IM is IM, 'панель зовёт сам модуль кога, не копию')
import services.panel_menu as PM
prot_pages = [pg['path'] for g in PM.MENU if g['key'] == 'protection'
              for pg in g['pages']]
check('/antifake' in prot_pages, 'пункт меню «Антифейк» в категории «Защита»')
check(PM.PAGE_COGS.get('/antifake') == ('impersonation',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('antifake_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
