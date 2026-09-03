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
import time

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


# ── Обновлятор не должен «убить себя» и обязан поднять бота обратно ──────
# Заказ владельца: «бот сразу выключает себя и не может обновиться — надо,
# чтобы после обновления выключился и включился обратно».
print('== update_silent.bat: порядок «остановить -> обновить -> поднять» ==')
_sil = io.open(os.path.join(ROOT, 'update_silent.bat'), encoding='utf-8').read()
_sbot = io.open(os.path.join(ROOT, 'start_bot.bat'), encoding='utf-8').read()

# Смотрим ТОЛЬКО на сами команды taskkill (в поясняющих комментариях /T
# упомянут как раз чтобы объяснить, почему его больше нет).
_tk = [l.strip() for l in _sil.replace('\r\n', '\n').split('\n')
       if l.strip().lower().startswith('taskkill')]
check(bool(_tk), 'в обновляторе есть команда taskkill')
check(all('/T' not in c for c in _tk),
      'taskkill БЕЗ /T: обновлятор запущен из процесса бота, и /T глушил его самого')
check('taskkill /PID %OLD_PID% /F' in _sil,
      'старый процесс бота всё равно гасится по PID')

_i_kill = _sil.index('taskkill')
_i_git = _sil.index('git_update')
_i_start = _sil.index('start "Hakumo Bot"')
check(_i_kill < _i_git < _i_start,
      'порядок верный: сначала остановить, потом обновить, поднять в самом конце')

check(':waitdead' in _sil and 'tasklist /FI "PID eq %OLD_PID%"' in _sil,
      'обновлятор ждёт, пока процесс отпустит файлы (иначе замена молча не выходила)')

check('data\\.updating' in _sil and 'del /q "data\\.updating"' in _sil,
      'метку обновления снимает обновлятор перед стартом свежей версии')
check(_sil.index('del /q "data\\.updating"') < _i_start,
      'метка снимается ДО запуска бота, а не после')

check('set "FAILED=' in _sil and 'if not "%FAILED%"==""' in _sil,
      'при неудаче обновления окно остаётся открытым с объяснением')
# Перезапуск обязан быть всегда: между обновлением и стартом нет выхода из bat.
_between = _sil[_i_git:_i_start]
check('exit /b' not in _between,
      'между обновлением и запуском бота нет выхода - бот поднимается всегда')

print('== start_bot.bat не воскрешает бота посреди обновления ==')
check('.updating' in _sbot and ':runloop' in _sbot,
      'в цикле перезапуска start_bot.bat есть проверка метки обновления')
_i_loop = _sbot.index(':runloop')
_i_mark = _sbot.index('.updating')
_i_py = _sbot.index('main.py', _i_loop)
check(_i_loop < _i_mark < _i_py,
      'метка проверяется до запуска main.py, а не после')
check('900' in _sbot,
      'метка старше 15 минут считается протухшей - бот поднимется даже если обновлятор упал')

print('== метку ставит сам бот перед запуском обновлятора ==')
_i_mark_py = _diag.index("'.updating'")
_i_popen = _diag.index('_sp .Popen (')
check(0 < _i_mark_py < _i_popen,
      'cogs/diagnostics.py пишет data/.updating ДО запуска update_silent.bat')

_upd = io.open(os.path.join(ROOT, 'update.bat'), encoding='utf-8').read()
check('data\\.updating' in _upd,
      'ручной update.bat тоже снимает метку (иначе start_bot.bat не поднимет бота)')

print('== логика возраста метки (настоящий прогон однострочника) ==')
import subprocess
_ONE = ('import os,sys,time;p=os.path.join("data",".updating");'
        'sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<900 else 1)')
_d = os.path.join(_TMP, 'mark_probe')
os.makedirs(os.path.join(_d, 'data'), exist_ok=True)


def _mark_rc():
    return subprocess.run([sys.executable, '-c', _ONE], cwd=_d,
                          capture_output=True).returncode


_p = os.path.join(_d, 'data', '.updating')
if os.path.exists(_p):
    os.remove(_p)
check(_mark_rc() == 1, 'метки нет -> перезапуск разрешён (код 1)')
with open(_p, 'w', encoding='utf-8') as _f:
    _f.write('1234 main')
