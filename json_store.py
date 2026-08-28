"""json_store — единое JSON-хранилище бота с кешем чтения.

Зачем: раньше 20+ когов таскали свои копипасты ``_load``/``_save``,
и конфиги/XP перечитывались с диска на КАЖДОЕ сообщение (health, leveling,
sticky-заметки, реакции модкита). Теперь всё идёт через этот модуль:

* ``load_json``  — чтение с кешем по (mtime_ns, size): файл не менялся —
  диск вообще не трогаем. Возвращается глубокая копия, мутировать можно.
* ``save_json``  — атомарная запись (tmp + os.replace), кеш обновляется
  сразу, следующее чтение — попадание.
* Потокобезопасно (Flask-панель живёт в своих потоках), а mtime/size-ключ
  подхватывает и правки «со стороны» — например, панель перезаписала
  конфиг, бот увидит это на следующем обращении.
"""

import json
import os
import threading
from copy import deepcopy

from logger import get_logger

_log = get_logger("json_store")

_LOCK = threading.RLock()
_CACHE = {}  # {abs_path: ((mtime_ns, size) | None, сырое содержимое файла | None)}


def _abs(path) -> str:
    return os.path.abspath(os.fspath(path))


def _stat_key(path: str):
    """Ключ свежести файла: (mtime в нс, размер). None — файла нет."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def load_json(path, default=None, *, log=None):
    """Прочитать JSON-файл с кешем. Всегда возвращает глубокую копию —
    результат можно свободно мутировать, кеш не пострадает.

    Файл отсутствует, битый, пустой (falsy) или тип не совпал с типом
    ``default`` — вернётся копия ``default`` (и залогируется, если файл
    был именно битый). В кеше лежит сырое содержимое файла, поэтому
    один и тот же путь могут читать с разными дефолтами — не отравится.
    """
    lg = log or _log
    key = _abs(path)
    sk = _stat_key(key)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == sk:
        raw = hit[1]
    else:
        raw = None
        if sk is not None:
            try:
                with open(key, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                lg.warning("json_store: битый JSON %s (%s) — берём дефолт", path, e)
                raw = None
        with _LOCK:
            _CACHE[key] = (sk, raw)
    if not raw or (default is not None and not isinstance(raw, type(default))):
        return deepcopy(default)
    return deepcopy(raw)


def save_json(path, data, *, indent=2, log=None) -> bool:
    """Атомарно записать JSON (через .tmp + os.replace — ни одного
    полу-записанного файла при падении) и сразу обновить кеш.
    Возвращает True/False."""
    lg = log or _log
    key = _abs(path)
    try:
        d = os.path.dirname(key)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = key + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp, key)
    except Exception as e:
        lg.warning("json_store: не записался %s: %s", path, e)
        return False
    with _LOCK:
        _CACHE[key] = (_stat_key(key), deepcopy(data))
    return True


def invalidate(path):
    """Выбросить файл из кеша (если кто-то перезаписал его в обход стора
    без смены mtime/size — редкий ручной случай)."""
    with _LOCK:
        _CACHE.pop(_abs(path), None)


def clear_cache():
    """Полностью очистить кеш (для тестов/диагностики)."""
    with _LOCK:
        _CACHE.clear()


def cache_stats() -> dict:
    """Снимок состояния кеша для тестов и диагностики."""
    with _LOCK:
        return {"entries": len(_CACHE), "paths": sorted(_CACHE)}
