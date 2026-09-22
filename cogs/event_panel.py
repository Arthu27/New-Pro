# -*- coding: utf-8 -*-
"""Панель событий Discord — Components V2 + свои стикеры (как /modpanel).

Сценарий: Анонс → Записаться → ▶ Старт (пинг + войс) → Финиш.
Публикация: LayoutView (чёрные Container + баннер Events) со стикерами
Hakumo; фолбек — классический embed, если V2 недоступен.
"""
from __future__ import annotations

import io
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

PHASE_IDLE = 'idle'
PHASE_OPEN = 'open'
PHASE_LIVE = 'live'
PHASE_ENDED = 'ended'

COLOR_IDLE = 0x5EC8FF
COLOR_OPEN = 0x2ECC71
COLOR_LIVE = 0xF0A202
COLOR_ENDED = 0x7A8699
PANEL_COLOR = COLOR_IDLE
_BLACK = 0x000000

DEFAULT_EVENT_VOICE = 1550986919981351043
_BANNER_NAME = 'hakumo_events_banner_v15.png'


def configured_panel_channel_id() -> int:
    try:
        from config import Config
        return int(getattr(Config, 'EVENT_PANEL_CHANNEL_ID', 0) or 0)
    except Exception:
        return 0


def event_voice_channel_id() -> int:
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
    if cfg is None and guild_id is not None:
        cfg = load_panel_cfg(guild_id)
    cfg = cfg or {}
    try:
        return int(cfg.get('target_channel_id') or 0)
    except (TypeError, ValueError):
        return 0


def set_target_channel_id(guild_id: int, channel_id: int) -> dict:
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


def apply_start(cfg: dict, *, by_user_id: str | int | None = None) -> dict:
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


def _howto_text(voice_id: int) -> str:
    return (
        '**Как играем**\n'
        '① Ведущий жмёт **Анонс** — открывает набор\n'
        '② Игроки жмут **Записаться**\n'
        f'③ Ведущий жмёт **Старт** — пинг списка + зовём в <#{voice_id}>\n'
        '④ После игры — **Финиш**'
    )


def panel_status_markdown(cfg: dict) -> tuple[str, str, str, str]:
    """title, phase_line, voice_line, body для V2-шапки."""
    cfg = cfg or {}
    phase = normalize_phase(cfg)
    title = (cfg.get('title') or 'События сервера').strip()[:200]
    voice_id = event_voice_channel_id()
    n = len(cfg.get('signups') or [])
    open_reg = bool(cfg.get('registration_open', True)) and phase not in (
        PHASE_LIVE, PHASE_ENDED)
    phase_line = (
        f'**Статус:** {phase_label(phase)} · '
        f'запись {"открыта" if open_reg else "закрыта"} · '
        f'участников **{n}**'
    )
    voice_line = f'**Войс старта:** <#{voice_id}>'
    if phase == PHASE_LIVE:
        body = (
            cfg.get('description')
            or f'**Игра запущена.** Заходите в <#{voice_id}>\n'
               f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
        )
        if cfg.get('started_at') and _iso_to_ts(cfg['started_at']):
            body += f'\nСтарт <t:{_iso_to_ts(cfg["started_at"])}:R>'
    elif phase == PHASE_ENDED:
        body = (
            cfg.get('description')
            or 'Ивент завершён. Новый набор — кнопка **Анонс**.'
        )
    else:
        body = cfg.get('description') or (
            f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.\n'
            'Сначала **Анонс**, потом набор, потом **Старт**.'
        )
    return title, phase_line, voice_line, str(body)[:2500]


