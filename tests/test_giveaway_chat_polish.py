# -*- coding: utf-8 -*-
"""Гивки и чат «как в Discord» (заказ владельца 2026-08-26).

Гивки раньше «иногда не грузились» (при пустом списке серверов страница
висела на спиннере) и показывали участников одной цифрой. Теперь:
- участники — список с именами (user_info → кэш бота → демо-состав);
- у карточек настоящий прогресс (created_at → ends_at) и победители;
- «Новый розыгрыш» — живая форма к существующему API, не заглушка;
- страница никогда не зависает: пустой список серверов не ломает загрузку.

Чат: клик по автору/аватару открывает ЛС (openDm по author_id), локаль
ру-RU, без турецких строк («Botlar», tr-TR).

Запуск: python3 tests/test_giveaway_chat_polish.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_gwchat_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


print('== 1. API гивок (демо): участники-люди, победители, created_at ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

resp = client.get('/api/giveaway/777')
check(resp.status_code == 200, 'endpoint отвечает')
gws = resp.get_json()
check(isinstance(gws, list) and len(gws) >= 3, f'карточек ≥ 3 ({len(gws)})')
live = [g for g in gws if g['status'] != 'ended']
ended = [g for g in gws if g['status'] == 'ended']
check(len(live) >= 2 and len(ended) >= 1, 'есть активные и завершённые')
for g in gws:
    check(isinstance(g.get('participants'), list) and g['participants'],
          f'«{g["prize"][:20]}»: участники — список с именами')
    check(all(p.get('name') and 'ID' not in p['name'] for p in g['participants']),
          f'«{g["prize"][:20]}»: у всех участников имена, не сырые ID')
    check(bool(g.get('created_at')), f'«{g["prize"][:20]}»: created_at есть (для прогресса)')
check(all(g.get('winners_list') for g in ended), 'завершённые показывают победителей')
check(all(not g.get('winner_ids') for g in live), 'активные победителей ещё не имеют')

print('== 2. API гивок (реальный файл): имена из user_info ==')
own = {
    'gw1': {'prize': 'Тест', 'winners': 1, 'status': 'ended',
            'created_at': '2026-08-20T10:00:00', 'ends_at': '2026-08-25T10:00:00',
            'channel_id': '1004', 'participants': ['111', '222'],
            'user_info': {'111': {'name': 'GhostBlade'}, '222': {'name': 'Sonya'}},
            'winner_ids': ['111']}
}
with open(os.path.join(_TMP, 'data', 'giveaways_778.json'), 'w', encoding='utf-8') as fp:
    json.dump(own, fp, ensure_ascii=False)
resp2 = client.get('/api/giveaway/778')
g2 = resp2.get_json()[0]
names = [p['name'] for p in g2['participants']]
check(names == ['GhostBlade', 'Sonya'], f'имена из user_info: {names}')
check(g2['winner_ids'] == ['111'] and g2['winners_list'][0]['name'] == 'GhostBlade',
      'победитель по имени')

print('== 3. Шаблон гивок: не зависает, прогресс живой, мёртвых кнопок нет ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'giveaway.html'), encoding='utf-8').read()
check('pct = 100' not in tpl.replace('return 100', ''), 'прогресс не захардкожен на 100%')
check('progressOf' in tpl and 'created_at' in tpl, 'прогресс считается по created_at → ends_at')
check('появится здесь' not in tpl, 'заглушка «форма появится» убрана — форма настоящая')
check('Не удалось загрузить' in tpl, 'есть честное состояние ошибки загрузки')
check('__gwToggle' in tpl and 'gw-list' in tpl, 'список участников раскрывается по клику')
check('fa-crown' in tpl, 'победители отмечены короной')
check('Демо-сервер' in tpl, 'пустой список серверов не ломает страницу (главный сервер)')
check('gw-modal' in tpl and 'api/giveaway/' in tpl and '/create' in tpl,
      'форма создания обращается к живому API создания')

print('== 4. Чат: клик по автору → ЛС, локаль ru-RU ==')
ctpl = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
check('tr-TR' not in ctpl, 'турецкая локаль убрана')
check('Botlar' not in ctpl, '«Botlar» переведён')
check("openDm(\\'' + String(m.author_id)" in ctpl or 'openDm(\'' + "' + String(m.author_id)" in ctpl,
      'клик по автору сообщения открывает ЛС по author_id')
check('msg-act-btn dm' in ctpl, 'у сообщений есть кнопка «Написать в ЛС»')
check('Написать в личные сообщения' in ctpl, 'подсказка при наведении на автора')
check('(изменено)' in ctpl, 'метка редактирования по-русски')
check('msg-author.clickable' in ctpl and 'msg-avatar-wrap.clickable' in ctpl,
      'автор и аватар стилизованы как кликабельные')

# демо-сообщения чата содержат author_id (нужен для клика в ЛС)
croute = open(os.path.join(ROOT, 'web', 'routes', 'chat.py'), encoding='utf-8').read()
check("'author_id':str (m .author .id )" in croute, 'API канала отдаёт author_id')

print('== 4b. Чат-апгрейд 2026-08-26: без кнопки DM, поиск, скролл-кнопка ==')
check('dm-open-btn' not in ctpl, 'кнопка «DM» у поля ввода убрана')
check('scroll-down-btn' in ctpl and 'updateScrollBtn' in ctpl,
      'кнопка «вниз» с счётчиком новых сообщений есть')
check('toggleChatSearch' in ctpl and 'chat-search-count' in ctpl,
      'поиск по сообщениям в шапке канала')
check('fa-copy' in ctpl and 'copyMsg' in ctpl, 'копирование текста сообщения')
check('hlContent' in ctpl, 'подсветка совпадений поиска')
check('ch-item ch-muted' in ctpl and 'fa-volume-high' in ctpl,
      'голосовые каналы видны (некликабельны), форум — с иконкой')
check('_chat_demo_seed' in croute, 'демо-сид: живая беседа вместо заглушки')
check("'Демо-режим: бот не подключён'" not in croute,
      'пугающая заглушка «Демо-режим: бот не подключён» удалена из сида')

# демо-сид живёт и мигрирует старый стор
resp = client.get('/api/chat/777/1004/messages')
dmsgs = resp.get_json()
check(resp.status_code == 200 and len(dmsgs) >= 6,
      f'демо-канал отдаёт живую беседу ({len(dmsgs)} сообщений)')
check(all(m.get('author_id') for m in dmsgs), 'у демо-сообщений есть author_id')
check(any(not m['bot'] for m in dmsgs) and any(m['bot'] for m in dmsgs),
      'в беседе и участники, и бот')
check(not any(str(m.get('content', '')).startswith('Демо-режим') for m in dmsgs),
      'старая заглушка из стора вычищена')

print('== 5. Ког гивок: победители сохраняются ==')
gsrc = open(os.path.join(ROOT, 'cogs', 'giveaway.py'), encoding='utf-8').read()
check('winner_ids' in gsrc, 'ког сохраняет победителей в файл')
check('"created_at"' in gsrc, 'ког пишет created_at при создании')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
