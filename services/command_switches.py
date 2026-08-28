# -*- coding: utf-8 -*-
"""Вкл/выкл команд владельцем из панели (заказ 2026-08-25).

Каждой командой можно пользоваться — или отключить её. Отключённая
команда:
- мгновенно перестаёт отвечать (prefix и slash-чеки в main.py);
- исчезает из slash-меню Discord: команда УБИРАЕТСЯ из дерева и дерево
  пересинхронизируется (объект команды «паркуется», чтобы вернуть
  одним кликом без перезагрузки бота);
- в каталоге панели остаётся видимой, но приглушённой с бейджем
  «выключена» — чтобы её можно было включить обратно.

Хранилище: data/command_switches.json, имена нормализуются
(регистр и _/- эквивалентны) — рассинхрона между /mod_panel,
modpanel и ModPanel не бывает.
"""
import asyncio
import json
import os
import threading

_PATH = 'data/command_switches.json'
_lock = threading.Lock()
_log = None


def _logger():
    global _log
    if _log is None:
        import logging
        _log = logging.getLogger('command_switches')
        _log.addHandler(logging.NullHandler())
    return _log


def normalize(name):
    """Единый вид имени: нижний регистр, _ -> - (mod_panel == mod-panel)."""
    return str(name or '').strip().lower().replace('_', '-')


def _read():
    if not os.path.exists(_PATH):
        return {}
    try:
        with open(_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as ex:
        _logger().debug('command_switches: читать не вышло: %s', ex)
        return {}


def _write(data):
    tmp = _PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, _PATH)


def disabled_set():
    """Множество выключенных команд (нормализованные имена)."""
    with _lock:
        vals = _read().get('disabled') or []
    return {normalize(v) for v in vals if str(v or '').strip()}


def is_disabled(name):
    return normalize(name) in disabled_set()


def set_disabled(name, off):
    """Выключить/включить команду. Возвращает новое множество выключенных."""
    key = normalize(name)
    if not key:
        return disabled_set()
    with _lock:
        data = _read()
        cur = {normalize(v) for v in (data.get('disabled') or [])}
        (cur.add if off else cur.discard)(key)
        data['disabled'] = sorted(cur)
        try:
            _write(data)
        except OSError as ex:
            _logger().warning('command_switches: запись не удалась: %s', ex)
    return {normalize(v) for v in _read().get('disabled') or []}


def set_disabled_bulk(names, off):
    """Вкл/выкл сразу много команд — одна запись, один resync бота.
    Возвращает новое множество выключенных."""
    keys = {normalize(n) for n in names if normalize(n)}
    if not keys:
        return disabled_set()
    with _lock:
        data = _read()
        cur = {normalize(v) for v in (data.get('disabled') or [])}
        if off:
            cur |= keys
        else:
            cur -= keys
        data['disabled'] = sorted(cur)
        try:
            _write(data)
        except OSError as ex:
            _logger().warning('command_switches: запись не удалась: %s', ex)
    return {normalize(v) for v in _read().get('disabled') or []}


# ── применение к живому боту ────────────────────────────────────────────
def apply_to_bot(bot):
    """Синхронно применить выключенные к дереву команд (без sync).

    Убирает выключенные команды из дерева (паркуя их на bot-е, чтобы
    вернуть без перезагрузки) и возвращает включённые из парковки.
    Возвращает (hidden, restored) — списки имён. Вызывать в цикле бота.
    """
    tree = getattr(bot, 'tree', None)
    if tree is None:
        return [], []
    parked = getattr(bot, '_hakumo_parked_commands', None)
    if parked is None:
        parked = {}
        bot._hakumo_parked_commands = parked
    off = disabled_set()
    hidden, restored = [], []

    def _names(cmd):
        base = getattr(cmd, 'name', '') or ''
        qual = getattr(cmd, 'qualified_name', base) or base
        return {normalize(base), normalize(qual)}

    for cmd in list(tree.get_commands()):
        if _names(cmd) & off:
            name = getattr(cmd, 'name', '') or ''
            try:
                tree.remove_command(name)
                parked[normalize(name)] = cmd
                hidden.append(name)
            except (TypeError, ValueError) as ex:
                _logger().debug('command_switches: снять %s: %s', name, ex)

    for key, cmd in list(parked.items()):
        if key not in off:
            try:
                tree.add_command(cmd)
                del parked[key]
                restored.append(getattr(cmd, 'name', key))
            except Exception as ex:      # уже зарегистрирована и т.п.
                _logger().debug('command_switches: вернуть %s: %s', key, ex)
    return hidden, restored


async def resync(bot, debounce=1.2):
    """Применить переключения и пересинхронизировать slash-меню Discord.

    Небольшой debounce: владелец щёлкает несколько тумблеров подряд —
    синк уходит один, после паузы. Пока идёт debounce, повторный вызов
    продлевает окно.
    """
    import time
    tree = getattr(bot, 'tree', None)
    if tree is None:
        return False, [], []
    loop = getattr(bot, 'loop', None) or asyncio.get_running_loop()
    until = loop.time() + debounce
    setattr(bot, '_hakumo_switch_sync_until', until)
    while loop.time() < getattr(bot, '_hakumo_switch_sync_until', 0):
        await asyncio.sleep(0.25)
        if getattr(bot, '_hakumo_switch_sync_until', 0) > until:
            until = getattr(bot, '_hakumo_switch_sync_until', 0)
    # Полный синк через guild-команды: выключенные мгновенно ИСЧЕЗАЮТ
    # из списка «/» Discord (а не отвечают «выключена» после ввода).
    try:
        from services.sync_filtered import full_sync
        await full_sync(bot)
        _logger().info('command_switches: полный sync применён')
        return True, [], []
    except Exception as ex:
        _logger().warning('command_switches: sync не удался: %s', ex)
        return False, [], []
