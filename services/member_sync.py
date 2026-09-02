# -*- coding: utf-8 -*-
"""Фоновая дозагрузка участников сервера в кэш бота.

Зачем: панель и пикеры участников (member-card/suggest, профили, варны,
лестница, доказательства…) ищут людей по ``guild.members`` — это ЛОКАЛЬНЫЙ
кэш дискорд-клиента. На старте в нём сидят только онлайн/активные участники,
пока гильдия не «дочанкена» (gateway chunking). Из-за этого поиск не находил
людей, которых «нет в листе».

Раз в ~20 секунд обходим гильдии бота и, если локальный список неполный,
догружаем недостающих. Тяжёлая часть (chunk шлёт запросы gateway и сам
пагинирует с учётом рейт-лимитов discord.py) выполняется аккуратно:

* не дёргаем сеть, если гильдия уже полностью зачанкена
  (``guild.chunked``) и число участников в кэше совпало с ``member_count``;
* на каждой итерации обрабатываем ОДНУ гильдию и потом пауза, чтобы не
  бёрстить gateway; большие гильдии discord.py докачивает пачками по 1000;
* всё в try/except с log.debug — недоступность gateway не должна ронять цикл.

Включается вместе с ботом (intents.members у нас привилегированный и задан
через Intents.all()). Отдельных команд не добавляет.
"""
import asyncio

from logger import get_logger

_log = get_logger("member_sync")

SYNC_INTERVAL_SEC = 20.0
# Одна итерация не должна висеть вечно: discord.py сам пагинирует, но ставим
# разумный потолок на докачку одной гильдии.
CHUNK_TIMEOUT_SEC = 60.0
# Большой сервер (20 000+ людей) Discord отдаёт пачками по ~1000 человек:
# фиксированные 60 с на таком объёме не хватает, докачка обрывалась и
# начиналась заново каждый тик — список участников никогда не становился
# полным. Масштабируем потолок по числу участников.
CHUNK_SEC_PER_1K = 8.0
CHUNK_TIMEOUT_MAX_SEC = 600.0


def _chunk_timeout(guild) -> float:
    """Сколько секунд даём на докачку: 60 с минимум, +8 с на каждую 1000 людей."""
    try:
        total = int(getattr(guild, "member_count", 0) or 0)
    except (TypeError, ValueError):
        total = 0
    scaled = CHUNK_TIMEOUT_SEC + (total / 1000.0) * CHUNK_SEC_PER_1K
    return min(max(scaled, CHUNK_TIMEOUT_SEC), CHUNK_TIMEOUT_MAX_SEC)

_task = None
_started = False


async def _sync_guild(guild) -> bool:
    """Догрузить участников одной гильдии, если кэш неполный. True — работали."""
    try:
        # Уже полностью синхронизировано? chunked=True = gateway прислал все
        # чанки; сверяем ещё и количество — бывает рассинхрон на старте.
        cached = len(guild.members)
        total = getattr(guild, "member_count", 0) or 0
        if getattr(guild, "chunked", False) and total and cached >= total:
            return False

        # Догружаем пачками через gateway (respect-рейтлимиты внутри discord.py).
        coro = guild.chunk(cache=True)
        timeout = _chunk_timeout(guild)
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            _log.debug("member_sync: chunk guild=%s таймаут (%.0fс, людей %s), попробую позже",
                       guild.id, timeout, total or "?")
            return False
        except TypeError:
            # Старые/урезанные сборки discord.py без chunk() — тихо пропускаем.
            _log.debug("member_sync: guild.chunk недоступна для guild=%s", guild.id)
            return False

        new_cached = len(guild.members)
        _log.info("member_sync: guild=%s участников в кэше %s -> %s (всего %s)",
                  guild.id, cached, new_cached, total or "?")
        return True
    except Exception as _ex:  # сеть/правы/прочее — не ядро, ждём следующий тик
        _log.debug("member_sync: guild=%s ошибка: %s", getattr(guild, "id", "?"), _ex)
        return False


async def _member_sync_loop(bot):
    """Бесконечный цикл: раз в SYNC_INTERVAL_SEC докачиваем по одной гильдии."""
    try:
        await bot.wait_until_ready()
    except Exception as _ex:
        _log.debug("member_sync: wait_until_ready: %s", _ex)
        return

    # Очередь гильдий: за несколько тиков обходим все, по одной за итерацию.
    guild_queue = []
    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL_SEC)
            if not getattr(bot, "is_ready", lambda: False)():
                continue

            if not guild_queue:
                # переформировываем очередь из текущих гильдий бота
                guild_queue = list(getattr(bot, "guilds", []) or [])

            if guild_queue:
                guild = guild_queue.pop(0)
                await _sync_guild(guild)
        except asyncio.CancelledError:
            raise
        except Exception as _ex:
            _log.debug("member_sync loop: %s", _ex)
            await asyncio.sleep(SYNC_INTERVAL_SEC)


def start_member_sync(bot):
    """Запустить фоновую дозагрузку участников (идемпотентно)."""
    global _task, _started
    if _started:
        return
    _started = True
    try:
        _task = asyncio.get_event_loop().create_task(_member_sync_loop(bot))
        _log.info("member_sync: фоновая дозагрузка участников запущена (каждые %sс)",
                  SYNC_INTERVAL_SEC)
    except Exception as _ex:
        _log.debug("member_sync: не удалось запустить: %s", _ex)


async def stop_member_sync():
    """Остановить фоновую задачу (для чистого рестарта/тестов)."""
    global _task, _started
    _started = False
    if _task is not None:
        try:
            _task.cancel()
        except Exception as _ex:
            _log.debug("stop_member_sync(): подавлено: %s", _ex)
        _task = None


async def ensure_guild_members(bot, guild_id: int):
    """Принудительно догрузить участников конкретной гильдии прямо сейчас
    (для мест, где полный список нужен немедленно). Безопасно вызывать часто:
    если уже синхронизировано — сетевого вызова не будет."""
    try:
        guild = bot.get_guild(int(guild_id)) if bot else None
        if guild is not None:
            await _sync_guild(guild)
    except Exception as _ex:
        _log.debug("ensure_guild_members(%s): %s", guild_id, _ex)