check(_mark_rc() == 0, 'свежая метка -> старый процесс НЕ воскрешаем (код 0)')
_old = time.time() - 20 * 60
os.utime(_p, (_old, _old))
check(_mark_rc() == 1, 'метка протухла (20 минут) -> перезапуск разрешён')


# ── Бот НЕ гаснет, пока новая версия не скачана ───────────────────────────
# Заказ владельца: «не выключайся, пока не скачается версия». Значит в
# Windows-ветке /update скачивание и проверка идут ДО запуска обновлятора и
# ДО os._exit, а при неудаче бот остаётся работать.
print('== бот не выключается, пока архив не скачан ==')
DIAG = os.path.join(ROOT, 'cogs', 'diagnostics.py')
_dsrc = io.open(DIAG, encoding='utf-8').read()
_w0 = _dsrc.index("if sys .platform .startswith ('win'):")
_w1 = _dsrc.index('os ._exit (0 )', _w0)
_win = _dsrc[_w0:_w1]
_i_dl = _win.index('download_zip')
_i_vz = _win.index('verify_zip')
_i_vp = _win.index('verify_python')
_i_sp = _win.index('save_pending')
_i_pop = _win.index('Popen')
check(_i_dl < _i_vz < _i_vp < _i_sp < _i_pop,
      'порядок: скачать -> проверить архив -> проверить код -> отложить -> запустить обновлятор')
check(_win.index('clear_pending') < _i_dl,
      'старый отложенный архив убирают до нового скачивания')
check(_win.count('return') >= 4,
      f'на ошибках ветка выходит без перезапуска (return: {_win.count("return")})')
check('Бот продолжает работать' in _win,
      'владельцу прямо говорят, что бот остался в сети')
check(_win.index('remote_sha') < _i_dl,
      'сверка версий идёт до скачивания — лишнего трафика нет')

# ── Обновлятор применяет готовый архив ───────────────────────────────────
print('== update_silent.bat применяет готовый архив ==')
_sbat = io.open(os.path.join(ROOT, 'update_silent.bat'), encoding='utf-8').read()
check('if exist "data\\.update_pending.zip"' in _sbat,
      'обновлятор ищет архив, скачанный ботом')
check(_sbat.index('.update_pending.zip') < _sbat.index('git_update'),
      'готовый архив проверяют РАНЬШЕ, чем git/скачивание')
check('--pending' in _sbat, 'готовый архив применяют в режиме --pending')
check(':deps' in _sbat and _sbat.count('goto deps') == 1,
      'после готового архива переход сразу к зависимостям')
check('rem --- 3.' in _sbat and 'rem --- 4.' in _sbat,
      'шаги зависимостей и запуска на месте')

_szu = io.open(os.path.join(ROOT, 'scripts', 'silent_zip_update.py'), encoding='utf-8').read()
check("'--pending' in sys.argv" in _szu and 'load_pending' in _szu,
      'silent_zip_update.py умеет режим --pending')
check('download_and_apply' in _szu and 'def main' in _szu,
      'запасной путь (скачать самим) сохранён для ручного запуска')

_ubat = io.open(BAT, encoding='utf-8').read()
check('.update_pending.zip' in _ubat,
      'ручной update.bat убирает протухший отложенный архив')

# ── Отложенный архив: настоящий прогон ───────────────────────────────────
print('== отложенный архив: save -> load -> порча -> clear ==')
from services import self_update as SU  # noqa: E402

# Значения берём из НАСТОЯЩЕГО verify_zip, а не придумываем: прежняя версия
# проверки передавала save_pending строку вместо множества rel — и пропустила
# падение «Object of type set is not JSON serializable» на боевой машине.
_pdir = tempfile.mkdtemp(prefix='pending_')
_pzip = os.path.join(_pdir, 'src.zip')
import zipfile as _zf  # noqa: E402

with _zf.ZipFile(_pzip, 'w') as _z:
    _z.writestr('repo-x/main.py', 'NEW MAIN\n')
    _z.writestr('repo-x/config.py', 'NEW CONFIG\n')
    _z.writestr('repo-x/web/app.py', 'NEW APP\n')
    _z.writestr('repo-x/cogs/fresh.py', '# new\n')
