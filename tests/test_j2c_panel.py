# -*- coding: utf-8 -*-
"""Панель «Комнаты join-to-create» (идеи #76-80).

Конфиг 1:1 с DEFAULT_CFG кога, живой бот — через экземпляр кога
(set_cfg/_del_room: память+диск), офлайн — файлы; рамки /j2c
(лимит 0..99, шаблон [:96], пустой → дефолт); превью имени — строчка
_create_room кога (срез у шаблона, не у результата); реестр с живыми/
сиротами; prune только при онлайне; права mod+/admin+.

Запуск: python3 tests/test_j2c_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_j2c_test_')
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


from web.routes import j2c_panel as JP  # noqa: E402
from cogs import join_to_create as JC  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
DEF = JC.DEFAULT_CFG


class _FakeChannel:
    def __init__(self, cid, members=()):
        self.id = cid
        self.members = list(members)


class _FakeGuild:
    id = 777
    name = 'Тестхейм'

    def __init__(self, channels):
        self._ch = channels

    def get_channel(self, cid):
        return self._ch.get(cid)


class _FakeCog:
    def __init__(self):
        self._cfgs = {'777': {'enabled': True, 'lobby_id': 111}}
        self._rooms = {'777': {'555': 42, '557': 44}}

    def cfg(self, gid):
        c = dict(DEF)
        c.update(self._cfgs.get(str(gid), {}))
        return c

    def set_cfg(self, gid, key, value):
        self._cfgs.setdefault(str(gid), {})[key] = value

    def _room_map(self, gid):
        return self._rooms.setdefault(str(gid), {})

    def _del_room(self, gid, cid):
        self._rooms.get(str(gid), {}).pop(str(cid), None)


class _FakeBot:
    def __init__(self, cog, guild):
        self._cog = cog
        self._guild = guild
        self.guilds = [guild]

    def get_guild(self, gid):
        return self._guild if gid == 777 else None

    def get_cog(self, name):
        return self._cog if name == 'JoinToCreate' else None


print('== 1. Конфиг: дефолты кога, живой/офлайн ==')
check(JP.JC is JC and JP.JC.DEFAULT_CFG is DEF, 'дефолты — словарь кога, без копий')
cfg, live = JP.read_cfg(None, 777)
check(live is False and cfg == DEF, 'без файла — чистый DEFAULT_CFG')
with open('data/j2c.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': {'enabled': False, 'lobby_id': 111}, '778': 'oops'}, fh)
cfg, live = JP.read_cfg(None, 777)
check(live is False and cfg['enabled'] is False and cfg['lobby_id'] == 111
      and cfg['user_limit'] == 0 and cfg['name_template'] == DEF['name_template'],
      'файл поверх дефолтов')
cfg, _ = JP.read_cfg(None, 778)
check(cfg == DEF, 'битая запись соседа — дефолты')
fake_cog = _FakeCog()
fake_bot = _FakeBot(fake_cog, _FakeGuild({111: _FakeChannel(111)}))
cfg, live = JP.read_cfg(fake_bot, 777)
check(live is True and cfg['enabled'] is True and cfg['lobby_id'] == 111,
      'живой бот — конфиг из памяти кога')

print('== 2. Готовность ==')
base = dict(DEF, enabled=True, lobby_id=111)
check(JP.readiness(base, True, None) == {'ready': True, 'issues': []},
      'лобби на месте — жива')
check(JP.readiness(dict(base, enabled=False), True, None)['issues'] ==
      ['система выключена'], 'выключена')
check(JP.readiness(dict(DEF, enabled=True), None, None)['issues'] ==
      ['лобби не задан (0)'], 'лобби 0')
r = JP.readiness(base, False, None)
check(r['ready'] is False and r['issues'] == ['лобби не найден у бота — задайте заново'],
      'потерянный лобби фатален')
r = JP.readiness(base, True, False)
check(r['ready'] is True and r['issues'] == ['категория потеряна — комнаты лягут к лобби'],
      'потерянная категория — мягкое замечание (ког фоллбечит к лобби)')
check(JP.readiness(base, None, None)['ready'] is True,
      'офлайн-проверка не валит готовность')

print('== 3. Настройки: рамки /j2c ==')
upd, err = JP.normalize_settings({'enabled': True, 'lobby_id': '111',
                                  'category_id': '222', 'user_limit': '10',
                                  'name_template': 'Комната {user}'})
check(upd == {'enabled': True, 'lobby_id': 111, 'category_id': 222,
              'user_limit': 10, 'name_template': 'Комната {user}'} and err == '',
      'полная установка: ID числами, как пишет ког')
check(JP.normalize_settings({'user_limit': -1})[1] == 'Лимит — целое число от 0 до 99'
      and JP.normalize_settings({'user_limit': 100})[1] ==
      'Лимит — целое число от 0 до 99'
      and JP.normalize_settings({'user_limit': 'x'})[1] ==
      'Лимит — целое число от 0 до 99'
      and JP.normalize_settings({'user_limit': True})[1] ==
      'Лимит — целое число от 0 до 99', 'лимит 0..99, как Range у бота')
check(JP.normalize_settings({'lobby_id': 'abc'})[1] == 'ID лобби — только цифры',
      'лобби буквами — 400')
check(JP.normalize_settings({'category_id': ''})[0]['category_id'] == 0,
      'пустая категория — 0 (как у лобби)')
check(JP.normalize_settings({'enabled': 'да'})[1] == 'Включение — true или false',
      'строка вместо bool — 400')
upd, _ = JP.normalize_settings({'name_template': ''})
check(upd['name_template'] == DEF['name_template'], 'пустой шаблон — дефолт кога')
upd, _ = JP.normalize_settings({'name_template': 'x' * 120})
check(len(upd['name_template']) == 96, 'шаблон режется до 96, как /j2c template')
check(JP.normalize_settings({}) == ({}, ''), 'пустой запрос — ничего не меняет')

print('== 4. Превью имени 1:1 с _create_room ==')
check(JP.preview_name({}) == DEF['name_template'].replace('{user}', 'Мария'),
      'дефолт с образцом владельца')
check(JP.preview_name({'name_template': 'Комната {user}'}) == 'Комната Мария',
      'свой шаблон')
long_name = JP.preview_name({'name_template': '{user} ' + 'z' * 100})
check(len(long_name) == 95 and long_name.startswith('Мария ')
      and long_name.endswith('zzz'),
      'срез [:96] у шаблона до подстановки — 96-6+5=95, как у кога')

print('== 5. Реестр и сироты ==')
guild = _FakeGuild({555: _FakeChannel(555), 556: _FakeChannel(556, ['a', 'b'])})
bot = _FakeBot(_FakeCog(), guild)
rows = JP.room_rows({'555': 42, '556': 43, '557': 44}, bot, 777,
                    names={'42': 'Кирилл'})
check([r['channel_id'] for r in rows] == ['555', '556', '557'],
      'живые первыми по ID, сирота в хвосте')
check(rows[0]['live'] is True and rows[0]['members'] == 0
      and rows[0]['owner_name'] == 'Кирилл', 'пустая живая, имя из аудита')
check(rows[1]['members'] == 2, 'двое в живой')
check(rows[2]['live'] is False and rows[2]['members'] is None, 'сирота помечена')
rows = JP.room_rows({'556': 43, '555': 42}, None, 777)
check(all(r['live'] is None for r in rows)
      and [r['channel_id'] for r in rows] == ['555', '556'],
      'офлайн — честные None и порядок по ID')

print('== 6. Запись: живой ког/файл ==')
cfg_before = json.load(open('data/j2c.json', encoding='utf-8'))
live = JP.apply_settings(None, 777, {'user_limit': 5})
disk = json.load(open('data/j2c.json', encoding='utf-8'))
check(live is False and disk['777']['user_limit'] == 5
      and disk['777']['enabled'] is False and disk['778'] == 'oops',
      'офлайн: файл дополнен, соседи целы')
fake_cog = _FakeCog()
live = JP.apply_settings(_FakeBot(fake_cog, guild), 777,
                         {'enabled': False, 'user_limit': 3})
check(live is True and fake_cog._cfgs['777']['enabled'] is False
      and fake_cog._cfgs['777']['user_limit'] == 3,
      'живой: через set_cfg кога (память бота обновлена)')

print('== 7. API: права и потоки ==')
with open('data/j2c_rooms.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': {'555': 42, '557': 44}}, fh)
with open('data/j2c.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': {'enabled': True, 'lobby_id': 111}}, fh)
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '42', 'user_name': 'Кирилл',
         'timestamp': '2026-08-16T10:00:00+00:00'},
    ]}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/j2c/overview'
check(client.get('/join-to-create').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/join-to-create').status_code == 200, 'mod открывает страницу')

appmod.set_bot_instance(None)
ov = client.get(OV).get_json()
check(ov['bot_online'] is False and ov['live'] is False
      and ov['readiness']['ready'] is True, 'офлайн: живём по файлам, готова')
check(all(r['live'] is None for r in ov['rooms']) and ov['rooms_total'] == 2,
      'офлайн: реестр с диска, статусы «не проверить»')
r = client.post('/api/guild/777/j2c/rooms/prune', json={})
check(r.status_code == 403, 'mod не чистит реестр')

login('admin')
r = client.post('/api/guild/777/j2c/rooms/prune', json={})
check(r.status_code == 409
      and r.get_json()['error'] == 'Бот офлайн — сироты не проверить',
      'офлайн-чистка — 409 честно')

cog = _FakeCog()
guild = _FakeGuild({111: _FakeChannel(111), 555: _FakeChannel(555)})
appmod.set_bot_instance(_FakeBot(cog, guild))
ov = client.get(OV).get_json()
check(ov['bot_online'] is True and ov['live'] is True
      and ov['readiness'] == {'ready': True, 'issues': []},
      'онлайн: конфиг кога, лобби найден')
check(ov['rooms_live'] == 1 and ov['rooms'][-1]['live'] is False,
      'одна живая, сирота в хвосте')
check(ov['rooms'][0]['owner_name'] == 'Кирилл', 'владелец из аудит-журнала')
check(ov['preview'] == DEF['name_template'].replace('{user}', 'Мария'),
      'превью дефолтного шаблона')

r = client.post('/api/guild/777/j2c/settings',
                json={'user_limit': '25', 'name_template': 'Комната {user}'})
d = r.get_json()
check(r.status_code == 200 and d['live'] is True and d['changed'] == 2,
      'admin сохранил в живого кога')
check(cog._cfgs['777']['user_limit'] == 25
      and cog._cfgs['777']['name_template'] == 'Комната {user}',
      'память кога обновлена')
check(d['config']['user_limit'] == 25 and d['preview'] == 'Комната Мария',
      'свежие конфиг и превью в ответе')
r = client.post('/api/guild/777/j2c/settings', json={'user_limit': 100})
check(r.status_code == 400
      and r.get_json()['error'] == 'Лимит — целое число от 0 до 99', 'лимит — 400')
r = client.post('/api/guild/777/j2c/settings', json={'lobby_id': 'abc'})
check(r.status_code == 400
      and r.get_json()['error'] == 'ID лобби — только цифры', 'лобби — 400')

guild._ch.pop(111)
ov = client.get(OV).get_json()
check(ov['readiness']['ready'] is False
      and 'лобби не найден у бота — задайте заново' in ov['readiness']['issues'],
      'удалённый лобби виден в диагностике')

r = client.post('/api/guild/777/j2c/rooms/prune', json={})
check(r.status_code == 200 and r.get_json()['removed'] == 1, 'сирота вычищена')
check('557' not in cog._rooms['777'] and '555' in cog._rooms['777'],
      'реестр кога почищен точечно')
r = client.post('/api/guild/777/j2c/rooms/prune', json={})
check(r.get_json()['removed'] == 0, 'повтор — чисто')

print('== 8. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/j2c.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('j2Kpis', 'j2Status', 'j2Rooms', 'j2Form', 'j2Enabled', 'j2Lobby',
            'j2Category', 'j2Limit', 'j2Template', 'j2Msg', 'j2PreviewBox',
            'j2Prune', 'j2PruneWrap'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/settings'" in tpl and "'/rooms/prune'" in tpl,
      'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/join-to-create' in com_pages, 'пункт «Комнаты J2C» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/join-to-create') == ('join_to_create',),
      'join_to_create-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('j2c_panel') >= 1, 'модуль зарегистрирован в routes_extra')
import services.notification_dispatcher as ND
check(ND.EVENTS['j2c'][0] == 'event_j2c'
      and ND.DEFAULT_SETTINGS['event_j2c'] is True
      and ND.EVENT_LINKS['j2c'] == '/join-to-create',
      'событие j2c зарегистрировано в диспетчере')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
