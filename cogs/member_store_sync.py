# -*- coding: utf-8 -*-
"""Состав участников — в файл (services/member_store.py).

Заказ владельца: участники сохраняются В ФАЙЛАХ, а не выкачиваются заново
каждые несколько секунд; бот сам правит файл по событиям — вошёл добавил,
вышел удалил; панель читает файл и видит состав сразу.

Что делает ког
--------------
* ``on_member_join``   → добавить участника в хранилище;
* ``on_member_remove`` → удалить участника из хранилища;
* ``on_member_update`` → обновить (роли/ник/аватар);
* ``on_guild_role_*``  → обновить таблицу ролей гильдии;
* раз в ``FLUSH_SEC``  → сбросить накопленное на диск В РАБОЧЕМ ПОТОКЕ
  (``aflush``): синхронная запись мегабайтного файла в async-обработчике
  морозила бы event loop шлюза;
* на старте            → если файла ещё нет, засеять состав из живого кэша.

Сами события диск не трогают — правки копятся в памяти, поэтому вход/выход
участника не стоит записи на диск.
"""
import asyncio

import discord
from discord.ext import commands

try:
    from logger import get_logger
    _log = get_logger('member_store_sync')
except Exception:                                     # noqa: BLE001
    import logging
    _log = logging.getLogger('member_store_sync')

from services import member_store as MS


class MemberStoreSync(commands.Cog):
    """Держит data/members_<gid>.json в соответствии с составом сервера."""

    def __init__(self, bot):
        self.bot = bot
        self._flusher = None

    # ── старт: засеять файл, если его ещё нет ────────────────────────────
    async def _seed(self, guild):
        gid = str(getattr(guild, 'id', '') or '')
        if not gid:
            return
        try:
            if MS.count(gid):
                return                     # файл уже есть — не перезаписываем
            members = list(getattr(guild, 'members', []) or [])
            if not members:
                return
            n = MS.upsert_many(gid, members)
            await MS.aflush(gid)
            _log.info('member_store: %s засеян из кэша (%s участников)', gid, n)
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store seed %s: %s', gid, _ex)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._flusher is None:
            self._flusher = asyncio.create_task(self._flush_loop())
        for g in list(getattr(self.bot, 'guilds', []) or []):
            await self._seed(g)

    @commands.Cog.listener()
    async def on_guild_available(self, guild):
        await self._seed(guild)

    # ── участники ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            MS.upsert(getattr(member.guild, 'id', None), member)
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store join: %s', _ex)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            gid = getattr(member.guild, 'id', None)
            uid = getattr(member, 'id', None)
            if gid and uid and MS.remove(gid, uid):
                _log.debug('member_store: %s вышел — убран из хранилища', uid)
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store remove: %s', _ex)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        try:
            if (before.roles != after.roles
                    or before.display_name != after.display_name
                    or getattr(before, 'avatar', None) != getattr(after, 'avatar', None)):
                MS.upsert(getattr(after.guild, 'id', None), after)
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store update: %s', _ex)

    # ── роли: таблица имён/цветов для пикеров и тегов ────────────────────
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        self._roles_changed(role.guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        self._roles_changed(after.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        self._roles_changed(role.guild)

    def _roles_changed(self, guild):
        try:
            gid = getattr(guild, 'id', None)
            if gid:
                MS.replace_guild_roles(gid, getattr(guild, 'roles', []) or [])
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store roles: %s', _ex)

    # ── сброс накопленного на диск (в рабочем потоке) ────────────────────
    async def _flush_loop(self):
        try:
            while True:
                await asyncio.sleep(MS.FLUSH_SEC)
                try:
                    if MS.needs_flush():
                        await MS.aflush()
                except Exception as _ex:                  # noqa: BLE001
                    _log.debug('member_store flush loop: %s', _ex)
        except asyncio.CancelledError:
            raise

    async def cog_unload(self):
        if self._flusher is not None:
            self._flusher.cancel()
            self._flusher = None
        try:
            await MS.aflush()          # не теряем последние входы/выходы
        except Exception as _ex:                          # noqa: BLE001
            _log.debug('member_store unload flush: %s', _ex)


async def setup(bot):
    await bot.add_cog(MemberStoreSync(bot))
