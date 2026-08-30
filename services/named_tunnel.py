"""Именованный Cloudflare-туннель (постоянный домен панели).

Появился как замена старого «случайного» quick-туннеля (trycloudflare URL
менялся каждый запуск). После scripts/setup_panel_tunnel.bat у панели есть
постоянный адрес (напр. https://hakumods.xyz). Этот модуль — чистая логика
без побочек, чтобы main.py был тонким, а тесты — простыми.
"""

import logging
import os

_log = logging.getLogger(__name__)

URL_FILE = 'tunnel_url.txt'
# Имя туннеля — то же, что в scripts/setup_panel_tunnel.bat.
TUNNEL_NAME = 'hakumo-panel'


def find_config(root):
    """Путь к config.yml именованного туннеля или None (ещё не настраивали)."""
    # Каноничное место — профиль пользователя (туда пишет setup батник),
    # scripts/ — запасной вариант «всё в одной папке».
    candidates = (
        os.path.join(os.path.expanduser('~'), '.cloudflared', 'config.yml'),
        os.path.join(root, 'scripts', 'config.yml'),
    )
    for path in candidates:
        try:
            if os.path.isfile(path):
                return path
        except Exception as _ex:
            _log.debug('named_tunnel.find_config(): подавлено: %s', _ex)
    return None


