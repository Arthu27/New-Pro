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
Серверы, где бот состоит вне MAIN/EXTRA_GUILD_IDS, очищаются от
устаревших локальных копий (иначе дубли живут там вечно).
Если MAIN_GUILD_ID не задан — прежнее глобальное поведение."""

import asyncio

from logger import get_logger

_log = get_logger('sync_filtered')

# Антигонка: full_sync вызывается из загрузки, кнопки панели, тумблеров
# команд и настроек — два параллельных прогона перемешивают парковки и
# sync-пейлоады (дубли и падение панели на двойном клике). Локи ведём
# per-event-loop: тесты гоняют функцию на свежих циклах.
_loop_locks = {}


def _current_lock():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = id(loop)
    lk = _loop_locks.get(key)
    if lk is None:
        lk = asyncio.Lock()
        _loop_locks[key] = lk
    return lk


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
    from discord import AppCommandType
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
    # Дубли апелляции: команды с extras['keep_global'] (/апелляция) живут
    # ТОЛЬКО глобально (работают в ЛС). Гильдовая копия = вторая строка с
    # тем же именем в меню сервера. Снимаем такие копии и НЕ возвращаем их
    # в локальное дерево: при следующем guild-sync старые копии, оставшиеся
    # в Discord с прошлых версий, стираются (самолечение).
    if ctx is not None:
        try:
            _kept_global = [
                c for c in tree.get_commands(guild=ctx)
                if bool((getattr(c, 'extras', None) or {}).get('keep_global'))
            ]
        except Exception as _e:
            _log.debug('get_commands(keep_global): %s', _e)
            _kept_global = []
        for c in _kept_global:
            try:
                tree.remove_command(
                    c.name, guild=ctx,
                    type=getattr(c, 'type', None) or AppCommandType.chat_input)
                _log.info('sync: гильдовая копия keep_global «%s» снята '
                          '(команда живёт глобально — дубля в меню не будет)',
                          c.name)
            except Exception as e:
                _log.debug('remove_command(keep_global %s): %s', c.name, e)
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


async def _clean_stray_guilds(bot, tree, exclude_ids):
    """Стереть команды на серверах ВНЕ целевого списка (exclude_ids).

    Гильдовый sync затирает только свой scope: на «чужих» серверах
    (бот состоит, но их нет в MAIN/EXTRA_GUILD_IDS) старые локальные копии
    никто никогда не трогал — вечные дубли. Пустой payload = очистка.
    Запускается и когда targets пуст (глобальный режим): гильдовые копии
    там вообще вне закона (именно так вечно жила вторая «апелляция»).
    """
    cleaned = []
    try:
        import discord as _d
        _exclude = {int(x or 0) for x in (exclude_ids or set())}
        for g in list(getattr(bot, 'guilds', []) or []):
            gid = int(getattr(g, 'id', 0) or 0)
            if not gid or gid in _exclude:
                continue
            try:
                await tree.sync(guild=_d.Object(id=gid))   # локально пусто
                cleaned.append(gid)
                _log.info('sync: сервер %s очищен от устаревших копий команд '
                          '(нужны команды там — добавьте его в EXTRA_GUILD_IDS)', gid)
            except Exception as _e:
                _log.debug('sync: очистка чужого сервера %s: %s', gid, _e)
    except Exception as _e:
        _log.debug('sync: обход чужих серверов: %s', _e)
    return cleaned


def _note_sync_done(bot, mode, targets_ids=(), stray_cleaned=()):
    """Метка последнего полного синка (диагностика в панели: data/sync_last.json)."""
    try:
        import json as _json
        import os as _os
        from datetime import datetime as _dt, timezone as _tz
        for base in (getattr(bot, 'base_dir', None), _os.getcwd()):
            if not base:
                continue
            try:
                _os.makedirs(_os.path.join(base, 'data'), exist_ok=True)
                payload = {
                    'at': _dt.now(_tz.utc).isoformat(timespec='seconds'),
                    'mode': mode,
                    'targets': [int(x or 0) for x in targets_ids],
                    'stray_cleaned': [int(x or 0) for x in stray_cleaned],
                }
                with open(_os.path.join(base, 'data', 'sync_last.json'), 'w',
                          encoding='utf-8') as f:
                    _json.dump(payload, f, ensure_ascii=False)
                return
            except OSError as _oe:
                _log.debug('sync: не записал метку в %s: %s', base, _oe)
                continue
    except Exception as _e:
        _log.debug('sync: метка последнего синка: %s', _e)


async def full_sync(bot):
    """Полный синк с защитой от параллельного входа (двойной клик кнопки)."""
    lk = _current_lock()
    if lk.locked():
        _log.warning('full_sync уже выполняется — повторный вход пропускаю '
                     '(параллельный прогон дал бы дубли/перемешанные пейлоады)')
        return []
    async with lk:
        return await _full_sync_inner(bot)


async def _full_sync_inner(bot):
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
            # Гильдия может ещё не быть в кэше (холодный старт/переподключение) —
            # Object(id) для guild-синка достаточно. Раньше пустой targets
            # включал «глобальный режим» и стирал гильдовые меню на ровном месте.
            targets.append(g if g is not None else obj)
    except Exception as e:
        _log.debug('targets(): %s', e)

    if not targets:
        # .env пуст — глобальное поведение (любой сервер), но с фильтром.
        # И старые ГИЛЬДОВЫЕ копии от прежних регистраций стираем тоже —
        # иначе вторая «апелляция» и прочие дубли живут на серверах вечно.
        synced = await sync_tree(bot)
        cleaned = await _clean_stray_guilds(bot, tree, set())
        _note_sync_done(bot, 'global', (), cleaned)
        return synced

    # 1) глобальный список в Discord очищаем (чтобы не было дублей).
    #    Исключение — команды с extras['keep_global'] (напр. /апелляция):
    #    они обязаны остаться глобальными, чтобы работали в ЛС бота.
    #    ВАЖНО: паркуем не только слэш-команды, но и контекстные меню
    #    (user/message). copy_global_to тащит глобальные контекстные меню
    #    в каждую гильдию — если оставить их ещё и глобальными, Discord
    #    показывает их ДВАЖДЫ (дубли «Варн за сообщение», «Войс-мут» …).
    parked = []   # (cmd, type)
    kept = []     # keep_global: (имя, type) — их из гильдовых копий выкинуть
    for _t in (AppCommandType.chat_input, AppCommandType.user,
               AppCommandType.message):
        try:
            _cmds = list(tree.get_commands(type=_t))
        except TypeError:          # минималистичные деревья без type=
            if _t is not AppCommandType.chat_input:
                continue
            _cmds = list(tree.get_commands())
        for cmd in _cmds:
            keep_it = False
            try:
                keep_it = bool((getattr(cmd, 'extras', None) or {}).get('keep_global'))
            except Exception:
                keep_it = False
            if keep_it:
                kept.append((cmd.name, _t))
                continue
            try:
                tree.remove_command(cmd.name, type=_t)
                parked.append((cmd, _t))
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
        for cmd, _t in parked:
            try:
                tree.add_command(cmd)
            except Exception as _e:
                _log.debug('вернуть %s в дерево: %s', cmd.name, _e)
        _note_sync_done(bot, 'failed-global-clear',
                        [int(getattr(g, 'id', 0) or 0) for g in targets], ())
        return []

    for cmd, _t in parked:        # локально возвращаем — источник для копий
        try:
            tree.add_command(cmd)
        except Exception as e:
            _log.debug('вернуть %s в дерево: %s', cmd.name, e)

    # 2) копируем глобальное дерево в каждый разрешённый сервер.
    #    ИСКЛЮЧАЯ keep_global (/апелляция): она уже опубликована ГЛОБАЛЬНО
    #    (Discord показывает глобальные команды во всех гильдиях и в ЛС) —
    #    гильдовая копия = вторая строчка с тем же именем в меню. Плюс это
    #    самолечит сервер: ранее скопированные keep_global-остатки стираются.
    for g in targets:
        try:
            tree.copy_global_to(guild=g)
            for _kname, _kt in kept:
                try:
                    tree.remove_command(_kname, guild=g, type=_kt)
                except Exception as _e:
                    _log.debug('выкинуть keep_global %s из %s: %s', _kname, g.id, _e)
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

    # 4) «Чужие» серверы (бот состоит, но их нет в MAIN/EXTRA_GUILD_IDS):
    #    старые гильдовые копии там вечны, пока их не стереть пустым sync.
    cleaned = await _clean_stray_guilds(
        bot, tree, {int(getattr(g, 'id', 0) or 0) for g in targets})

    # 5) Откат: все guild-синки упали. Глобальный список в Discord УЖЕ
    #    правильный (шаг 1 опубликовал только keep_global), а упавший
    #    guild-синк НЕ трогает старый список сервера — меню живо.
    #    Раньше здесь делали tree.sync() всем деревом: parked-команды
    #    (контекстные меню и пр.) публикавались ГЛОБАЛЬНО поверх
    #    гильдовых копий — и каждая команда появлялась ПО ДВАЖДЫ.
    #    Теперь честно перепубликуем только keep_global (идемпотентно
    #    с шагом 1 — дублей не бывает физически).
    if targets and ok_guilds == 0:
        _log.error('ни один guild-синк не удался — глобальное меню '
                   'оставляю как после шага 1 (только keep_global): '
                   'гильдовые списки не тронуты, дублей не будет')
        try:
            for cmd, _t in parked:
                try:
                    tree.remove_command(cmd.name, type=_t)
                except Exception as _e:
                    _log.debug('снять перед откатом %s: %s', cmd.name, _e)
            await tree.sync()
        except Exception as _e:
            _log.error('перепубликация keep_global после сбоя: %s', _e)
        finally:
            for cmd, _t in parked:
                try:
                    tree.add_command(cmd)
                except Exception as _e:
                    _log.debug('вернуть после отката %s: %s', cmd.name, _e)
    _note_sync_done(bot, 'guilds',
                    [int(getattr(g, 'id', 0) or 0) for g in targets],
                    cleaned)
    return out
