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


# ──────────────────────────────────────────────────────────────────────────
# Автоматическая установка (если ffmpeg не нашёлся)
#
# Раньше скачивание было только в scripts/ensure_ffmpeg.bat, который зовут
# start.bat/start_bot.bat. Если бот запущен иначе (python main.py, служба,
# другой лаунчер) — ffmpeg не ставился и музыка молча не играла. Теперь
# бот сам докачивает статический билд в ./bin при старте (фоновый поток) и
# при первом /play. Стандартная библиотека + urllib, без сторонних пакетов.
# ──────────────────────────────────────────────────────────────────────────
import threading
import time
import zipfile
import tarfile
import urllib.request
import shutil as _shutil

# Статические билды (без установщика, просто распаковать).
_URL_WIN = ('https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/'
            'ffmpeg-master-latest-win64-gpl.zip')
_URL_WIN_GYAN = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
_URL_LINUX = ('https://johnvansickle.com/ffmpeg/releases/'
              'ffmpeg-release-amd64-static.tar.xz')

_install_lock = threading.Lock()
_install_state = {'done': False, 'running': False, 'ok': False, 'path': None}


def _bin_dir():
    return os.path.join(_repo_root(), 'bin')


def _download(url, dest, timeout=60):
    """Скачать url → dest (бинарно). Бросает исключение при ошибке."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, 'wb') as out:
        _shutil.copyfileobj(resp, out, length=1024 * 256)


def _extract_ffmpeg(archive, bin_dir, is_windows):
    """Достать ffmpeg(.exe) (и ffprobe) из архива прямо в bin_dir."""
    os.makedirs(bin_dir, exist_ok=True)
    target = 'ffmpeg.exe' if is_windows else 'ffmpeg'
    if is_windows:
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                base = name.replace('\\', '/').split('/')[-1].lower()
                if base in ('ffmpeg.exe', 'ffprobe.exe'):
                    with z.open(name) as src, open(os.path.join(bin_dir, base), 'wb') as dst:
                        _shutil.copyfileobj(src, dst)
    else:
        with tarfile.open(archive, 'r:*') as t:
            for member in t.getmembers():
                if not member.isfile():
                    continue
                base = os.path.basename(member.name)
                if base in ('ffmpeg', 'ffprobe'):
                    src = t.extractfile(member)
                    if src is None:
                        continue
                    with src, open(os.path.join(bin_dir, base), 'wb') as dst:
                        _shutil.copyfileobj(src, dst)
    out = os.path.join(bin_dir, target)
    if not os.path.isfile(out):
        raise RuntimeError('ffmpeg не найден внутри скачанного архива')
    if not is_windows:
        try:
            os.chmod(out, 0o755)
            fp = os.path.join(bin_dir, 'ffprobe')
            if os.path.isfile(fp):
                os.chmod(fp, 0o755)
        except OSError:
            pass
    return out


def _install_blocking():
    """Скачать и распаковать ffmpeg в ./bin. Вернуть путь или None."""
    is_windows = os.name == 'nt'
    bin_dir = _bin_dir()
    os.makedirs(bin_dir, exist_ok=True)
    ext = '.zip' if is_windows else '.tar.xz'
    archive = os.path.join(bin_dir, 'ffmpeg_dl' + ext)
    urls = ([_URL_WIN, _URL_WIN_GYAN] if is_windows else [_URL_LINUX])
    last_err = None
    for url in urls:
        try:
            log.debug('ffmpeg: скачиваю %s', url)
            _download(url, archive)
            path = _extract_ffmpeg(archive, bin_dir, is_windows)
            try:
                if os.path.exists(archive):
                    os.remove(archive)
            except OSError:
                pass
            log.debug('ffmpeg: установлен в %s', path)
            return os.path.abspath(path)
        except Exception as ex:                       # noqa: BLE001
            last_err = ex
            log.debug('ffmpeg: источник %s не сработал: %s', url, ex)
            try:
                if os.path.exists(archive):
                    os.remove(archive)
            except OSError:
                pass
            continue
    log.warning('ffmpeg: автоустановка не удалась: %s', last_err)
    return None


def ensure_ffmpeg(blocking=False):
    """Гарантировать ffmpeg: если он есть — вернуть путь; иначе скачать.

    blocking=False (по умолчанию) — ставит в фоновом потоке и сразу
    возвращает текущий find_ffmpeg() (None, если ещё качается). Вызывать
    при старте, чтобы не тормозить вход бота в Discord.
    blocking=True — дождаться установки (для /play: пользователь и так
    ждёт трек); вернуть путь или None.
    """
    found = find_ffmpeg()
    if found:
        with _install_lock:
            _install_state.update(done=True, ok=True, path=found)
        return found

    with _install_lock:
        if _install_state['done']:
            # Уже пробовали и не вышло — не долбим сеть на каждый /play.
            return _install_state.get('path')
        if _install_state['running']:
            # Установка уже идёт (фоновый поток). В нефорсированном режиме
            # сразу выходим; в blocking — подождём её ниже по статусу.
            if not blocking:
                return None

    if blocking:
        # Если в фоне уже качает другой поток — дождемся завершения по статусу,
        # не запуская второе скачивание.
        while True:
            with _install_lock:
                st = dict(_install_state)
            if st.get('done'):
                return st.get('path')
            if not st.get('running'):
                break   # никто не ставит и не done — ставим сами
            time.sleep(0.5)
        # Синхронная установка (мы вне event-loop — вызывается из to_thread).
        path = _install_blocking()
        with _install_lock:
            _install_state.update(done=True, ok=bool(path), path=path, running=False)
        return path

    # Фоновая установка: помечаем running и отпускаем лок ДО скачивания,
    # чтобы install_status()/повторные вызовы не ждали сеть.
    with _install_lock:
        if _install_state['running'] or _install_state['done']:
            return None
        _install_state['running'] = True

    def _worker():
        path = _install_blocking()
        with _install_lock:
            _install_state['running'] = False
            _install_state['done'] = True
            _install_state['ok'] = bool(path)
            _install_state['path'] = path

    threading.Thread(target=_worker, name='ffmpeg-install', daemon=True).start()
    return None


def install_status():
    """Словарь состояния установки (для диагностики/панели)."""
    with _install_lock:
        return dict(_install_state)


if __name__ == '__main__':
    found = find_ffmpeg()
    if found:
        print('ffmpeg:', found)
    else:
        print('ffmpeg не найден — ставлю...')
        print('ffmpeg:', ensure_ffmpeg(blocking=True) or 'НЕ УДАЛОСЬ УСТАНОВИТЬ')
