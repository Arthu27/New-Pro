# -*- coding: utf-8 -*-
"""Карточка приветствия: темы, авто/URL/выкл, настройки из панели и пример.

- services/welcome_card_gen: 5 тем в стиле Hakumo, appearance round-trip
  с валидацией мусора, аватар-заглушка и настоящий аватар;
- API панели: GET appearance (mod+), POST (admin+, https-only URL),
  preview.png живой и без кэша + права гостя;
- cogs/welcome_card.py: _send_card читает оформление (auto → карточка
  в теме, url → эмбед с set_image, off → текст);
- шаблон welcome_editor.html: панель оформления с превью и сохранением.

Запуск: python3 tests/test_welcome_card_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_wcard_test_')
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
from services import welcome_card_gen as WCG  # noqa: E402

check(set(WCG.WELCOME_THEME_ORDER) == set(WCG.WELCOME_THEMES),
      'порядок тем = реестру')
check(WCG.DEFAULT_WELCOME_THEME == 'hakumo',
      'дефолт — фирменное золото (как было всегда)')

base = WCG.render_welcome_card('Кипарис', 'Hakumo Demo', 1024, kind='welcome')
check(base and base[:8].startswith(b'\x89PNG'), 'базовая карточка рисуется')
check(len(base) > 40000, f'карточка не заглушка ({len(base)} байт)')

seen = set()
for th in WCG.WELCOME_THEME_ORDER:
    png = WCG.render_welcome_card('Lina', 'Hakumo', 7, kind='welcome', theme=th)
    check(png and png[:8].startswith(b'\x89PNG'), f'тема «{th}» рендерится')
    seen.add(png)
check(len(seen) == len(WCG.WELCOME_THEME_ORDER), 'темы различаются визуально')

bye = WCG.render_welcome_card('GhostBlade', 'Hakumo', 1003, kind='goodbye')
check(bye and bye[:8].startswith(b'\x89PNG') and bye != base,
      'карта прощания рисуется и отличается от приветствия')
junk = WCG.render_welcome_card('u', 'g', 'мусор', kind='junk', theme='nope')
check(junk and junk[:8].startswith(b'\x89PNG'),
      'мусорные тема/kind/счётчик → дефолты, без падения')
long_name = WCG.render_welcome_card('очень_длинный_никнейм_' * 6, 'g' * 200,
                                    5, kind='welcome', theme='ocean')
check(long_name and long_name[:8].startswith(b'\x89PNG'),
      'длинные имя/гильдия обрезаются, без падения')

# настоящий аватар проходит через круглую маску
from PIL import Image as _IMG  # noqa: E402
import io as _io  # noqa: E402
_av = _io.BytesIO()
_IMG.new('RGB', (128, 128), (90, 120, 200)).save(_av, format='PNG')
with_av = WCG.render_welcome_card('Ava', 'g', 3, avatar_bytes=_av.getvalue())
check(with_av and with_av != base, 'карточка с аватаром отличается от заглушки')

print('== 2. Склейка с когом ==')
cog_src = open(os.path.join(ROOT, 'cogs', 'welcome_card.py'), encoding='utf-8').read()
flat = re.sub(r'\s+', '', cog_src)
check('welcome_card_genasWCG' in flat.replace(' ', ''),
      'ког подключён к services/welcome_card_gen')
check("appearance['mode']=='url'" in flat and 'set_image' in flat,
      'режим URL: эмбед с set_image')
check("appearance['mode']=='off'" in flat and 'content=text' in flat,
      'режим off: текстовое приветствие')
check("theme=appearance['theme']" in flat and 'welcome_card_filename' in flat,
      'режим auto: карточка в выбранной теме с фирменным именем файла')
check("appearance['mode']=='file'" in flat and 'load_bg_bytes' in flat
      and 'bg_bytes=bg' in flat,
      'режим file: ког подмешивает загруженный фон в рендер')
check('render_card' in flat and 'def render_card' in cog_src,
      'старая обёртка render_card сохранена (обратная совместимость)')
check("appearance" in flat and "_appearance" in flat,
      'ког читает оформление сервера')

print('== 3. Настройки appearance ==')
ap0 = WCG.get_appearance('424242')
check(ap0 == {'mode': 'auto', 'theme': 'hakumo', 'url': '', 'file': ''},
      'нет файла → дефолт')
saved = WCG.save_appearance('424242', {'mode': 'URL', 'theme': 'OCEAN',
                                       'url': 'https://cdn.example.com/w.png'})
check(saved == {'mode': 'url', 'theme': 'ocean',
                'url': 'https://cdn.example.com/w.png', 'file': ''},
      'сохранение нормализует регистр и тему')
check(WCG.get_appearance('424242') == saved, 'читается обратно один в один')
junk = WCG.save_appearance('424242', {'mode': 'junk', 'theme': 'junk',
                                      'url': 'x' * 900})
check(junk['mode'] == 'auto' and junk['theme'] == 'hakumo' and len(junk['url']) == 500,
      'мусор в POST не пролезает: режим/тема по реестру, url до 500')

# файл того же формата, что ждёт ког (data/welcome_card.json, ключи — str(gid))
import json as _json  # noqa: E402
raw = _json.load(open(WCG.CFG_PATH, encoding='utf-8'))
check(isinstance(raw.get('424242'), dict)
      and raw['424242']['appearance']['mode'] == 'auto',
      'data/welcome_card.json — общий формат с когом')
os.remove(WCG.CFG_PATH)
check(WCG.get_appearance('424242') == ap0, 'после удаления файла снова дефолт')

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
    guest_get = client.get('/api/guild/777/welcome-card/appearance')
    guest_png = client.get('/api/guild/777/welcome-card/preview.png')
    guest_post = client.post('/api/guild/777/welcome-card/appearance', json={})
finally:
    os.environ['DEMO_MODE'] = '1'
check(guest_get.status_code in (302, 401, 403), 'гостю оформление закрыто (GET)')
check(guest_png.status_code in (302, 401, 403), 'гостю предпросмотр закрыт')
check(guest_post.status_code in (302, 401, 403), 'гостю оформление закрыто (POST)')

login('mod')
r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'url', 'url': 'https://x/y.png'})
check(r.status_code == 403, 'мод не меняет оформление (admin+)')
r = client.get('/api/guild/777/welcome-card/preview.png')
check(r.status_code == 200 and r.mimetype == 'image/png',
      'мод смотрит предпросмотр')
check(r.headers.get('Cache-Control') == 'no-store', 'предпросмотр не кэшируется')
r = client.get('/api/guild/777/welcome-card/preview.png?kind=goodbye&theme=ocean')
check(r.status_code == 200 and r.get_data()[:8].startswith(b'\x89PNG'),
      'предпросмотр прощания в океанской теме')
r = client.get('/api/guild/777/welcome-card/preview.png?kind=junk&theme=zzz')
check(r.status_code == 200, 'мусорные kind/theme → дефолты, не 500')

login('uye')
check(client.get('/api/guild/777/welcome-card/appearance').status_code == 403,
      'uye не читает оформление')

login('admin')
r = client.get('/api/guild/777/welcome-card/appearance').get_json()
check(r['appearance'] == {'mode': 'auto', 'theme': 'hakumo', 'url': '', 'file': ''},
      'appearance по умолчанию: авто + hakumo')
check(len(r['themes']) == 5 and r['themes'][0]['label'] == 'Hakumo Gold (фирменная)',
      'пять тем с понятными подписями в GET')

r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'url', 'url': 'http://evil.example/x.png'})
check(r.status_code == 400 and 'https' in r.get_json()['error'],
      'http URL картинки отвергнут (Discord не показывает)')
r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'url', 'url': 'http://127.0.0.1/x.png'})
check(r.status_code == 400, 'локальный адрес картинки отвергнут')

r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'url', 'url': 'https://cdn.example.com/welcome.png'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['appearance']['mode'] == 'url',
      'свой https URL принят')
r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'AUTO', 'theme': 'FOREST'})
d = r.get_json()
check(d['success'] and d['appearance'] == {'mode': 'auto', 'theme': 'forest',
                                           'url': '', 'file': ''},
      'режим/тема нормализуются (регистр)')
check('Лес' in d['message'], 'понятное сообщение о сохранении')
check(WCG.get_appearance('777')['theme'] == 'forest', 'тема записалась в файл кога')
client.post('/api/guild/777/welcome-card/appearance',
            json={'mode': 'auto', 'theme': 'hakumo', 'url': ''})
if os.path.exists(WCG.CFG_PATH):
    os.remove(WCG.CFG_PATH)

print('== 5. Загрузка файла-фона ==')
_guest_up = None
os.environ['DEMO_MODE'] = '0'
try:
    with client.session_transaction() as sess:
        sess.clear()
    _guest_up = client.post('/api/guild/777/welcome-card/upload', data={})
finally:
    os.environ['DEMO_MODE'] = '1'
check(_guest_up.status_code in (302, 401, 403), 'гостю загрузка фона закрыта')

# хелпер: валидная картинка
def _img_bytes(color=(140, 90, 200), fmt='PNG', size=(64, 32)):
    bo = _io.BytesIO()
    _IMG.new('RGB', size, color).save(bo, format=fmt)
    return bo.getvalue()

login('mod')
r = client.post('/api/guild/777/welcome-card/upload',
                data={'file': (_io.BytesIO(_img_bytes()), 'bg.png')},
                content_type='multipart/form-data')
check(r.status_code == 403, 'мод не грузит фон (admin+)')

login('admin')
r = client.post('/api/guild/777/welcome-card/upload', data={},
                content_type='multipart/form-data')
check(r.status_code == 400, 'загрузка без файла → 400')

r = client.post('/api/guild/777/welcome-card/upload',
                data={'file': (_io.BytesIO(b'not an image at all'), 'bg.png')},
                content_type='multipart/form-data')
check(r.status_code == 400 and 'картинка' in r.get_json()['error'],
      'не-картинка отвергнута с понятной ошибкой')

r = client.post('/api/guild/777/welcome-card/upload',
                data={'file': (_io.BytesIO(_img_bytes()), 'bg.png')},
                content_type='multipart/form-data')
d = r.get_json()
check(r.status_code == 200 and d['success'], 'валидный PNG загружен')
ap_up = d['appearance']
check(ap_up['mode'] == 'file' and ap_up['file'] == 'bg_777.png',
      'загрузка включает режим file и сохраняет безопасное имя')
saved_path = WCG.bg_path(ap_up['file'])
check(saved_path and os.path.isfile(saved_path)
      and saved_path.endswith('bg_777.png'),
      'файл лежит в data/uploads/welcome под именем сервера')
check(WCG.load_bg_bytes(ap_up['file']) == _img_bytes(),
      'load_bg_bytes отдаёт ровно загруженные байты')
check(WCG.get_appearance('777') == ap_up, 'appearance с файлом читается из файла')

# имя файла санитизируется: путь не пролезает в appearance
evil = WCG.normalize_appearance({'mode': 'file', 'file': '../evil/../../etc/x.png'})
check(evil['file'] == 'x.png', 'в имени файла только basename')
safe_p = WCG.bg_path('../hack')
check(safe_p is not None
      and os.path.dirname(safe_p) == os.path.abspath(WCG.BG_DIR),
      'bg_path режет путь до basename: внутри каталога фонов')
check(WCG.bg_path('..') is None and WCG.bg_path('') is None,
      'bg_path отрезает «..» и пустое имя')

# сохранение оформления в режиме file не затирает загруженный файл
r = client.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'file', 'theme': 'ocean'})
ap_keep = r.get_json()['appearance']
check(ap_keep['mode'] == 'file' and ap_keep['file'] == 'bg_777.png',
      'POST appearance в режиме file сохраняет загруженный фон')

# предпросмотр рисует на загруженном фоне и отличается от голого градиента
r_plain = client.get('/api/guild/777/welcome-card/preview.png')
plain_png = r_plain.get_data()
client.post('/api/guild/777/welcome-card/appearance',
            json={'mode': 'file', 'theme': 'hakumo'})
r_bg = client.get('/api/guild/777/welcome-card/preview.png')
bg_png = r_bg.get_data()
check(r_bg.status_code == 200 and bg_png[:8].startswith(b'\x89PNG'),
      'предпросмотр на своём фоне рисуется')
check(r_plain.status_code == 200 and plain_png != bg_png,
      'свой фон визуально меняет карточку')

# рендер с bg_bytes напрямую: падение недопустимо, битый файл → градиент
png_bg = WCG.render_welcome_card('Тест', 'g', 1, kind='welcome',
                                 bg_bytes=WCG.load_bg_bytes('bg_777.png'))
check(png_bg[:8].startswith(b'\x89PNG') and len(png_bg) > 40000,
      'render_welcome_card с bg_bytes → полноценная карточка')
png_broken = WCG.render_welcome_card('Тест', 'g', 1, kind='welcome',
                                     bg_bytes=b'garbage')
check(png_broken[:8].startswith(b'\x89PNG'),
      'битый фон молча откатывается на градиент')
jpeg_up = WCG.save_bg_file('777', 'x.jpg', b'x' * (WCG.BG_MAX_BYTES + 1))
check(jpeg_up['ok'] is False and '8 МБ' in jpeg_up['error'],
      'слишком большой файл отвергнут (>8 МБ)')

# уборка: сносим загруженные фоны из tmp-окружения
for f in os.listdir(WCG.BG_DIR):
    os.remove(os.path.join(WCG.BG_DIR, f))
client.post('/api/guild/777/welcome-card/appearance',
            json={'mode': 'auto', 'theme': 'hakumo', 'url': ''})
if os.path.exists(WCG.CFG_PATH):
    os.remove(WCG.CFG_PATH)

print('== 6. Шаблон ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'welcome_editor.html'),
           encoding='utf-8').read()
for fid in ('wCardBox', 'wCardMode', 'wCardTheme', 'wCardUrl', 'wCardKind',
            'wCardSave', 'wCardMsg', 'wCardPv', 'wCardFileBox', 'wCardFile',
            'wCardUpload', 'wCardFileMsg'):
    check(f'id="{fid}"' in tpl, f'контрол {fid} на месте')
check('/welcome-card/appearance' in tpl, 'API оформления подключён в шаблоне')
check('/welcome-card/preview.png' in tpl, 'предпросмотр подключён в шаблоне')
check('/welcome-card/upload' in tpl and 'wCardUploadBg' in tpl,
      'загрузка файла-фона подключена в шаблоне')
for opt in ('value="auto"', 'value="url"', 'value="file"', 'value="off"'):
    check(opt in tpl, f'режим {opt} есть в выборе')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
check('wCardRefreshPreview' in tpl, 'превью обновляется с паузой')
ext = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
check('welcome_panel' in ext, 'модуль welcome_panel зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