def public_url(cfg_path):
    """Первый hostname из config.yml -> 'https://host'. None, если не нашли."""
    try:
        with open(cfg_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                s = line.strip()
                if s.startswith('- hostname:'):
                    host = s.split(':', 1)[1].strip().strip('\'"')
                    if host:
                        return 'https://' + host
    except Exception as _ex:
        _log.debug('named_tunnel.public_url(): подавлено: %s', _ex)
    return None


def remember_url(root, url):
    """Записать постоянную ссылку — on_ready отправит её в канал панели."""
    try:
        with open(os.path.join(root, URL_FILE), 'w', encoding='utf-8') as fh:
            fh.write(url)
    except Exception as _ex:
        _log.debug('named_tunnel.remember_url(): подавлено: %s', _ex)


def drop_stale_url(root):
    """Убрать старую случайную ссылку, чтобы бот не постил её в Discord."""
    try:
        path = os.path.join(root, URL_FILE)
        if os.path.isfile(path):
            os.remove(path)
    except Exception as _ex:
        _log.debug('named_tunnel.drop_stale_url(): подавлено: %s', _ex)


RUNTIME_CONFIG = '.hakumo_tunnel_runtime.yml'
# до ребрендинга файл назывался aether — переносим, чтобы туннель на VDS
# не настраивался заново после обновления
_LEGACY_RUNTIME_CONFIG = '.aether_tunnel_runtime.yml'


def _migrate_legacy_runtime(scripts_dir):
    """Старый runtime-конфиг туннеля → новое имя (один раз, молча)."""
    try:
        old = os.path.join(scripts_dir, _LEGACY_RUNTIME_CONFIG)
        new = os.path.join(scripts_dir, RUNTIME_CONFIG)
        if os.path.isfile(old) and not os.path.exists(new):
            os.replace(old, new)
            _log.info('named_tunnel: перенёс %s → %s',
                      _LEGACY_RUNTIME_CONFIG, RUNTIME_CONFIG)
    except Exception as _ex:
        _log.debug('named_tunnel.migrate(): подавлено: %s', _ex)


def ensure_binary(scripts_dir):
    """Вернуть путь к cloudflared в scripts/, докачав при необходимости.

    Режим «только start.bat» (VDS): настраивать руками ничего не нужно —
    бинарник (~30 МБ) качается один раз сам и переиспользуется.
    """
    import platform
    import urllib.request

    is_win = platform.system().lower() == 'windows'
    name = 'cloudflared.exe' if is_win else 'cloudflared'
    path = os.path.join(scripts_dir, name)
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            return path
    except Exception as _ex:
        _log.debug('named_tunnel.ensure_binary(): stat подавлен: %s', _ex)

    url = ('https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
           if is_win else
           'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64')
    try:
        os.makedirs(scripts_dir, exist_ok=True)
        urllib.request.urlretrieve(url, path)
        if not is_win:
            os.chmod(path, 0o755)
        if os.path.isfile(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            return path
    except Exception as _ex:
        _log.debug('named_tunnel.ensure_binary(): скачивание подавлено: %s', _ex)
    # Битый/пустой файл не оставляем — следующий старт попробует снова.
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as _ex:
        _log.debug('named_tunnel.ensure_binary(): очистка подавлена: %s', _ex)
    return None


def runtime_config(root, cfg_path):
    """Конфиг для запуска с живым credentials-путём.

    После переезда на другой ПК/VDS путь внутри config.yml (профиль старой
    машины) мёртв. Тогда ищем credentials-файл рядом (scripts/<TID>.json или
    scripts/tunnel-creds.json) и пишем рантайм-копию конфига с абсолютным путём.
    Если записанный путь жив (та же машина) — конфиг не трогаем.
    """
    _migrate_legacy_runtime(root)
    try:
        with open(cfg_path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except Exception as _ex:
        _log.debug('named_tunnel.runtime_config(): чтение подавлено: %s', _ex)
        return cfg_path

    import re
    m_cred = re.search(r'(?m)^credentials-file:\s*(\S+)\s*$', text)
    if m_cred and os.path.isfile(m_cred.group(1).strip('\'"')):
        return cfg_path  # путь жив (та же машина) — без изменений

    scripts_dir = os.path.join(root, 'scripts')
    candidates = []
    m_tid = re.search(r'(?m)^tunnel:\s*(\S+)\s*$', text)
    if m_tid:
        candidates.append(os.path.join(scripts_dir, m_tid.group(1).strip('\'"') + '.json'))
    candidates.append(os.path.join(scripts_dir, 'tunnel-creds.json'))
    cred = next((c for c in candidates if os.path.isfile(c)), None)
    if not cred:
        return cfg_path  # нечего подставить — пусть cloudflared скажет сам

    if m_cred:
        text = text[:m_cred.start()] + 'credentials-file: ' + cred + text[m_cred.end():]
    else:
        text = text.rstrip('\n') + '\ncredentials-file: ' + cred + '\n'
    runtime_path = os.path.join(scripts_dir, RUNTIME_CONFIG)
    try:
        with open(runtime_path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return runtime_path
    except Exception as _ex:
        _log.debug('named_tunnel.runtime_config(): запись подавлена: %s', _ex)
        return cfg_path


def _cloudflared_home():
    """Папка профиля cloudflared (~/.cloudflared)."""
    return os.path.join(os.path.expanduser('~'), '.cloudflared')


def _run_cmd(cmd, timeout=120):
    """cloudflared <args> без всплывающего окна; None при любой ошибке запуска."""
    import subprocess as _sp

    try:
        flags = _sp.CREATE_NO_WINDOW if os.name == 'nt' and hasattr(_sp, 'CREATE_NO_WINDOW') else 0
        return _sp.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace', creationflags=flags)
    except Exception as _ex:
        _log.debug('named_tunnel._run_cmd(): подавлено: %s', _ex)
        return None


def _rewrite_config(path, tid, creds_path):
    """Подменить tunnel:/credentials-file: на свежие (in-place)."""
    import re

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except Exception as _ex:
        _log.debug('named_tunnel._rewrite_config(): чтение подавлено: %s', _ex)
        return
    if re.search(r'(?m)^tunnel:\s*\S+\s*$', text):
        text = re.sub(r'(?m)^tunnel:\s*\S+\s*$', 'tunnel: ' + tid, text)
    else:
        text = 'tunnel: ' + tid + '\n' + text
    if re.search(r'(?m)^credentials-file:\s*\S+\s*$', text):
        text = re.sub(r'(?m)^credentials-file:\s*\S+\s*$',
                      'credentials-file: ' + creds_path, text)
    else:
        text = text.rstrip('\n') + '\ncredentials-file: ' + creds_path + '\n'
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
    except Exception as _ex:
        _log.debug('named_tunnel._rewrite_config(): запись подавлена: %s', _ex)


def ensure_credentials(root, scripts_dir, exe):
    """Ключ туннеля (credentials json) живой на ЭТОЙ машине — или None.

    Ключ рождается один раз — на ПК, где делали login + tunnel create.
    После переезда на VDS его на машине нет. Тогда:
      1. поднимаем из портативных копий в scripts/ (приехали вместе с папкой);
      2. если и их нет, но есть cert.pem (логин здесь уже делался) —
         пересоздаём туннель: delete + create с тем же именем + перепривязка
         DNS-хостов из конфига; конфиги патчим на новый ID.
    Возвращает (tunnel_id, путь_к_ключу), когда пришлось чинить,
    и None — когда чинить нечего (ключ на месте) или нечем (нет cert.pem).
    """
    import re
    import shutil as _sh

    home = _cloudflared_home()
    candidates = [os.path.join(home, 'config.yml'),
                  os.path.join(root, 'scripts', 'config.yml')]
    paths = [p for p in candidates if os.path.isfile(p)]
    if not paths:
        return None
    try:
        with open(paths[0], 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except Exception as _ex:
        _log.debug('named_tunnel.ensure_credentials(): чтение подавлено: %s', _ex)
        return None
    m = re.search(r'(?m)^tunnel:\s*(\S+)\s*$', text)
    if not m:
        return None
    tid = m.group(1).strip('\'"')

    creds = os.path.join(home, tid + '.json')
    if os.path.isfile(creds):
        return None  # ключ на месте — ничего не сломано

    healed = None

    # 1) Портативные копии рядом с ботом (залиты на VDS вместе с папкой)
    for cand in (os.path.join(scripts_dir, tid + '.json'),
                 os.path.join(scripts_dir, 'tunnel-creds.json')):
        if os.path.isfile(cand):
            try:
                os.makedirs(home, exist_ok=True)
                _sh.copy2(cand, creds)
                _log.info('named_tunnel: ключ туннеля поднят из scripts/ (%s)',
                          os.path.basename(cand))
                healed = (tid, creds)
                break
            except Exception as _ex:
                _log.debug('named_tunnel.ensure_credentials(): копия подавлена: %s', _ex)

    # 2) Полная пересборка на новой машине — достаточно cert.pem от логина
    if healed is None:
        if not os.path.isfile(os.path.join(home, 'cert.pem')):
            return None  # нечем чинить — ошибку покажет сам cloudflared
        _log.info('named_tunnel: ключа нет — пересоздаю туннель %s на этой машине',
                  TUNNEL_NAME)
        _run_cmd([exe, 'tunnel', 'delete', '-f', tid], timeout=180)
        res = _run_cmd([exe, 'tunnel', 'create', TUNNEL_NAME], timeout=180)
        out = ((res.stdout or '') + '\n' + (res.stderr or '')) if res else ''
        m2 = re.search(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})', out)
        new_tid = m2.group(1) if m2 else None
        new_creds = os.path.join(home, new_tid + '.json') if new_tid else None
        if not new_tid or not os.path.isfile(new_creds):
            _log.warning('named_tunnel: пересоздание не удалось — нет ключа после create')
            return None
        hosts = [h.strip('\'"') for h in
                 re.findall(r'(?m)^\s*-\s*hostname:\s*(\S+)\s*$', text)]
        for host in hosts:
            if host:
                _run_cmd([exe, 'tunnel', 'route', 'dns', '--overwrite-dns', new_tid, host],
                         timeout=180)
        for p in paths:
            _rewrite_config(p, new_tid, new_creds)
        # Свежий ключ сразу в портативные копии — следующий переезд уже с ключом.
        try:
            _sh.copy2(new_creds, os.path.join(scripts_dir, 'tunnel-creds.json'))
        except Exception as _ex:
            _log.debug('named_tunnel.ensure_credentials(): экспорт ключа подавлен: %s', _ex)
        _log.info('named_tunnel: туннель пересоздан, домены перепривязаны (%s шт.)', len(hosts))
        healed = (new_tid, new_creds)

    _sync_service_profile(*healed)
    return healed


def _sync_service_profile(tid, creds_path):
    """Профиль службы Windows (systemprofile): ключ + конфиг тоже живые.

    Службу ставит setup-батник; при пересоздании туннеля её копии протухают —
    после перезагрузки VDS служба бы упала. Синхронизируем молча.
    """
    import shutil as _sh

    if os.name != 'nt':
        return
    try:
        sysdir = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                              'System32', 'config', 'systemprofile', '.cloudflared')
        if not os.path.isdir(sysdir):
            return
        sys_creds = os.path.join(sysdir, tid + '.json')
        _sh.copy2(creds_path, sys_creds)
        sys_cfg = os.path.join(sysdir, 'config.yml')
        if os.path.isfile(sys_cfg):
            _rewrite_config(sys_cfg, tid, sys_creds)
    except Exception as _ex:
        _log.debug('named_tunnel._sync_service_profile(): подавлено: %s', _ex)


def export_portable(root, cfg_path):
    """Портативные копии конфига и ключа туннеля в scripts/ (ID-заказ VDS).

    Если они настроены батником в профиль пользователя, хозяин папки получит
    scripts/config.yml + scripts/tunnel-creds.json и зальёт весь кейс на VDS
    «как есть» — запуск сделает только start.bat. Тихо, никаких падений.
    """
    import re
    import shutil as _sh

    try:
        scripts_dir = os.path.join(root, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(cfg_path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
        dst_cfg = os.path.join(scripts_dir, 'config.yml')
        if os.path.abspath(cfg_path) != os.path.abspath(dst_cfg) \
                and not os.path.isfile(dst_cfg):
            with open(dst_cfg, 'w', encoding='utf-8') as fh:
                fh.write(text)
        creds_src = None
        m = re.search(r'(?m)^credentials-file:\s*(\S+)\s*$', text)
        if m:
            cand = m.group(1).strip('\'"')
            if os.path.isfile(cand):
                creds_src = cand
        dst_creds = os.path.join(scripts_dir, 'tunnel-creds.json')
        if creds_src and not os.path.isfile(dst_creds):
            _sh.copy2(creds_src, dst_creds)
    except Exception as _ex:
        _log.debug('named_tunnel.export_portable(): подавлено: %s', _ex)


def heal_localhost_origins(cfg_path):
    """localhost → 127.0.0.1 в service:-строках конфига туннеля.

    На Windows VDS «localhost» часто резолвится в ::1 (IPv6), а панель
    слушает 0.0.0.0 — только IPv4. cloudflared тогда ловит
    «dial tcp [::1]:5001: connectex: connection refused» и домен лежит,
    хотя панель жива. Явный 127.0.0.1 в origin убирает этот класс
    ошибок полностью. Возвращает True, если файл переписали.
    """
    import re

    try:
        with open(cfg_path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except Exception as _ex:
        _log.debug('named_tunnel.heal_localhost_origins(): чтение подавлено: %s', _ex)
        return False
    # Только http://localhost:ПОРТ в ingress-строках; https и другие
    # хосты не трогаем (http_status:404 и прочее остаются как есть).
    healed_text = re.sub(
        r'(?m)^(\s*-?\s*service:\s*http://)localhost(:\d+\s*)$',
        lambda m: m.group(1) + '127.0.0.1' + m.group(2),
        text)
    if healed_text == text:
        return False
    try:
        with open(cfg_path, 'w', encoding='utf-8') as fh:
            fh.write(healed_text)
        _log.info('named_tunnel: origin localhost -> 127.0.0.1 в %s', cfg_path)
        return True
    except Exception as _ex:
        _log.debug('named_tunnel.heal_localhost_origins(): запись подавлена: %s', _ex)
        return False


def _all_config_copies(root, cfg_path=None):
    """Все места, где может лежать конфиг туннеля на этой машине.

    Конфиг живёт в трёх местах: профиль пользователя (~/.cloudflared),
    портативная копия в scripts/ и профиль службы Windows (systemprofile).
    """
    candidates = [
        cfg_path,
        os.path.join(_cloudflared_home(), 'config.yml'),
        os.path.join(root, 'scripts', 'config.yml'),
        os.path.join(root, 'scripts', RUNTIME_CONFIG),
    ]
    if os.name == 'nt':
        sysdir = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                              'System32', 'config', 'systemprofile', '.cloudflared')
        candidates.append(os.path.join(sysdir, 'config.yml'))
    return [p for p in candidates if p]


def heal_all_origins(root, cfg_path=None):
    """Починить origin во ВСЕХ копиях конфига туннеля на этой машине.

    Чиним всё, что нашли, — какая копия ни заработала, origin будет верный.
    Возвращает список переписанных путей (может быть пустым).
    """
    healed = []
    for path in _all_config_copies(root, cfg_path):
        try:
            if os.path.isfile(path) and heal_localhost_origins(path):
                healed.append(path)
        except Exception as _ex:
            _log.debug('named_tunnel.heal_all_origins(): подавлено: %s', _ex)
    return healed


def ensure_protocol_line(root, cfg_path, proto='http2'):
    """Прописать top-level `protocol:` во все копии конфига туннеля.

    cloudflared по умолчанию соединяется с Cloudflare по QUIC (UDP). На части
    VDS UDP-путь до края нестабилен: туннель рвётся каждые ~20 секунд
    («timeout: no recent network activity», «failed to run the datagram
    handler»), перерегистрируется и домен флапает. `protocol: http2`
    переводит соединение на TCP — стабильно на любой сети. Служба Windows
    флага командной строки не получает, поэтому протокол пишем прямо
    в конфиг. Уже существующую строку protocol: не трогаем — это осознанная
    настройка. Возвращает список переписанных путей (может быть пустым).
    """
    import re

    if proto not in ('http2', 'quic', 'auto'):
        _log.debug('named_tunnel.ensure_protocol_line(): неизвестный протокол %r', proto)
        return []
    touched = []
    for path in _all_config_copies(root, cfg_path):
        try:
            if not os.path.isfile(path):
                continue
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                text = fh.read()
            if re.search(r'(?m)^protocol:\s*\S+', text):
                continue  # протокол уже задан вручную — не трогаем
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(f'protocol: {proto}\n' + text)
            touched.append(path)
        except Exception as _ex:
            _log.debug('named_tunnel.ensure_protocol_line(): подавлено: %s', _ex)
    return touched
