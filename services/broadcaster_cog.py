# -*- coding: utf-8 -*-
"""Slash /create tribune, /delete tribune, /edit tribune + лав-румы и пожелания."""
from __future__ import annotations

import traceback
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from logger import get_logger
from services.broadcaster_catalog import all_tribunes, tribune_by_key
from services.broadcaster_config import load_cfg, wishes_cfg
from services.broadcaster_logic import (
    can_edit_schedule,
    can_touch,
    due_wish_slots,
    member_is_broadcaster,
    parse_start,
    pick_wish,
    validate_start,
    zone,
)
from services import broadcaster_actions as actions
from services import broadcaster_store as store

log = get_logger('broadcaster')


def _role_ids(member) -> list:
    return [int(r.id) for r in (getattr(member, 'roles', None) or [])]


class DateTimeModal(discord.ui.Modal, title='Дата и время'):
    date = discord.ui.TextInput(
        label='Дата',
        placeholder='ДД.ММ.ГГГГ',
        max_length=10,
        required=True,
    )
    time = discord.ui.TextInput(
        label='Время',
        placeholder='ЧЧ:ММ',
        max_length=5,
        required=True,
    )

    def __init__(self, cog: 'BroadcasterCog', *, mode: str, catalog_key: str,
                 tribune_id: str = ''):
        super().__init__()
        self.cog = cog
        self.mode = mode
        self.catalog_key = catalog_key
        self.tribune_id = tribune_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.mode == 'create':
            await self.cog.finish_create(
                interaction, self.catalog_key,
                str(self.date.value or ''), str(self.time.value or ''),
            )
        else:
            await self.cog.finish_edit(
                interaction, self.tribune_id, self.catalog_key,
                str(self.date.value or ''), str(self.time.value or ''),
            )


class CreateView(discord.ui.View):
    def __init__(self, cog: 'BroadcasterCog'):
        super().__init__(timeout=300)
        self.cog = cog
        options = []
        for item in all_tribunes()[:25]:
            options.append(discord.SelectOption(
                label=item['title'][:100],
                value=item['key'],
                description=(item.get('blurb') or '')[:100],
            ))
        select = discord.ui.Select(
            placeholder='Название трибуны',
            options=options,
            min_values=1,
            max_values=1,
        )

        async def _pick(interaction: discord.Interaction):
            if not await cog.guard(interaction):
                return
            key = select.values[0]
            await interaction.response.send_modal(
                DateTimeModal(cog, mode='create', catalog_key=key)
            )

        select.callback = _pick
        self.add_item(select)


class DeleteView(discord.ui.View):
    def __init__(self, cog: 'BroadcasterCog', rows: list, tz, actor_id: int):
        super().__init__(timeout=300)
        options = []
        for row in rows[:25]:
            mine = 'своя' if int(row.get('owner_id') or 0) == int(actor_id) else 'чужая'
            try:
                start = datetime.fromisoformat(row['starts_at']).astimezone(tz)
                when = start.strftime('%d.%m %H:%M')
            except Exception:
                when = '—'
            options.append(discord.SelectOption(
                label=f"{row.get('title') or 'трибуна'}"[:100],
                value=row['id'],
                description=f'{when} · {mine}'[:100],
            ))
        select = discord.ui.Select(
            placeholder='Какую трибуну удалить',
            options=options,
            min_values=1,
            max_values=1,
        )

        async def _pick(interaction: discord.Interaction):
            await cog.finish_delete(interaction, select.values[0])

        select.callback = _pick
        self.add_item(select)


class EditPickView(discord.ui.View):
    def __init__(self, cog: 'BroadcasterCog', rows: list):
        super().__init__(timeout=300)
        options = []
        for row in rows[:25]:
            options.append(discord.SelectOption(
                label=(row.get('title') or 'трибуна')[:100],
                value=row['id'],
                description=(row.get('status') or '')[:100],
            ))
        select = discord.ui.Select(
            placeholder='Какую трибуну править',
            options=options,
            min_values=1,
            max_values=1,
        )

        async def _pick(interaction: discord.Interaction):
            await cog.begin_edit(interaction, select.values[0])

        select.callback = _pick
        self.add_item(select)


