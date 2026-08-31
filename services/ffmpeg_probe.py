# -*- coding: utf-8 -*-
"""Единый поиск ffmpeg для музыки.

Раньше логика была размазана: main.py смотрел только PATH, а
music_cog._ffmpeg_binary() — PATH + пару папок. На Windows VDS ffmpeg
часто ставят через winget/choco/scoop, распаковывают рядом с ботом или
держат в Program Files\\ffmpeg\\bin — и музыка молча не играла («Нет
ffmpeg»), хотя бинарь на диске есть.

Теперь один детектор с широким списком мест:
  1) FFMPEG_BINARY из .env (файл или папка);
  2) системный PATH (ffmpeg / ffmpeg.exe);
  3) типичные места установки на Windows и Linux;
  4) копия рядом с ботом (./ffmpeg/bin, ./bin) — «скачал и положил».

Чистый модуль без discord — безопасно звать из main.py, кога и preflight.
"""

import os
import shutil

try:
    from logger import get_logger
    log = get_logger('ffmpeg_probe')
except Exception:                       # логгер опционален (чистый модуль)
    class _Log:
        def debug(self, *a, **k):
            pass
    log = _Log()

_EXE = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_candidates():
    """Путь из FFMPEG_BINARY (.env): может быть файлом или каталогом."""
    raw = os.environ.get('FFMPEG_BINARY')
    if not raw:
        return []
    p = raw.strip().strip('"').strip("'")
    if not p:
        return []
    out = []
    if os.path.isfile(p):
        out.append(p)
    if os.path.isdir(p):
        out.append(os.path.join(p, _EXE))
        out.append(os.path.join(p, 'bin', _EXE))
    # могли указать без .exe на Windows
    if os.name == 'nt' and not p.lower().endswith('.exe') and os.path.isfile(p + '.exe'):
        out.append(p + '.exe')
    return out


def _path_candidates():
    """ffmpeg в системном PATH."""
    out = []
    for name in ('ffmpeg', 'ffmpeg.exe'):
        try:
            w = shutil.which(name)
            if w:
                out.append(w)
        except Exception as _ex:
            log.debug('ffmpeg: which(%s): %s', name, _ex)
    return out


def _common_locations():
    """Типичные места установки (Windows + Linux)."""
    cands = []
    root = _repo_root()
    cwd = os.getcwd()

    # Рядом с ботом — «скачал и положил» (приоритет, не требует прав)
    for base in (cwd, root):
        cands.append(os.path.join(base, _EXE))
        cands.append(os.path.join(base, 'bin', _EXE))
        cands.append(os.path.join(base, 'ffmpeg', _EXE))
        cands.append(os.path.join(base, 'ffmpeg', 'bin', _EXE))

    if os.name == 'nt':
        # Переменные окружения Program Files / системный диск
        pf = os.environ.get('ProgramFiles', r'C:\Program Files')
        pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        local = os.environ.get('LOCALAPPDATA', '')
        progdata = os.environ.get('ProgramData', r'C:\ProgramData')
        sysdrv = os.environ.get('SystemDrive', 'C:') + os.sep
        userprof = os.environ.get('USERPROFILE', '')
        bases = [
            os.path.join(pf, 'ffmpeg'),
            os.path.join(pf86, 'ffmpeg'),
            r'C:\ffmpeg',
            os.path.join(sysdrv, 'ffmpeg'),
            # winget ставит сюда (ссылка в WindowsApps, но бинарь рядом)
            os.path.join(local, 'Microsoft', 'WinGet', 'Links') if local else '',
            # chocolatey
            os.path.join(progdata, 'chocolatey', 'bin'),
            # scoop
            os.path.join(userprof, 'scoop', 'shims') if userprof else '',
            os.path.join(userprof, 'scoop', 'apps', 'ffmpeg', 'current', 'bin') if userprof else '',
            # python встал в AppData — ffmpeg могли положить туда же
            os.path.join(local, 'Programs', 'Python') if local else '',
        ]
        for b in bases:
            if not b:
                continue
            cands.append(os.path.join(b, _EXE))
            cands.append(os.path.join(b, 'bin', _EXE))
    else:
        # Linux: пакетные менеджеры и ручная распаковка в /opt, /usr/local
        for b in ('/usr/bin', '/usr/local/bin', '/bin',
                  '/opt/ffmpeg/bin', '/opt/ffmpeg',
                  '/snap/bin', '/var/lib/flatpak/exports/bin'):
            cands.append(os.path.join(b, _EXE))
    return cands


def find_ffmpeg():
    """Вернуть путь к рабочему ffmpeg или None.

    Проверяем по очереди: .env → PATH → типичные места. Возвращаем
    первый реально существующий файл.
    """
    seen = set()
    for group in (_env_candidates(), _path_candidates(), _common_locations()):
        for c in group:
            if not c:
                continue
            c = os.path.abspath(c)
            if c in seen:
                continue
            seen.add(c)
            try:
                if os.path.isfile(c):
                    return c
            except OSError as _ex:
                log.debug('ffmpeg: проверка пути %s: %s', c, _ex)
                continue
    return None


if __name__ == '__main__':
    found = find_ffmpeg()
    print('ffmpeg:', found if found else 'НЕ НАЙДЕН')
