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


async def _verify_menu(bot):
    """(ok, текст) — сверка РЕАЛЬНЫХ списков Discord с кураторским набором.

    Ищем ровно то, на что жаловался владелец 30.08 («команды не удалились,
    дубли есть»): старые хвосты на сервере (имена вне KEEP_SLASH) и
    гильдейские КОПИИ глобальных команд (второй источник дублей).
    """
    import discord
    from slash_budget import KEEP_SLASH
    try:
        from config import Config
        targets = [int(getattr(g, 'id', 0) or 0)
                   for g in Config.guild_objects()]
    except Exception as ex:
        _logger().debug('menu_mode: guild_objects(): %s', ex)
        targets = []
    keep = set(KEEP_SLASH)
    try:
        keep_global = {getattr(c, 'name', '')
                       for c in bot.tree.get_commands()
                       if bool((getattr(c, 'extras', None) or {}).get('keep_global'))}
    except Exception as ex:
        _logger().debug('menu_mode: keep_global: %s', ex)
        keep_global = set()
    problems = []

    def _chat_names(cmds):
        # только слеш-команды (контекстные меню — отдельный разговор
        # и отдельный лимит Discord); type — enum AppCommandType
        from discord import AppCommandType
        return {getattr(c, 'name', '') for c in cmds
                if getattr(c, 'type', None) in (None, AppCommandType.chat_input)}

    try:
        glob_names = _chat_names(await bot.tree.fetch_commands())
        bad = sorted(glob_names - keep)
        if bad:
            problems.append('глобально лишние: ' + ', '.join(bad))
    except Exception as ex:
        problems.append(f'глобальный список не прочитан: {ex}')

    for gid in targets:
        if not gid:
            continue
        try:
            names = _chat_names(await bot.tree.fetch_commands(
                guild=discord.Object(id=gid)))
        except Exception as ex:
            problems.append(f'сервер {gid}: список не прочитан: {ex}')
            continue
        bad = sorted(names - keep)
        if bad:
            problems.append(f'сервер {gid}: лишние — ' + ', '.join(bad))
        dupes = sorted(names & keep_global)
        if dupes:
            problems.append(f'сервер {gid}: дубли глобальных — ' + ', '.join(dupes))
    return (not problems, '; '.join(problems) or 'меню чистое, дублей нет')


def _note_verify(bot, verdict):
    """Дописать итог сверки в data/sync_last.json (панель показывает)."""
    import json as _json
    import os as _os
    for base in (getattr(bot, 'base_dir', None), _os.getcwd()):
        if not base:
            continue
        path = _os.path.join(base, 'data', 'sync_last.json')
        try:
            data = {}
            if _os.path.exists(path):
                with open(path, encoding='utf-8') as fh:
                    data = _json.load(fh)
            if not isinstance(data, dict):
                data = {}
            data['verify'] = str(verdict)[:400]
            _os.makedirs(_os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                _json.dump(data, fh, ensure_ascii=False)
            return
        except Exception as ex:
            _logger().debug('menu_mode: note_verify(%s): %s', base, ex)


async def apply_to_bot(bot):
    """Применить режим К ЖИВОМУ боту: почистить дерево бюджетом,
    пересинхронизировать Discord и СВЕРИТЬ результат с реальностью.

    Кураторский режим применяется сразу и без перезапуска: лишние команды
    уходят из дерева (остаются на префиксе «!»), guild-синк затирает
    списки серверов — меню сжимается до 7. Полный режим живого пути не
    имеет (команды сверх кураторских выгружаются при загрузке когов) —
    панели остаётся подсказать про перезапуск.

    После синка читаем списки команд ИЗ Discord: найдены старые хвосты
    или дубли — один повторный синк, затем итог сверки пишется в
    data/sync_last.json (поле verify — панель показывает честный итог,
    а не слепое «синк запущен»).

    Возвращает (ok, kept, pruned) — имена оставленных/убранных из меню.
    """
    tree = getattr(bot, 'tree', None)
    if tree is None:
        return False, [], []
    from slash_budget import apply_slash_budget
    from services.sync_filtered import full_sync
    kept, pruned = apply_slash_budget(tree)
    await full_sync(bot)
    ok, details = await _verify_menu(bot)
    if not ok:
        _logger().warning('menu_mode: сверка нашла расхождения (%s) — '
                          'повторный синк', details)
        await full_sync(bot)
        ok, details = await _verify_menu(bot)
    _note_verify(bot, ('ок: ' + details) if ok else ('РАСХОЖДЕНИЯ: ' + details))
    _logger().info('menu_mode: режим применён к живому боту — в меню %d '
                   'команд, убрано %d; сверка: %s',
                   len(kept), len(pruned), 'ок' if ok else 'расхождения')
    return True, kept, pruned