class EditNameView(discord.ui.View):
    def __init__(self, cog: 'BroadcasterCog', tribune_id: str, current_key: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.tribune_id = tribune_id
        self.catalog_key = current_key
        options = []
        for item in all_tribunes()[:25]:
            options.append(discord.SelectOption(
                label=item['title'][:100],
                value=item['key'],
                description=(item.get('blurb') or '')[:100],
                default=(item['key'] == current_key),
            ))
        select = discord.ui.Select(
            placeholder='Новое название',
            options=options,
            min_values=1,
            max_values=1,
        )

        async def _pick(interaction: discord.Interaction):
            self.catalog_key = select.values[0]
            await interaction.response.defer()

        select.callback = _pick
        self.add_item(select)

        button = discord.ui.Button(
            label='Дата и время',
            style=discord.ButtonStyle.secondary,
        )

        async def _next(interaction: discord.Interaction):
            row = store.get_tribune(self.tribune_id) or {}
            modal = DateTimeModal(
                cog, mode='edit', catalog_key=self.catalog_key,
                tribune_id=self.tribune_id,
            )
            try:
                cfg = load_cfg()
                start = datetime.fromisoformat(row.get('starts_at') or '')
                local = start.astimezone(zone(cfg.get('timezone')))
                modal.date.default = local.strftime('%d.%m.%Y')
                modal.time.default = local.strftime('%H:%M')
            except Exception:
                pass
            await interaction.response.send_modal(modal)

        button.callback = _next
        self.add_item(button)


class BroadcasterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._loops_started = False
        self._love_lock: set[int] = set()

    create_group = app_commands.Group(name='create', description='Создать')
    delete_group = app_commands.Group(name='delete', description='Удалить')
    edit_group = app_commands.Group(name='edit', description='Изменить')

    async def cog_load(self):
        store.ensure()

    async def cog_unload(self):
        for loop in (self._open_loop, self._wish_loop, self._delete_loop):
            if loop.is_running():
                loop.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: Exception):
        log.error('broadcaster command: %s\n%s', error, traceback.format_exc())
        text = f'Не вышло: {error}'
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except Exception:
            pass

    def _cfg(self) -> dict:
        return load_cfg()

    async def guard(self, interaction: discord.Interaction) -> bool:
        cfg = self._cfg()
        if interaction.guild is None:
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return False
        want = int(cfg.get('guild_id') or 0)
        if want and int(interaction.guild.id) != want:
            await interaction.response.send_message(
                'Этот сервер не подключён к Broadcaster.', ephemeral=True)
            return False
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(int(interaction.user.id))
        role_id = int(cfg.get('broadcaster_role_id') or 0)
        if not member_is_broadcaster(_role_ids(member), role_id):
            if interaction.response.is_done():
                await interaction.followup.send(
                    'Команда только для роли Broadcaster.', ephemeral=True)
            else:
                await interaction.response.send_message(
                    'Команда только для роли Broadcaster.', ephemeral=True)
            return False
        return True

    def _parse_when(self, date_s: str, time_s: str, cfg: dict):
        tz = zone(cfg.get('timezone'))
        local, err = parse_start(date_s, time_s, tz)
        if err or local is None:
            return None, err or 'Неверные дата и время'
        bad = validate_start(local, datetime.now(tz))
        if bad:
            return None, bad
        return local, ''

    @create_group.command(name='tribune', description='Создать трибуну')
    async def create_tribune(self, interaction: discord.Interaction):
        if not await self.guard(interaction):
            return
        await interaction.response.send_message(
            'Выбери трибуну из базы. Потом дата и время.',
            view=CreateView(self),
            ephemeral=True,
        )

    async def finish_create(self, interaction, catalog_key, date_s, time_s):
        if not await self.guard(interaction):
            return
        cfg = self._cfg()
        local, err = self._parse_when(date_s, time_s, cfg)
        if err or local is None:
            await interaction.response.send_message(err or 'Неверное время', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, text, _row = await actions.create_tribune(
            interaction.guild, cfg,
            owner_id=int(interaction.user.id),
            catalog_key=catalog_key,
            start=local,
        )
        await interaction.followup.send(text, ephemeral=True)

    @delete_group.command(name='tribune', description='Удалить свою трибуну')
    async def delete_tribune_cmd(self, interaction: discord.Interaction):
        if not await self.guard(interaction):
            return
        rows = store.list_live(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                'Через бота ещё нет живых трибун.', ephemeral=True)
            return
        tz = zone(self._cfg().get('timezone'))
        await interaction.response.send_message(
            'Все трибуны бота. Удалить можно только свою.',
            view=DeleteView(self, rows, tz, int(interaction.user.id)),
            ephemeral=True,
        )

    async def finish_delete(self, interaction, tribune_id: str):
        if not await self.guard(interaction):
            return
        row = store.get_tribune(tribune_id)
        ok, why = can_touch(interaction.user.id, row)
        if not ok:
            await interaction.response.send_message(why, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, text = await actions.delete_tribune(interaction.guild, row)
        await interaction.followup.send(text, ephemeral=True)

    @edit_group.command(name='tribune', description='Изменить свою трибуну')
    async def edit_tribune_cmd(self, interaction: discord.Interaction):
        if not await self.guard(interaction):
            return
        rows = store.list_live(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                'Нет трибун, которые можно править.', ephemeral=True)
            return
        await interaction.response.send_message(
            'Выбери трибуну. Чужую править нельзя.',
            view=EditPickView(self, rows),
            ephemeral=True,
        )

    async def begin_edit(self, interaction, tribune_id: str):
        if not await self.guard(interaction):
            return
        row = store.get_tribune(tribune_id)
        ok, why = can_touch(interaction.user.id, row)
        if not ok:
            await interaction.response.send_message(why, ephemeral=True)
            return
        view = EditNameView(self, tribune_id, row.get('catalog_key') or '')
        await interaction.response.edit_message(
            content=f'Трибуна **{row.get("title")}**. Название, потом дата и время.',
            view=view,
        )

    async def finish_edit(self, interaction, tribune_id, catalog_key, date_s, time_s):
        if not await self.guard(interaction):
            return
        row = store.get_tribune(tribune_id)
        ok, why = can_touch(interaction.user.id, row)
        if not ok:
            await interaction.response.send_message(why, ephemeral=True)
            return
        cfg = self._cfg()
        local, err = self._parse_when(date_s, time_s, cfg)
        if err or local is None:
            await interaction.response.send_message(err or 'Неверное время', ephemeral=True)
            return
        change_time = True
        schedule_ok, schedule_why = can_edit_schedule(row)
        if not schedule_ok:
            # имя меняем, время оставляем прежним
            change_time = False
            try:
                local = datetime.fromisoformat(row['starts_at'])
            except Exception:
                await interaction.response.send_message(schedule_why, ephemeral=True)
                return
        if not tribune_by_key(catalog_key):
            await interaction.response.send_message('Такой трибуны нет в базе', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, text = await actions.edit_tribune(
            interaction.guild, cfg, row,
            catalog_key=catalog_key, start=local, change_time=change_time,
        )
        if not change_time:
            text = f'{text}\n{schedule_why}'
        await interaction.followup.send(text, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        cfg = self._cfg()
        guild = self.bot.get_guild(int(cfg.get('guild_id') or 0))
        if guild is not None:
            try:
                await actions.ensure_love_lobby(guild, cfg)
            except Exception as ex:
                log.warning('love lobby: %s', ex)
        if self._loops_started:
            return
        self._loops_started = True
        if not self._open_loop.is_running():
            self._open_loop.start()
        if not self._wish_loop.is_running():
            self._wish_loop.start()
        if not self._delete_loop.is_running():
            self._delete_loop.start()
        log.info('broadcaster loops started')

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        cfg = self._cfg()
        if int(guild.id) != int(cfg.get('guild_id') or 0):
            return
        try:
            await actions.ensure_love_lobby(guild, cfg)
        except Exception as ex:
            log.warning('love lobby on join: %s', ex)
        try:
            synced = await self.bot.tree.sync(guild=guild)
            log.info('slash sync after join → %s', [c.name for c in (synced or [])])
        except Exception as ex:
            log.warning('sync after join: %s', ex)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member is None or getattr(member, 'bot', False):
            return
        guild = member.guild
        cfg = self._cfg()
        want = int(cfg.get('guild_id') or 0)
        if want and int(guild.id) != want:
            return
        lobby_id = int(store.meta_get(f'love_lobby:{guild.id}') or 0)
        joined = after.channel
        left = before.channel
        if joined is not None and int(joined.id) == lobby_id and (
                left is None or int(left.id) != lobby_id):
            if int(member.id) in self._love_lock:
                return
            self._love_lock.add(int(member.id))
            try:
                await actions.spawn_love_room(guild, cfg, member, joined)
            except Exception as ex:
                log.warning('spawn love: %s', ex)
            finally:
                self._love_lock.discard(int(member.id))
        if left is not None and store.is_love(int(left.id)):
            try:
                await actions.delete_empty_love(left)
            except Exception as ex:
                log.warning('empty love: %s', ex)

    @tasks.loop(seconds=20)
    async def _open_loop(self):
        try:
            now = datetime.now(timezone.utc).isoformat()
            for row in store.due_tribunes(now):
                if not store.claim_open(row['id']):
                    continue
                cfg = self._cfg()
                guild = self.bot.get_guild(int(row['guild_id']))
                if guild is None:
                    store.release_open(row['id'])
                    continue
                ok, why = await actions.open_tribune(guild, cfg, row)
                if not ok:
                    log.warning('open tribune %s: %s', row['id'], why)
                    store.release_open(row['id'])
                else:
                    log.info('tribune opened %s %s', row['id'], row.get('title'))
        except Exception as ex:
            log.error('open loop: %s\n%s', ex, traceback.format_exc())

    @_open_loop.before_loop
    async def _open_wait(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=20)
    async def _wish_loop(self):
        try:
            cfg = self._cfg()
            w = wishes_cfg(cfg)
            tz = zone(w.get('timezone') or cfg.get('timezone'))
            now = datetime.now(tz)
            due = due_wish_slots(
                now, w.get('times') or [], store.sent_wish_slots(),
                grace_minutes=20,
            )
            if not due:
                return
            guild = self.bot.get_guild(int(cfg.get('guild_id') or 0))
            if guild is None:
                return
            channel = await self._wish_channel(guild, w)
            if channel is None:
                log.info('wish channel is not set')
                return
            deck, last = store.wish_memory()
            for slot in due:
                if not store.claim_wish_slot(slot):
                    continue
                text, deck, last = pick_wish(w.get('messages') or [], deck, last)
                if not text:
                    store.release_wish_slot(slot)
                    continue
                try:
                    msg = await channel.send(text)
                except Exception as ex:
                    log.warning('wish send: %s', ex)
                    store.release_wish_slot(slot)
                    continue
                delay = max(1, int(w.get('delete_after_minutes') or 30))
                delete_at = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()
                store.schedule_wish_delete(int(msg.id), int(channel.id), delete_at)
                store.save_wish_memory(deck, last or '')
                log.info('wish sent slot=%s', slot)
        except Exception as ex:
            log.error('wish loop: %s\n%s', ex, traceback.format_exc())

    async def _wish_channel(self, guild, wishes: dict):
        try:
            cid = int(wishes.get('channel_id') or 0)
        except Exception:
            cid = 0
        if cid:
            found = guild.get_channel(cid)
            if found is not None:
                return found
        for ch in list(getattr(guild, 'text_channels', []) or []):
            low = (ch.name or '').lower()
            if 'пожелан' in low:
                return ch
        return None

    @_wish_loop.before_loop
    async def _wish_wait(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=30)
    async def _delete_loop(self):
        try:
            now = datetime.now(timezone.utc).isoformat()
            for row in store.due_wish_deletes(now):
                channel = self.bot.get_channel(int(row['channel_id']))
                if channel is None:
                    store.finish_wish_delete(int(row['message_id']))
                    continue
                try:
                    msg = await channel.fetch_message(int(row['message_id']))
                    await msg.delete()
                except discord.NotFound:
                    pass
                except Exception as ex:
                    log.warning('wish delete: %s', ex)
                    continue
                store.finish_wish_delete(int(row['message_id']))
        except Exception as ex:
            log.error('wish delete loop: %s', ex)

    @_delete_loop.before_loop
    async def _delete_wait(self):
        await self.bot.wait_until_ready()


def command_paths(bot: commands.Bot) -> list[str]:
    """Имена как в меню: «create tribune»."""
    out = []
    for cmd in bot.tree.get_commands():
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.commands:
                out.append(f'{cmd.name} {sub.name}')
        else:
            out.append(cmd.name)
    return out
