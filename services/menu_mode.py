# -*- coding: utf-8 -*-
"""Режим слеш-меню Discord: кураторский (7 команд) или полный (BOT_FULL).

Заказ 30.08 «давай удалим все команды, оставим только это»: владелец
хочет компактное меню из 7 кураторских команд, но .env на его машине
держит BOT_FULL=1 (прошлая настройка «покажи всё»). Править .env из
панели нельзя — поэтому режим живёт в data/menu_mode.json и
переключается кнопкой на странице «Команды».

Приоритет при чтении: тумблер панели (файл) → BOT_FULL из .env.
Файла нет — поведение ровно как раньше, .env решает сам: ни у кого
ничего не меняется при обновлении.
"""
import json
import logging
import os
import threading

_PATH = 'data/menu_mode.json'
_lock = threading.Lock()
_log = None


def _logger():
    global _log
    if _log is None:
        _log = logging.getLogger('menu_mode')
        _log.addHandler(logging.NullHandler())
    return _log


_TRUE = ('1', 'true', 'yes', 'on')


def _read():
    """Режим из data/menu_mode.json (True/False) или None — файла нет."""
    if not os.path.exists(_PATH):
        return None
    try:
        with open(_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get('full'), bool):
            return data['full']
        _logger().warning('menu_mode: %s непонятного вида — режим беру из '
                          '.env (BOT_FULL)', _PATH)
    except (OSError, json.JSONDecodeError) as ex:
        _logger().warning('menu_mode: прочитать %s не вышло (%s) — режим '
                          'беру из .env (BOT_FULL)', _PATH, ex)
    return None


def is_full(environ=None):
    """Полное ли меню. Приоритет: тумблер панели → BOT_FULL из .env."""
    override = _read()
    if override is not None:
        return override
    env = os.environ if environ is None else environ
    return str(env.get('BOT_FULL', '') or '').strip().lower() in _TRUE


def set_full(value):
    """Записать режим тумблером панели. Возвращает действующий режим."""
    with _lock:
        try:
            os.makedirs(os.path.dirname(_PATH) or '.', exist_ok=True)
            tmp = _PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'full': bool(value)}, fh, ensure_ascii=False)
            os.replace(tmp, _PATH)
        except OSError as ex:
            _logger().warning('menu_mode: записать %s не вышло: %s', _PATH, ex)
    return is_full()


async def apply_to_bot(bot):
    """Применить режим К ЖИВОМУ боту: почистить дерево бюджетом и
    пересинхронизировать Discord.

    Кураторский режим применяется сразу и без перезапуска: лишние команды
    уходят из дерева (остаются на префиксе «!»), guild-синк затирает
    списки серверов — меню сжимается до 7. Полный режим живого пути не
    имеет (команды сверх кураторских выгружаются при загрузке когов) —
    панели остаётся подсказать про перезапуск.

    Возвращает (ok, kept, pruned) — имена оставленных/убранных из меню.
    """
    tree = getattr(bot, 'tree', None)
    if tree is None:
        return False, [], []
    from slash_budget import apply_slash_budget
    from services.sync_filtered import full_sync
    kept, pruned = apply_slash_budget(tree)
    await full_sync(bot)
    _logger().info('menu_mode: режим применён к живому боту — в меню %d '
                   'команд, убрано %d', len(kept), len(pruned))
    return True, kept, pruned