def panel_embed(guild: discord.Guild, cfg: dict | None = None) -> discord.Embed:
    """Фолбек-эмбед (без V2)."""
    cfg = cfg or {}
    phase = normalize_phase(cfg)
    title, phase_line, voice_line, body = panel_status_markdown(cfg)
    e = discord.Embed(
        title=title[:256],
        description=f'{phase_line}\n{voice_line}\n\n{body}\n\n'
                    f'{_howto_text(event_voice_channel_id())}'[:4000],
        color=phase_color(phase),
        timestamp=datetime.now(timezone.utc),
    )
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text='Hakumo Events · V2 · Анонс → Запись → Старт')
    return e


def start_announce_embed(guild: discord.Guild, cfg: dict,
                         started_by: discord.abc.User | None = None) -> discord.Embed:
    title = (cfg.get('title') or 'Ивент').strip()
    voice_id = event_voice_channel_id()
    signups = list(cfg.get('signups') or [])
    e = discord.Embed(
        title=f'▶  Старт · {title}'[:256],
        description=(
            f'Сбор в <#{voice_id}>\n'
            f'Участников: **{len(signups)}**\n\n'
            'Заходите — ведущие уже на месте.'
        ),
        color=COLOR_LIVE,
        timestamp=datetime.now(timezone.utc),
    )
    if started_by is not None:
        e.add_field(
            name='Запустил',
            value=getattr(started_by, 'mention', None) or str(started_by),
            inline=True)
    e.set_footer(text='Hakumo Events')
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    return e


def _events_banner_file():
    try:
        from services.menu_banners import menu_banner_file
        from services.v2_layouts import SHOW_MENU_BANNER
        if not SHOW_MENU_BANNER:
            return None, None
        bio, name = menu_banner_file('events')
        raw = bio.getvalue() if hasattr(bio, 'getvalue') else bio.read()
        out = io.BytesIO(raw)
        out.seek(0)
        return discord.File(out, filename=name), name
    except Exception as ex:
        log.debug('events banner: %s', ex)
        return None, None


def _sticker_emoji(kind: str):
    try:
        from services.menu_emojis import emoji_for_event
        return emoji_for_event(kind)
    except Exception:
        return {
            'signup': '✋', 'announce': '📣', 'start': '▶',
            'finish': '🏁', 'elist': '📋', 'reg': '🔓',
        }.get(kind, '🤍')


# ── Buttons (persistent custom_id) ───────────────────────────────────

class _EvBtn(discord.ui.Button):
    kind: str = ''

    def __init__(self, *, label: str, style: discord.ButtonStyle,
                 custom_id: str, row: int = 0):
        super().__init__(
            label=label, style=style, custom_id=custom_id, row=row,
            emoji=_sticker_emoji(self.kind) if self.kind else None)


class SignupBtn(_EvBtn):
    kind = 'signup'

    def __init__(self):
        super().__init__(
            label='Записаться', style=discord.ButtonStyle.success,
            custom_id='event_panel:signup', row=0)

    async def callback(self, interaction: discord.Interaction):
        await _handle_signup(interaction, self.view)


class AnnounceBtn(_EvBtn):
    kind = 'announce'

    def __init__(self):
        super().__init__(
            label='Анонс', style=discord.ButtonStyle.primary,
            custom_id='event_panel:announce', row=0)

    async def callback(self, interaction: discord.Interaction):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Только Event Admin / Event Mod.', ephemeral=True)
        await interaction.response.send_modal(EventAnnounceModal(None))


class StartBtn(_EvBtn):
    kind = 'start'

    def __init__(self):
        super().__init__(
            label='Старт', style=discord.ButtonStyle.danger,
            custom_id='event_panel:start', row=0)

    async def callback(self, interaction: discord.Interaction):
        await _handle_start(interaction, self.view)


class RegBtn(_EvBtn):
    kind = 'reg'

    def __init__(self):
        super().__init__(
            label='Запись', style=discord.ButtonStyle.secondary,
            custom_id='event_panel:close', row=0)

    async def callback(self, interaction: discord.Interaction):
        await _handle_toggle_reg(interaction, self.view)


