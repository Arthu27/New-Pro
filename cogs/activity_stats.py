# -*- coding: utf-8 -*-
"""Активность сервера → «Аналитика» в панели.

Каждое сообщение участников (не ботов, не вебхуки, не ЛС) идёт лёгкой
записью в services.message_stats — оттуда панель рисует сообщения/дня,
топ участников, топ каналов и теплокарту. Текст сообщения НЕ пишется.
Сбор работает всегда и не зависит от настроек лог-каналов: это внутренняя
статистика, а не лог на всеобщее обозрение.
"""
import discord
from discord.ext import commands

from logger import get_logger
from services import message_stats

_log = get_logger('activity_stats')

_MIGRATED = set()   # гильдии, чьи старые записи уже проштампованы uid


async def _migrate_legacy_names(bot):
    """Старые записи без uid привязать к людям по текущим никам (один раз).

    Жалоба владельца 2026-09-05: «система не видит изменения ников — это
    один и тот же человек». Теперь новые записи пишутся с user_id, а уже
    накопленные (без uid) штампуем по совпадению имени: display_name /
    username / ник на сервере, без учёта регистра. Кого не узнали —
    оставляем как было: окно скользящее, они выйдут из статистики сами.
    """
    await bot.wait_until_ready()
    for guild in list(getattr(bot, 'guilds', []) or []):
        gid = getattr(guild, 'id', None)
        if not gid or gid in _MIGRATED:
            continue
        _MIGRATED.add(gid)
        try:
            events = message_stats.load_full(gid)
            if not any(isinstance(e, dict) and not e.get('uid') for e in events):
                continue
            by_name = {}
            for m in getattr(guild, 'members', []) or []:
                mid = getattr(m, 'id', None)
                if not mid:
                    continue
                for nm in (getattr(m, 'display_name', None),
                           getattr(m, 'name', None),
                           getattr(m, 'nick', None)):
                    if nm:
                        by_name.setdefault(str(nm).strip().lower(), mid)
            changed = message_stats.attach_uids(
                events, lambda nm: by_name.get(str(nm).strip().lower()))
            if changed:
                message_stats.save_full(gid, events)
                _log.info('activity_stats: к людям привязано %s старых '
                          'записей на %s (смена ника больше не дробит топ)',
                          changed, gid)
        except Exception as _ex:
            _log.debug('activity_stats: миграция имён %s: %s', gid, _ex)


class ActivityStats(commands.Cog):
    """Счётчик сообщений для аналитики (слушатель, без команд)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if not message.guild or message.author.bot or message.webhook_id:
                return
            message_stats.record(
                message.guild.id,
                message.author.display_name or str(message.author),
                getattr(message.channel, 'name', 'неизвестно'),
                user_id=getattr(message.author, 'id', None),
            )
        except Exception as _se:
            _log.debug('activity_stats: подавлено: %s', _se)  # статистика не ломает обработку


async def setup(bot):
    await bot.add_cog(ActivityStats(bot))
    message_stats.start()
    try:
        bot.loop.create_task(_migrate_legacy_names(bot))
    except Exception as _ex:
        _log.debug('activity_stats: задача миграции не запущена: %s', _ex)
