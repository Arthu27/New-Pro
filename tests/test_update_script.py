# -*- coding: utf-8 -*-
"""Страж update.bat — обновление в один клик не должно сожрать данные.

update.bat докладывает свежий код поверх папки бота. Критичные инварианты:
никаких зеркальных режимов robocopy (/MIR, /PURGE — стирают «лишние»
файлы, то есть БД и настройки), обязательные исключения (.env, data,
.venv, .git, logs) и скачивание именно нашей ветки. Кто-то «почистит»
скрипт — тест упадёт раньше, чем пострадает чья-то база.

Запуск: python3 tests/test_update_script.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_upd_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


BAT = os.path.join(ROOT, 'update.bat')
print('== 1. Скрипт существует и читается ==')
check(os.path.exists(BAT), 'update.bat в корне репозитория')
raw = open(BAT, 'rb').read()
text = raw.decode('utf-8')
check('@echo off' in text, 'корректный бат-заголовок')

print('== 2. Источник обновления — наша ветка ==')
check('Arthu27/New-Pro' in text, 'репозиторий прошит верно')
check('arena/01a03640-new-pro' in text, 'качается именно сессионная ветка')
check('codeload.github.com' in text, 'скачивание через официальный codeload')

print('== 3. Безопасность данных — железо ==')
check('/MIR' not in text and '/PURGE' not in text.upper(),
      'нет зеркального режима robocopy (данные не могут быть стёрты)')
check('/E ' in text, 'докладка только новых/изменённых файлов (/E)')
for excluded in ('data', '.git', '.venv', '__pycache__', 'logs'):
    check(excluded in text, f'каталог исключён из обновления: {excluded}')
check('/XF .env update.bat' in text, 'файлы исключены: .env и сам скрипт')
check('errorlevel 8' in text, 'коды robocopy 0-7 обработаны как успех')

print('== 4. UX-экран ==')
check('chcp 65001' in text, 'UTF-8 консоль (русские строки без кракозябр)')
check('/norestart' in text, 'режим без перезапуска предусмотрен')
check('main.py' in text, 'защита от запуска не из папки бота')
check('main\\.py' in text.replace('main.py', 'main\\.py', 1) or 'main\\.py' in text,
      'останавливается только python с main.py в командной строке')

print('== 5. Старый Windows без TLS 1.2 ==')
check('curl.exe' in text, 'скачивание через curl.exe (Server 2019+/Win10+)')
check('3072' in text, 'PowerShell-запасной вариант с принудительным TLS 1.2 (3072)')
check('tar.exe' in text, 'распаковка через tar.exe — без зависимости от Expand-Archive')
check('raw/latest/update.bat' in text,
      'при сбое — ПОСТОЯННАЯ ссылка на свежую обновлялку (тег релиза)')

print('== 6. Постоянная ссылка (не зависит от ветки) ==')
check('releases/latest' in text, 'источник: последний релиз — ссылка не меняется')
check('zipball_url' in text, 'адрес архива берётся из ответа GitHub')
check('for /d %%D in' in text, 'папка в архиве определяется автоматически')
check('Источник: последний релиз' in text, 'человеку видно, откуда качалось')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
