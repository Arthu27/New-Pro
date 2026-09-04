# -*- coding: utf-8 -*-
"""Логи-2026: образы по категориям, «Никнеймы», фон по URL (Pinterest).

Заказ владельца:
  • у каждой категории логов свой образ карточки (theme_by_cat);
  • смена ников — отдельная категория со своим каналом;
  • фон карточки приветствия по ссылке теперь работает и с Pinterest
    (панель скачивает и хранит файл, вытащив og:image со страницы).

Запуск: python3 tests/test_log_looks.py
"""
import json
import os
import sys
import tempfile

os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'
os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='hakumo_lookdb_'), 'bot.db')
_TMP = tempfile.mkdtemp(prefix='hakumo_look_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))

from services import log_card as LC
from services import log_settings as LS
from services import welcome_card_gen as WCG

# изоляция: log_cards_cfg_path — АБСОЛЮТНЫЙ путь в data/ репозитория;
# в тесте уводим его в tempdir, чтобы не читать/не писать мусор в репо.
_LC_DIR = os.path.join(_TMP, 'data')
LC.log_cards_cfg_path = lambda gid: os.path.join(_LC_DIR, f'log_cards_{gid}.json')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


# ── 1. Реестр тем: 9 образов, все рендерятся ────────────────────────────────
for t in LC.LOG_CARD_THEME_ORDER:
    png = LC.render_log_card('mod', 'Пример', [('Юзер', 'X'), ('Модератор', 'Y')],
                             cat_name='Модерация', theme=t, fmt='jpeg')
    check(bool(png) and len(png) > 20000, f'тема «{LC.LOG_CARD_THEMES[t]["label"]}» рендерится', len(png or ''))

# ── 2. Категория «Никнеймы» повсюду ─────────────────────────────────────────
cats = [k for k, _, _ in LS.LOG_CATEGORIES]
check('nick' in cats, 'log_settings: категория nick в панели')
check('nick' in LC.CATEGORY_STYLES, 'карточки: свой стиль НИКНЕЙМЫ')
check(LC.DEFAULT_THEME_BY_CAT.get('nick') == 'sakura', 'дефолтный образ ников — Сакура')
png = LC.render_log_card('nick', 'Псевдоним изменён',
                         [('GhostBlade', 'старый → новый')], cat_name='Никнеймы',
                         theme='sakura', fmt='jpeg')
check(bool(png) and len(png) > 20000, 'карточка ника рендерится в sakura', len(png or ''))

# ── 3. theme_by_cat: сохранение, валидация, дефолты ────────────────────────
cfg = LC.get_log_cards_cfg('777')
check(cfg['theme_by_cat'] == LC.DEFAULT_THEME_BY_CAT, 'без сохранённого — образы по умолчанию')
saved = LC.save_log_cards_cfg('777', {'theme': 'hakumo',
                                      'theme_by_cat': {'message': 'ocean', 'ник': 'zzz'}})
check(saved['theme_by_cat'] == {'message': 'ocean'}, 'мусорные ключи/темы отброшены', saved['theme_by_cat'])
loaded = LC.get_log_cards_cfg('777')
check(loaded['theme_by_cat'] == {'message': 'ocean'}, 'сохранённые образы читаются с диска')
saved2 = LC.save_log_cards_cfg('777', {'theme': 'hakumo'})
check(saved2['theme_by_cat'] == LC.DEFAULT_THEME_BY_CAT, 'пустой theme_by_cat → снова дефолтные образы')

# ── 3b. Категория «Наказания»: варны и авто-наказания — отдельный канал ─────
check('punish' in [k for k, _, _ in LS.LOG_CATEGORIES], 'log_settings: категория punish')
check('punish' in LC.CATEGORY_STYLES, 'карточки: стиль НАКАЗАНИЯ')
check(LC.DEFAULT_THEME_BY_CAT.get('punish') == 'crimson', 'образ наказаний — Багровый неон')
png = LC.render_log_card('punish', 'Авто-наказание',
                         [('Участник', 'GhostBlade'), ('Варнов всего', '3'),
                          ('Применено', 'Мут: роль «Наказан» 60 мин')],
                         cat_name='Наказания', theme='crimson', fmt='jpeg')
check(bool(png) and len(png) > 20000, 'карточка наказания рендерится в crimson', len(png or ''))
# warnings.py: варны и авто-наказания идут в канал «наказания»
_ws = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check("ensure_log_channel(guild,'наказания')" in _ws.replace(' ', ''),
      'варны логируются в канал «наказания»')
check('_log_punish_to_channel' in _ws, 'авто-наказание логируется отдельно в «наказания»')

# ── 4. Маршрут канала «Никнеймы» ────────────────────────────────────────────
LS.set_log_settings('777', channels={'nick': '1379190715426410726'})
check(str(LS.target_channel_id('777', 'nick')) == '1379190715426410726',
      'log_settings: nick → ID канала владельца', LS.target_channel_id('777', 'nick'))
# зашёл-вышел / сообщения / войсы / модерация+роли
LS.set_log_settings('777', channels={'member': '1379191035300675784',
                                     'message': '1379190295723511949',
                                     'voice': '1379190587579961466',
                                     'mod': '1518751543329951904',
                                     'role': '1518751543329951904',
                                     'automod': '1518751543329951904',
                                     'punish': '1545468739221327942'})
want = {'nick': 1379190715426410726, 'member': 1379191035300675784,
        'message': 1379190295723511949, 'voice': 1379190587579961466,
        'mod': 1518751543329951904, 'role': 1518751543329951904,
        'punish': 1545468739221327942}
for k, v in want.items():
    check(str(LS.target_channel_id('777', k)) == str(v), f'маршрут {k} → {v}')

# ── 5. Резолвер URL: Pinterest-страница, прямая ссылка, мусор ──────────────
import io as _io
from PIL import Image as _PImage
_buf = _io.BytesIO()
_PImage.new('RGB', (8, 8), (200, 80, 120)).save(_buf, 'PNG')
IMG_PNG = _buf.getvalue()


class FakeResp:
    def __init__(self, ct, body=b'', status=200, url='https://x'):
        self.headers = {'Content-Type': ct}
        self.status_code = status
        self.url = url
        self._chunks = [body]

    def iter_content(self, n):
        for c in self._chunks:
            yield c


HTML_PIN = (b'<html><head><meta property="og:image" '
            b'content="https://i.pinimg.com/originals/aa/bb/cc/pic.jpg">'
            b'</head></html>')


def fake_get(url, **kw):
    if url.startswith('https://i.pinimg.com'):
        return FakeResp('image/jpeg', IMG_PNG, url=url)
    if url.startswith('https://httpbin'):
        return FakeResp('image/png', IMG_PNG, url=url)
    if 'pin.it' in url or 'pinterest.com' in url:
        return FakeResp('text/html', HTML_PIN, url=url)
    if url == 'https://mildsite.example/':
        return FakeResp('text/html', b'<html>no image here</html>', url=url)
    if url == 'https://dead.example/x':
        return FakeResp('text/html', b'gone', status=404, url=url)
    return FakeResp('image/png', IMG_PNG, url=url)


import services.welcome_card_gen as _wcg
_orig_get = _wcg.__dict__.get('requests')
_wc = {'get': fake_get}


def patched_resolve(url, max_bytes=None):
    """resolve_image_url с подменённым requests.get."""
    import types
    src = WCG.resolve_image_url
    real_requests = __import__('requests')
    class FakeReq(types.SimpleNamespace):
        pass
    fake_mod = types.SimpleNamespace(get=fake_get)
    real_get = real_requests.get
    real_requests.get = fake_get
    try:
        return src(url, max_bytes=max_bytes)
    finally:
        real_requests.get = real_get


r = patched_resolve('https://i.pinimg.com/originals/aa/bb/cc/pic.jpg')
check(r.get('ok') and r['data'][:4] == IMG_PNG[:4] and r['via'] == 'прямая ссылка',
      'прямая ссылка на картинку → скачана', str(r)[:120])
r = patched_resolve('https://pin.it/abc123')
check(r.get('ok') and r['direct_url'].startswith('https://i.pinimg.com')
      and r['via'] == 'страница → og:image',
      'страница Pinterest → вытащена og:image и скачана', str(r)[:140])
r = patched_resolve('https://httpbin.example/img.png')
check(r.get('ok'), 'прямая ссылка без расширения (по Content-Type) → ок', str(r)[:120])
r = patched_resolve('https://mildsite.example/')
check(not r.get('ok') and 'прямая' in r.get('error', ''), 'страница без картинки → внятная подсказка', str(r)[:120])
r = patched_resolve('https://dead.example/x')
check(not r.get('ok') and '404' in r.get('error', ''), 'сайт недоступен → код в ошибке', str(r)[:120])
r = WCG.resolve_image_url('ftp://x')
check(not r.get('ok') and 'https' in r.get('error', ''), 'не-https → отказ', str(r)[:80])
r = WCG.resolve_image_url('')
check(not r.get('ok'), 'пустая ссылка → отказ')

# ── 6. Панель: сохранение URL-фона (mode=url → скачан как файл) ────────────
from types import SimpleNamespace as NS
import asyncio, threading
import web.app as A
guild = NS(id=777, owner_id=42, name='Looks', roles=[], channels=[],
           get_member=lambda u: None, get_channel=lambda c: None, get_role=lambda r: None)
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
A.bot_instance = NS(guilds=[guild], get_guild=lambda g: guild if g == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda n: None,
                    get_channel=lambda c: None, get_role=lambda r: None,
                    change_presence=lambda **k: None, description='s', application_id=1,
                    user=NS(id=1, name='bot'))
c = A.app.test_client()
c.post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})

