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


# ── Жёсткий белый список команд, публикуемых в Discord ──────────────────
# Заказ владельца: в меню «/» должно быть РОВНО шесть боевых команд —
# никаких настроечных/служебных/setup-команд (вкл/выкл/канал/порог/module/
# proof и пр.), даже для админа. Всё остальное управление — через /modpanel
# и веб-панель. Команды из этого списка живут в Discord; всё прочее
# снимается с дерева перед sync (и старые лишние копии затираются), но в
# локальном дереве остаётся — панель и внутренние вызовы видят их.
PUBLIC_COMMAND_WHITELIST = frozenset({
    'modpanel',      # панель модерации — все действия отсюда
    'апелляция',     # подать апелляцию (глобально, работает и в ЛС)
    'update',        # обслуживание (только владелец)
    'afk',           # отойти/вернуться
    'report',        # жалоба на участника
    'my-violations', # свои наказания
})


def _is_public(c):
    """Публиковать ли команду в Discord (и имя, и контекстные меню)."""
    try:
        name = getattr(c, 'name', '') or ''
    except Exception:
        name = ''
    return normalize_cmd(name) in {normalize_cmd(x) for x in PUBLIC_COMMAND_WHITELIST}


def normalize_cmd(name):
    return str(name or '').strip().lower()


# ── Таймауты и идемпотентность синка ───────────────────────────────────
# Инцидент 31.08: стартовый синк зависал дольше 180с и сдавался, меню
# оставалось старым. Причины: (1) каждый full_sync делал PUT-перезапись
# глобально и по каждому серверу, даже если в Discord всё уже совпадает
# (глобальные PUT жёстко лимитированы — 200/сутки, при лимите Discord
# присылает огромный retry_after и discord.py молча ждёт); (2) один
# залипший вызов блокировал весь прогон — таймаут был только снаружи.
# Теперь: сверяемся с Discord дешёвым GET и пропускаем PUT при совпадении;
# на каждый сетевой вызов — свой короткий таймаут (висяк не держит весь
# синк); чистка чужих серверов ограничена по времени и объёму.
SCOPE_TIMEOUT_SEC = 25      # один tree.sync / fetch_commands по скоупу
STRAY_MAX_CLEAN = 10        # сколько «чужих» серверов чистим за один прогон
STRAY_TIME_BUDGET_SEC = 30  # общий бюджет на чистку чужих серверов