class ListBtn(_EvBtn):
    kind = 'elist'

    def __init__(self):
        super().__init__(
            label='Список', style=discord.ButtonStyle.secondary,
            custom_id='event_panel:list', row=1)

    async def callback(self, interaction: discord.Interaction):
        await _handle_list(interaction)


class FinishBtn(_EvBtn):
    kind = 'finish'

    def __init__(self):
        super().__init__(
            label='Финиш', style=discord.ButtonStyle.secondary,
            custom_id='event_panel:end', row=1)

    async def callback(self, interaction: discord.Interaction):
        await _handle_end(interaction, self.view)


# ── Views ────────────────────────────────────────────────────────────

class EventPanelLegacyView(discord.ui.View):
    """Классические кнопки — фолбек без Components V2."""

    def __init__(self):
        super().__init__(timeout=None)
        for btn in (SignupBtn(), AnnounceBtn(), StartBtn(),
                    RegBtn(), ListBtn(), FinishBtn()):
            self.add_item(btn)


class EventPanelView(discord.ui.LayoutView):
    """Components V2 панель ивентов (баннер + стикеры), persistent."""

    def __init__(self, cfg: dict | None = None, *, guild: discord.Guild | None = None):
        super().__init__(timeout=None)
        self.cfg = dict(cfg or {})
        self.guild = guild
        self._banner_name = _BANNER_NAME
        self._use_v2 = True
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        self.btn_signup = SignupBtn()
        self.btn_announce = AnnounceBtn()
        self.btn_start = StartBtn()
        self.btn_reg = RegBtn()
        self.btn_list = ListBtn()
        self.btn_finish = FinishBtn()

        from services.v2_layouts import (
            V2_AVAILABLE, SHOW_MENU_BANNER, build_event_panel_items)

        title, phase_line, voice_line, body = panel_status_markdown(self.cfg)
        phase = normalize_phase(self.cfg)
        accent = _BLACK  # как модпанель
        howto = _howto_text(event_voice_channel_id())

        if V2_AVAILABLE and self._use_v2:
            # ActionRows внутри Container
            row_p = discord.ui.ActionRow()
            row_p.add_item(self.btn_signup)
            row_s = discord.ui.ActionRow()
            row_s.add_item(self.btn_announce)
            row_s.add_item(self.btn_start)
            row_s.add_item(self.btn_reg)
            row_s2 = discord.ui.ActionRow()
            row_s2.add_item(self.btn_list)
            row_s2.add_item(self.btn_finish)

            banner = self._banner_name if SHOW_MENU_BANNER else None
            items = build_event_panel_items(
                banner_filename=banner or '',
                title=title,
                body=body,
                phase_line=phase_line,
                voice_line=voice_line,
                howto=howto,
                player_row=row_p,
                staff_row=row_s,
                staff_row2=row_s2,
                show_banner=bool(banner),
                accent=accent,
            )
            if items:
                for it in items:
                    self.add_item(it)
                return

        # fallback rows
        for b in (self.btn_signup, self.btn_announce, self.btn_start,
                  self.btn_reg, self.btn_list, self.btn_finish):
            self.add_item(b)

    def sync_cfg(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self._rebuild()


def make_panel_view(cfg: dict | None = None,
                    guild: discord.Guild | None = None):
    """V2 LayoutView или legacy View."""
    try:
        from services.v2_layouts import V2_AVAILABLE
        if V2_AVAILABLE:
            return EventPanelView(cfg, guild=guild)
    except Exception:
        pass
    return EventPanelLegacyView()


async def resolve_panel_channel(
    guild: discord.Guild,
    interaction: discord.Interaction | None = None,
    channel_opt: discord.abc.GuildChannel | None = None,
    cfg: dict | None = None,
) -> discord.abc.Messageable | None:
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


async def _edit_panel_message(message: discord.Message, cfg: dict,
                              guild: discord.Guild) -> None:
    view = make_panel_view(cfg, guild=guild)
    # V2: только view= — attachments (баннер) не трогаем
    try:
        from services.v2_layouts import V2_AVAILABLE
        if V2_AVAILABLE and isinstance(view, discord.ui.LayoutView):
            await message.edit(view=view, content=None, embed=None)
            return
    except Exception as ex:
        log.debug('v2 edit: %s', ex)
    await message.edit(embed=panel_embed(guild, cfg), view=view)


async def publish_event_panel(
    guild: discord.Guild,
    *,
    channel: discord.abc.Messageable | None = None,
    posted_by: str | int | None = None,
    interaction: discord.Interaction | None = None,
) -> tuple[discord.Message, dict]:
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

    view = make_panel_view(cfg, guild=guild)
    banner_file, banner_name = _events_banner_file()
    if banner_name and isinstance(view, EventPanelView):
        view._banner_name = banner_name
        view._rebuild()

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
            # переиздание: можно перезалить баннер
            kw = {'view': view}
            if isinstance(view, EventPanelView):
                kw['content'] = None
                kw['embed'] = None
                if banner_file is not None:
                    kw['attachments'] = [banner_file]
            else:
                kw['embed'] = panel_embed(guild, cfg)
            await msg.edit(**kw)
        except Exception as ex:
            log.debug('event-panel edit existing: %s', ex)
            msg = None
            banner_file, banner_name = _events_banner_file()

    if msg is None:
        send_kw = {'view': view}
        if isinstance(view, EventPanelView):
            if banner_file is not None:
                send_kw['file'] = banner_file
        else:
            send_kw['embed'] = panel_embed(guild, cfg)
            if banner_file is not None:
                send_kw['file'] = banner_file
                send_kw['embed'].set_image(url=f'attachment://{banner_name}')
        msg = await target.send(**send_kw)

    cfg['message_id'] = msg.id
    cfg['channel_id'] = getattr(target, 'id', None)
    if posted_by is not None:
        cfg['posted_by'] = str(posted_by)
    cfg['posted_at'] = datetime.now(timezone.utc).isoformat()
    cfg['style'] = 'v2' if isinstance(view, EventPanelView) else 'embed'
    save_panel_cfg(guild.id, cfg)
    return msg, cfg


# ── Handlers ─────────────────────────────────────────────────────────

async def _handle_signup(interaction: discord.Interaction, view):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message(
            'Только на сервере.', ephemeral=True)
    cfg = load_panel_cfg(guild.id)
    phase = normalize_phase(cfg)
    voice_id = event_voice_channel_id()
    if phase == PHASE_LIVE:
        return await interaction.response.send_message(
            f'Игра уже идёт — заходи в <#{voice_id}>', ephemeral=True)
    if phase == PHASE_ENDED or not cfg.get('registration_open', True):
        return await interaction.response.send_message(
            'Запись закрыта. Жди следующий **Анонс**.', ephemeral=True)
    uid = str(interaction.user.id)
    signups = list(cfg.get('signups') or [])
    if uid in signups:
        return await interaction.response.send_message(
            f'Ты уже в списке. Жди **Старт** → <#{voice_id}>', ephemeral=True)
    signups.append(uid)
    cfg['signups'] = signups
    if not cfg.get('phase') or cfg.get('phase') == PHASE_IDLE:
        cfg['phase'] = PHASE_OPEN
    save_panel_cfg(guild.id, cfg)
    try:
        if interaction.message:
            await _edit_panel_message(interaction.message, cfg, guild)
    except Exception as ex:
        log.debug('signup edit: %s', ex)
    await interaction.response.send_message(
        f'✅ Ты в списке (**{len(signups)}**). На **Старт** — в <#{voice_id}>.',
        ephemeral=True)


async def _handle_start(interaction: discord.Interaction, view):
    if not is_event_mod(interaction.user):
        return await interaction.response.send_message(
            'Старт только для Event Admin / Event Mod.', ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message(
            'Только на сервере.', ephemeral=True)
    cfg = load_panel_cfg(guild.id)
    if normalize_phase(cfg) == PHASE_LIVE:
        return await interaction.response.send_message(
            f'Уже запущено. Войс: <#{event_voice_channel_id()}>', ephemeral=True)

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
            await _edit_panel_message(interaction.message, cfg, guild)
    except Exception as ex:
        log.debug('start edit: %s', ex)

    channel = await resolve_panel_channel(guild, interaction, cfg=cfg)
    if channel is not None:
        mentions = _signup_mentions(signups)
        content = (
            f'▶ **Старт!** {mentions}'.strip()
            if mentions else
            f'▶ **Старт!** <@&{EVENT_ADMIN_ROLE_ID}> <@&{EVENT_MOD_ROLE_ID}>'
        )
        sent = False
        try:
            from services.v2_layouts import (
                V2_AVAILABLE, build_event_start_items)
            if V2_AVAILABLE:
                items = build_event_start_items(
                    title=(cfg.get('title') or 'Ивент'),
                    body=(
                        f'Сбор в <#{voice_id}>\n'
                        f'Участников в списке: **{len(signups)}**\n\n'
                        'Заходите, микрофон по желанию — ведущие на месте.\n'
                        f'Запустил: {interaction.user.mention}'
                    ),
                    footer='Hakumo Events · приятной игры',
                )
                if items:
                    lv = discord.ui.LayoutView(timeout=None)
                    for it in items:
                        lv.add_item(it)
                    await channel.send(
                        content=content[:1900],
                        view=lv,
                        allowed_mentions=discord.AllowedMentions(
                            users=True, roles=True, everyone=False),
                    )
                    sent = True
        except Exception as ex:
            log.debug('start v2: %s', ex)
        if not sent:
            try:
                await channel.send(
                    content=content[:1900],
                    embed=start_announce_embed(
                        guild, cfg, started_by=interaction.user),
                    allowed_mentions=discord.AllowedMentions(
                        users=True, roles=True, everyone=False),
                )
            except Exception as ex:
                log.warning('start announce: %s', ex)

    await interaction.followup.send(
        f'▶ Игра запущена. Зовём в <#{voice_id}> ({len(signups)} в списке).',
        ephemeral=True)


async def _handle_toggle_reg(interaction: discord.Interaction, view):
    if not is_event_mod(interaction.user):
        return await interaction.response.send_message(
            'Только Event Admin / Event Mod.', ephemeral=True)
    guild = interaction.guild
    cfg = load_panel_cfg(guild.id)
    if normalize_phase(cfg) == PHASE_LIVE:
        return await interaction.response.send_message(
            'Игра идёт — сначала **Финиш**.', ephemeral=True)
    cfg['registration_open'] = not cfg.get('registration_open', True)
    if cfg['registration_open']:
        cfg['phase'] = PHASE_OPEN
        cfg['live'] = False
    save_panel_cfg(guild.id, cfg)
    try:
        if interaction.message:
            await _edit_panel_message(interaction.message, cfg, guild)
    except Exception as ex:
        log.debug('toggle reg: %s', ex)
    state = 'открыта' if cfg.get('registration_open') else 'закрыта'
    await interaction.response.send_message(
        f'Запись теперь **{state}**.', ephemeral=True)


async def _handle_list(interaction: discord.Interaction):
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
    await interaction.response.send_message(
        f'**{phase_label(normalize_phase(cfg))} · {len(signups)}:**\n'
        f'{mentions}{more}',
        ephemeral=True)


async def _handle_end(interaction: discord.Interaction, view):
    if not is_event_mod(interaction.user):
        return await interaction.response.send_message(
            'Финиш только для Event Admin / Event Mod.', ephemeral=True)
    guild = interaction.guild
    cfg = load_panel_cfg(guild.id)
    if normalize_phase(cfg) == PHASE_ENDED:
        return await interaction.response.send_message(
            'Уже завершено. Новый набор — **Анонс**.', ephemeral=True)
    cfg = apply_end(cfg, by_user_id=interaction.user.id)
    cfg['description'] = (
        'Ивент завершён. Спасибо за игру!\n'
        'Следующий набор — **Анонс**.\n'
        f'Ведут — <@&{EVENT_ADMIN_ROLE_ID}> · <@&{EVENT_MOD_ROLE_ID}>.'
    )
    save_panel_cfg(guild.id, cfg)
    try:
        if interaction.message:
            await _edit_panel_message(interaction.message, cfg, guild)
    except Exception as ex:
        log.debug('end edit: %s', ex)
    await interaction.response.send_message(
        '🏁 Ивент завершён. Новый набор — **Анонс**.', ephemeral=True)


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
        placeholder='Правила, слоты… После набора жми Старт',
        max_length=1000, required=False)

    def __init__(self, cog: 'EventPanel'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not is_event_mod(interaction.user):
            return await interaction.response.send_message(
                'Только Event Admin / Event Mod.', ephemeral=True)
        guild = interaction.guild
        cfg = load_panel_cfg(guild.id)
        cfg['title'] = str(self.title_in.value).strip()
        voice_id = event_voice_channel_id()
        details = (str(self.details_in.value or '').strip()
                   or 'Подробности у ведущих.')
        cfg['description'] = (
            f'**Когда:** {str(self.when_in.value).strip()}\n'
            f'{details}\n\n'
            f'① **Записаться** → ② **Старт** → ③ войс <#{voice_id}>'
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
                'Не найден канал панели.', ephemeral=True)
        try:
            await publish_event_panel(
                guild, channel=channel, posted_by=interaction.user.id,
                interaction=interaction)
        except Exception as ex:
            log.warning('announce republish: %s', ex)
            return await interaction.response.send_message(
                f'Не удалось обновить панель: {ex}', ephemeral=True)
        await interaction.response.send_message(
            f'✅ Анонс в {channel.mention}. Когда соберутся — **Старт**.',
            ephemeral=True)


class EventPanel(commands.Cog):
    """Публикация панели событий (V2 + стикеры)."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name='event-panel',
        description='Опубликовать панель ивентов V2 (Event Admin / Mod)')
    @app_commands.describe(
        channel='Куда отправить панель')
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
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(interaction.client)
        except Exception:
            pass
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
                '❌ Не найден канал. Укажи `channel` или задай на /events.',
                ephemeral=True)
        except Exception as ex:
            log.exception('event-panel publish: %s', ex)
            return await interaction.followup.send(
                f'❌ Не удалось опубликовать: {ex}', ephemeral=True)

        style = cfg.get('style') or 'v2'
        await interaction.followup.send(
            f'✅ Панель **{style.upper()}** в <#{cfg.get("channel_id")}>.\n'
            f'**Анонс** → игроки **Записаться** → **Старт** '
            f'(войс <#{event_voice_channel_id()}>).\n'
            f'Event Admin <@&{EVENT_ADMIN_ROLE_ID}> · '
            f'Event Mod <@&{EVENT_MOD_ROLE_ID}>',
            ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(self.bot)
        except Exception:
            pass
        try:
            from services.menu_banners import ensure_sticker_pack
            ensure_sticker_pack()
        except Exception:
            pass
        # Один persistent view (одинаковые custom_id) — V2 или legacy
        try:
            from services.v2_layouts import V2_AVAILABLE
            if V2_AVAILABLE:
                self.bot.add_view(EventPanelView({}))
            else:
                self.bot.add_view(EventPanelLegacyView())
        except Exception as ex:
            log.debug('add_view event panel: %s', ex)
            try:
                self.bot.add_view(EventPanelLegacyView())
            except Exception:
                pass


async def setup(bot):
    from config import Config
    await bot.add_cog(EventPanel(bot), guilds=Config.guild_objects())
