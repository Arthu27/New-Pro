# -*- coding: utf-8 -*-
"""Event lifecycle per TZ: /eventstart · анонс · запись · напоминания · статистика.

V2 чёрный UI + selects где уместно. Работает на Event-боте.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from logger import get_logger
from services import event_lifecycle_config as CFG
from services import event_lifecycle_store as STORE

log = get_logger('event_lifecycle')

MSK = ZoneInfo('Europe/Moscow')
_BLACK = 0x000000


def _cfg():
    return CFG.load_config()


def _is_event_staff(member: discord.Member | None) -> bool:
    if member is None:
        return False
    perms = getattr(member, 'guild_permissions', None)
    if perms and (perms.administrator or perms.manage_guild or perms.manage_events):
        return True
    cfg = _cfg()
    ids = {CFG.iid(cfg, 'event_mod_role_id'), CFG.iid(cfg, 'event_admin_role_id')}
    ids.discard(0)
    return any(getattr(r, 'id', None) in ids for r in getattr(member, 'roles', []))


def _is_organizer(member: discord.Member | None, event: dict) -> bool:
    if member is None:
        return False
    if _is_event_staff(member):
        return True
    try:
        return int(member.id) == int(event.get('organizer_id') or 0)
    except (TypeError, ValueError):
        return False


def _parse_dt(date_s: str, time_s: str) -> Optional[datetime]:
    """Parse date+time in MSK → aware UTC datetime."""
    date_s = (date_s or '').strip()
    time_s = (time_s or '').strip()
    # accept DD.MM.YYYY / DD.MM / YYYY-MM-DD / DD сентября
    months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
    }
    now = datetime.now(MSK)
    d = None
    m = re.match(r'^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?$', date_s)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3) or now.year)
        if year < 100:
            year += 2000
        try:
            d = datetime(year, month, day, tzinfo=MSK)
        except ValueError:
            return None
    else:
        m2 = re.match(r'^(\d{1,2})\s+([А-Яа-яA-Za-z]+)$', date_s)
        if m2:
            day = int(m2.group(1))
            mon = months.get(m2.group(2).lower())
            if not mon:
                return None
            year = now.year
            try:
                d = datetime(year, mon, day, tzinfo=MSK)
            except ValueError:
                return None
            if d < now - timedelta(days=1):
                d = d.replace(year=year + 1)
    if d is None:
        return None
    tm = re.match(r'^(\d{1,2})[:.\-](\d{2})$', time_s)
    if not tm:
        return None
    hh, mm = int(tm.group(1)), int(tm.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return d.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _fmt_when(ts: float) -> tuple[str, str]:
    dt = datetime.fromtimestamp(float(ts), tz=MSK)
    months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    return f'{dt.day} {months[dt.month - 1]}', f'{dt.hour:02d}:{dt.minute:02d}'


def _announce_body(event: dict, voice_name: str = '') -> str:
    date_s, time_s = _fmt_when(event.get('starts_at') or 0)
    title = event.get('title') or 'Ивент'
    desc = (event.get('description') or '').strip() or '—'
    channel = voice_name or event.get('voice_name') or '—'
    signups = list(event.get('signups') or [])
    limit = int(event.get('max_participants') or 0)
    if limit > 0:
        free = max(0, limit - len(signups))
        part = f'Участники: **{len(signups)}/{limit}**\nСвободно: **{free}** мест'
    else:
        part = f'Участники: **{len(signups)}**'
    status = event.get('status') or 'scheduled'
    head = f'# {title}\n-# HAKUMO · Events'
    if status == 'cancelled':
        head = f'# ❌ Отменён · {title}\n-# HAKUMO · Events'
    elif status == 'finished':
        head = f'# ✓ Завершён · {title}\n-# HAKUMO · Events'
    return (
        f'{head}\n\n'
        f'**{date_s}** · **{time_s}** МСК\n'
        f'Канал: **{channel}**\n\n'
        f'{desc}\n\n'
        f'{part}'
    )


def _v2_or_embed(title: str, body: str, footer: str = 'Hakumo · Events'):
    try:
        from services.v2_layouts import V2_AVAILABLE, notice_layout_view
        if V2_AVAILABLE:
            v = notice_layout_view(
                title=title, body=body, footer=footer,
                accent=_BLACK, brand='HAKUMO')
            if v is not None:
                return {'view': v}
    except Exception:
        pass
    e = discord.Embed(color=_BLACK)
    e.description = f'## {title}\n{body}'
    e.set_footer(text=footer)
    return {'embed': e}


async def _ensure_category(guild: discord.Guild, cfg: dict) -> Optional[discord.CategoryChannel]:
    cid = CFG.iid(cfg, 'events_category_id')
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.CategoryChannel):
            return ch
    for ch in guild.categories:
        n = (ch.name or '').lower()
        if 'ивент' in n or n in ('events', 'event'):
            cfg['events_category_id'] = str(ch.id)
            CFG.save_config(cfg)
            return ch
    if not cfg.get('create_missing'):
        return None
    try:
        cat = await guild.create_category('・ивенты', reason='eventstart: seed category')
        cfg['events_category_id'] = str(cat.id)
        CFG.save_config(cfg)
        return cat
    except Exception as ex:
        log.warning('create category: %s', ex)
        return None


async def _ensure_announce_channel(guild: discord.Guild, cfg: dict) -> Optional[discord.TextChannel]:
    cid = CFG.iid(cfg, 'announce_channel_id')
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            ch = await guild.fetch_channel(cid)
            if isinstance(ch, discord.TextChannel):
                return ch
        except Exception:
            pass
    for name in ('・анонсы-ивентов', 'анонсы-ивентов', 'events', 'ивенты-анонсы'):
        for ch in guild.text_channels:
            if (ch.name or '').lower() == name.lower() or (ch.name or '').lstrip('・').lower() == name.lstrip('・').lower():
                cfg['announce_channel_id'] = str(ch.id)
                CFG.save_config(cfg)
                return ch
    if not cfg.get('create_missing'):
        return None
    cat = await _ensure_category(guild, cfg)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
    }
    try:
        ch = await guild.create_text_channel(
            '・анонсы-ивентов',
            category=cat,
            overwrites=overwrites,
            reason='eventstart: seed announce')
        cfg['announce_channel_id'] = str(ch.id)
        CFG.save_config(cfg)
        return ch
    except Exception as ex:
        log.warning('create announce: %s', ex)
        return None


async def _refresh_announce(guild: discord.Guild, event: dict) -> Optional[discord.Message]:
    cfg = _cfg()
    ch_id = int(event.get('announce_channel_id') or 0)
    msg_id = int(event.get('announce_message_id') or 0)
    if not ch_id or not msg_id:
        return None
    ch = guild.get_channel(ch_id)
    if ch is None:
        try:
            ch = await guild.fetch_channel(ch_id)
        except Exception:
            return None
    if not isinstance(ch, discord.TextChannel):
        return None
    voice_name = event.get('voice_name') or ''
    vid = int(event.get('voice_channel_id') or 0)
    if vid:
        vc = guild.get_channel(vid)
        if vc:
            voice_name = vc.name
    body = _announce_body(event, voice_name)
    view = PublicSignupView(event['id']) if event.get('status') == 'scheduled' else None
    try:
        msg = await ch.fetch_message(msg_id)
        # Prefer classic embed+view for public signup reliability
        e = discord.Embed(color=_BLACK, description=body[:4000])
        e.set_footer(text=f'Hakumo · Events · id {event["id"]}')
        await msg.edit(embed=e, view=view)
        return msg
    except Exception as ex:
        log.debug('refresh announce: %s', ex)
        return None


async def _sync_discord_event(guild: discord.Guild, event: dict) -> Optional[int]:
    """Create/edit/cancel scheduled event. Returns scheduled_event id."""
    sid = int(event.get('scheduled_event_id') or 0)
    status = event.get('status') or 'scheduled'
    start = datetime.fromtimestamp(float(event['starts_at']), tz=timezone.utc)
    if start < datetime.now(timezone.utc) + timedelta(seconds=30):
        start = datetime.now(timezone.utc) + timedelta(minutes=5)
    voice = None
    vid = int(event.get('voice_channel_id') or 0)
    if vid:
        voice = guild.get_channel(vid)
    try:
        if status == 'cancelled' and sid:
            se = guild.get_scheduled_event(sid)
            if se is None:
                se = await guild.fetch_scheduled_event(sid)
            if se:
                await se.cancel()
            return sid
        if status == 'finished' and sid:
            se = guild.get_scheduled_event(sid)
            if se is None:
                try:
                    se = await guild.fetch_scheduled_event(sid)
                except Exception:
                    se = None
            if se and se.status == discord.EventStatus.active:
                await se.end()
            elif se and se.status == discord.EventStatus.scheduled:
                await se.cancel()
            return sid
        kwargs = dict(
            name=str(event.get('title') or 'Ивент')[:100],
            description=str(event.get('description') or '')[:1000] or 'Hakumo event',
            start_time=start,
            privacy_level=discord.PrivacyLevel.guild_only,
        )
        if isinstance(voice, discord.VoiceChannel):
            kwargs['entity_type'] = discord.EntityType.voice
            kwargs['channel'] = voice
        else:
            kwargs['entity_type'] = discord.EntityType.external
            kwargs['location'] = str(event.get('voice_name') or 'Events')[:100]
            kwargs['end_time'] = start + timedelta(hours=2)
        if sid:
            se = guild.get_scheduled_event(sid)
            if se is None:
                try:
                    se = await guild.fetch_scheduled_event(sid)
                except Exception:
                    se = None
            if se and se.status == discord.EventStatus.scheduled:
                await se.edit(**{k: v for k, v in kwargs.items() if k != 'entity_type'})
                return sid
        se = await guild.create_scheduled_event(**kwargs)
        return int(se.id)
    except Exception as ex:
        log.warning('scheduled_event sync: %s', ex)
        return sid or None


# ── Views ───────────────────────────────────────────────────────────────

class PublicSignupView(discord.ui.View):
    def __init__(self, event_id: str):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.add_item(SignupButton(event_id))
        self.add_item(UnsignupButton(event_id))


class SignupButton(discord.ui.Button):
    def __init__(self, event_id: str):
        super().__init__(
            label='✅ Участвую', style=discord.ButtonStyle.success,
            custom_id=f'evlife:join:{event_id}')

    async def callback(self, interaction: discord.Interaction):
        eid = self.custom_id.split(':')[-1]
        ev, reason = STORE.add_signup(eid, interaction.user.id)
        if reason == 'missing':
            return await interaction.response.send_message('Ивент не найден.', ephemeral=True)
        if reason == 'dup':
            return await interaction.response.send_message('Вы уже записаны.', ephemeral=True)
        if reason == 'closed':
            return await interaction.response.send_message('Запись закрыта.', ephemeral=True)
        if reason == 'full':
            return await interaction.response.send_message('Мест больше нет.', ephemeral=True)
        if interaction.guild and ev:
            await _refresh_announce(interaction.guild, ev)
        await interaction.response.send_message('Вы в списке участников ✅', ephemeral=True)


class UnsignupButton(discord.ui.Button):
    def __init__(self, event_id: str):
        super().__init__(
            label='❌ Отменить участие', style=discord.ButtonStyle.secondary,
            custom_id=f'evlife:leave:{event_id}')

    async def callback(self, interaction: discord.Interaction):
        eid = self.custom_id.split(':')[-1]
        ev, reason = STORE.remove_signup(eid, interaction.user.id)
        if reason == 'missing':
            return await interaction.response.send_message('Ивент не найден.', ephemeral=True)
        if reason == 'missing_user':
            return await interaction.response.send_message('Вас нет в списке.', ephemeral=True)
        if interaction.guild and ev:
            await _refresh_announce(interaction.guild, ev)
        await interaction.response.send_message('Запись отменена.', ephemeral=True)


class OrganizerView(discord.ui.View):
    def __init__(self, event_id: str):
        super().__init__(timeout=None)
        self.add_item(OrgActionSelect(event_id))


class OrgActionSelect(discord.ui.Select):
    def __init__(self, event_id: str):
        self.event_id = event_id
        opts = [
            discord.SelectOption(label='Редактировать', value='edit',
                                 description='Дата / время / название / лимит'),
            discord.SelectOption(label='Участники', value='list',
                                 description='Список записавшихся'),
            discord.SelectOption(label='Напомнить', value='remind',
                                 description='Пинг участников сейчас'),
            discord.SelectOption(label='Отменить ивент', value='cancel',
                                 description='Обновить анонс: отменён'),
            discord.SelectOption(label='Завершить ивент', value='finish',
                                 description='Удалить войс + закрыть Discord Event'),
        ]
        super().__init__(
            placeholder='Действие организатора…', min_values=1, max_values=1,
            options=opts, custom_id=f'evlife:org:{event_id}')

    async def callback(self, interaction: discord.Interaction):
        eid = self.custom_id.split(':')[-1]
        ev = STORE.get_event(eid)
        if not ev:
            return await interaction.response.send_message('Ивент не найден.', ephemeral=True)
        if not _is_organizer(interaction.user if isinstance(interaction.user, discord.Member) else None, ev):
            # try guild member
            mem = interaction.user
            if interaction.guild and not isinstance(mem, discord.Member):
                mem = interaction.guild.get_member(interaction.user.id)
            if not _is_organizer(mem, ev):
                return await interaction.response.send_message('Только организатор / Event staff.', ephemeral=True)
        act = self.values[0]
        if act == 'edit':
            return await interaction.response.send_modal(EditEventModal(eid))
        if act == 'list':
            signups = ev.get('signups') or []
            if not signups:
                return await interaction.response.send_message('Пока никто не записался.', ephemeral=True)
            text = ', '.join(f'<@{u}>' for u in signups[:50])
            more = f'\n…и ещё {len(signups) - 50}' if len(signups) > 50 else ''
            return await interaction.response.send_message(
                f'**Участники ({len(signups)}):**\n{text}{more}', ephemeral=True)
        if act == 'remind':
            await interaction.response.defer(ephemeral=True)
            n = await _dm_remind(interaction.client, ev, 'Напоминание от организатора')
            return await interaction.followup.send(f'Напоминание отправлено: {n} чел.', ephemeral=True)
        if act == 'cancel':
            await interaction.response.defer(ephemeral=True)
            await _cancel_event(interaction.guild, ev)
            return await interaction.followup.send('Ивент отменён.', ephemeral=True)
        if act == 'finish':
            await interaction.response.defer(ephemeral=True)
            await _finish_event(interaction.guild, ev)
            return await interaction.followup.send('Ивент завершён.', ephemeral=True)


class EditEventModal(discord.ui.Modal, title='Редактировать ивент'):
    def __init__(self, event_id: str):
        super().__init__()
        self.event_id = event_id
        ev = STORE.get_event(event_id) or {}
        date_s, time_s = _fmt_when(ev.get('starts_at') or time_now())
        self.title_in = discord.ui.TextInput(
            label='Название', default=str(ev.get('title') or '')[:100],
            max_length=100, required=True)
        self.date_in = discord.ui.TextInput(
            label='Дата (ДД.ММ.ГГГГ / 27 сентября)', default=date_s,
            max_length=40, required=True)
        self.time_in = discord.ui.TextInput(
            label='Время МСК (ЧЧ:ММ)', default=time_s,
            max_length=10, required=True)
        self.desc_in = discord.ui.TextInput(
            label='Описание', style=discord.TextStyle.paragraph,
            default=str(ev.get('description') or '')[:800],
            max_length=800, required=False)
        self.limit_in = discord.ui.TextInput(
            label='Лимит участников (0 = без лимита)',
            default=str(int(ev.get('max_participants') or 0)),
            max_length=4, required=True)
        for x in (self.title_in, self.date_in, self.time_in, self.desc_in, self.limit_in):
            self.add_item(x)

    async def on_submit(self, interaction: discord.Interaction):
        ev = STORE.get_event(self.event_id)
        if not ev:
            return await interaction.response.send_message('Ивент не найден.', ephemeral=True)
        dt = _parse_dt(str(self.date_in.value), str(self.time_in.value))
        if dt is None:
            return await interaction.response.send_message(
                'Не понял дату/время. Пример: `27.09.2026` и `20:00`.', ephemeral=True)
        try:
            limit = int(str(self.limit_in.value).strip() or 0)
        except ValueError:
            limit = 0
        updated = STORE.update_event(
            self.event_id,
            title=str(self.title_in.value).strip()[:100],
            description=str(self.desc_in.value or '').strip()[:800],
            starts_at=dt.astimezone(timezone.utc).timestamp(),
            max_participants=max(0, limit),
        )
        await interaction.response.defer(ephemeral=True)
        if interaction.guild and updated:
            sid = await _sync_discord_event(interaction.guild, updated)
            if sid:
                updated = STORE.update_event(self.event_id, scheduled_event_id=sid) or updated
            # rename voice if title changed
            vid = int(updated.get('voice_channel_id') or 0)
            if vid:
                vc = interaction.guild.get_channel(vid)
                if isinstance(vc, discord.VoiceChannel):
                    try:
                        await vc.edit(name=str(updated.get('title') or vc.name)[:100])
                        STORE.update_event(self.event_id, voice_name=vc.name)
                        updated['voice_name'] = vc.name
                    except Exception as ex:
                        log.debug('rename voice: %s', ex)
            await _refresh_announce(interaction.guild, updated)
        await interaction.followup.send('Ивент обновлён (Discord Event + анонс).', ephemeral=True)


def time_now() -> float:
    return datetime.now(timezone.utc).timestamp()


class EventStartModal(discord.ui.Modal, title='Создать ивент'):
    title_in = discord.ui.TextInput(label='Название', max_length=100, required=True,
                                    placeholder='Among Us')
    date_in = discord.ui.TextInput(label='Дата', max_length=40, required=True,
                                   placeholder='27.09.2026 или 27 сентября')
    time_in = discord.ui.TextInput(label='Время начала (МСК)', max_length=10, required=True,
                                   placeholder='20:00')
    limit_in = discord.ui.TextInput(label='Лимит участников (0 = без)', max_length=4,
                                    required=True, default='0')
    desc_in = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph,
                                   max_length=800, required=False,
                                   placeholder='Коротко о ивенте…')

    def __init__(self, voice_channel_id: int):
        super().__init__()
        self.voice_channel_id = int(voice_channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        if not _is_event_staff(interaction.user):
            return await interaction.response.send_message('Нужна роль Event Mod / Admin.', ephemeral=True)
        dt = _parse_dt(str(self.date_in.value), str(self.time_in.value))
        if dt is None:
            return await interaction.response.send_message(
                'Не понял дату/время. Пример: `27.09.2026` + `20:00`.', ephemeral=True)
        try:
            limit = int(str(self.limit_in.value).strip() or 0)
        except ValueError:
            limit = 0
        title = str(self.title_in.value).strip()[:100]
        cfg = _cfg()
        templates = cfg.get('templates') or {}
        desc = str(self.desc_in.value or '').strip()
        if not desc and title in templates:
            desc = str(templates[title])
        await interaction.response.defer(ephemeral=True)
        try:
            event = await create_full_event(
                interaction.guild,
                organizer=interaction.user,
                title=title,
                description=desc,
                starts_at=dt,
                max_participants=max(0, limit),
                preferred_voice_id=self.voice_channel_id,
            )
        except Exception as ex:
            log.exception('create event: %s', ex)
            return await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        await interaction.followup.send(
            ephemeral=True,
            content=f'Ивент **{event["title"]}** создан · id `{event["id"]}`',
            view=OrganizerView(event['id']),
        )


async def create_full_event(
    guild: discord.Guild,
    *,
    organizer: discord.abc.User,
    title: str,
    description: str,
    starts_at: datetime,
    max_participants: int,
    preferred_voice_id: int = 0,
) -> dict:
    cfg = _cfg()
    cat = await _ensure_category(guild, cfg)
    announce_ch = await _ensure_announce_channel(guild, cfg)
    if announce_ch is None:
        raise RuntimeError('Нет канала анонсов (задайте EVENT_ANNOUNCE_CHANNEL_ID).')

    voice = None
    if preferred_voice_id:
        voice = guild.get_channel(preferred_voice_id)
        if not isinstance(voice, discord.VoiceChannel):
            try:
                voice = await guild.fetch_channel(preferred_voice_id)
            except Exception:
                voice = None
            if not isinstance(voice, discord.VoiceChannel):
                voice = None
    if voice is None:
        # create dedicated voice named after event
        try:
            voice = await guild.create_voice_channel(
                title[:100],
                category=cat,
                reason=f'eventstart by {organizer.id}')
        except Exception as ex:
            log.warning('create voice failed (%s) — fallback stay channel', ex)
            # fallback: event stay voice
            try:
                from services.event_voice_bot import _resolve_event_voice_channel_id
                fid = int(_resolve_event_voice_channel_id() or 0)
            except Exception:
                fid = 0
            if fid:
                voice = guild.get_channel(fid)
            if not isinstance(voice, discord.VoiceChannel):
                raise RuntimeError(
                    f'Не удалось создать войс ({ex}). '
                    f'Выдайте боту Manage Channels или укажите voice в /eventstart.'
                ) from ex
            preferred_voice_id = voice.id

    event = STORE.create_event(
        guild_id=guild.id,
        organizer_id=organizer.id,
        title=title,
        description=description,
        starts_at=starts_at.astimezone(timezone.utc).timestamp(),
        max_participants=max_participants,
        voice_channel_id=voice.id,
        voice_name=voice.name,
        announce_channel_id=announce_ch.id,
        created_voice=bool(preferred_voice_id == 0 or (
            preferred_voice_id and voice.id != preferred_voice_id)),
    )
    # If preferred existing voice was chosen, created_voice=False — don't delete on finish
    if preferred_voice_id and voice.id == preferred_voice_id:
        STORE.update_event(event['id'], created_voice=False)
        event['created_voice'] = False
    else:
        STORE.update_event(event['id'], created_voice=True)
        event['created_voice'] = True

    sid = await _sync_discord_event(guild, event)
    if sid:
        event = STORE.update_event(event['id'], scheduled_event_id=sid) or event

    body = _announce_body(event, voice.name)
    e = discord.Embed(color=_BLACK, description=body[:4000])
    e.set_footer(text=f'Hakumo · Events · id {event["id"]}')
    role_id = CFG.iid(cfg, 'announce_role_id')
    content = f'<@&{role_id}>' if role_id else None
    msg = await announce_ch.send(
        content=content,
        embed=e,
        view=PublicSignupView(event['id']),
        allowed_mentions=discord.AllowedMentions(roles=True),
    )
    event = STORE.update_event(
        event['id'],
        announce_message_id=msg.id,
        announce_channel_id=announce_ch.id,
    ) or event

    # DM organizer control card
    try:
        await organizer.send(
            content=f'Панель организатора · **{title}**',
            view=OrganizerView(event['id']),
        )
    except Exception:
        pass
    return event


async def _dm_remind(client, event: dict, prefix: str) -> int:
    n = 0
    title = event.get('title') or 'Ивент'
    date_s, time_s = _fmt_when(event.get('starts_at') or 0)
    text = f'{prefix}\n**{title}** · {date_s} {time_s} МСК'
    for uid in event.get('signups') or []:
        try:
            u = await client.fetch_user(int(uid))
            await u.send(**_v2_or_embed('⏰ Напоминание', text))
            n += 1
        except Exception:
            continue
    return n


async def _cancel_event(guild: discord.Guild, event: dict) -> None:
    updated = STORE.update_event(event['id'], status='cancelled') or event
    await _sync_discord_event(guild, updated)
    await _refresh_announce(guild, updated)


async def _finish_event(guild: discord.Guild, event: dict) -> None:
    cfg = _cfg()
    updated = STORE.update_event(event['id'], status='finished') or event
    await _sync_discord_event(guild, updated)
    # delete voice only if we created it for this event
    if updated.get('created_voice'):
        vid = int(updated.get('voice_channel_id') or 0)
        if vid:
            vc = guild.get_channel(vid)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.delete(reason='eventstart: finish')
                except Exception as ex:
                    log.info('delete voice: %s', ex)
    await _refresh_announce(guild, updated)
    STORE.record_organizer_finish(guild.id, int(updated.get('organizer_id') or 0), updated['id'])
    summary = STORE.attendance_summary(
        updated, min_seconds=int(cfg.get('min_attend_seconds') or 600))
    body = (
        f'**{updated.get("title")}**\n\n'
        f'Зарегистрировано: **{summary["registered"]}**\n'
        f'Пришло (≥10 мин): **{summary["came"]}**\n'
        f'Не пришло: **{summary["no_show"]}**'
    )
    try:
        org = await guild.fetch_member(int(updated.get('organizer_id') or 0))
        await org.send(**_v2_or_embed('📊 Статистика ивента', body))
    except Exception:
        pass
    # also post under announce if possible
    try:
        ch_id = int(updated.get('announce_channel_id') or 0)
        ch = guild.get_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(embed=discord.Embed(color=_BLACK, description=f'## 📊 Статистика\n{body}'))
    except Exception:
        pass


# ── Cog ─────────────────────────────────────────────────────────────────

class EventLifecycle(commands.Cog):
    """TZ: /eventstart + /eventstats + reminders + voice attendance."""

    def __init__(self, bot):
        self.bot = bot
        self._voice_join_at: dict[tuple[int, int], float] = {}
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @app_commands.command(name='eventstart', description='Создать ивент (форма · Discord Event · анонс)')
    @app_commands.describe(voice='Голосовой канал (иначе создадим в категории ・ивенты)')
    async def eventstart(self, interaction: discord.Interaction,
                         voice: discord.VoiceChannel | None = None):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        if not _is_event_staff(interaction.user):
            return await interaction.response.send_message(
                'Нужна роль Event Mod / Event Admin.', ephemeral=True)
        vid = voice.id if voice else 0
        await interaction.response.send_modal(EventStartModal(vid))

    @app_commands.command(name='eventstats', description='Статистика организаторов (неделя / месяц)')
    async def eventstats(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        if not _is_event_staff(interaction.user):
            return await interaction.response.send_message('Только Event staff.', ephemeral=True)
        rows = STORE.organizer_counts(interaction.guild.id)
        if not rows:
            return await interaction.response.send_message(
                ephemeral=True, **_v2_or_embed('Статистика', 'Пока нет завершённых ивентов.'))
        lines = []
        for r in rows[:25]:
            lines.append(
                f'<@{r["organizer_id"]}> — неделя **{r["week"]}** · месяц **{r["month"]}** · всего {r["total"]}')
        await interaction.response.send_message(
            ephemeral=True,
            **_v2_or_embed('📊 Организаторы', '\n'.join(lines)))

    @commands.Cog.listener()
    async def on_ready(self):
        # re-bind persistent views for active events
        try:
            for ev in STORE.list_events(status='scheduled'):
                eid = ev.get('id')
                if not eid:
                    continue
                self.bot.add_view(PublicSignupView(eid))
                self.bot.add_view(OrganizerView(eid))
        except Exception as ex:
            log.debug('bind views: %s', ex)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member is None or getattr(member, 'bot', False):
            return
        # track time in any scheduled event voice
        active = STORE.list_events(status='scheduled')
        voice_map = {int(e.get('voice_channel_id') or 0): e for e in active if e.get('voice_channel_id')}
        before_id = getattr(getattr(before, 'channel', None), 'id', None)
        after_id = getattr(getattr(after, 'channel', None), 'id', None)
        key = (int(member.guild.id), int(member.id))
        now = time_now()
        # leaving tracked voice
        if before_id and before_id in voice_map and before_id != after_id:
            started = self._voice_join_at.pop(key, None)
            if started:
                STORE.add_voice_seconds(voice_map[before_id]['id'], member.id, now - started)
        # joining tracked voice
        if after_id and after_id in voice_map:
            self._voice_join_at[key] = now

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        cfg = _cfg()
        now = time_now()
        h = int(cfg.get('remind_hours') or 1) * 3600
        m = int(cfg.get('remind_minutes') or 10) * 60
        for ev in STORE.list_events(status='scheduled'):
            start = float(ev.get('starts_at') or 0)
            if not start:
                continue
            left = start - now
            title = ev.get('title') or 'Ивент'
            if not ev.get('reminded_1h') and 0 < left <= h:
                await _dm_remind(self.bot, ev, f'Ивент «{title}» начнётся через 1 час.')
                STORE.update_event(ev['id'], reminded_1h=True)
            if not ev.get('reminded_10m') and 0 < left <= m:
                await _dm_remind(self.bot, ev, f'Ивент «{title}» начинается через 10 минут!')
                STORE.update_event(ev['id'], reminded_10m=True)

    @reminder_loop.before_loop
    async def _before_remind(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(EventLifecycle(bot))
