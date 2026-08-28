# -*- coding: utf-8 -*-
"""Slash-команды: где жить и что синхронить.

Заказ владельца 2026-08-27:
1) выключенная в панели команда должна ИСЧЕЗАТЬ из Discord (не предлагаться
   в списке «/»), а не отвечать «выключена» после ввода;
2) изменения — мгновенные.

Как: команды регистрируются КАК ГИЛЬДОВЫЕ на серверах из MAIN_GUILD_ID +
EXTRA_GUILD_IDS (гильдовые обновляются мгновенно, глобальные — до часа).
Глобальный список в Discord очищается, чтобы не было дублей. Перед sync
выключенные команды снимаются с дерева и возвращаются после — панель
по-прежнему видит их все и может включить обратно.
Если MAIN_GUILD_ID не задан — прежнее глобальное поведение."""

from logger import get_logger

_log = get_logger('sync_filtered')


def _is_disabled(name):
    try:
        from services.command_switches import is_disabled
        return bool(is_disabled(name))
    except Exception as e:
        _log.debug('is_disabled(%s): %s', name, e)
        return False


async def sync_tree(bot, guild=None):
    """tree.sync() без выключенных команд (контекст guild или глобально)."""
    import discord
    tree = bot.tree
    ctx = None
    if guild is not None:
        gid = getattr(guild, 'id', guild)
        ctx = guild if isinstance(guild, discord.Object) else discord.Object(id=int(gid))
    try:
        cmds = list(tree.get_commands(guild=ctx))
    except Exception as e:
        _log.debug('get_commands(): %s', e)
        cmds = []
    removed = []
    for c in cmds:
        if _is_disabled(getattr(c, 'name', '')):
            try:
                tree.remove_command(c.name, guild=ctx)
                removed.append(c)
            except Exception as e:
                _log.debug('remove_command(%s): %s', c.name, e)
    try:
        try:
            synced = await tree.sync(guild=ctx)
        except TypeError:            # минималистичные деревья без параметра
            synced = await tree.sync()
    finally:
        for c in removed:          # назад в локальное дерево — панель видит все
            try:
                tree.add_command(c, guild=ctx)
            except Exception as e:
                _log.debug('add_command(%s) назад: %s', c.name, e)
    if removed:
        _log.info('sync: скрыто выключенных команд — %d (%s)',
                  len(removed), ', '.join(c.name for c in removed))
    return synced


async def full_sync(bot):
    """Полный синк: гильдовые команды (мгновенно) + чистка глобальных."""
    from discord import AppCommandType
    tree = getattr(bot, 'tree', None)
    if tree is None:
        return []
    targets = []
    try:
        from config import Config
        for obj in Config.guild_objects():
            g = bot.get_guild(obj.id)
            if g is not None:
                targets.append(g)
    except Exception as e:
        _log.debug('targets(): %s', e)

    if not targets:
        # .env пуст — глобальное поведение (любой сервер), но с фильтром
        return await sync_tree(bot)

    # 1) глобальный список в Discord очищаем (чтобы не было дублей).
    #    Исключение — команды с extras['keep_global'] (напр. /апелляция):
    #    они обязаны остаться глобальными, чтобы работали в ЛС бота.
    parked = []
    for cmd in list(tree.get_commands()):
        keep_it = False
        try:
            keep_it = bool((getattr(cmd, 'extras', None) or {}).get('keep_global'))
        except Exception:
            keep_it = False
        if keep_it:
            continue
        try:
            tree.remove_command(cmd.name, type=AppCommandType.chat_input)
            parked.append(cmd)
        except Exception as e:
            _log.debug('снять глобально %s: %s', cmd.name, e)
    try:
        await tree.sync()
    except TypeError as e:          # дерево без параметров — уже очищено выше
        _log.debug('tree.sync(): %s', e)
    except Exception as e:
        # Очистка глобального списка НЕ прошла — старое глобальное меню
        # осталось в Discord. Копировать те же команды в гильдию = ДУБЛИ
        # в клиенте (именно «много дубликатов» из жалоб). Останавливаемся:
        # локальное дерево собираем обратно, до следующего рестарта
        # бот работает на старом глобальном меню — безопасно.
        _log.warning('глобальная очистка не удалась (%s) — guild-синк '
                     'пропущен, чтобы не задублировать меню', e)
        for cmd in parked:
            try:
                tree.add_command(cmd)
            except Exception as _e:
                _log.debug('вернуть %s в дерево: %s', cmd.name, _e)
        return []

    for cmd in parked:            # локально возвращаем — источник для копий
        try:
            tree.add_command(cmd)
        except Exception as e:
            _log.debug('вернуть %s в дерево: %s', cmd.name, e)

    # 2) копируем глобальное дерево в каждый разрешённый сервер
    for g in targets:
        try:
            tree.copy_global_to(guild=g)
        except Exception as e:
            _log.debug('copy_global_to(%s): %s', g.id, e)

    # 3) по каждому серверу — синк без выключенных
    out = []
    ok_guilds = 0
    for g in targets:
        try:
            out.extend(await sync_tree(bot, guild=g))
            ok_guilds += 1
        except Exception as e:
            _log.warning('sync(%s): %s', g.id, e)

    # 4) Откат: все guild-синки упали — глобальное меню уже стёрто,
    #    серверные не появились = пользователь видел бы ПУСТОЕ меню
    #    («команды не работают»). Возвращаем глобальное меню в Discord,
    #    до следующего рестарта дублей не будет, команды живы.
    if targets and ok_guilds == 0:
        _log.error('ни один guild-синк не удался — возвращаю глобальное '
                   'меню, чтобы команды не пропали из списка')
        try:
            await tree.sync()
        except Exception as _e:
            _log.error('откат глобального меню тоже не удался: %s', _e)
    return out
