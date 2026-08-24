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
