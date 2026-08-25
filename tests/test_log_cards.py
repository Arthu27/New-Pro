# -*- coding: utf-8 -*-
"""Карточки логов: темы, акцент, настройки из панели и живой предпросмотр.

- services/log_card: 5 тем в стиле Aether, свой акцент, мусор → дефолт;
- data/log_cards_<gid>.json: cfg round-trip с валидацией, enabled=False честно
  выключает картинку (бот оставляет текстовый эмбед);
- API панели: GET/POST settings (admin+ пишет), preview.png + права гостя;
- cogs/logs.py: _safe_send читает cfg (theme/accent/enabled проброшены);
- шаблон message_logs.html: панель оформления с превью и сохранением.

Запуск: python3 tests/test_log_cards.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_logcards_test_')
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


print('== 1. Палитры и рендер ==')
from services import log_card as LC  # noqa: E402

check(set(LC.LOG_CARD_THEME_ORDER) == set(LC.LOG_CARD_THEMES),
      'порядок тем = реестру')
check(LC.DEFAULT_LOG_THEME == 'aether', 'дефолт — фирменное золото (как было)')

rows = [('Пользователь', 'GhostBlade · 523456789012345678'),
        ('Модератор', 'sonya.staff'),
        ('Причина', 'Повторные провокации после предупреждения в #general')]
base = LC.render_log_card('mod', 'Выдано предупреждение', rows, color=0xE2455A,
                          cat_name='модерация', guild_name='Aether', time_str='20:41 UTC')
check(base and base[:2] == b'\xff\xd8', 'базовая карточка рисуется (JPEG — мгновенные логи)')
check(len(base) > 40000, f'карточка не заглушка ({len(base)} байт)')

seen = set()
for th in LC.LOG_CARD_THEME_ORDER:
    png = LC.render_log_card('member', 'Новый участник', [('Участник', 'Lina')],
                             cat_name='участники', theme=th)
    check(png and png[:2] == b'\xff\xd8', f'тема «{th}» рендерится')
    seen.add(png)
check(len(seen) == len(LC.LOG_CARD_THEME_ORDER), 'темы различаются визуально')

acc = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='aether', accent='#22d3ee')
acc2 = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='aether', accent='22ff88')
check(acc != acc2, 'свой акцент меняет карточку')
junk = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='nope', accent='zzz')
check(junk and junk[:2] == b'\xff\xd8', 'мусорные тема/цвет → дефолт, без падения')
check(LC._ui_color('#22D3EE') == (34, 211, 238) and LC._ui_color('junk') is None,
      '_ui_color: hex → RGB, мусор → None')
pal = LC._palette('ocean', 'ff8800')
check(pal['gold'] == (255, 136, 0) and pal['bright'] != pal['gold'],
      'акцент заменяет золотую гамму (основную и светлую)')

print('== 2. Настройки cfg ==')
cfg = LC.get_log_cards_cfg('424242')
check(cfg == {'enabled': True, 'theme': 'aether', 'accent': ''}, 'нет файла → дефолт')
saved = LC.save_log_cards_cfg('424242', {'enabled': False, 'theme': 'ocean', 'accent': '#22d3ee'})
check(saved == {'enabled': False, 'theme': 'ocean', 'accent': '22d3ee'},
      'сохранение нормализует (accent без #)')
check(LC.get_log_cards_cfg('424242') == saved, 'читается обратно один в один')
saved2 = LC.save_log_cards_cfg('424242', {'enabled': 'yes', 'theme': 'bad', 'accent': 'bad'})
check(saved2 == {'enabled': True, 'theme': 'aether', 'accent': ''},
      'мусор в POST не пролезает: enabled bool, тема/акцент по реестру')
os.remove(LC.log_cards_cfg_path('424242'))

print('== 3. Склейка с ботом ==')
logs_src = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
flat = re.sub(r'\s+', '', logs_src)
check('get_log_cards_cfg' in flat and '_cfg.get(\'enabled\',True)' in flat.replace('"', "'"),
      '_safe_send читает cfg сервера')
check("theme=_cfg.get('theme')" in flat and "accent=_cfg.get('accent')" in flat,
      'тема/акцент проброшены из cfg вrender')
check("ifnot_cfg.get('enabled',True)" in flat.replace('"', "'")
      and "_png=None" in flat,
      'enabled=False выключает картинку, текст остаётся')

print('== 4. API панели ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


os.environ['DEMO_MODE'] = '0'
try:
    guest = client.get('/api/guild/777/log-cards/settings')
finally:
    os.environ['DEMO_MODE'] = '1'
check(guest.status_code in (302, 401, 403), 'гостю настройки закрыты')

login('mod')
r = client.post('/api/guild/777/log-cards/settings', json={'theme': 'night'})
check(r.status_code == 403, 'мод не меняет оформление (admin+)')
r = client.get('/api/guild/777/log-cards/preview.png')
check(r.status_code == 200 and r.mimetype == 'image/png', 'мод смотрит предпросмотр')
check(r.headers.get('Cache-Control') == 'no-store', 'предпросмотр не кэшируется')

login('admin')
r = client.post('/api/guild/777/log-cards/settings',
                json={'enabled': True, 'theme': 'forest', 'accent': '#22ff88'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['cfg']['theme'] == 'forest',
      'админ сохранил forest + акцент')
check(d['cfg']['accent'] == '22ff88', 'акцент сохранён без решётки')
check(LC.get_log_cards_cfg('777')['theme'] == 'forest', 'файл на диске — forest')
r = client.get('/api/guild/777/log-cards/settings').get_json()
check(r['cfg']['theme'] == 'forest' and len(r['themes']) == 5,
      'GET отдаёт cfg и 5 тем')
r = client.get('/api/guild/777/log-cards/preview.png?theme=ocean&accent=22d3ee&cat=voice')
body = r.get_data()
check(body[:8].startswith(b'\x89PNG') and len(body) > 30000,
      f'предпросмотр голосовой категории ({len(body)} байт)')
r = client.get('/api/guild/777/log-cards/preview.png?theme=zzz&cat=unknown')
check(r.status_code == 200, 'мусорные theme/cat → дефолты, не 500')
LC.save_log_cards_cfg('777', {'enabled': True, 'theme': 'aether', 'accent': ''})
for f in ('data/log_cards_777.json',):
    if os.path.exists(f):
        os.remove(f)

print('== 5. Шаблон ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'message_logs.html'),
           encoding='utf-8').read()
for fid in ('lcSetBox', 'lcOn', 'lcTheme', 'lcCat', 'lcAccent', 'lcSave',
            'lcPreview', 'lcMsg'):
    check(f'id="{fid}"' in tpl, f'контрол {fid} на месте')
check('/log-cards/settings\' + ' in tpl or 'log-cards/settings' in tpl,
      'API настроек подключён в шаблоне')
check('/log-cards/preview.png' in tpl, 'предпросмотр подключён в шаблоне')
check('schedulePreview' in tpl, 'превью обновляется с паузой')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')

print('== 6. Имена вместо сырых ID (заказ владельца 2026-08-25) ==')
from cogs import logs as LOGS  # noqa: E402


class _FM:
    id = 523456789012345678
    display_name = 'GhostBlade'

    def __str__(self):
        return 'ghost.blade'


class _FG:
    def get_member(self, mid):
        return _FM() if mid == _FM.id else None


_fg = _FG()
check(LOGS._card_friendly('GhostBlade (523456789012345678)', _fg) == 'GhostBlade',
      '«Имя (ID)» -> просто имя')
check(LOGS._card_friendly('GhostBlade · 523456789012345678', _fg) == 'GhostBlade',
      '«Имя · ID» -> просто имя')
check(LOGS._card_friendly(
    '**GhostBlade** · <@523456789012345678> · `523456789012345678`', _fg)
    == 'GhostBlade · @GhostBlade',
    'упоминание резолвится в имя, ID-хвост исчезает')
check(LOGS._card_friendly('предупреждение 2 из 3', _fg) == 'предупреждение 2 из 3',
    'короткие числа и обычный текст не трогаем')
check('\u00b7' not in LOGS._strip_raw_id(
    '**Имя** · <@523456789012345678> · `523456789012345678`').split(' ')[-1],
    'эмбед-строка теряет голый ID-хвост')
src_logs = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('_card_friendly(n, guild), _card_friendly(v, guild)' in src_logs,
      'все строки карточек проходят чистильщик (в центре рендера)')
from web.routes import log_cards_panel as LCP  # noqa: E402
check(not any(re.search(r'\d{15,25}', v) for _n, v in LCP.PREVIEW_ROWS),
      'демо-карточка в панели: имена без ID (заказ «сначала демо-версию»)')
check('GhostBlade' in dict(LCP.PREVIEW_ROWS)['Пользователь'],
      'демо-пример: пользователь показан именем')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
