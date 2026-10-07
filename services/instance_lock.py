# -*- coding: utf-8 -*-
"""Защита от двойного запуска бота с одним токеном/ключом.

Lock-файл data/.bot_lock_<name> содержит PID. Если процесс жив —
второй экземпляр не стартует. Мёртвый PID — перезаписываем.
"""
from __future__ import annotations

import atexit
import os
import sys

from logger import get_logger

_log = get_logger('instance_lock')
_HELD: dict[str, str] = {}


def _lock_path(name: str) -> str:
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in (name or 'bot'))
    base = os.path.join('data')
    try:
        from config import Config
        base = Config.DATA_DIR
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f'.bot_lock_{safe}')


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # процесс есть, но нет прав слать сигнал — считаем живым
        return True
    except Exception:
        return False
    # Windows: os.kill(pid, 0) может не отличать; доп. проверка через psutil
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return True


def acquire(name: str, *, force: bool = False) -> bool:
    """Захватить lock. False = другой экземпляр уже бежит."""
    path = _lock_path(name)
    my_pid = os.getpid()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                old = int((f.read() or '0').strip() or 0)
        except Exception:
            old = 0
        if old and old != my_pid and _pid_alive(old):
            if not force:
                _log.error(
                    'ДВОЙНОЙ ЗАПУСК: %s уже работает (PID %s). '
                    'Этот процесс (PID %s) останавливается. '
                    'Оставь один экземпляр на токен.',
                    name, old, my_pid)
                print(
                    f'[LOCK] {name}: уже запущен PID {old} — '
                    f'второй экземпляр (PID {my_pid}) не стартует.',
                    file=sys.stderr)
                return False
            _log.warning('instance_lock force: убиваем старый PID %s', old)
            try:
                os.kill(old, 9)
            except Exception as ex:
                _log.debug('kill old: %s', ex)
        else:
            _log.info('instance_lock: снимаем мёртвый lock PID %s', old)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(str(my_pid))
        _HELD[name] = path
        atexit.register(release, name)
        _log.info('instance_lock acquired %s PID=%s path=%s', name, my_pid, path)
        return True
    except Exception as ex:
        _log.error('instance_lock acquire failed: %s', ex)
        return False


def release(name: str) -> None:
    path = _HELD.pop(name, None) or _lock_path(name)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                pid = int((f.read() or '0').strip() or 0)
            if pid == os.getpid() or not _pid_alive(pid):
                os.remove(path)
                _log.info('instance_lock released %s', name)
    except Exception as ex:
        _log.debug('instance_lock release: %s', ex)