_real = real_requests_get_holder = {}


def fake_requests_get(url, **kw):
    return fake_get(url, **kw)


import requests as _rqmod
_orig = _rqmod.get
_rqmod.get = fake_requests_get
try:
    r = c.post('/api/guild/777/welcome-card/appearance',
               json={'mode': 'url', 'url': 'https://pin.it/xyz', 'theme': 'aurora'})
    j = r.get_json()
    check(r.status_code == 200 and j.get('success'), 'POST appearance c Pinterest-страницей → ок',
          f'{r.status_code} {str(j)[:140]}')
    check(j['appearance']['mode'] == 'file' and j['appearance']['file'],
          'фон сохранён ФАЙЛОМ (работает везде, не зависит от сайта)', str(j['appearance'])[:120])
    check(j['appearance']['url'].startswith('https://i.pinimg.com'),
          'прямая ссылка сохранена для embed-ов', j['appearance']['url'][:80])
    check('Pinterest' in j.get('message', '') or 'скачан' in j.get('message', ''),
          'сообщение владельцу', j.get('message', '')[:100])
    r2 = c.post('/api/guild/777/welcome-card/appearance',
                json={'mode': 'url', 'url': 'https://mildsite.example/', 'theme': 'aurora'})
    check(r2.status_code == 400 and 'прямая' in r2.get_json().get('error', ''),
          'битая для скачивания страница → 400 с подсказкой', f'{r2.status_code} {r2.get_data(as_text=True)[:100]}')
finally:
    _rqmod.get = _orig

print(f'\n════ LOG LOOKS: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
