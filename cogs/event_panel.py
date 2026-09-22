# -*- coding: utf-8 -*-
"""Панель событий Discord — бот сам постит embed + кнопки в канал.

Команда /event-panel (Event Admin / Event Mod / админ) публикует панель
в Discord. Целевой канал: опция `channel` → Config.EVENT_PANEL_CHANNEL_ID
→ канал вызова. Участники жмут «Записаться»; Event Admin
(1551527644326002748) и Event Mod (852634463535759461) — анонс и закрытие
записи. Persistent View переживает рестарт бота.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger('event_panel')

EVENT_ADMIN_ROLE_ID = 1551527644326002748
EVENT_MOD_ROLE_ID = 852634463535759461
EVENT_STAFF_ROLE_IDS = (EVENT_ADMIN_ROLE_ID, EVENT_MOD_ROLE_ID)
PANEL_COLOR = 0x5EC8FF


def configured_panel_channel_id() -> int:
    """Snowflake канала из .env / Config (0 = не задан)."""
    try:
        from config import Config
        return int(getattr(Config, 'EVENT_PANEL_CHANNEL_ID', 0) or 0)
    except Exception:
        return 0


def target_channel_id(cfg: dict | None = None, guild_id: int | None = None) -> int:
    """Канал назначения из панели (target_channel_id), 0 если не задан."""
    if cfg is None and guild_id is not None:
        cfg = load_panel_cfg(guild_id)
    cfg = cfg or {}
    try:
        return int(cfg.get('target_channel_id') or 0)
    except (TypeError, ValueError):
        return 0


def set_target_channel_id(guild_id: int, channel_id: int) -> dict:
    """Сохранить канал назначения панели (из веб-UI / маршрутов)."""
    cfg = load_panel_cfg(guild_id)
    cfg['target_channel_id'] = int(channel_id or 0)
    save_panel_cfg(guild_id, cfg)
    return cfg


async def resolve_panel_channel(
    guild: discord.Guild,
    interaction: discord.Interaction | None = None,
    channel_opt: discord.abc.GuildChannel | None = None,
    cfg: dict | None = None,
) -> discord.abc.Messageable | None:
    """Куда слать/обновлять панель.

    Приоритет: опция команды → target_channel_id (панель) →
    EVENT_PANEL_CHANNEL_ID → cfg.channel_id (последний пост) →
    канал вызова команды.
    """
    if cfg is None and guild is not None:
        cfg = load_panel_cfg(guild.id)
    candidates: list[int] = []
    if channel_opt is not None and getattr(channel_opt, 'id', None):
        candidates.append(int(channel_opt.id))
    tgt = target_channel_id(cfg)
    if tgt:
        candidates.append(tgt)
    fixed = configured_panel_channel_id()
    if fixed:
        candidates.append(fixed)
    if cfg and cfg.get('channel_id'):
        try:
            candidates.append(int(cfg['channel_id']))
        except (TypeError, ValueError):
            pass
    if interaction is not None and getattr(interaction, 'channel', None) is not None:
        cid = getattr(interaction.channel, 'id', None)
        if cid:
            candidates.append(int(cid))

    seen = set()
    for cid in candidates:
        if not cid or cid in seen:
            continue
        seen.add(cid)
        ch = guild.get_channel(cid)
        if ch is None:
            try:
                ch = await guild.fetch_channel(cid)
            except Exception as ex:
                log.debug('event panel fetch_channel %s: %s', cid, ex)
                continue
        if ch is not None and hasattr(ch, 'send'):
            return ch
    return None


async def publish_event_panel(
    guild: discord.Guild,
    *,
    channel: discord.abc.Messageable | None = None,
    posted_by: str | int | None = None,
    interaction: discord.Interaction | None = None,
) -> tuple[discord.Message, dict]:
    """Опубликовать или обновить панель в целевом канале.

    Возвращает (message, cfg). Кидает ValueError если канал не найден.
    """
    cfg = load_panel_cfg(guild.id)
    target = channel or await resolve_panel_channel(
        guild, interaction=interaction, cfg=cfg)
    if target is None:
        raise ValueError(
            'Не найден канал. Задай канал в панели /events, '
            'EVENT_PANEL_CHANNEL_ID или опцию channel в /event-panel.')

    cfg.setdefault('registration_open', True)
    cfg.setdefault('signups', [])
    embed = panel_embed(guild, cfg)
    view = EventPanelView()

    msg = None
    mid = cfg.get('message_id')
    same_ch = (
        mid
        and cfg.get('channel_id')
        and int(cfg['channel_id']) == int(getattr(target, 'id', 0) or 0)
    )
    if same_ch:
        try:
            msg = await target.fetch_message(int(mid))
            await msg.edit(embed=embed, view=view)
        except Exception as ex:
            log.debug('event-panel edit existing: %s', ex)
            msg = None
    if msg is None:
        msg = await target.send(embed=embed, view=view)

    cfg['message_id'] = msg.id
    cfg['channel_id'] = getattr(target, 'id', None)
    if posted_by is not None:
        cfg['posted_by'] = str(posted_by)
    cfg['posted_at'] = datetime.now(timezone.utc).isoformat()
    save_panel_cfg(guild.id, cfg)
    return msg, cfg


def _cfg_path(guild_id: int) -> str:
    return f'data/event_panel_{int(guild_id)}.json'


def load_panel_cfg(guild_id: int) -> dict:
    path = _cfg_path(guild_id)
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_panel_cfg(guild_id: int, data: dict) -> None:
    os.makedirs('data', exist_ok=True)
    path = _cfg_path(guild_id)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def is_event_mod(member: discord.Member) -> bool:
    """Event Admin, Event Mod, manage_guild / admin / владелец бота."""
    if member is None:
        return False
    try:
        if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
            return True
    except Exception:
        pass
    try:
        from config import Config
        if int(member.id) in Config.all_owner_ids():
            return True
    except Exception:
        pass
    roles = getattr(member, 'roles', None) or []
    have = {int(getattr(r, 'id', 0) or 0) for r in roles}
    return any(rid in have for rid in EVENT_STAFF_ROLE_IDS)


def panel_embed(guild: discord.Guild, cfg: dict | None = None) -> discord.Embed:
    cfg = cfg or {}
    title = (cfg.get('title') or 'События сервера').strip()
    desc = cfg.get('description') or (
        'Анонсы и запись на ивенты сервера.\n'
        'Нажми **Записаться**, чтобы отметить интерес.\n'
        f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
    )
    e = discord.Embed(
        title=title[:256],
        description=str(desc)[:4000],
        color=PANEL_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    open_reg = cfg.get('registration_open', True)
    e.add_field(
        name='Запись',
        value='**Открыта**' if open_reg else '**Закрыта**',
        inline=True,
    )
    signup = cfg.get('signups') or []
    e.add_field(name='Участников', value=f'**{len(signup)}**', inline=True)
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text='Hakumo · /event-panel')
    return e


class EventAnnounceModal(discord.ui.Modal, title='Анонс события'):
    title_in = discord.ui.TextInput(
        label='Название', placeholder='Игровой вечер / турнир / кино',
        max_length=100, required=True)
    when_in = discord.ui.TextInput(
        label='Когда', placeholder='Сегодня 20:00 МСК',
        max_length=100, required=True)
    details_in = discord.ui.TextInput(
        label='Детали', style=discord.TextStyle.paragraph,
        placeholder='Где собираемся, правила, награды…',
        max_length=1000, required=False)

    def __init__(self, cog: 'EventPanel'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Только Event Mod может анонсировать.', ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        cfg['title'] = str(self.title_in.value).strip()
        cfg['description'] = (
            f"**Когда:** {str(self.when_in.value).strip()}\n"
            f"{(str(self.details_in.value or '').strip() or 'Подробности у ведущих.')}\n\n"
            'Нажми **Записаться** ниже.'
        )
        cfg['registration_open'] = True
        cfg['signups'] = []
        cfg['last_announce_by'] = str(interaction.user.id)
        cfg['last_announce_at'] = datetime.now(timezone.utc).isoformat()
        save_panel_cfg(guild.id, cfg)

        embed = panel_embed(guild, cfg)
        view = EventPanelView()
        # Обновить существующее сообщение панели, иначе отправить новое
        msg = None
        channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
        if channel is None:
            return await interaction.response.send_message(
                'Не найден канал для панели. Задай EVENT_PANEL_CHANNEL_ID '
                'или укажи канал в /event-panel.',
                ephemeral=True)
        mid = cfg.get('message_id')
        if mid and channel:
            try:
                msg = await channel.fetch_message(int(mid))
                await msg.edit(embed=embed, view=view)
            except Exception as ex:
                log.debug('event announce edit: %s', ex)
                msg = None
        if msg is None:
            msg = await channel.send(embed=embed, view=view)
            cfg['message_id'] = msg.id
            cfg['channel_id'] = channel.id
            save_panel_cfg(guild.id, cfg)

        await interaction.response.send_message(
            f'✅ Анонс опубликован в {channel.mention}', ephemeral=True)
        # пинг роли event mod + заинтересованных — мягко
        try:
            await channel.send(
                f'<@&{EVENT_ADMIN_ROLE_ID}> <@&{EVENT_MOD_ROLE_ID}> '
                f'новый анонс: **{cfg["title"]}**',
                delete_after=30)
        except Exception:
            pass


class EventPanelView(discord.ui.View):
    """Persistent кнопки панели событий."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label='Записаться', style=discord.ButtonStyle.success,
        custom_id='event_panel:signup')
    async def signup(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        cfg = load_panel_cfg(guild.id)
        if not cfg.get('registration_open', True):
            return await interaction.response.send_message(
                'Запись на это событие закрыта.', ephemeral=True)
        uid = str(interaction.user.id)
        signups = list(cfg.get('signups') or [])
        if uid in signups:
            return await interaction.response.send_message(
                'Ты уже в списке 👍', ephemeral=True)
        signups.append(uid)
        cfg['signups'] = signups
        save_panel_cfg(guild.id, cfg)
        try:
            if interaction.message:
                await interaction.message.edit(
                    embed=panel_embed(guild, cfg), view=self)
        except Exception as ex:
            log.debug('signup edit: %s', ex)
        await interaction.response.send_message(
            f'✅ Ты в списке ({len(signups)} чел.)', ephemeral=True)

    @discord.ui.button(
        label='Анонс', style=discord.ButtonStyle.primary,
        custom_id='event_panel:announce')
    async def announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Кнопка только для Event Mod.', ephemeral=True)
        await interaction.response.send_modal(EventAnnounceModal(None))

    @discord.ui.button(
        label='Запись', style=discord.ButtonStyle.secondary,
        custom_id='event_panel:close')
    async def close_reg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Кнопка только для Event Mod.', ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        cfg['registration_open'] = not cfg.get('registration_open', True)
        save_panel_cfg(guild.id, cfg)
        try:
            if interaction.message:
                await interaction.message.edit(
                    embed=panel_embed(guild, cfg), view=self)
        except Exception as ex:
            log.debug('close_reg edit: %s', ex)
        state = 'открыта' if cfg.get('registration_open') else 'закрыта'
        await interaction.response.send_message(
            f'Запись теперь **{state}**.', ephemeral=True)

    @discord.ui.button(
        label='Список', style=discord.ButtonStyle.secondary,
        custom_id='event_panel:list')
    async def show_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Список видят только Event Mod.', ephemeral=True)
        cfg = load_panel_cfg(interaction.guild.id)
        signups = cfg.get('signups') or []
        if not signups:
            return await interaction.response.send_message(
                'Пока никто не записался.', ephemeral=True)
        mentions = ', '.join(f'<@{u}>' for u in signups[:40])
        more = f'\n…и ещё {len(signups) - 40}' if len(signups) > 40 else ''
        await interaction.response.send_message(
            f'**Записались ({len(signups)}):**\n{mentions}{more}',
            ephemeral=True)


class EventPanel(commands.Cog):
    """Публикация панели событий в канал."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name='event-panel',
        description='Опубликовать панель событий (Event Mod / админ)')
    @app_commands.describe(
        channel='Куда отправить панель (иначе EVENT_PANEL_CHANNEL_ID или этот канал)')
    async def event_panel_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Нужна роль Event Mod или право Manage Server.', ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        cfg = load_panel_cfg(interaction.guild.id)
        try:
            target = await resolve_panel_channel(
                interaction.guild, interaction, channel_opt=channel, cfg=cfg)
            if target is None:
                raise ValueError('channel')
            _msg, cfg = await publish_event_panel(
                interaction.guild,
                channel=target,
                posted_by=interaction.user.id,
                interaction=interaction,
            )
        except ValueError:
            return await interaction.followup.send(
                '❌ Не найден канал. Укажи опцию `channel`, задай канал '
                'на странице /events или `EVENT_PANEL_CHANNEL_ID` в .env.',
                ephemeral=True)
        except Exception as ex:
            log.exception('event-panel publish: %s', ex)
            return await interaction.followup.send(
                f'❌ Не удалось опубликовать: {ex}', ephemeral=True)

        await interaction.followup.send(
            f'✅ Панель событий в <#{cfg.get("channel_id")}>. '
            f'Event Admin: <@&{EVENT_ADMIN_ROLE_ID}> · '
            f'Event Mod: <@&{EVENT_MOD_ROLE_ID}>',
            ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.add_view(EventPanelView())
        except Exception as ex:
            log.debug('add_view EventPanelView: %s', ex)


async def setup(bot):
    from config import Config
    await bot.add_cog(EventPanel(bot), guilds=Config.guild_objects())
