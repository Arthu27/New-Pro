# -*- coding: utf-8 -*-
"""UX-полировка (идеи #96-100).

pickers.js v2: bindSlashFocus («/» в поиск списка), dirtyTrack (сторож
незакрытых черновиков, reset после сохранения), freshStamp (чип
«обновлено HH:MM:SS»), самозапускающаяся кнопка «наверх». aria-label
у иконочных кнопок. Подключение на страницах кармы сообщества.

Запуск: python3 tests/test_ux_polish.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_ux2_test_')
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


def tpl(name):
    return open(os.path.join(ROOT, 'web/templates', name), encoding='utf-8').read()


EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 1. Хелперы v2 в pickers.js ==')
js = open(os.path.join(ROOT, 'web/static/pickers.js'), encoding='utf-8').read()
for fn in ('window.bindSlashFocus', 'window.dirtyTrack', 'window.freshStamp'):
    check(fn in js, f'хелпер {fn} на месте')
check("e.key !== '/'" in js and 'isContentEditable' in js,
      '«/» не крадёт ввод из полей')
check('beforeunload' in js and 'e.returnValue' in js,
      'сторож черновиков предупреждает об уходе')
check('reset: function () { dirty = false; }' in js,
      'сброс черновика после сохранения')
check("getElementById('scrollTopBtn')" in js and 'aria-label' in js
      and 'behavior' in js and 'smooth' in js,
      'кнопка «наверх» самозапускается, с aria-label')
check(not EMOJI_RE.search(js), 'эмодзи не появились в хелпере')
css = open(os.path.join(ROOT, 'web/static/polish.css'), encoding='utf-8').read()
check('.scroll-top-btn' in css and '.scroll-top-btn.show' in css
      and '.fresh-chip' in css, 'стили кнопки и чипа свежести')

print('== 2. Версионирование подключений ==')
for name in ('j2c.html', 'anime_daily.html', 'birthdays.html', 'social.html'):
    check('pickers.js?v=2' in tpl(name), f'{name}: хелпер v2')

print('== 3. «/» в поиск списка ==')
check('bindSlashFocus(document.getElementById(\'j2RoomSearch\'))' in tpl('j2c.html'),
      'j2c: поиск комнат')
check('bindSlashFocus(document.getElementById(\'bdSearch\'))' in tpl('birthdays.html'),
      'birthdays: поиск календаря')
check(tpl('social.html').count('bindSlashFocus') == 2,
      'social: оба поиска под клавишей')

print('== 4. Сторожа черновиков ==')
j2c, an, bd = tpl('j2c.html'), tpl('anime_daily.html'), tpl('birthdays.html')
check('dirtyTrack([' in j2c and "'j2Lobby'" in j2c and '_j2Dirty.reset()' in j2c,
      'j2c: сторож на пяти полях, сброс после сохранения')
check('dirtyTrack([' in an and "'anChannel'" in an and '_anDirty.reset()' in an,
      'anime: сторож и сброс')
check('dirtyTrack([' in bd and "'bdSetChannel'" in bd and '_bdDirty.reset()' in bd,
      'birthdays: сторож и сброс')

print('== 5. Чипы свежести ==')
check('id="j2Fresh"' in j2c and "freshStamp(document.getElementById('j2Fresh'))" in j2c,
      'j2c: чип и штамп')
check('id="anFresh"' in an and "freshStamp(document.getElementById('anFresh'))" in an,
      'anime: чип и штамп')
check('id="bdFresh"' in bd and "freshStamp(document.getElementById('bdFresh'))" in bd,
      'birthdays: чип и штамп')
check('id="soFresh"' in tpl('social.html')
      and "freshStamp(document.getElementById('soFresh'))" in tpl('social.html'),
      'social: чип и штамп')

print('== 6. Доступность и чистота шаблонов ==')
so = tpl('social.html')
check('aria-label="Вычистить сирот из реестра"' in j2c, 'j2c: aria у уборки')
check('aria-label="Удалить запись"' in bd, 'birthdays: aria у удаления')
check(so.count('aria-label="Состав в CSV"') == 1
      and 'aria-label="Удалить событие"' in so
      and 'aria-label="Закрыть поиск"' in so, 'social: aria у иконочных')
check('aria-label="Выгрузить календарь в CSV"' in bd, 'birthdays: aria у CSV')
for name in ('j2c.html', 'anime_daily.html', 'birthdays.html', 'social.html'):
    check(not EMOJI_RE.search(tpl(name)), f'{name}: эмодзи не появились')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