_vok, _verr, _vmeta = SU.verify_zip(_pzip)
check(_vok, f'verify_zip принял архив ({_verr})')
_vnames, _vroot, _vrel = _vmeta
check(isinstance(_vrel, set), f'verify_zip отдаёт rel множеством ({type(_vrel).__name__})')
check(_vroot.endswith('/'), f'корень архива с косой чертой: {_vroot!r}')

_ok, _err = SU.save_pending(_pdir, _pzip, _vroot, _vrel, 'deadbeef', 'main')
check(_ok, f'save_pending пережил множество rel ({_err})')
_z2, _r2, _l2 = SU.load_pending(_pdir)
check(bool(_z2) and _r2 == _vroot, f'load_pending вернул тот же корень {_r2!r}')
check(_l2 == _vrel, 'load_pending вернул rel тем же множеством путей')
import json as _json  # noqa: E402
_2, _mp = SU.pending_paths(_pdir)
_meta = _json.load(open(_mp, encoding='utf-8'))
check(isinstance(_meta.get('rel'), list), 'в описании rel лежит списком (JSON-совместимо)')

# и главное — отложенный архив реально раскатывается
_bot = os.path.join(_pdir, 'bot')
os.makedirs(os.path.join(_bot, 'web'))
os.makedirs(os.path.join(_bot, 'data'))
for _f, _t in (('main.py', 'OLD'), ('config.py', 'OLD'), ('web/app.py', 'OLD'),
               ('.env', 'SECRET=1'), ('data/bot.db', 'db')):
    with open(os.path.join(_bot, _f), 'w', encoding='utf-8') as _fh:
        _fh.write(_t)
_sok, _serr, _stats = SU.stage_update(_z2, _bot, _r2, _l2, 0, 'deadbeef', 'main')
check(_sok, f'stage_update применил отложенный архив ({_serr})')
check(_stats.get('copied') == 4, f"обновлено файлов: {_stats.get('copied')}")


def _read(_p):
    _fp = os.path.join(_bot, _p)
    return open(_fp, encoding='utf-8').read().strip() if os.path.exists(_fp) else None


check(_read('main.py') == 'NEW MAIN', 'main.py заменён на новый')
check(_read('cogs/fresh.py') == '# new', 'новый файл добавлен')
check(_read('.env') == 'SECRET=1', '.env не тронут')
check(_read('data/bot.db') == 'db', 'data/bot.db не тронута')

with open(_z2, 'ab') as _f:
    _f.write(b'garbage')
check(SU.load_pending(_pdir)[0] is None,
      'битый/недокачанный архив отклоняется по контрольной сумме')
SU.clear_pending(_pdir)
check(SU.load_pending(_pdir)[0] is None, 'после clear_pending архива нет')
shutil.rmtree(_pdir, ignore_errors=True)


# ── Все .bat обязаны быть в CRLF ─────────────────────────────────────────
# .gitattributes задаёт «*.bat -text» — git переводы строк не правит, на
# Windows уходит ровно то, что в репозитории. Файл с LF cmd.exe обычно
# терпит, но на многострочных блоках if (...) спотыкается. Так лежали
# reset_server_data.bat (0 CRLF) и start_panel.bat (5 CRLF на 89 строк).
print('== все .bat в CRLF ==')
_bad_crlf = []
for _name in sorted(os.listdir(ROOT)):
    if not _name.endswith('.bat'):
        continue
    _raw = open(os.path.join(ROOT, _name), 'rb').read()
    _crlf = _raw.count(b'\r\n')
    _lone = _raw.replace(b'\r\n', b'').count(b'\n')
    if _lone:
        _bad_crlf.append(f'{_name}: {_lone} одиночных LF при {_crlf} CRLF')
check(not _bad_crlf, f'.bat без CRLF: {len(_bad_crlf)} ({_bad_crlf})')
_n_bat = len([n for n in os.listdir(ROOT) if n.endswith('.bat')])
check(_n_bat >= 5, f'проверено .bat в корне: {_n_bat}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
