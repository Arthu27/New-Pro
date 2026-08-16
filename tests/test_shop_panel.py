# -*- coding: utf-8 -*-
"""Менеджер магазина в панели (идея #10).

Проверяем: чистые функции cogs.economy_shop (валидация 1:1, лимит, нормализация
карточки, метаданные, remove с undo-карточкой), effective_items (merge без
мутации базы), интероп с когом (_items_for видит кастом), API панели
(права mod/admin, ошибки 400/404 байт-в-байт как у функций), шаблон (гейтинг
по роли, без эмодзи), меню.

Запуск: python3 tests/test_shop_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_shoppanel_test_')
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


from cogs import economy_shop as ES  # noqa: E402
from cogs import economy_cog as EC  # noqa: E402

GID = 777
BASE = EC.ITEM_DETAILS
RAR = list(EC.RARITY_ORDER)
CATS = sorted({d['category'] for d in BASE.values()} | {ES.DEFAULT_CATEGORY})
CARD = {'price': 700, 'rarity': 'редкий', 'desc': 'Светится в темноте',
        'sell': 350, 'category': 'инструменты'}

print('== 1. Чистые: валидация ==')
check(ES.load_custom(GID) == {}, 'пусто на чистой БД')
ok, err = ES.upsert_item(GID, 'амулет луны', CARD, base=BASE, rarities=RAR,
                         categories=CATS, by='panel:tester')
check(ok and err == '', 'валидный предмет сохранён')
saved = ES.load_custom(GID).get('амулет луны')
check(saved is not None and saved['price'] == 700 and saved['sell'] == 350, 'карточка как задана')
check(saved.get('by') == 'panel:tester' and saved.get('created_at') and saved.get('updated_at'),
      'метаданные by/created_at/updated_at')

cases = [
    ('', CARD, 'Введите название предмета.'),
    ('x' * 41, CARD, 'Название слишком длинное (максимум 40 символов).'),
    ('амулет!', CARD, 'В названии можно использовать только буквы, цифры, пробелы и дефис.'),
    ('ноутбук', CARD, 'Предмет с таким названием уже есть в базовом магазине.'),
    ('тест1', dict(CARD, price=' дорого '), 'Цена должна быть целым числом.'),
    ('тест1', dict(CARD, price=0), f'Цена должна быть от 1 до {ES.PRICE_MAX:,}.'),
    ('тест1', dict(CARD, price=ES.PRICE_MAX + 1), f'Цена должна быть от 1 до {ES.PRICE_MAX:,}.'),
    ('тест1', dict(CARD, sell=999999999), 'Цена продажи не может быть больше цены покупки.'),
    ('тест1', dict(CARD, sell='много'), 'Цена продажи должна быть целым числом.'),
    ('тест1', dict(CARD, rarity='мемный'), 'Неизвестная редкость.'),
    ('тест1', dict(CARD, category='зелья'), 'Неизвестная категория.'),
    ('тест1', dict(CARD, desc='д' * 101), 'Описание слишком длинное (максимум 100 символов).'),
    ('тест1', dict(CARD, category='питомцы', pet_bonus=None), 'Укажите бонус питомца (от 1 до 100%).'),
    ('тест1', dict(CARD, category='питомцы', pet_bonus=0), 'Бонус питомца должен быть от 1 до 100%.'),
    ('тест1', dict(CARD, category='питомцы', pet_bonus=101), 'Бонус питомца должен быть от 1 до 100%.'),
]
for nm, cd, want in cases:
    ok, err = ES.upsert_item(GID, nm, cd, base=BASE, rarities=RAR, categories=CATS)
    check(not ok and err == want, f'ошибка 1:1: {want[:38]}...')

ok2, err2 = ES.upsert_item(GID, 'кролик', dict(CARD, category='питомцы', pet_bonus=12),
                           base=BASE, rarities=RAR, categories=CATS)
pet = ES.load_custom(GID).get('кролик')
check(ok2 and pet['pet_bonus'] == 12 and pet['category'] == 'питомцы', 'питомец с бонусом жив')
ok3, _ = ES.upsert_item(GID, 'тень', dict(CARD, sell=None), base=BASE, rarities=RAR, categories=CATS)
check(ok3 and ES.load_custom(GID)['тень']['sell'] == CARD['price'] // 2, 'sell пустой → половина цены')

full = {f'предмет{i}': dict(saved) for i in range(ES.MAX_CUSTOM_ITEMS)}
ES._save_custom(900, full)
ok4, err4 = ES.upsert_item(900, 'ещё один', CARD, base=BASE, rarities=RAR, categories=CATS)
check(not ok4 and err4 == f'Достигнут лимит кастомных предметов ({ES.MAX_CUSTOM_ITEMS}).',
      'лимит 50 соблюдён')
ok5, _ = ES.upsert_item(900, 'предмет0', CARD, base=BASE, rarities=RAR, categories=CATS)
check(ok5, 'обновление существующего на лимите — ок')

ok6, _, removed = ES.remove_item(GID, 'тень')
check(ok6 and removed and removed['price'] == CARD['price'], 'remove отдаёт карточку для undo')
ok7, err7, _ = ES.remove_item(GID, 'тень')
check(not ok7 and err7 == 'Такого кастомного предмета нет.', 'повторный remove — честная 404-ошибка')

print('== 2. Ког: effective_items/_items_for ==')
merged = ES.effective_items(GID, BASE)
check('амулет луны' in merged and 'ноутбук' in merged, 'merge: база + кастом')
check(len(BASE) == 18, 'базовый каталог не замутирован')
check(set(ES.effective_items(None, BASE).keys()) == set(BASE.keys()), 'без сервера — только база')
check('амулет луны' in EC._items_for(777), 'ког _items_for видит кастом сервера')
check('амулет луны' not in EC._items_for(888), 'чужой сервер кастом не видит')
check(set(EC._items_for(None).keys()) == set(BASE.keys()), 'ког без гильдии — базовый каталог')
from db import GuildData  # noqa: E402
GuildData('economy_shop').set(999, 'items', 'строка-вместо-словаря')
check(ES.load_custom(999) == {}, 'битое значение в БД → пусто, не падаем')

print('== 3. API: права и интероп ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/shop').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/shop/state').status_code in (302, 401, 403), 'гостю state закрыт')
login('uye')
check(client.get('/shop').status_code == 403, 'uye нельзя страницу')
login('mod')
check(client.get('/shop').status_code == 200, 'mod читает страницу (200)')
check(client.get('/api/shop/state').status_code == 200, 'mod читает state (200)')
check(post('/api/shop/upsert', {'name': 'x', 'price': 1})[0] == 403, 'mod не создаёт (403)')
check(post('/api/shop/remove', {'name': 'амулет луны'})[0] == 403, 'mod не удаляет (403)')

login('admin')
code, d = post('/api/shop/upsert',
               {'name': 'перо феникса', 'price': 4200, 'rarity': 'эпический',
                'category': 'другое', 'desc': 'Тёплое', 'sell': ''})
check(code == 200 and d['success'] and d['custom_count'] >= 3, 'admin создаёт (200)')
row = [i for i in d['items'] if i['name'] == 'перо феникса'][0]
check(row['source'] == 'custom' and row['sell'] == 2100 and row['rarity'] == 'эпический',
      'state отдаёт нормализованную карточку')
check(row['by'] == 'panel:admin', 'авторство panel:admin')
code, d = post('/api/shop/upsert', {'name': 'дом', 'price': 1, 'rarity': 'редкий',
                                    'category': 'другое'})
check(code == 400 and d['error'] == 'Предмет с таким названием уже есть в базовом магазине.',
      'API отдаёт текст функции 1:1 (clash)')
code, d = post('/api/shop/upsert', {'name': 'x!', 'price': 1, 'rarity': 'редкий',
                                    'category': 'другое'})
check(code == 400 and d['error'] == 'В названии можно использовать только буквы, цифры, пробелы и дефис.',
      'API отдаёт текст функции 1:1 (символы)')
code, d = post('/api/shop/remove', {'name': 'призрак'})
check(code == 404 and d['error'] == 'Такого кастомного предмета нет.', 'remove призрака — 404 1:1')
code, d = post('/api/shop/remove', {'name': 'перо феникса'})
removed = d.get('removed') or {}
check(code == 200 and removed.get('price') == 4200 and removed.get('rarity') == 'эпический',
      'remove 200 + undo-карточка')
undo_payload = dict(removed, name='перо феникса')
code, d = post('/api/shop/upsert', undo_payload)
check(code == 200 and any(i['name'] == 'перо феникса' for i in d['items']),
      'undo: та же карточка восстанавливается')

print('== 4. Шаблон и меню ==')
html = client.get('/shop').get_data(as_text=True)
check('id="shForm"' in html, 'admin видит форму')
check('var CAN_EDIT = true' in html, 'admin: CAN_EDIT=true')
login('mod')
html_mod = client.get('/shop').get_data(as_text=True)
check('id="shForm"' not in html_mod and 'var CAN_EDIT = false' in html_mod,
      'mod: без формы, CAN_EDIT=false')
tpl = open(os.path.join(ROOT, 'web/templates/shop.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check('uxUndo' in tpl and 'askConfirm' in tpl, 'undo и confirm-проводка на месте')
import services.panel_menu as PM
paths = [p['path'] for g in PM.MENU for p in g['pages']]
check('/shop' in paths, 'пункт меню «Магазин» есть')
check(PM.PAGE_COGS.get('/shop') == ('economy_cog',), 'PAGE_COGS привязан к economy_cog')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
