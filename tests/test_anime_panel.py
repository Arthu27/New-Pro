# -*- coding: utf-8 -*-
"""Панель «Аниме дня» (идеи #66-70).

Конфиг 1:1 с записью /anime-setup (пять ключей, типы), категории —
единый словарь кога, next_run 1:1 с before_loop (10:00 локально),
превью настоящим _embed_build кога (обрезка сводки 300+«...»),
диагностика готовности, права mod+/admin+, шаблон без эмодзи.

Запуск: python3 tests/test_anime_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix='aether_anime_test_')
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


from web.routes import anime_panel as AP  # noqa: E402
from cogs import anime_daily as AD  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')


print('== 1. Конфиг 1:1 с записью кога ==')
check(AP.KATEGORILER is AD.KATEGORILER, 'категории — единый словарь кога')
pub = AP.public_config(None, 777)
check(pub == {'configured': False, 'enabled': False, 'channel_id': None,
              'role_id': None, 'tur_id': None, 'category': 'Случайно'},
      'пустое хранилище — честные дефолты')
pub = AP.public_config({'777': {'enabled': True, 'channel_id': 123, 'tur_id': 4,
                                'tur_adi': 'Комедия', 'role_id': 456}}, '777')
check(pub['configured'] and pub['enabled'] and pub['channel_id'] == 123
      and pub['category'] == 'Комедия' and pub['tur_id'] == 4,
      'запись гильдии читается')
pub = AP.public_config({'777': 'oops'}, 777)
check(pub['configured'] is False and pub['enabled'] is False,
      'не-словарь вместо записи — дефолты')

print('== 2. Следующая отправка 1:1 с before_loop ==')
check(AP.next_run(datetime(2026, 8, 16, 9, 30)) == datetime(2026, 8, 16, 10, 0),
      'утро — сегодня в 10:00')
check(AP.next_run(datetime(2026, 8, 16, 10, 0)) == datetime(2026, 8, 17, 10, 0),
      'ровно 10:00 — уже завтра (ког: now >= target)')
check(AP.next_run(datetime(2026, 8, 16, 10, 0, 0, 1)) == datetime(2026, 8, 17, 10, 0),
      'секунда после — завтра')
check(AP.next_run(datetime(2026, 8, 16, 23, 59)) == datetime(2026, 8, 17, 10, 0),
      'вечер — завтра')
check(AP.next_run(datetime(2026, 12, 31, 23, 59)) == datetime(2027, 1, 1, 10, 0),
      'переход через Новый год')

print('== 3. Диагностика готовности ==')
ready = AP.readiness(AP.public_config({}, 1), None, None)
check(ready['ready'] is False
      and any('не заданы' in t for t in ready['issues'])
      and any('выключена' in t for t in ready['issues'])
      and any('канал не задан' in t for t in ready['issues']),
      'пустой конфиг — три причины молчания')
cfg_on = {'configured': True, 'enabled': True, 'channel_id': 123, 'role_id': 456,
          'tur_id': 4, 'category': 'Комедия'}
check(AP.readiness(cfg_on, True, True) == {'ready': True, 'issues': []},
      'всё на месте — готово без замечаний')
check(AP.readiness(cfg_on, False, True)['ready'] is False
      and AP.readiness(cfg_on, False, True)['issues'] ==
      ['канал не найден у бота — задайте заново'],
      'потерянный канал — отдельная причина, готовности нет')
r = AP.readiness(cfg_on, None, False)
check(r['ready'] is True and r['issues'] == ['роль не найдена у бота — задайте заново'],
      'офлайн-канал не мешает (None), потерянная роль — замечание')
off = dict(cfg_on, enabled=False)
check(AP.readiness(off, True, True)['issues'] == ['рассылка выключена'],
      'выключено — одна причина')

print('== 4. Нормализация настроек ==')
rec, err = AP.normalize_settings({}, {'enabled': True, 'channel_id': '123',
                                      'category': 'Комедия', 'role_id': ''})
check(rec == {'enabled': True, 'channel_id': 123, 'tur_id': 4,
              'tur_adi': 'Комедия', 'role_id': None} and err == '',
      'полная установка: типы как у /anime-setup (числа!), роль None')
rec, err = AP.normalize_settings({'enabled': True, 'channel_id': 123, 'tur_id': 4,
                                  'tur_adi': 'Комедия', 'role_id': None},
                                 {'category': 'Драма'})
check(rec['tur_adi'] == 'Драма' and rec['tur_id'] == 8
      and rec['channel_id'] == 123 and rec['enabled'] is True,
      'частичная правка: категория сменилась, остальное цело')
rec, err = AP.normalize_settings({}, {'category': 'Случайно'})
check(rec['tur_id'] is None and rec['tur_adi'] == 'Случайно',
      '«Случайно» — tur_id None, как у кога')
check(AP.normalize_settings({}, {'category': 'Меха'})[1] == 'Категория — из списка',
      'левая категория отброшена')
check(AP.normalize_settings({}, {'enabled': True})[1] == 'Без канала включать нельзя',
      'включение без канала запрещено')
check(AP.normalize_settings({}, {'enabled': 'да'})[1] == 'Включение — true или false',
      'строка вместо bool — 400')
check(AP.normalize_settings({}, {'channel_id': 'abc'})[1] == 'ID канала — только цифры',
      'канал буквами — 400')
check(AP.normalize_settings({}, {'role_id': '12a'})[1] == 'ID роли — только цифры',
      'роль буквами — 400')
rec, _ = AP.normalize_settings({'enabled': True, 'channel_id': 123, 'tur_id': 4,
                                'tur_adi': 'Комедия', 'role_id': 456},
                               {'channel_id': '', 'enabled': False})
check(rec['channel_id'] is None and rec['enabled'] is False
      and rec['role_id'] == 456,
      'очистка канала ставит на паузу, роль цела')

print('== 5. Превью настоящим _embed_build ==')
p = AP.preview_embed('Тестхейм', 'Комедия')
check(p['title'] == ' Аниме-предложение дня: Cowboy Bebop', 'заголовок кога')
check(len(p['description']) == 303 and p['description'].endswith('...'),
      'сводка обрезана 300+«...» — как у кога')
check([f['name'] for f in p['fields']] == [' Категория', ' Оценка', ' Эпизодов'],
      'поля в порядке кога')
check(p['fields'][0]['value'] == 'Комедия' and p['fields'][1]['value'] == '8.75'
      and p['fields'][2]['value'] == '26', 'значения полей')
check(p['footer'] == 'Тестхейм  ·  Ежедневное аниме', 'подпись кога')
check(p['has_translate_button'] is True and p['sample'] is True
      and p['summary_full_len'] == 519, 'кнопка перевода и флаг образца')

print('== 6. API: права, потоки, живой бот ==')
with open('data/anime_daily_config.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': {'enabled': True, 'channel_id': 123, 'tur_id': 4,
                       'tur_adi': 'Комедия', 'role_id': 456}}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


class _FakeGuild:
    id = 777
    name = 'Тестхейм'

    def get_channel(self, cid):
        return object() if cid == 123 else None

    def get_role(self, rid):
        return object() if rid == 456 else None


class _FakeBot:
    guilds = [_FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/anime-daily/overview'
check(client.get('/anime-daily').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/anime-daily')
check(page.status_code == 200 and 'Аниме дня' in page.get_data(as_text=True),
      'mod открывает страницу')

appmod.set_bot_instance(_FakeBot())
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает без права правки')
check(ov['config']['enabled'] is True and ov['config']['category'] == 'Комедия',
      'конфиг кога в снимке')
check(ov['readiness'] == {'ready': True, 'issues': []},
      'канал и роль нашлись у бота — готово')
check(ov['bot_online'] is True and ov['next']['at'].endswith('T10:00')
      and ov['next']['in_seconds'] > 0, 'бот онлайн, отсчёт до 10:00')
check(ov['preview']['fields'][1]['value'] == '8.75', 'превью в снимке')
check(ov['categories'] == ['Случайно'] + list(AP.KATEGORILER),
      'категории: «Случайно» + словарь кога')
check(client.post('/api/guild/777/anime-daily/settings',
                  json={'enabled': False}).status_code == 403,
      'mod не трогает настройки')

login('admin')
r = client.post('/api/guild/777/anime-daily/settings', json={'channel_id': '999'})
check(r.status_code == 200 and r.get_json()['config']['channel_id'] == 999,
      'admin сменил канал')
ov = client.get(OV).get_json()
check(ov['readiness']['ready'] is False
      and ov['readiness']['issues'] == ['канал не найден у бота — задайте заново'],
      'чужой канал сразу виден в диагностике')
disk = json.load(open('data/anime_daily_config.json', encoding='utf-8'))
check(sorted(disk['777'].keys()) == ['channel_id', 'enabled', 'role_id',
                                     'tur_adi', 'tur_id'],
      'на диске ровно пять ключей формата кога')
check(isinstance(disk['777']['channel_id'], int) and disk['777']['channel_id'] == 999,
      'канал числом (ког зовёт get_channel(int))')

r = client.post('/api/guild/777/anime-daily/settings',
                json={'enabled': 'да', 'channel_id': '123'})
check(r.status_code == 400
      and r.get_json()['error'] == 'Включение — true или false', 'не-bool — 400')
r = client.post('/api/guild/777/anime-daily/settings', json={'category': 'Меха'})
check(r.status_code == 400 and r.get_json()['error'] == 'Категория — из списка',
      'левая категория — 400')
r = client.post('/api/guild/777/anime-daily/settings',
                json={'channel_id': '', 'enabled': True})
check(r.status_code == 400 and r.get_json()['error'] == 'Без канала включать нельзя',
      'включить с пустым каналом нельзя')
r = client.post('/api/guild/777/anime-daily/settings',
                json={'channel_id': '123', 'category': 'Детектив'})
check(r.status_code == 200 and r.get_json()['config']['tur_id'] == 7,
      'детектив — tur_id 7 словарём кога')

appmod.set_bot_instance(None)
ov = client.get(OV).get_json()
check(ov['bot_online'] is False, 'офлайн честно помечен')
check(ov['readiness']['ready'] is True and ov['readiness']['issues'] == [],
      'без бота канал не валим — статус «живём по конфигу»')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/anime_daily.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('anKpis', 'anStatus', 'anForm', 'anChannel', 'anCategory', 'anRole',
            'anToggle', 'anMsg', 'anPreview'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/settings'" in tpl, 'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/anime-daily' in com_pages, 'пункт «Аниме дня» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/anime-daily') == ('anime_daily',),
      'anime_daily-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('anime_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
