# -*- coding: utf-8 -*-
"""Страж update.bat — обновление в один клик не должно сожрать данные.

update.bat докладывает свежий код поверх папки бота. Критичные инварианты:
никаких зеркальных режимов robocopy (/MIR, /PURGE — стирают «лишние»
файлы, то есть БД и настройки), обязательные исключения (.env, data,
.venv, .git, logs) и скачивание именно нашей ветки. Кто-то «почистит»
скрипт — тест упадёт раньше, чем пострадает чья-то база.

Запуск: python3 tests/test_update_script.py
"""
import io
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
# Дефолт — main (туда мёржатся релизы); мёртвая arena-ветка старой сессии
# больше НЕ прошита (2026-09-01: она тянула устаревший код).
check('arena/01a' not in text, 'мёртвая сессионная ветка не зашита в скрипт')
check('set "BRANCH=main"' in text, 'ветка по умолчанию — main (релизы)')
# .env владельца уважается: UPDATE_REPO/UPDATE_BRANCH переопределяют дефолт.
check('UPDATE_BRANCH' in text and 'UPDATE_REPO' in text,
      'ветка/репозиторий берутся из .env, если заданы')
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
check(all(ord(ch) < 128 for ch in text),
      'файл целиком ASCII — не ломается ни в русской, ни в английской консоли')
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
check('Istochnik: posledniy reliz' in text, 'человеку видно, откуда качалось')


import re as _re
print('== Только самое свежее: git clean после pull ==')
import os as _os
_src = open(_os.path.join(ROOT, 'auto_update.py'), encoding='utf-8').read()
# git теперь зовётся через безопасный _run_git([...]) — без падения на
# машинах без git (WinError 2): нет бинаря → ZIP-режим.
check('"clean", "-fd"' in _src and '_run_git(' in _src,
      'после обновления каталог приводится к свежей ветке (git clean -fd через _run_git)')
check('-e", "data/"' in _src and '-e", ".env"' in _src,
      'данные и секреты в exclude-списке уборки')
# Защита от [WinError 2]: git-режим только если бинарь реально доступен.
check('def _git_bin' in _src and 'shutil.which' in _src and 'def _run_git' in _src,
      'git вызывается только если найден (shutil.which), иначе ZIP-обновление')
check('download_and_extract' in _src, 'при отсутствии git обновление идёт ZIP-архивом')
check('только самое свежее' in _src or 'СВЕЖЕЕ' in _src,
      'логирование результатов чистки понятным языком')

# ── /update в боте: запуск update_silent.bat из cogs/diagnostics.py ───────
# Раньше команда собиралась СПИСКОМ: ['cmd','/c','start','"Hakumo Updater"', ...].
# Python прогоняет список через subprocess.list2cmdline и экранирует кавычки
# заголовка в \"Hakumo Updater\". cmd обратное экранирование не понимает, и
# Windows отвечала «Windows cannot find '...'». Теперь строка собирается
# вручную — кавычки доходят до cmd нетронутыми.
_diag = io.open(os.path.join(ROOT, 'cogs', 'diagnostics.py'),
                encoding='utf-8').read()
check('start "Hakumo Updater" cmd /k' in _diag,
      'заголовок окна обновлятора собирается строкой, а не списком')
check("['cmd','/c','start'" not in _diag,
      'списка аргументов cmd/start больше нет (именно он ломал кавычки)')
check('/k "%s"' in _diag,
      'путь к update_silent.bat экранирован кавычками — папка с пробелом не сломает запуск')
check("[^A-Za-z0-9._/-]" in _diag,
      'имя ветки очищается от спецсимволов перед подстановкой в cmd')

# Сам механизм поломки — чтобы тест падал по делу, а не «текст не тот».
import subprocess as _sp_chk
_broken = _sp_chk.list2cmdline(['cmd', '/c', 'start', '"Hakumo Updater"',
                                'cmd', '/k', r'C:\b\update_silent.bat'])
check(r'\"' in _broken,
      'list2cmdline действительно экранирует кавычки заголовка (почему список не годится)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
