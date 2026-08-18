# -*- coding: utf-8 -*-
"""Панель «Локдаун» (идеи #121-125).

Замок/откат семантикой команд кога на фейк-гильдии (снимки до мутации,
пропуски, метаданные since/by/reason, сброс при полном откате), статус
строкой state_summary, предпросмотр целей, офлайн — 409, CSV, права.

Запуск: python3 tests/test_lockdown_panel.py
"""
import asyncio
import importlib
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_lockdown_test_')
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


import discord  # noqa: E402
from db import GuildData  # noqa: E402
from cogs import lockdown as LD  # noqa: E402
from web.routes import lockdown_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
T = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)

LOOP = asyncio.new_event_loop()
threading.Thread(target=LOOP.run_forever, daemon=True).start()

PERMS1 = {'send_messages': True, 'add_reactions': None,
          'create_public_threads': None, 'connect': True}
PERMS2 = {'send_messages': None, 'add_reactions': True,
          'create_public_threads': False, 'connect': None}


class FakeChannel:
    def __init__(self, cid, name, perms):
        self.id, self.name = cid, name
        self.ow = SimpleNamespace(**perms)

    def overwrites_for(self, role):
        return self.ow

    async def set_permissions(self, role, overwrite=None, reason=None):
        self.ow = overwrite


class FakeGuild:
    def __init__(self, gid, channels):
        self.id, self.name = gid, 'Тестоград'
        self.text_channels = channels
        self.default_role = object()
        self.system_channel = None

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == cid), None)


class FakeBot:
    def __init__(self, guild):
        self.guild, self.guilds = guild, [guild]
        self.loop = LOOP

    def get_guild(self, gid):
        return self.guild if gid == self.guild.id else None

    def get_cog(self, name):
        return None


print('== 1. Чистая арифметика 1:1 ==')
check(LD.state_summary(None) == 'локдауна нет', 'пусто — словами кога')
ow = SimpleNamespace(**PERMS1)
snap = LD.snapshot_overwrite(ow)
check(snap == PERMS1 and set(snap) == set(LD.WATCHED_PERMS), 'снимок по 4 правам')
LD.apply_lock(ow)
check(all(getattr(ow, p) is False for p in LD.WATCHED_PERMS), 'замок — всё в False')
LD.apply_restore(ow, snap)
check(all(getattr(ow, p) == PERMS1[p] for p in LD.WATCHED_PERMS), 'откат вернул исходник')
st = LD.empty_state()
st['channels'] = {'5': dict(PERMS1), '6': dict(PERMS2)}
st['since'] = 'не дата'
st['reason'] = 'рейд ' + 'х' * 100
check(LD.state_locked_count(st) == 2 and LD.is_locked(st, 5) and not LD.is_locked(st, 7),
      'счёт и проверка замка')
summary = LD.state_summary(st, now=T)
check(summary.startswith('2 канала закрыто') and 'давно' in summary
      and 'рейд ' + 'х' * 55 in summary, 'сводка: битая дата → «давно», причина [:60]')

print('== 2. Виды без бота ==')
view = SP.status_view(None, st)
check(view['summary'] == summary and view['count'] == 2, 'статус без бота')
check(view['channels'][0]['name'] == '' and view['channels'][0]['saved'] == PERMS1,
      'без бота имён нет — только ID и снимки')
labels = {p['perm']: p['label'] for p in SP.saved_perms_view(PERMS1)}
check(labels['send_messages'] == 'разрешено' and labels['add_reactions'] == 'наследуется',
      'права словами')
guild = FakeGuild(777, [FakeChannel(5, 'general', PERMS1), FakeChannel(6, 'memes', PERMS2)])
pv = SP.preview_targets(guild, st, 'all')
check([t['name'] for t in pv] == ['general', 'memes']
      and all(t['already'] for t in pv), 'предпросмотр: оба уже под замком')
check([t['id'] for t in SP.preview_targets(guild, st, '5')] == ['5'], 'цель по ID')
check([t['id'] for t in SP.preview_targets(guild, st, '#memes')] == ['6'], 'цель по имени')
check(SP.preview_targets(guild, st, '#нет') == [], 'нет такого — пусто')

