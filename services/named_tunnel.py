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


RUNTIME_CONFIG = '.aether_tunnel_runtime.yml'


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
