# -*- coding: utf-8 -*-
"""Карточки логов: темы, акцент, настройки из панели и живой предпросмотр.

- services/log_card: 5 тем в стиле Hakumo, свой акцент, мусор → дефолт;
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

_TMP = tempfile.mkdtemp(prefix='hakumo_logcards_test_')
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
check(LC.DEFAULT_LOG_THEME == 'hakumo', 'дефолт — фирменное золото (как было)')

rows = [('Пользователь', 'GhostBlade · 523456789012345678'),
        ('Модератор', 'sonya.staff'),
        ('Причина', 'Повторные провокации после предупреждения в #general')]
base = LC.render_log_card('mod', 'Выдано предупреждение', rows, color=0xE2455A,
                          cat_name='модерация', guild_name='Hakumo', time_str='20:41 UTC')
check(base and base[:2] == b'\xff\xd8', 'базовая карточка рисуется (JPEG — мгновенные логи)')
check(len(base) > 40000, f'карточка не заглушка ({len(base)} байт)')

seen = set()
for th in LC.LOG_CARD_THEME_ORDER:
    png = LC.render_log_card('member', 'Новый участник', [('Участник', 'Lina')],
                             cat_name='участники', theme=th)
    check(png and png[:2] == b'\xff\xd8', f'тема «{th}» рендерится')
    seen.add(png)
check(len(seen) == len(LC.LOG_CARD_THEME_ORDER), 'темы различаются визуально')

acc = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='hakumo', accent='#22d3ee')
acc2 = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='hakumo', accent='22ff88')
check(acc != acc2, 'свой акцент меняет карточку')
junk = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', theme='nope', accent='zzz')
check(junk and junk[:2] == b'\xff\xd8', 'мусорные тема/цвет → дефолт, без падения')
check(LC._ui_color('#22D3EE') == (34, 211, 238) and LC._ui_color('junk') is None,
      '_ui_color: hex → RGB, мусор → None')
pal = LC._palette('ocean', 'ff8800')
check(pal['gold'] == (255, 136, 0) and pal['bright'] != pal['gold'],
      'акцент заменяет золотую гамму (основную и светлую)')

print('== 2. Настройки cfg ==')
_CFG_SKIP = ('theme_by_cat', 'bg_url', 'bg_url_by_cat', 'form', 'form_color', 'delivery')
cfg = LC.get_log_cards_cfg('424242')
check({k: v for k, v in cfg.items() if k not in _CFG_SKIP} == {'enabled': True, 'theme': 'hakumo', 'accent': ''}
      and cfg['theme_by_cat'] == LC.DEFAULT_THEME_BY_CAT and cfg['bg_url'] == ''
      and cfg['form'] == 'glass' and cfg['form_color'] == ''
      and cfg['delivery'] == 'embed',
      'нет файла → дефолт (эмбед Discord, образы по категориям, фон пустой, форма стекло)')
saved = LC.save_log_cards_cfg('424242', {'enabled': False, 'theme': 'ocean', 'accent': '#22d3ee'})
check({k: v for k, v in saved.items() if k not in _CFG_SKIP} == {'enabled': False, 'theme': 'ocean', 'accent': '22d3ee'}
      and saved['bg_url'] == '', 'сохранение нормализует (accent без #)')
check(LC.get_log_cards_cfg('424242') == saved, 'читается обратно один в один')
saved2 = LC.save_log_cards_cfg('424242', {'enabled': 'yes', 'theme': 'bad', 'accent': 'bad'})
check({k: v for k, v in saved2.items() if k not in _CFG_SKIP} == {'enabled': True, 'theme': 'hakumo', 'accent': ''}
      and saved2['theme_by_cat'] == LC.DEFAULT_THEME_BY_CAT,
      'мусор в POST не пролезает: enabled bool, тема/акцент по реестру')
os.remove(LC.log_cards_cfg_path('424242'))
check(LC._valid_delivery('PHOTO') == 'photo' and LC._valid_delivery('nope') == 'embed',
      'delivery: photo/embed, мусор → эмбед')
ph = LC.save_log_cards_cfg('424246', {'delivery': 'photo'})
check(ph['delivery'] == 'photo', 'delivery=photo сохраняется')
LC.save_log_cards_cfg('424246', {'theme': 'ocean'})
check(LC.get_log_cards_cfg('424246')['delivery'] == 'photo'
      and LC.get_log_cards_cfg('424246')['theme'] == 'ocean',
      'смена темы не сносит вид лога')
junk_d = LC.save_log_cards_cfg('424246', {'delivery': 'postcard'})
check(junk_d['delivery'] == 'embed', 'мусорный delivery → эмбед')
os.remove(LC.log_cards_cfg_path('424246'))

print('== 2в. Форма и цвет плашек ==')
check(set(LC.CARD_FORMS) == {'glass', 'rounded', 'pill', 'sharp'},
      'четыре формы плашек')
check(LC._valid_form('nope') == 'glass' and LC._valid_form('PILL') == 'pill',
      'мусорная форма → стекло, регистр не мешает')
pill = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', form='pill',
                          form_color='112233')
glass = LC.render_log_card('mod', 'T', rows[:1], cat_name='mod', form='glass')
check(pill and glass and pill != glass, 'форма и цвет меняют карточку')
from PIL import Image as _Im
_bg = __import__('io').BytesIO()
_Im.new('RGB', (960, 540), (220, 160, 70)).save(_bg, 'JPEG')
on_photo = LC.render_log_card('mod', 'Выдано предупреждение', rows,
                              cat_name='модерация', bg_bytes=_bg.getvalue(),
                              form='glass', form_color='0c101c')
check(on_photo and on_photo[:2] == b'\xff\xd8' and len(on_photo) > 20000,
      'плашки рисуются поверх фото-фона без падения')
saved_f = LC.save_log_cards_cfg('424244', {'form': 'pill', 'form_color': '#aabbcc'})
check(saved_f['form'] == 'pill' and saved_f['form_color'] == 'aabbcc',
      'форма и цвет сохраняются')
LC.save_log_cards_cfg('424244', {'theme': 'ocean'})
check(LC.get_log_cards_cfg('424244')['form'] == 'pill'
      and LC.get_log_cards_cfg('424244')['form_color'] == 'aabbcc',
      'смена темы не сносит форму и цвет')
junk_f = LC.save_log_cards_cfg('424244', {'form': 'blob', 'form_color': 'zz'})
check(junk_f['form'] == 'glass' and junk_f['form_color'] == '',
      'мусорная форма/цвет → дефолт')
os.remove(LC.log_cards_cfg_path('424244'))

print('== 2б. Фон по категории (merge-on-save) ==')
LC.save_log_cards_cfg('424243', {'enabled': True, 'theme': 'ocean',
                                 'bg_url': 'https://example.com/all.jpg'})
LC.save_log_cards_cfg('424243', {'bg_url_by_cat': {
    'mod': 'https://example.com/mod.jpg',
    'voice': 'https://pin.it/abc',
    'junk': 'not-a-url',
}})
cfg3 = LC.get_log_cards_cfg('424243')
check(cfg3['theme'] == 'ocean' and cfg3['bg_url'] == 'https://example.com/all.jpg',
      'POST только bg_url_by_cat не затирает тему и общий фон')
check(cfg3['bg_url_by_cat'].get('mod') == 'https://example.com/mod.jpg'
      and cfg3['bg_url_by_cat'].get('voice') == 'https://pin.it/abc'
      and 'junk' not in cfg3['bg_url_by_cat'],
      'URL по категориям сохраняется, мусор отсекается')
check(LC.bg_url_for_cat(cfg3, 'mod') == 'https://example.com/mod.jpg'
      and LC.bg_url_for_cat(cfg3, 'member') == 'https://example.com/all.jpg',
      'bg_url_for_cat: свой URL категории, иначе общий')
LC.save_log_cards_cfg('424243', {'theme': 'forest'})
cfg4 = LC.get_log_cards_cfg('424243')
check(cfg4['theme'] == 'forest'
      and cfg4['bg_url_by_cat'].get('mod') == 'https://example.com/mod.jpg',
      'смена темы не стирает URL по категориям')
os.remove(LC.log_cards_cfg_path('424243'))

print('== 3. Склейка с ботом ==')
logs_src = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
flat = re.sub(r'\s+', '', logs_src)
check('get_log_cards_cfg' in flat and "_cfg.get('enabled',True)" in flat.replace('"', "'"),
      '_safe_send читает cfg сервера')
check('bg_url_for_cat' in logs_src,
      '_safe_send берёт фон категории, а не только общий bg_url')
check('render_log_card' in logs_src and 'hakumo_log.jpg' in logs_src,
      '_safe_send рисует лог на фото владельца и шлёт файл')
check("pop ('embed'" in logs_src or "pop('embed'" in logs_src,
      'фото-режим прячет эмбед Discord, в канал уходит файл')
check('compact_log_photo' not in logs_src and 'hakumo_log_photo.jpg' not in logs_src,
      'полоска без текста в канал не уходит')
check("if_cfg.get('enabled',True)and_deliv=='photo'" in flat.replace('"', "'")
      or "if_cfg.get('enabled',True)and_deliv==\"photo\"" in flat,
      'фото только если delivery=photo; иначе эмбед')

print('== 3б. Отправка: эмбед по умолчанию, фото — по выбору ==')
import asyncio
from cogs.logs import _safe_send, _styled_log_embed  # noqa: E402

_bgbuf = __import__('io').BytesIO()
_Im.new('RGB', (960, 540), (40, 28, 18)).save(_bgbuf, 'JPEG')
_fake_bg = _bgbuf.getvalue()
_orig_bg = LC.get_bg_bytes_sync
LC.get_bg_bytes_sync = lambda url, ttl=300: _fake_bg if url else None


class _G:
    id = 424245
    name = 'Hakumo'
    icon = None

    def get_member(self, *a):
        return None

    def get_role(self, *a):
        return None

    def get_channel(self, *a):
        return None


class _Ch:
    def __init__(self):
        self.guild = _G()
        self.name = 'модерация'
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)


LC.save_log_cards_cfg('424245', {'enabled': True,
                                 'bg_url': 'https://example.com/bg.jpg'})
_ch = _Ch()
_e = _styled_log_embed(_G(), 'mod', 'Выдано предупреждение',
                       fields=[('Пользователь', 'GhostBlade'),
                               ('Причина', 'спам')])
asyncio.run(_safe_send(_ch, embed=_e))
_kw = _ch.sent[-1] if _ch.sent else {}
check('embed' in _kw and 'file' not in _kw,
      'по умолчанию в канал уходит эмбед Discord, без фото')

LC.save_log_cards_cfg('424245', {'enabled': True, 'delivery': 'photo',
                                 'bg_url': 'https://example.com/bg.jpg'})
_chp = _Ch()
asyncio.run(_safe_send(_chp, embed=_e))
_kwp = _chp.sent[-1] if _chp.sent else {}
check('file' in _kwp and 'embed' not in _kwp,
      'delivery=photo: в канал уходит только фото')
check(getattr(_kwp.get('file'), 'filename', '') == 'hakumo_log.jpg',
      'файл hakumo_log.jpg')

LC.save_log_cards_cfg('424245', {'enabled': False, 'delivery': 'photo',
                                 'bg_url': 'https://example.com/bg.jpg'})
_ch2 = _Ch()
_e2 = _styled_log_embed(_G(), 'mod', 'Выдано предупреждение',
                        fields=[('Пользователь', 'GhostBlade')])
asyncio.run(_safe_send(_ch2, embed=_e2))
_kw2 = _ch2.sent[-1] if _ch2.sent else {}
check('embed' in _kw2 and 'file' not in _kw2,
      'enabled=False: текстовый эмбед, без фото')

os.remove(LC.log_cards_cfg_path('424245'))
_ch3 = _Ch()
_e3 = _styled_log_embed(_G(), 'mod', 'Событие', fields=[('А', 'б')])
asyncio.run(_safe_send(_ch3, embed=_e3))
_kw3 = _ch3.sent[-1] if _ch3.sent else {}
check('embed' in _kw3 and 'file' not in _kw3,
      'нет файла настроек: эмбед Discord')
LC.save_log_cards_cfg('424245', {'delivery': 'photo'})
_ch4 = _Ch()
asyncio.run(_safe_send(_ch4, embed=_e3))
_kw4 = _ch4.sent[-1] if _ch4.sent else {}
check('file' in _kw4 and 'embed' not in _kw4,
      'photo без URL: фото со стеклом на стандартном фоне')
LC.get_bg_bytes_sync = _orig_bg

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
check(r.status_code == 403, 'мод не меняет оформление')
r = client.get('/api/guild/777/log-cards/preview.png')
check(r.status_code == 403, 'мод не смотрит предпросмотр оформления')
r = client.get('/api/guild/777/log-cards/settings')
check(r.status_code == 403, 'мод не читает оформление карточек')

login('admin')
r = client.post('/api/guild/777/log-cards/settings', json={'theme': 'forest'})
check(r.status_code == 403, 'админ не меняет оформление — только владелец')

login('owner')
r = client.post('/api/guild/777/log-cards/settings',
                json={'enabled': True, 'theme': 'forest', 'accent': '#22ff88'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['cfg']['theme'] == 'forest',
      'владелец сохранил forest + акцент')
check(d['cfg']['accent'] == '22ff88', 'акцент сохранён без решётки')
check(LC.get_log_cards_cfg('777')['theme'] == 'forest', 'файл на диске — forest')
r = client.get('/api/guild/777/log-cards/settings').get_json()
check(r['cfg']['theme'] == 'forest' and len(r['themes']) == len(LC.LOG_CARD_THEMES),
      'GET отдаёт cfg и все темы реестра')
r = client.get('/api/guild/777/log-cards/preview.png?theme=ocean&accent=22d3ee&cat=voice')
body = r.get_data()
check(body[:8].startswith(b'\x89PNG') and len(body) > 2000,
      f'предпросмотр фото-полосы ({len(body)} байт)')
r = client.get('/api/guild/777/log-cards/preview.png?theme=zzz&cat=unknown')
check(r.status_code == 200, 'мусорные theme/cat → дефолты, не 500')
LC.save_log_cards_cfg('777', {'enabled': True, 'theme': 'hakumo', 'accent': ''})
for f in ('data/log_cards_777.json',):
    if os.path.exists(f):
        os.remove(f)

print('== 5. Шаблон ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'message_logs.html'),
           encoding='utf-8').read()
for fid in ('lcSetBox', 'lcDelivery', 'lcTheme', 'lcCat', 'lcAccent', 'lcSave',
            'lcPreview', 'lcMsg', 'lcForm'):
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