print('== 3. API офлайн ==')
GuildData('lockdown').set('777', 'state', st)
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


ST_URL = '/api/guild/777/lockdown/status'
check(client.get('/lockdown').status_code in (302, 401, 403), 'гостю страница закрыта')
login('uye')
check(client.get(ST_URL).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/lockdown')
check(page.status_code == 200 and 'Локдаун' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(ST_URL).get_json()
check(d['status']['count'] == 2 and d['bot_online'] is False and d['can_edit'] is False,
      'статус из хранилища, бот офлайн')
r = client.post('/api/guild/777/lockdown/preview', json={'spec': 'all'})
check(r.status_code == 409 and 'Бот офлайн' in r.get_json()['error'], 'предпросмотр — 409')
r = client.post('/api/guild/777/lockdown/lock', json={'spec': 'all'})
check(r.status_code == 403, 'mod не жмёт красную кнопку')
login('admin')
r = client.post('/api/guild/777/lockdown/lock', json={'spec': 'all'})
check(r.status_code == 409, 'admin офлайн — 409 без частичного замка')
r = client.post('/api/guild/777/lockdown/unlock', json={'spec': 'all'})
check(r.status_code == 409, 'откат офлайн — тоже 409')
check(GuildData('lockdown').get('777', 'state', {})['channels'] != {},
      'после 409 состояние не пострадало')

print('== 4. Живой замок и откат ==')
bot = FakeBot(FakeGuild(777, [FakeChannel(5, 'general', dict(PERMS1)),
                              FakeChannel(6, 'memes', dict(PERMS2))]))
GuildData('lockdown').set('777', 'state', LD.empty_state())
appmod.bot_instance = bot

ok, err, payload = SP.lock_flow(bot, '777', bot.guild, '#нет', None, 'Панелька', now=T)
check(not ok and err == SP.NO_TARGET_TEXT, 'нет цели — текст команды')
ok, err, payload = SP.lock_flow(bot, '777', bot.guild, 'all', 'рейд из чата', 'Панелька', now=T)
check(ok and payload['title'] == 'Локдаун включён' and payload['line'] == '2 канала закрыто',
      'замок: оба канала')
ch1, ch2 = bot.guild.text_channels
check(all(getattr(ch1.ow, p) is False for p in LD.WATCHED_PERMS), 'канал 1 реально закрыт')
saved = GuildData('lockdown').get('777', 'state', {})
check(saved['channels']['5'] == PERMS1 and saved['channels']['6'] == PERMS2,
      'снимки исходные, не замковые')
check(saved['by'] == 'Панелька' and saved['reason'] == 'рейд из чата'
      and saved['since'] == T.isoformat(), 'метаданные как у команды')
ok, err, payload = SP.lock_flow(bot, '777', bot.guild, 'all', None, 'Панелька', now=T)
check(ok and payload['title'] == 'Локдаун: ничего не закрылось'
      and len(payload['skipped']) == 2, 'повторный замок — все в пропусках')
saved2 = GuildData('lockdown').get('777', 'state', {})
check(saved2['since'] == T.isoformat() and len(saved2['channels']) == 2,
      'since не перетёрся повтором')
ok, err, payload = SP.unlock_flow(bot, '777', bot.guild, '5', now=T)
check(ok and payload['title'] == 'Локдаун снят' and len(payload['restored']) == 1,
      'точечный откат одного канала')
check(all(getattr(ch1.ow, p) == PERMS1[p] for p in LD.WATCHED_PERMS),
      'права канала 1 — исходные')
check(GuildData('lockdown').get('777', 'state', {})['since'] == T.isoformat(),
      'замок не пуст — метаданные живы')
ok, err, payload = SP.unlock_flow(bot, '777', bot.guild, '999', now=T)
check(not ok and err == 'Не нашёл такой канал.', 'откат чужого — текст команды')
ok, err, payload = SP.unlock_flow(bot, '777', bot.guild, 'all', now=T)
check(ok and len(payload['restored']) == 1 and payload['summary'] == 'локдауна нет',
      'полный откат — сводка кога')
saved3 = GuildData('lockdown').get('777', 'state', {})
check(saved3['channels'] == {} and saved3['since'] is None and saved3['by'] is None,
      'пустой замок — метаданные сброшены, как у кога')
ok, err, payload = SP.unlock_flow(bot, '777', bot.guild, 'all', now=T)
check(ok and payload['title'] == 'Локдаун: нечего открывать'
      and payload['missing'][0]['why'] == 'не был под замком', 'откат без замка')

print('== 5. Сбой прав Discord — в пропуски ==')


class BrokenChannel(FakeChannel):
    async def set_permissions(self, role, overwrite=None, reason=None):
        resp = SimpleNamespace(status=403, reason='Forbidden')
        raise discord.HTTPException(resp, 'Missing Permissions')


GuildData('lockdown').set('777', 'state', LD.empty_state())
bot2 = FakeBot(FakeGuild(777, [FakeChannel(5, 'general', dict(PERMS1)),
                               BrokenChannel(9, 'mod-chat', dict(PERMS2))]))
appmod.bot_instance = bot2
ok, err, payload = SP.lock_flow(bot2, '777', bot2.guild, 'all', 'рейд', 'Панелька', now=T)
check(ok and len(payload['locked']) == 1 and payload['skipped'][0]['why'] == 'нет прав у бота',
      'Forbidden → пропуск, как у команды')
st4 = GuildData('lockdown').get('777', 'state', {})
check(list(st4['channels']) == ['5'], 'битый канал без снимка')
ok, err, payload = SP.unlock_flow(bot2, '777', bot2.guild, 'all', now=T)
check(ok and len(payload['restored']) == 1, 'откат целого проходит при битом соседе')

print('== 6. Живые эндпоинты ==')
appmod.bot_instance = bot2
login('mod')
r = client.post('/api/guild/777/lockdown/preview', json={'spec': 'all'})
d = r.get_json()
check(r.status_code == 200 and len(d['targets']) == 2, 'предпросмотр живой')
login('admin')
r = client.post('/api/guild/777/lockdown/lock', json={'spec': '5', 'reason': 'волна спама'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['line'] == '1 канал закрыт',
      'замок через API')
r = client.get(ST_URL)
d = r.get_json()
check(d['status']['count'] == 1 and d['status']['by'] == 'admin'
      and d['status']['reason'] == 'волна спама', 'статус видит замок с метаданными')
check(d['status']['channels'][0]['name'] == 'general', 'имя канала от живого бота')
r = client.post('/api/guild/777/lockdown/unlock', json={'spec': '5'})
check(r.get_json()['success'] and r.get_json()['restored'], 'откат через API')
appmod.bot_instance = None

print('== 7. CSV ==')
GuildData('lockdown').set('777', 'state', st)
rows = SP.csv_rows(FakeGuild(777, [FakeChannel(5, 'general', PERMS1)]), st)
check(rows[0][1] == 'general' and 'send_messages: разрешено' in rows[0][2],
      'строка выгрузки с правами')
check(rows[1][1] == '—', 'без канала — прочерк')
login('mod')
csv_r = client.get('/api/guild/777/lockdown/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'lockdown_777.csv' in csv_r.headers.get('Content-Disposition', ''), 'имя файла')
check(body.startswith('\ufeffchannel_id;channel'), 'BOM + шапка')
login('uye')
check(client.get('/api/guild/777/lockdown/export.csv').status_code == 403, 'uye не выгружает')

print('== 8. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/lockdown.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('ldBanner', 'ldList', 'ldControls', 'ldSpec', 'ldReason', 'ldLock',
            'ldUnlock', 'ldPreview', 'ldCsv'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/status'" in tpl and "'/preview'" in tpl and "API + '/' + action" in tpl
      and '/export.csv' in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/lockdown' in mod_pages, 'пункт меню «Локдаун» в «Модерации»')
check(PM.PAGE_COGS.get('/lockdown') == ('lockdown',), 'lockdown-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('lockdown_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
