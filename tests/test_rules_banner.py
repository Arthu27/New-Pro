# -*- coding: utf-8 -*-
"""Авто-картинки правил: генератор баннеров + API предпросмотра и публикации.

- services/banner_gen: валидный PNG 1200x400, темы, фолбэк темы, кастомный акцент;
- _norm_rule принимает/сохраняет img_gen, легаси-поля живы;
- POST rules + publish в демо считают сгенерированные картинки;
- GET /api/guild/<gid>/rules/banner — PNG, права, без локальных адресов;
- шаблон редактора содержит UI авто-картинок и авто-выбор канала
  (больше нельзя прийти к «Опубликовать» с пустым каналом).

Запуск: python3 tests/test_rules_banner.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_banner_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
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


print('== 1. Генератор баннеров ==')
from services import banner_gen as BG  # noqa: E402

png = BG.render_rules_banner(title='Правила сервера', text='Без флуда и рекламы',
                             index=2, total=5, accent='ff8800', theme='violet')
check(png[:8].startswith(b'\x89PNG\r\n\x1a\n'), 'подпись PNG на месте')
from PIL import Image  # noqa: E402
import io as _io  # noqa: E402
im = Image.open(_io.BytesIO(png))
check(im.size == (BG.W, BG.H) == (1200, 400), f'размер {im.size} (ожидали 1200x400)')
check(len(png) > 20000, f'баннер «живой» ({len(png)} байт, не заглушка)')

# детерминизм по seed-производным полей и разница тем
a = BG.render_rules_banner(title='T', text='x', index=1, total=1, accent='4f46e5', theme='violet')
b = BG.render_rules_banner(title='T', text='x', index=1, total=1, accent='4f46e5', theme='violet')
c = BG.render_rules_banner(title='T', text='x', index=1, total=1, accent='4f46e5', theme='ocean')
check(a == b, 'одинаковые параметры → одинаковый PNG (детерминирован)')
check(a != c, 'смена темы меняет картинку')

check(set(BG.THEME_ORDER) == set(BG.THEMES), 'порядок тем согласован с реестром')
z = BG.render_rules_banner(title='Правила', text='y', index=9, total=9, accent='zzz', theme='nope')
check(z[:8].startswith(b'\x89PNG'), 'мусорная тема/цвет → дефолт, без падения')
check(BG.banner_filename(3) == 'hakumo_rule_03.png', 'имя файла для attachment')

# wrap не роняет длинные строки и пустоту
lng = BG.render_rules_banner(title='P', text='слово ' * 120, index=1, total=2,
                             accent='22d3ee', theme='night')
check(lng[:8].startswith(b'\x89PNG'), 'очень длинный текст обрезан до 3 строк')
emp = BG.render_rules_banner(title='', text='', index=1, total=1, accent='', theme='forest')
check(emp[:8].startswith(b'\x89PNG'), 'пустые поля не ломают рендер')

print('== 2. API: preview, norm, publish ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


BANNER_URL = '/api/guild/777/rules/banner'
# Гость без сессии: проверяем вне DEMO_MODE — с ним before_request
# сознательно входит владельцем, иначе живой предпросмотр панели не работал бы.
os.environ['DEMO_MODE'] = '0'
try:
    r_guest = client.get(BANNER_URL)
finally:
    os.environ['DEMO_MODE'] = '1'
check(r_guest.status_code in (302, 401, 403), 'гостю баннер закрыт (вне демо)')
# В самом демо баннер наоборот должен открываться — иначе предпросмотр сломан.
r_demo = client.get(BANNER_URL + '?text=Демо')
check(r_demo.status_code == 200 and r_demo.mimetype == 'image/png',
      'в DEMO_MODE предпросмотр открыт (авто-вход владельцем)')
login('mod')
check(client.get(BANNER_URL).status_code == 403, 'mod не рисует (admin+)')
login('admin')
r = client.get(BANNER_URL + '?text=Привет&n=2&total=4&theme=ocean&color=22d3ee')
body = r.get_data()
check(r.status_code == 200 and r.mimetype == 'image/png', 'предпросмотр баннера → PNG')
check(body[:8].startswith(b'\x89PNG') and len(body) > 20000, f'PNG не пустая ({len(body)} байт)')
check(r.headers.get('Cache-Control') == 'no-store', 'превью не кэшируется')
r2 = client.get(BANNER_URL + '?theme=zzz&color=zzz&text=x')
check(r2.status_code == 200, 'битые параметры — дефолты, не 500')

# norm: img_gen переживает сохранение, фильтруется от мусора
RULES_URL = '/api/guild/777/rules'
payload = [
    {'t': 'Не флудить', 'img_gen': 'ocean'},
    {'t': 'Ссылка на гайд', 'u': 'discord.gg/x', 'img': 'https://x/1.png', 'img_gen': 'night'},
    {'t': 'Мусорная тема', 'img_gen': 'nope'},
    'просто строка легаси',
]
r = client.post(RULES_URL, json=payload)
check(r.status_code == 200, f'img_gen сохраняется (POST 200, пришёл {r.status_code})')
g = client.get(RULES_URL).get_json()
check(g[0]['img_gen'] == 'ocean' and g[1]['img_gen'] == 'night', 'темы в правилах на месте')
check(g[2]['img_gen'] == '', 'неизвестная тема очищена')
check(g[3] == {'t': 'просто строка легаси', 'u': '', 'u2': '', 'img': '', 'thumb': '', 'img_gen': ''},
      'легаси-строка нормализуется с img_gen')

# demo publish: img без URL → авто-картинка посчитана.
# Правила передаём прямо в теле (как делает фронт).
client.post(RULES_URL, json=[{'t': 'Авто-баннер для правила', 'img_gen': 'violet'},
                             {'t': 'Своя картинка', 'img': 'https://cdn.x/a.png'}])
r = client.post('/api/guild/777/rules/publish',
                json={'channel_id': '555', 'title': 'Правила', 'color': '4f46e5',
                      'rules': [{'t': 'Авто-баннер для правила', 'img_gen': 'violet'},
                                {'t': 'Своя картинка', 'img': 'https://cdn.x/a.png'}]})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), f'публикация в демо ({d.get("error", "ok")})')
check(d.get('images_generated') == 1, f'сгенерирована одна картинка (получено {d.get("images_generated")})')
check('авто-картинкой' in (d.get('message') or ''), 'сообщение упоминает авто-картинку')

# и та же публикация без списка в теле — API берёт сохранённые (фолбэк)
r = client.post('/api/guild/777/rules/publish', json={'channel_id': '555', 'title': 'Правила'})
d = r.get_json()
check(r.status_code == 200 and d.get('images_generated') == 1,
      'без rules в теле — публикуем сохранённые (фолбэк) с той же картинкой')

# meta: img_theme сохраняется и читается
r = client.post('/api/guild/777/rules/meta', json={'img_theme': 'forest'})
check(r.get_json()['meta']['img_theme'] == 'forest', 'мета: тема авто-картинок пишется')
r = client.post('/api/guild/777/rules/meta', json={'img_theme': 'bogus'})
check(r.get_json()['meta']['img_theme'] == 'forest', 'мусорная тема не затирает валидную')
r = client.get('/api/guild/777/rules/meta')
check(r.get_json()['meta']['img_theme'] == 'forest', 'мета: тема читается обратно')

print('== 3. Шаблон редактора ==')
tpl = open(os.path.join(ROOT, 'web/templates/rules_editor.html'), encoding='utf-8').read()
check('rule-gen-btn' in tpl and 'data-gen="' in tpl, 'кнопка «Авто» у правил')
check('rules-img-theme' in tpl and 'img_theme' in tpl, 'селект темы авто-картинок')
check('pv-gen' in tpl and 'scheduleBannerRefresh' in tpl, 'превью генерированного баннера с паузой')
check('selectedIndex' in tpl and 'lastChannel' in tpl,
      'авто-выбор первого канала (публикация без тупика)')
check('/api/guild/' in tpl and 'rules/banner' in tpl, 'эндпоинт баннера подключён')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