async def _gather_timeout(coro, timeout, what):
    """Дождаться coro с таймаутом; по таймауту отменить и бросить TimeoutError."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        _log.warning('sync: %s не уложилось в %sс — пропускаю скоуп '
                     '(меню в Discord не тронуто, повтор позже)', what, timeout)
        raise


def _sig(cmd):
    """Сигнатуры команды (frozenset строк) для сравнения «локально == Discord».

    Для контекстного меню или одиночной слэш-команды — одна строка
    (имя|тип|описание|число-параметров). Для слэш-группы — по строке на
    каждую подкоманду (qualified-имя), без мутации объектов. Набор строк
    уравнивает порядок и работает и у локальной команды, и у ответа
    Discord API (AppCommand)."""
    name = getattr(cmd, 'name', '') or ''
    try:
        ctype = int(getattr(cmd, 'type', 1)) or 1
    except (TypeError, ValueError):
        ctype = 1
    if ctype != 1:                      # контекстные меню (user/message)
        return frozenset({f'{name}|{ctype}||'})

    def _row(c, qname):
        desc = (getattr(c, 'description', '') or '').strip()
        try:
            npar = len(getattr(c, 'parameters', None) or [])
        except Exception:
            npar = 0
        return f'{qname}|1|{desc}|{npar}'

    out = set()

    def _walk(c, prefix):
        subs = getattr(c, 'commands', None)
        if subs:                        # группа/подгруппа
            for s in subs:
                _walk(s, f'{prefix} {s.name}'.strip())
        else:
            out.add(_row(c, prefix))

    _walk(cmd, str(name))
    if not out:                         # одиночная слэш-команда
        out.add(_row(cmd, str(name)))
    return frozenset(out)


async def _remote_sigs(tree, ctx):
    """Сигнатуры команд, реально зарегистрированных в Discord по скоупу.

    None — если не удалось прочитать (сеть): тогда вызывающий делает
    обычный sync (не рискуем пропустить нужное обновление)."""
    try:
        if ctx is None:
            fetched = await asyncio.wait_for(tree.fetch_commands(),
                                             timeout=SCOPE_TIMEOUT_SEC)
        else:
            fetched = await asyncio.wait_for(tree.fetch_commands(guild=ctx),
                                             timeout=SCOPE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        _log.warning('sync: чтение команд Discord (%s) зависло — '
                     'будет обычный PUT', 'глобально' if ctx is None else ctx.id)
        return None
    except TypeError:
        # минималистичные деревья/старый discord.py без fetch_commands
        return None
    except Exception as e:
        _log.debug('sync: fetch_commands(%s): %s', ctx, e)
        return None
    out = set()
    for c in (fetched or []):
        out |= _sig(c)
    return out


def _local_sigs(tree, ctx):
    """Сигнатуры команд локального дерева по скоупу (как их ждём в Discord)."""
    try:
        cmds = tree.get_commands(guild=ctx)
    except TypeError:
        cmds = tree.get_commands()
    except Exception as e:
        _log.debug('sync: get_commands(%s): %s', ctx, e)
        cmds = []
    out = set()
    for c in cmds:
        out |= _sig(c)
    return out


async def _push_sync(tree, ctx):
    """tree.sync с таймаутом и идемпотентным пропуском.

    Сначала дешёвый GET: если в Discord ровно то же дерево — PUT не шлём
    (экономим суточный лимит глобальных команд и время; при исчерпании
    лимита Discord держит соединение на минуты — раньше это и вешало
    синк). Не удалось прочитать — делаем обычный PUT как раньше.

    Возвращает (synced, put_done): synced — список команд (как tree.sync),
    put_done=False означает «пропущено, уже совпадало»."""
    where = 'глобально' if ctx is None else f'сервер {ctx.id}'
    remote = await _remote_sigs(tree, ctx)
    if remote is not None:
        local = _local_sigs(tree, ctx)
        if remote == local:
            _log.info('sync: %s уже совпадает с Discord (%d команд) — PUT пропущен',
                      where, len(local))
            try:
                cmds = tree.get_commands(guild=ctx)
            except TypeError:
                cmds = tree.get_commands()
            return cmds, False
    try:
        try:
            synced = await asyncio.wait_for(tree.sync(guild=ctx),
                                            timeout=SCOPE_TIMEOUT_SEC)
        except TypeError:                # минималистичные деревья без guild=
            synced = await asyncio.wait_for(tree.sync(),
                                            timeout=SCOPE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        _log.error('sync: %s не завершилось за %sс — отмена', where,
                   SCOPE_TIMEOUT_SEC)
        raise
    return synced, True


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
    def _cmd_type(c):
        # Явный тип для remove_command: у chat-команд в дереве c.type = None,
        # а remove_command без type ищет только chat_input — контекстные меню
        # (user/message) иначе не снимаются. discord.py матчит по имени enum
        # ('chat_input'/'user'/'message'), поэтому возвращаем именно член
        # AppCommandType (принимаем int, строку-имя или уже готовый enum).
        t = getattr(c, 'type', None)
        if isinstance(t, AppCommandType):
            return t
        if t in (None, '', 'chat', 'chat_input', 1):
            return AppCommandType.chat_input
        if t in ('user', 2):
            return AppCommandType.user
        if t in ('message', 3):
            return AppCommandType.message
        try:
            return AppCommandType(t)
        except (ValueError, TypeError):
            try:
                return AppCommandType[str(t)]
            except Exception:
                return AppCommandType.chat_input

    removed = []
    for c in cmds:
        # Снимаем из публикации: (а) выключенные владельцем, либо
        # (б) команды НЕ из белого списка — в Discord должны жить только
        # шесть боевых команд (modpanel, апелляция, update, afk, report,
        # my-violations); все служебные/настроечные команды не публикуются.
        if _is_disabled(getattr(c, 'name', '')) or not _is_public(c):
            try:
                tree.remove_command(c.name, guild=ctx, type=_cmd_type(c))
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
        synced, _put = await _push_sync(tree, ctx)
    finally:
        for c in removed:          # назад в локальное дерево — панель видит все
            try:
                tree.add_command(c, guild=ctx)
            except Exception as e:
                _log.debug('add_command(%s) назад: %s', c.name, e)
    if removed:
        _log.info('sync: не публикуем (не в белом списке/выключены) — %d команд (%s)',
                  len(removed), ', '.join(c.name for c in removed))
    return synced


async def _clean_stray_guilds(bot, tree, exclude_ids):
    """Стереть команды на серверах ВНЕ целевого списка (exclude_ids).

    Гильдовый sync затирает только свой scope: на «чужих» серверах
    (бот состоит, но их нет в MAIN/EXTRA_GUILD_IDS) старые локальные копии
    никто никогда не трогал — вечные дубли. Пустой payload = очистка.
    Запускается и когда targets пуст (глобальный режим): гильдовые копии
    там вообще вне закона (именно так вечно жила вторая «апелляция»).

    Раньше функция делала PUT (пустой sync) ПО КАЖДОМУ серверу подряд,
    даже если там давно пусто — десятки синхронных HTTP подряд вешали
    весь full_sync (инцидент «не уложился в 180с»). Теперь: параллельно
    (GET) смотрим, где команды реально есть; чистим только такие и не
    больше STRAY_MAX_CLEAN за прогон, с общим бюджетом времени —
    остальное дочистят следующие запуски.
    """
    import discord as _d
    cleaned = []
    try:
        _exclude = {int(x or 0) for x in (exclude_ids or set())}
        stray = [int(getattr(g, 'id', 0) or 0)
                 for g in list(getattr(bot, 'guilds', []) or [])]
        stray = [gid for gid in stray if gid and gid not in _exclude]
        if not stray:
            return cleaned

        loop = asyncio.get_running_loop()
        deadline = loop.time() + STRAY_TIME_BUDGET_SEC

        async def _has_cmds(gid):
            """Есть ли на чужом сервере зарегистрированные команды (GET)."""
            if loop.time() > deadline:
                return None
            try:
                fetched = await asyncio.wait_for(
                    tree.fetch_commands(guild=_d.Object(id=gid)),
                    timeout=SCOPE_TIMEOUT_SEC)
                return bool(fetched)
            except Exception as _e:
                _log.debug('sync: проверка чужого сервера %s: %s', gid, _e)
                return None

        # параллельно (до 8 за раз) выясняем, где реально что-то висит
        sem = asyncio.Semaphore(8)

        async def _check(gid):
            async with sem:
                return gid, await _has_cmds(gid)

        results = await asyncio.gather(*[_check(g) for g in stray],
                                       return_exceptions=True)
        dirty = []
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            gid, has = r
            if has:
                dirty.append(gid)

        for gid in dirty[:STRAY_MAX_CLEAN]:
            if loop.time() > deadline:
                _log.info('sync: бюджет чистки чужих серверов исчерпан — '
                          '%d из них дочистятся следующим синком',
                          len(dirty) - len(cleaned))
                break
            try:
                await asyncio.wait_for(
                    tree.sync(guild=_d.Object(id=gid)),
                    timeout=SCOPE_TIMEOUT_SEC)   # локально пусто -> стирание
                cleaned.append(gid)
                _log.info('sync: сервер %s очищен от устаревших копий команд '
                          '(нужны команды там — добавьте его в EXTRA_GUILD_IDS)',
                          gid)
            except asyncio.TimeoutError:
                _log.warning('sync: очистка чужого сервера %s не уложилась '
                             'в %sс — в следующий раз', gid, SCOPE_TIMEOUT_SEC)
            except Exception as _e:
                _log.debug('sync: очистка чужого сервера %s: %s', gid, _e)
        if len(dirty) > len(cleaned):
            _log.info('sync: чужих серверов с командами %d, за прогон '
                      'почищено %d (лимит/бюджет) — остаток позже',
                      len(dirty), len(cleaned))
    except Exception as _e:
        _log.debug('sync: обход чужих серверов: %s', _e)
    return cleaned


def _note_sync_done(bot, mode, targets_ids=(), stray_cleaned=(), commands=None,
                    failed_guilds=(), error=''):
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
                if failed_guilds:
                    # каким серверам команды НЕ дошли (видно в панели,
                    # жалоба 30.08: «на сервере 33 команды и две апелляции»)
                    payload['failed_guilds'] = [int(x or 0) for x in failed_guilds]
                if error:
                    payload['error'] = str(error)[:300]
                if commands is not None:
                    payload['commands'] = int(commands)
                with open(_os.path.join(base, 'data', 'sync_last.json'), 'w',
                          encoding='utf-8') as f:
                    _json.dump(payload, f, ensure_ascii=False)
                return
            except OSError as _oe:
                _log.debug('sync: не записал метку в %s: %s', base, _oe)
                continue
    except Exception as _e:
        _log.debug('sync: метка последнего синка: %s', _e)


def note_sync_error(bot, error, mode='error'):
    """Синк упал (on_ready или кнопка) — причину видно в панели
    (data/sync_last.json), а не только в консоли."""
    import json as _json
    import os as _os
    from datetime import datetime as _dt, timezone as _tz
    try:
        for base in (getattr(bot, 'base_dir', None), _os.getcwd()):
            if not base:
                continue
            _os.makedirs(_os.path.join(base, 'data'), exist_ok=True)
            payload = {'at': _dt.now(_tz.utc).isoformat(timespec='seconds'),
                       'mode': mode,
                       'error': str(error)[:300]}
            with open(_os.path.join(base, 'data', 'sync_last.json'), 'w',
                      encoding='utf-8') as f:
                _json.dump(payload, f, ensure_ascii=False)
            return
    except Exception as e:
        _log.debug('note_sync_error(): %s', e)


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
        _note_sync_done(bot, 'global', (), cleaned, commands=len(synced))
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
    # С РЕТРАЯМИ (как guild-синки, жалоба 30.08 «опять так же — команды
    # не удалились»): разовый обрыв сети/замерзание loop убивал очистку
    # ОДНОЙ попыткой — старое глобальное меню жило в Discord вечно.
    _global_cleared = False
    _global_err = None
    for _attempt in (1, 2, 3):
        try:
            # _push_sync сам сходит GET и пропустит PUT, если глобально уже
            # ровно keep_global — это не тратит суточный лимит и не виснет.
            await _push_sync(tree, None)
            _global_cleared = True
            break
        except TypeError as e:      # дерево без параметров — уже очищено выше
            _log.debug('tree.sync(): %s', e)
            _global_cleared = True
            break
        except asyncio.TimeoutError as e:
            _global_err = e
            if _attempt < 3:
                _log.warning('глобальная очистка: попытка %d/3 зависла '
                             '(>%sс — rate limit/сеть) — повтор через 2с',
                             _attempt, SCOPE_TIMEOUT_SEC)
                await asyncio.sleep(2)
        except Exception as e:
            _global_err = e
            if _attempt < 3:
                _log.warning('глобальная очистка: попытка %d/3 не удалась (%s) '
                             '— повтор через 2с', _attempt, e)
                await asyncio.sleep(2)
    if not _global_cleared:
        # Очистка глобального списка НЕ прошла — старое глобальное меню
        # осталось в Discord. Копировать те же команды в гильдию = ДУБЛИ
        # в клиенте (именно «много дубликатов» из жалоб). Останавливаемся:
        # локальное дерево собираем обратно, до следующего рестарта
        # бот работает на старом глобальном меню — безопасно.
        _log.warning('глобальная очистка не удалась за 3 попытки (%s) — '
                     'guild-синк пропущен, чтобы не задублировать меню',
                     _global_err)
        for cmd, _t in parked:
            try:
                tree.add_command(cmd)
            except Exception as _e:
                _log.debug('вернуть %s в дерево: %s', cmd.name, _e)
        _note_sync_done(bot, 'failed-global-clear',
                        [int(getattr(g, 'id', 0) or 0) for g in targets], (),
                        error=str(_global_err))
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

    # 3) по каждому серверу — синк без выключенных. С РЕТРАЯМИ: разовый
    #    сбой сети/замерзание event-loop не должен оставлять сервер со
    #    СТАРЫМ меню (жалоба 30.08: на сервере висели 33 команды и две
    #    «апелляции» — последний успешный guild-синк был давно).
    out = []
    ok_guilds = 0
    failed_guilds = []
    for g in targets:
        _synced_guild = None
        for _attempt in (1, 2, 3):
            try:
                _synced_guild = await sync_tree(bot, guild=g)
                break
            except Exception as e:
                if _attempt < 3:
                    _log.warning('sync(%s): попытка %d/3 не удалась (%s) — '
                                 'повтор через 2с', getattr(g, 'id', g), _attempt, e)
                    await asyncio.sleep(2)
                else:
                    _log.warning('sync(%s): все 3 попытки не удались (%s) — меню '
                                 'сервера останется прежним до следующего синка',
                                 getattr(g, 'id', g), e)
        if _synced_guild is not None:
            out.extend(_synced_guild)
            ok_guilds += 1
        else:
            failed_guilds.append(int(getattr(g, 'id', 0) or 0))

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
            await asyncio.wait_for(tree.sync(), timeout=SCOPE_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            _log.error('перепубликация keep_global после сбоя зависла '
                       '>%sс — оставляю как есть (дублей не добавляется)',
                       SCOPE_TIMEOUT_SEC)
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
                    cleaned, commands=len(out), failed_guilds=failed_guilds)
    return out
