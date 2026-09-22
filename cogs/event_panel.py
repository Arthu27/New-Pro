# -*- coding: utf-8 -*-
"""Панель событий Discord — запись, анонс и красивый старт игры.

Команда /event-panel (Event Admin / Event Mod / админ) публикует панель.
Участники жмут «Записаться»; ведущие — «Анонс», затем «▶ Старт»
(пингует записавшихся + зовёт в войс Event-бота). Persistent View.
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

# Фазы: ожидание → набор → игра → финиш
PHASE_IDLE = 'idle'
PHASE_OPEN = 'open'
PHASE_LIVE = 'live'
PHASE_ENDED = 'ended'

COLOR_IDLE = 0x5EC8FF
COLOR_OPEN = 0x2ECC71
COLOR_LIVE = 0xF0A202
COLOR_ENDED = 0x7A8699
PANEL_COLOR = COLOR_IDLE  # совместимость

DEFAULT_EVENT_VOICE = 1550986919981351043


def configured_panel_channel_id() -> int:
    """Snowflake канала из .env / Config (0 = не задан)."""
    try:
        from config import Config
        return int(getattr(Config, 'EVENT_PANEL_CHANNEL_ID', 0) or 0)
    except Exception:
        return 0


def event_voice_channel_id() -> int:
    """Голосовой канал для старта (Event-бот stay)."""
    try:
        from services.event_voice_bot import _resolve_event_voice_channel_id
        cid = int(_resolve_event_voice_channel_id() or 0)
        if cid:
            return cid
    except Exception:
        pass
    env = (os.environ.get('EVENT_VOICE_CHANNEL_ID') or '').strip()
    if env.isdigit():
        return int(env)
    return DEFAULT_EVENT_VOICE


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


def normalize_phase(cfg: dict | None) -> str:
    """Вывести фазу из cfg (с учётом старых полей)."""
    cfg = cfg or {}
    raw = str(cfg.get('phase') or '').strip().lower()
    if raw in (PHASE_IDLE, PHASE_OPEN, PHASE_LIVE, PHASE_ENDED):
        return raw
    if cfg.get('live') or cfg.get('started_at'):
        return PHASE_LIVE
    if cfg.get('registration_open', True):
        return PHASE_OPEN if (cfg.get('title') or cfg.get('signups')) else PHASE_IDLE
    return PHASE_ENDED if cfg.get('ended_at') else PHASE_OPEN


def phase_label(phase: str) -> str:
    return {
        PHASE_IDLE: 'Ожидание',
        PHASE_OPEN: 'Набор открыт',
        PHASE_LIVE: 'Игра идёт',
        PHASE_ENDED: 'Завершено',
    }.get(phase, 'Ожидание')


def phase_color(phase: str) -> int:
    return {
        PHASE_IDLE: COLOR_IDLE,
        PHASE_OPEN: COLOR_OPEN,
        PHASE_LIVE: COLOR_LIVE,
        PHASE_ENDED: COLOR_ENDED,
    }.get(phase, COLOR_IDLE)


def panel_embed(guild: discord.Guild, cfg: dict | None = None) -> discord.Embed:
    cfg = cfg or {}
    phase = normalize_phase(cfg)
    title = (cfg.get('title') or 'События сервера').strip()
    voice_id = event_voice_channel_id()

    if phase == PHASE_LIVE:
        default_desc = (
            f'**Игра запущена.** Заходите в голосовой <#{voice_id}>\n'
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
    elif phase == PHASE_ENDED:
        default_desc = (
            'Ивент завершён. Ждите следующий анонс.\n'
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
    else:
        default_desc = (
            'Анонсы и запись на ивенты сервера.\n'
            '1. Жми **Записаться**\n'
            '2. Когда ведущий нажмёт **▶ Старт** — зайди в войс\n'
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
    desc = cfg.get('description') or default_desc

    e = discord.Embed(
        title=title[:256],
        description=str(desc)[:4000],
        color=phase_color(phase),
        timestamp=datetime.now(timezone.utc),
    )
    e.add_field(name='Статус', value=f'**{phase_label(phase)}**', inline=True)
    open_reg = bool(cfg.get('registration_open', True)) and phase not in (
        PHASE_LIVE, PHASE_ENDED)
    e.add_field(
        name='Запись',
        value='**Открыта**' if open_reg else '**Закрыта**',
        inline=True,
    )
    signup = cfg.get('signups') or []
    e.add_field(name='Участников', value=f'**{len(signup)}**', inline=True)
    e.add_field(
        name='Голосовой',
        value=f'<#{voice_id}>',
        inline=True,
    )
    if phase == PHASE_LIVE and cfg.get('started_at'):
        e.add_field(
            name='Старт',
            value=f'<t:{_iso_to_ts(cfg["started_at"])}:R>'
            if _iso_to_ts(cfg['started_at']) else 'сейчас',
            inline=True,
        )
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text='Hakumo Events · /event-panel · Анонс → Запись → ▶ Старт')
    return e


def start_announce_embed(guild: discord.Guild, cfg: dict,
                         started_by: discord.abc.User | None = None) -> discord.Embed:
    """Красивый пост «игра началась»."""
    title = (cfg.get('title') or 'Ивент').strip()
    voice_id = event_voice_channel_id()
    signups = list(cfg.get('signups') or [])
    e = discord.Embed(
        title=f'▶  Старт · {title}'[:256],
        description=(
            f'Сбор в голосовом канале <#{voice_id}>\n'
            f'Участников в списке: **{len(signups)}**\n\n'
            'Заходите, микрофон по желанию — ведущие уже на месте.'
        ),
        color=COLOR_LIVE,
        timestamp=datetime.now(timezone.utc),
    )
    if started_by is not None:
        e.add_field(
            name='Запустил',
            value=getattr(started_by, 'mention', None) or str(started_by),
            inline=True,
        )
    e.add_field(name='Войс', value=f'<#{voice_id}>', inline=True)
    e.add_field(
        name='Ведут',
        value=f'<@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>',
        inline=False,
    )
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text='Hakumo Events · приятной игры')
    return e


def apply_start(cfg: dict, *, by_user_id: str | int | None = None) -> dict:
    """Перевести панель в фазу live (без Discord I/O)."""
    cfg = dict(cfg or {})
    cfg['phase'] = PHASE_LIVE
    cfg['registration_open'] = False
    cfg['live'] = True
    cfg['started_at'] = datetime.now(timezone.utc).isoformat()
    if by_user_id is not None:
        cfg['started_by'] = str(by_user_id)
    cfg.pop('ended_at', None)
    return cfg


def apply_end(cfg: dict, *, by_user_id: str | int | None = None) -> dict:
    """Завершить игру."""
    cfg = dict(cfg or {})
    cfg['phase'] = PHASE_ENDED
    cfg['registration_open'] = False
    cfg['live'] = False
    cfg['ended_at'] = datetime.now(timezone.utc).isoformat()
    if by_user_id is not None:
        cfg['ended_by'] = str(by_user_id)
    return cfg


def _iso_to_ts(iso: str) -> int:
    try:
        raw = str(iso).replace('Z', '+00:00')
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def _signup_mentions(signups: list, limit: int = 35) -> str:
    if not signups:
        return ''
    parts = [f'<@{u}>' for u in signups[:limit]]
    more = f' (+{len(signups) - limit})' if len(signups) > limit else ''
    return ' '.join(parts) + more


async def resolve_panel_channel(
    guild: discord.Guild,
    interaction: discord.Interaction | None = None,
    channel_opt: discord.abc.GuildChannel | None = None,
    cfg: dict | None = None,
) -> discord.abc.Messageable | None:
    """Куда слать/обновлять панель."""
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


async def _refresh_panel_message(
    guild: discord.Guild,
    cfg: dict,
    *,
    interaction: discord.Interaction | None = None,
) -> discord.Message | None:
    channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
    if channel is None:
        return None
    embed = panel_embed(guild, cfg)
    view = EventPanelView()
    mid = cfg.get('message_id')
    msg = None
    if mid:
        try:
            msg = await channel.fetch_message(int(mid))
            await msg.edit(embed=embed, view=view)
        except Exception as ex:
            log.debug('refresh panel edit: %s', ex)
            msg = None
    if msg is None:
        msg = await channel.send(embed=embed, view=view)
        cfg['message_id'] = msg.id
        cfg['channel_id'] = getattr(channel, 'id', None)
        save_panel_cfg(guild.id, cfg)
    return msg


async def publish_event_panel(
    guild: discord.Guild,
    *,
    channel: discord.abc.Messageable | None = None,
    posted_by: str | int | None = None,
    interaction: discord.Interaction | None = None,
) -> tuple[discord.Message, dict]:
    """Опубликовать или обновить панель в целевом канале."""
    cfg = load_panel_cfg(guild.id)
    target = channel or await resolve_panel_channel(
        guild, interaction=interaction, cfg=cfg)
    if target is None:
        raise ValueError(
            'Не найден канал. Задай канал в панели /events, '
            'EVENT_PANEL_CHANNEL_ID или опцию channel в /event-panel.')

    cfg.setdefault('registration_open', True)
    cfg.setdefault('signups', [])
    if not cfg.get('phase'):
        cfg['phase'] = PHASE_OPEN if cfg.get('registration_open', True) else PHASE_IDLE
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


class EventAnnounceModal(discord.ui.Modal, title='Новый ивент'):
    title_in = discord.ui.TextInput(
        label='Название игры / ивента',
        placeholder='Mafia · Among Us · Киновечер',
        max_length=100, required=True)
    when_in = discord.ui.TextInput(
        label='Когда старт', placeholder='Сегодня 20:00 МСК',
        max_length=100, required=True)
    details_in = discord.ui.TextInput(
        label='Детали', style=discord.TextStyle.paragraph,
        placeholder='Правила, слоты, награды… После набора жми ▶ Старт',
        max_length=1000, required=False)

    def __init__(self, cog: 'EventPanel'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Только Event Admin / Event Mod могут анонсировать.',
                ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        cfg['title'] = str(self.title_in.value).strip()
        voice_id = event_voice_channel_id()
        details = (str(self.details_in.value or '').strip()
                   or 'Подробности у ведущих.')
        cfg['description'] = (
            f'**Когда:** {str(self.when_in.value).strip()}\n'
            f'{details}\n\n'
            f'① **Записаться** → ② ждём **▶ Старт** → ③ войс <#{voice_id}>'
        )
        cfg['registration_open'] = True
        cfg['phase'] = PHASE_OPEN
        cfg['live'] = False
        cfg['signups'] = []
        cfg.pop('started_at', None)
        cfg.pop('ended_at', None)
        cfg['last_announce_by'] = str(interaction.user.id)
        cfg['last_announce_at'] = datetime.now(timezone.utc).isoformat()
        save_panel_cfg(guild.id, cfg)

        channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
        if channel is None:
            return await interaction.response.send_message(
                'Не найден канал для панели. Задай EVENT_PANEL_CHANNEL_ID '
                'или укажи канал в /event-panel.',
                ephemeral=True)
        await _refresh_panel_message(guild, cfg, interaction=interaction)
        await interaction.response.send_message(
            f'✅ Анонс в {channel.mention}. Когда все соберутся — жми **▶ Старт**.',
            ephemeral=True)
        try:
            await channel.send(
                f'<@&{EVENT_ADMIN_ROLE_ID}> <@&{EVENT_MOD_ROLE_ID}> '
                f'новый набор: **{cfg["title"]}** — запись открыта',
                delete_after=45)
        except Exception:
            pass


class EventPanelView(discord.ui.View):
    """Persistent кнопки панели событий."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label='Записаться', style=discord.ButtonStyle.success,
        emoji='✋', custom_id='event_panel:signup')
    async def signup(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        cfg = load_panel_cfg(guild.id)
        phase = normalize_phase(cfg)
        if phase == PHASE_LIVE:
            voice_id = event_voice_channel_id()
            return await interaction.response.send_message(
                f'Игра уже идёт — заходи в <#{voice_id}>', ephemeral=True)
        if phase == PHASE_ENDED or not cfg.get('registration_open', True):
            return await interaction.response.send_message(
                'Запись закрыта. Жди следующий анонс.', ephemeral=True)
        uid = str(interaction.user.id)
        signups = list(cfg.get('signups') or [])
        if uid in signups:
            return await interaction.response.send_message(
                'Ты уже в списке. Жди **▶ Старт** от ведущих.', ephemeral=True)
        signups.append(uid)
        cfg['signups'] = signups
        if not cfg.get('phase') or cfg.get('phase') == PHASE_IDLE:
            cfg['phase'] = PHASE_OPEN
        save_panel_cfg(guild.id, cfg)
        try:
            if interaction.message:
                await interaction.message.edit(
                    embed=panel_embed(guild, cfg), view=self)
        except Exception as ex:
            log.debug('signup edit: %s', ex)
        await interaction.response.send_message(
            f'✅ Ты в списке (**{len(signups)}**). Когда жмут **▶ Старт** — '
            f'беги в <#{event_voice_channel_id()}>.',
            ephemeral=True)

    @discord.ui.button(
        label='Анонс', style=discord.ButtonStyle.primary,
        emoji='📣', custom_id='event_panel:announce')
    async def announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Кнопка только для Event Admin / Event Mod.', ephemeral=True)
        await interaction.response.send_modal(EventAnnounceModal(None))

    @discord.ui.button(
        label='Старт', style=discord.ButtonStyle.danger,
        emoji='▶', custom_id='event_panel:start')
    async def start_game(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        """Закрыть набор, пингануть игроков, позвать в войс."""
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Старт только для Event Admin / Event Mod.', ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        cfg = load_panel_cfg(guild.id)
        phase = normalize_phase(cfg)
        if phase == PHASE_LIVE:
            voice_id = event_voice_channel_id()
            return await interaction.response.send_message(
                f'Уже запущено. Войс: <#{voice_id}>', ephemeral=True)

        signups = list(cfg.get('signups') or [])
        cfg = apply_start(cfg, by_user_id=interaction.user.id)
        if not (cfg.get('title') or '').strip():
            cfg['title'] = 'Ивент'
        voice_id = event_voice_channel_id()
        cfg['description'] = (
            f'**Игра идёт.** Сбор в <#{voice_id}>\n'
            f'Участников: **{len(signups)}**\n'
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
        save_panel_cfg(guild.id, cfg)

        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.edit(
                    embed=panel_embed(guild, cfg), view=self)
            else:
                await _refresh_panel_message(guild, cfg, interaction=interaction)
        except Exception as ex:
            log.debug('start edit panel: %s', ex)

        channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
        if channel is not None:
            mentions = _signup_mentions(signups)
            content = (
                f'▶ **Старт!** {mentions}'.strip()
                if mentions else
                f'▶ **Старт!** <@&{EVENT_ADMIN_ROLE_ID}> <@&{EVENT_MOD_ROLE_ID}>'
            )
            try:
                await channel.send(
                    content=content[:1900],
                    embed=start_announce_embed(
                        guild, cfg, started_by=interaction.user),
                    allowed_mentions=discord.AllowedMentions(
                        users=True, roles=True, everyone=False),
                )
            except Exception as ex:
                log.warning('start announce send: %s', ex)

        await interaction.followup.send(
            f'▶ Игра запущена. Запись закрыта, зовём в <#{voice_id}> '
            f'({len(signups)} в списке).',
            ephemeral=True)

    @discord.ui.button(
        label='Запись', style=discord.ButtonStyle.secondary,
        emoji='🔓', custom_id='event_panel:close')
    async def close_reg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Кнопка только для Event Admin / Event Mod.', ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        if normalize_phase(cfg) == PHASE_LIVE:
            return await interaction.response.send_message(
                'Игра уже идёт — сначала **Финиш**, потом снова открой набор.',
                ephemeral=True)
        cfg['registration_open'] = not cfg.get('registration_open', True)
        if cfg['registration_open']:
            cfg['phase'] = PHASE_OPEN
            cfg['live'] = False
        else:
            cfg['phase'] = PHASE_IDLE if not cfg.get('signups') else PHASE_OPEN
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
        emoji='📋', custom_id='event_panel:list', row=1)
    async def show_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Список видят только Event Admin / Event Mod.', ephemeral=True)
        cfg = load_panel_cfg(interaction.guild.id)
        signups = cfg.get('signups') or []
        if not signups:
            return await interaction.response.send_message(
                'Пока никто не записался.', ephemeral=True)
        mentions = ', '.join(f'<@{u}>' for u in signups[:40])
        more = f'\n…и ещё {len(signups) - 40}' if len(signups) > 40 else ''
        phase = phase_label(normalize_phase(cfg))
        await interaction.response.send_message(
            f'**{phase} · записались ({len(signups)}):**\n{mentions}{more}',
            ephemeral=True)

    @discord.ui.button(
        label='Финиш', style=discord.ButtonStyle.secondary,
        emoji='🏁', custom_id='event_panel:end', row=1)
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Финиш только для Event Admin / Event Mod.', ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        if normalize_phase(cfg) == PHASE_ENDED:
            return await interaction.response.send_message(
                'Уже завершено. Новый набор — кнопка **Анонс**.', ephemeral=True)
        cfg = apply_end(cfg, by_user_id=interaction.user.id)
        cfg['description'] = (
            'Ивент завершён. Спасибо за игру!\n'
            'Следующий набор — кнопка **Анонс** у ведущих.\n'
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
        save_panel_cfg(guild.id, cfg)
        try:
            if interaction.message:
                await interaction.message.edit(
                    embed=panel_embed(guild, cfg), view=self)
        except Exception as ex:
            log.debug('end edit: %s', ex)
        await interaction.response.send_message(
            '🏁 Ивент завершён. Для нового набора жми **Анонс**.',
            ephemeral=True)
        channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
        if channel is not None:
            try:
                await channel.send(
                    embed=discord.Embed(
                        title=f'🏁 Финиш · {(cfg.get("title") or "Ивент")}'[:256],
                        description='Спасибо всем, кто был. До следующего раза.',
                        color=COLOR_ENDED,
                        timestamp=datetime.now(timezone.utc),
                    ),
                    delete_after=120,
                )
            except Exception:
                pass


class EventPanel(commands.Cog):
    """Публикация панели событий в канал."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name='event-panel',
        description='Опубликовать панель событий (Event Admin / Mod)')
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
                'Нужна роль Event Admin / Event Mod или Manage Server.',
                ephemeral=True)

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
            f'✅ Панель в <#{cfg.get("channel_id")}>.\n'
            f'Сценарий: **Анонс** → игроки **Записаться** → **▶ Старт** '
            f'(войс <#{event_voice_channel_id()}>).\n'
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
