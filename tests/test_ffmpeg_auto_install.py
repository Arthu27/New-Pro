# -*- coding: utf-8 -*-
"""Автоустановка ffmpeg (services/ffmpeg_probe.ensure_ffmpeg).

Проверяем БЕЗ реальной сети:
  • find_ffmpeg() не падает и возвращает путь/None;
  • машина состояний установки не запускает второй поток, пока первый идёт;
  • после неудачной установки (сеть недоступна) не долбим сеть повторно на
    каждый вызов — состояние done=True;
  • распаковка ffmpeg из поддельного архива (zip на Windows-пути логики и
    tar на linux) кладёт бинарь в bin/.

Запуск: python3 tests/test_ffmpeg_auto_install.py
"""
import os
import sys
import tempfile
import zipfile
import tarfile
import io

_TMP = tempfile.mkdtemp(prefix='hakumo_ffmpeg_test_')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(_TMP)

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


import services.ffmpeg_probe as FP  # noqa: E402

print('== 1. find_ffmpeg не падает ==')
try:
    found = FP.find_ffmpeg()
    check(True, f'find_ffmpeg() отработал (результат: {found})')
except Exception as ex:  # noqa: BLE001
    check(False, f'find_ffmpeg() бросил исключение: {ex}')

print('== 2. Машина состояний: повторный вызов при идущей установке ==')
FP._install_state.update({'done': False, 'running': True, 'ok': False, 'path': None})
# blocking=False при running -> None и НЕ сбрасывает running
res = FP.ensure_ffmpeg(blocking=False)
check(res is None and FP._install_state['running'] is True,
      'пока установка идёт — повторный нефорсированный вызов не мешает')

print('== 3. После неудачи повторно сеть не дёргаем ==')
# Симулируем неуспешную установку: подменяем _install_blocking на «вернул None»
orig = FP._install_blocking
calls = {'n': 0}


def _fail():
    calls['n'] += 1
    return None


FP._install_blocking = _fail
FP._install_state.update({'done': False, 'running': False, 'ok': False, 'path': None})
# find_ffmpeg форсим в None (в песочнице бинаря нет — так и есть)
r1 = FP.ensure_ffmpeg(blocking=True)
r2 = FP.ensure_ffmpeg(blocking=True)   # второй раз — из состояния, без сети
check(r1 is None and r2 is None, 'неудачная установка возвращает None')
check(calls['n'] == 1, f'_install_blocking вызван один раз (не долбим сеть): {calls["n"]}')
check(FP._install_state['done'] is True and FP._install_state['ok'] is False,
      'состояние: done=True, ok=False после неудачи')
FP._install_blocking = orig

print('== 4. Распаковка из zip (Windows-путь логики) ==')
bindir = os.path.join(_TMP, 'bin')
os.makedirs(bindir, exist_ok=True)
zip_path = os.path.join(_TMP, 'fake.zip')
with zipfile.ZipFile(zip_path, 'w') as z:
    z.writestr('ffmpeg-6/bin/ffmpeg.exe', b'FAKEFFMPEG')
    z.writestr('ffmpeg-6/bin/ffprobe.exe', b'FAKEFFPROBE')
    z.writestr('ffmpeg-6/doc/readme.txt', b'ignore me')
try:
    out = FP._extract_ffmpeg(zip_path, bindir, is_windows=True)
    check(os.path.isfile(os.path.join(bindir, 'ffmpeg.exe')),
          'ffmpeg.exe извлечён в bin/')
    check(os.path.isfile(os.path.join(bindir, 'ffprobe.exe')),
          'ffprobe.exe тоже извлечён')
    check(os.path.basename(out) == 'ffmpeg.exe', f'вернулся путь ffmpeg.exe: {out}')
except Exception as ex:  # noqa: BLE001
    check(False, f'распаковка zip упала: {ex}')

print('== 5. Распаковка из tar (Linux-путь логики) ==')
bindir2 = os.path.join(_TMP, 'bin2')
os.makedirs(bindir2, exist_ok=True)
tar_path = os.path.join(_TMP, 'fake.tar.xz')
with tarfile.open(tar_path, 'w:xz') as t:
    for name, payload in (('ffmpeg', b'FAKEFFMPEG'), ('ffprobe', b'FAKEPROBE')):
        info = tarfile.TarInfo(name=f'ffmpeg-static/{name}')
        data = payload
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    info = tarfile.TarInfo(name='ffmpeg-static/readme')
    t.addfile(info, io.BytesIO(b'x'))
try:
    out2 = FP._extract_ffmpeg(tar_path, bindir2, is_windows=False)
    check(os.path.isfile(os.path.join(bindir2, 'ffmpeg')),
          'ffmpeg извлечён в bin2/')
    check(os.access(out2, os.X_OK), 'бинарь помечен исполняемым (chmod +x)')
except Exception as ex:  # noqa: BLE001
    check(False, f'распаковка tar упала: {ex}')

print('== 6. ensure_ffmpeg возвращает find_ffmpeg, если бинарь уже есть ==')
FP._install_state.update({'done': False, 'running': False, 'ok': False, 'path': None})
# Подкладываем фейковый ffmpeg в ./bin и форсим find через monkeypatch
fake = os.path.join(_TMP, 'bin', 'ffmpeg.exe')
FP.find_ffmpeg = lambda: fake  # noqa: E731
r = FP.ensure_ffmpeg(blocking=False)
check(r == fake and FP._install_state['ok'] is True,
      'если ffmpeg уже найден — возвращаем его без установки')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
