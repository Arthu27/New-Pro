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

    # 1) копируем глобальное дерево в каждый разрешённый сервер
    for g in targets:
        try:
            tree.copy_global_to(guild=g)
        except Exception as e:
            _log.debug('copy_global_to(%s): %s', g.id, e)

    # 2) глобальный список в Discord очищаем (чтобы не было дублей)
    parked = []
    for cmd in list(tree.get_commands()):
        try:
            tree.remove_command(cmd.name, type=AppCommandType.chat_input)
            parked.append(cmd)
        except Exception as e:
            _log.debug('снять глобально %s: %s', cmd.name, e)
    try:
        await tree.sync()
    except TypeError:
        pass                         # дерево без параметров — уже очищено выше
    except Exception as e:
        _log.warning('глобальная очистка не удалась: %s', e)
    for cmd in parked:            # локально возвращаем — источник для копий
        try:
            tree.add_command(cmd)
        except Exception as e:
            _log.debug('вернуть %s в дерево: %s', cmd.name, e)

    # 3) по каждому серверу — синк без выключенных
    out = []
    for g in targets:
        try:
            out.extend(await sync_tree(bot, guild=g))
        except Exception as e:
            _log.warning('sync(%s): %s', g.id, e)
    return out
