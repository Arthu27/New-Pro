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
import time

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
# Сколько секунд ждём БЕЗ прогресса, прежде чем сдаться. Важен не размер
# сервера, а скорость отдачи Discord: пока пачки прибывают — ждём хоть час.
CHUNK_STALL_SEC = 60.0
# Как часто смотрим, прибавилось ли людей в кэше.
CHUNK_POLL_SEC = 0.5
# Страховка от зависшего корутина (не предел состава сервера): даже если
# пачки идут бесконечно, дольше этого не сидим в одной итерации.
CHUNK_HARD_MAX_SEC = 6 * 3600.0


def _chunk_timeout(guild) -> float:
    """Сколько секунд допустимо сидеть БЕЗ прогресса.

    Раньше это был потолок на ВСЮ докачку, масштабированный по числу
    участников (и с жёстким максимумом 600 с). На растущем сервере любой
    такой максимум однажды становился тесным: докачка обрывалась по
    таймауту, уже полученные пачки выбрасывались и всё начиналось заново
    каждый тик — состав никогда не становился полным. Теперь потолок
    снят, а сдаёмся мы только по отсутствию прогресса.
    """
    return float(CHUNK_STALL_SEC)


async def _await_chunk(guild, coro) -> str:
    """Дождаться докачки, пока есть прогресс.

    Возвращает 'ok' | 'stall' | 'unsupported'. В отличие от
    asyncio.wait_for(всё_сразу) здесь не выбрасывается уже полученное:
    как только люди перестали прибывать — выходим, а частичный состав
    сохраняет вызывающий код.
    """
    try:
        task = asyncio.create_task(coro)
    except TypeError:
        return "unsupported"

    last = len(guild.members)
    now = time.monotonic()
    last_growth = now
    started = now
    try:
        while not task.done():
            await asyncio.sleep(CHUNK_POLL_SEC)
            count = len(guild.members)
            if count != last:
                last = count
                last_growth = time.monotonic()
            elif time.monotonic() - last_growth > _chunk_timeout(guild):
                task.cancel()
                return "stall"
            elif time.monotonic() - started > CHUNK_HARD_MAX_SEC:
                task.cancel()
                return "stall"
    except asyncio.CancelledError:
        task.cancel()
        raise
    # Корутин мог завершиться с ошибкой (gateway 500, обрыв сокета). Без этой
    # проверки «done» выглядело бы как успешная докачка: исключение осталось
    # бы непросмотренным, а код отрапортовал «участников в кэше N -> N».
    if task.cancelled():
        return "stall"
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return "stall"
    if exc is not None:
        if isinstance(exc, TypeError):
            return "unsupported"
        return "error"
    return "ok"

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
        # Ждём ПО ПРОГРЕССУ: пока люди прибывают, докачка не обрывается —
        # потолка по размеру сервера нет.
        coro = guild.chunk(cache=True)
        try:
            state = await _await_chunk(guild, coro)
        except TypeError:
            # Старые/урезанные сборки discord.py без chunk() — тихо пропускаем.
            _log.debug("member_sync: guild.chunk недоступна для guild=%s", guild.id)
            return False

        if state == "unsupported":
            _log.debug("member_sync: guild.chunk недоступна для guild=%s", guild.id)
            return False

        new_cached = len(guild.members)

        async def _persist(partial: bool) -> None:
            """Состав — в файл. partial=True, когда докачка ещё не закончена."""
            try:
                from services import member_store as MS
                n = MS.upsert_many(guild.id, guild.members)
                await MS.aflush(guild.id)
                _log.info("member_sync: guild=%s состав%s сохранён в файл (%s участников)",
                          guild.id, " частично" if partial else "", n)
            except Exception as _ex:
                _log.debug("member_sync: сохранить состав %s: %s", guild.id, _ex)

        if state != "ok":
            # Пачки встали или докачка упала. Раньше здесь всё выбрасывалось
            # и докачка начиналась с нуля — на большом сервере состав никогда
            # не становился полным. Теперь частичный прогресс сохраняется,
            # и следующий тик продолжает с того, что уже есть.
            await _persist(partial=True)
            why = "докачка упала" if state == "error" else "докачка встала"
            _log.debug("member_sync: guild=%s %s (%s в кэше из %s) — "
                       "продолжу позже, прогресс сохранён",
                       guild.id, why, new_cached, total or "?")
            return False

        _log.info("member_sync: guild=%s участников в кэше %s -> %s (всего %s)",
                  guild.id, cached, new_cached, total or "?")
        # Дочитали — сразу сохраняем состав в файл: панель берёт список
        # оттуда мгновенно и не ждёт повторной докачки кэша.
        await _persist(partial=False)
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
