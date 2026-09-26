# -*- coding: utf-8 -*-
"""Support-бот: /verify · /norma · /top — V2 чёрный UI, только selects."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger('support_verify')

from services import support_bot_config as CFG
from services import support_store as STORE
from services import support_emojis as EMO

_BLACK = 0x000000
_BANNER = Path('assets/stickers/verify_banner.png')
_WEEKDAYS_RU = [
    'Понедельник', 'Вторник', 'Среда', 'Четверг',
    'Пятница', 'Суббота', 'Воскресенье',
]
_MONTHS_RU = [
    '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]
_VOICE_JOIN: dict[tuple[int, int], float] = {}


def _cfg():
    return CFG.load_config()


def _has_support(member, cfg: dict) -> bool:
    if member is None:
        return False
    perms = getattr(member, 'guild_permissions', None)
    if perms and getattr(perms, 'administrator', False):
        return True
    ids = {CFG.role_id(cfg, 'support_role_id'),
           CFG.role_id(cfg, 'support_lead_role_id')}
    ids.discard(0)
    return any(getattr(r, 'id', None) in ids for r in getattr(member, 'roles', []))


def _is_appeal_reviewer(member, cfg: dict) -> bool:
    if member is None:
        return False
    perms = getattr(member, 'guild_permissions', None)
    if perms and getattr(perms, 'administrator', False):
        return True
    lead = CFG.role_id(cfg, 'support_lead_role_id')
    if lead and any(getattr(r, 'id', None) == lead for r in getattr(member, 'roles', [])):
        return True
    for r in getattr(member, 'roles', []):
        n = (getattr(r, 'name', '') or '').lower()
        if 'administrator' in n or 'owner' in n:
            return True
    return False


def _gender_roles(cfg: dict):
    return CFG.role_id(cfg, 'male_role_id'), CFG.role_id(cfg, 'female_role_id')


def _is_verified(member, cfg: dict) -> bool:
    male, female = _gender_roles(cfg)
    ids = {getattr(r, 'id', None) for r in getattr(member, 'roles', [])}
    return bool((male and male in ids) or (female and female in ids))


def _current_gender(member, cfg: dict) -> Optional[str]:
    male, female = _gender_roles(cfg)
    ids = {getattr(r, 'id', None) for r in getattr(member, 'roles', [])}
    if male and male in ids:
        return 'male'
    if female and female in ids:
        return 'female'
    return None


def _gender_label(g: Optional[str]) -> str:
    if g == 'male':
        return 'Мальчик'
    if g == 'female':
        return 'Девочка'
    return '—'


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return '—'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    wd = _WEEKDAYS_RU[local.weekday()]
    try:
        mon = _MONTHS_RU[local.month]
    except Exception:
        mon = str(local.month)
    return f'{wd}, {local.day} {mon} {local.year} {local.hour:02d}:{local.minute:02d}'


def _fmt_seconds(sec: float) -> str:
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m = rem // 60
    return f'{h} час. {m} мин.'


async def resolve_member(guild: discord.Guild, query: str) -> Optional[discord.Member]:
    q = (query or '').strip()
    if not q:
        return None
    if q.startswith('<@') and q.endswith('>'):
        q = q.strip('<@!>')
    if q.isdigit():
        mid = int(q)
        m = guild.get_member(mid)
        if m:
            return m
        try:
            return await guild.fetch_member(mid)
        except Exception:
            return None
    qn = q.lower().lstrip('@')

    def _score_pool(members):
        exact, starts, contains = [], [], []
        for m in members:
            names = {
                (m.name or '').lower(),
                (m.display_name or '').lower(),
                (getattr(m, 'global_name', None) or '').lower(),
                (m.nick or '').lower() if m.nick else '',
            }
            names.discard('')
            if qn in names:
                exact.append(m)
            elif any(n.startswith(qn) for n in names):
                starts.append(m)
            elif any(qn in n for n in names):
                contains.append(m)
        for bucket in (exact, starts, contains):
            if len(bucket) == 1:
                return bucket[0]
            if len(bucket) > 1:
                return sorted(bucket, key=lambda x: x.id)[0]
        return None

    hit = _score_pool(list(guild.members))
    if hit:
        return hit
    try:
        found = await guild.query_members(query=qn[:100], limit=10)
        hit = _score_pool(found or [])
        if hit:
            return hit
        if found and len(found) == 1:
            return found[0]
    except Exception as ex:
        log.debug('query_members: %s', ex)
    return None


async def _ensure_role(guild: discord.Guild, cfg: dict, key: str,
                       name: str) -> Optional[discord.Role]:
    rid = CFG.role_id(cfg, key)
    if rid:
        r = guild.get_role(rid)
        if r:
            return r
    for r in guild.roles:
        if (r.name or '').lower() == name.lower():
            cfg[key] = str(r.id)
            CFG.save_config(cfg)
            return r
    if not cfg.get('create_missing'):
        return None
    try:
        r = await guild.create_role(name=name, reason='support-bot: seed')
        cfg[key] = str(r.id)
        CFG.save_config(cfg)
        return r
    except Exception as ex:
        log.warning('create role %s: %s', name, ex)
        return None


async def _ensure_channel(guild: discord.Guild, cfg: dict, key: str,
                          name: str) -> Optional[discord.TextChannel]:
    cid = CFG.role_id(cfg, key)
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            return ch
    needle = name.lstrip('・').lower()
    for ch in guild.text_channels:
        n = (ch.name or '')
        if n == name or n.lstrip('・').lower() == needle:
            cfg[key] = str(ch.id)
            CFG.save_config(cfg)
            return ch
    if not cfg.get('create_missing'):
        return None
    cat_id = CFG.role_id(cfg, 'staff_log_category_id')
    cat = guild.get_channel(cat_id) if cat_id else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_messages=True),
    }
    for rk in ('support_role_id', 'support_lead_role_id'):
        role = guild.get_role(CFG.role_id(cfg, rk))
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)
    try:
        ch = await guild.create_text_channel(
            name,
            category=cat if isinstance(cat, discord.CategoryChannel) else None,
            overwrites=overwrites, reason='support-bot: seed')
        cfg[key] = str(ch.id)
        CFG.save_config(cfg)
        return ch
    except Exception as ex:
        log.warning('create channel %s: %s', name, ex)
        return None


async def ensure_infra(guild: discord.Guild) -> dict:
    cfg = _cfg()
    await _ensure_role(guild, cfg, 'unverify_role_id', 'unverify')
    await _ensure_role(guild, cfg, 'nedopusk_role_id', 'недопуск')
    await _ensure_channel(guild, cfg, 'reviews_channel_id', '・отзывы-support')
    await _ensure_channel(guild, cfg, 'appeals_channel_id', '・апелляции-support')
    return _cfg()


def _embed_fallback(title: str, body: str, footer: str = 'Hakumo · Support',
                    thumb: str | None = None):
    e = discord.Embed(color=_BLACK)
    e.description = f'## {title}\n{body}'
    e.set_footer(text=footer)
    if thumb:
        e.set_thumbnail(url=thumb)
    return e


def _v2_or_embed(title: str, body: str, footer: str = 'Hakumo · Support'):
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
    return {'embed': _embed_fallback(title, body, footer)}


def _member_info_body(target: discord.Member, requester: discord.Member,
                      cfg: dict) -> str:
    meta = STORE.get_user_meta(target.guild.id, target.id)
    joined = _fmt_dt(getattr(target, 'joined_at', None))
    created = _fmt_dt(getattr(target, 'created_at', None))
    denials = int(meta.get('denials') or 0)
    reason = meta.get('last_deny_reason') or 'Отсутствует'
    if not reason.strip():
        reason = 'Отсутствует'
    rejoins = int(meta.get('rejoins') or 0)
    status_bits = []
    if _is_verified(target, cfg):
        status_bits.append(f'верифицирован · {_gender_label(_current_gender(target, cfg))}')
    ned = CFG.role_id(cfg, 'nedopusk_role_id')
    if ned and any(r.id == ned for r in target.roles):
        status_bits.append('недопуск')
    status = ', '.join(status_bits) if status_bits else 'без статуса'
    return (
        f'# Информация о {target.display_name}\n'
        f'-# HAKUMO · Support\n\n'
        f'**Присоединился**\n{joined}\n'
        f'**Создан аккаунт**\n{created}\n'
        f'**Устройство**\nНеизвестно\n\n'
        f'**Недопущен**\n{denials} раз(-а)\n'
        f'**Причина**\n{reason}\n'
        f'**Перезаходов**\n{rejoins}\n\n'
        f'**Цель:** {target.mention} (`{target.id}`)\n'
        f'**Статус:** {status}\n'
        f'-# Запросил(а) {requester.display_name}'
    )


# ── V2 panels (selects only) ────────────────────────────────────────────

class VerifyPanelView(discord.ui.LayoutView):
    """Карточка участника + select действий (без кнопок)."""

    def __init__(self, target_id: int, body: str, banner_name: str | None = None):
        super().__init__(timeout=300)
        from services.v2_layouts import black_container, SeparatorSpacing, V2_AVAILABLE
        from discord import ui as _ui
        if not V2_AVAILABLE:
            raise RuntimeError('V2 unavailable')
        self.target_id = target_id
        head = [
            _ui.TextDisplay(body[:3500]),
            _ui.Separator(spacing=SeparatorSpacing.small),
        ]
        if banner_name:
            try:
                from discord.components import MediaGalleryItem
                head.append(_ui.MediaGallery(MediaGalleryItem(f'attachment://{banner_name}')))
                head.append(_ui.Separator())
            except Exception:
                pass
        self.add_item(black_container(*head, accent=_BLACK))
        row = _ui.ActionRow()
        row.add_item(ActionSelect(target_id))
        self.add_item(black_container(
            _ui.TextDisplay('**Действие**'),
            row,
            accent=_BLACK,
        ))


class GenderPanelView(discord.ui.LayoutView):
    def __init__(self, target_id: int, support_id: int, body: str, mode: str):
        super().__init__(timeout=300)
        from services.v2_layouts import black_container, SeparatorSpacing
        from discord import ui as _ui
        self.add_item(black_container(
            _ui.TextDisplay(body[:3500]),
            _ui.Separator(spacing=SeparatorSpacing.small),
            accent=_BLACK,
        ))
        row = _ui.ActionRow()
        row.add_item(GenderSelect(target_id, support_id, mode=mode))
        self.add_item(black_container(
            _ui.TextDisplay('**Гендер**'),
            row,
            accent=_BLACK,
        ))


class ActionSelect(discord.ui.Select):
    def __init__(self, target_id: int):
        self.target_id = target_id
        opts = [
            discord.SelectOption(
                label='Верификация', value='verify',
                emoji=EMO.emoji_for('s_verify'),
                description='Выбрать гендерку и верифицировать'),
            discord.SelectOption(
                label='Недопуск', value='deny',
                emoji=EMO.emoji_for('s_deny'),
                description='Выдать недопуск + кик из войса'),
            discord.SelectOption(
                label='Снять недопуск', value='undeny',
                emoji=EMO.emoji_for('s_undeny'),
                description='Снять недопуск → unverify'),
            discord.SelectOption(
                label='Сменить пол', value='gender',
                emoji=EMO.emoji_for('s_gender'),
                description='Мальчик ↔ Девочка'),
            discord.SelectOption(
                label='Выход', value='exit',
                description='Закрыть панель'),
        ]
        super().__init__(placeholder='Выберите действие…', min_values=1,
                         max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        if not _has_support(interaction.user, cfg) or not interaction.guild:
            return await interaction.response.send_message('Нет доступа.', ephemeral=True)
        if self.values[0] == 'exit':
            return await interaction.response.send_message(
                ephemeral=True, **_v2_or_embed('Выход', 'Панель закрыта.'))
        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                return await interaction.response.send_message(
                    'Участник не найден.', ephemeral=True)
        action = self.values[0]
        if action == 'verify':
            if _is_verified(target, cfg):
                return await interaction.response.send_message(
                    ephemeral=True,
                    **_v2_or_embed(
                        'Уже верифицирован',
                        f'Этот пользователь верифицирован {target.mention}.\n'
                        f'Снова введите `/verify`, чтобы выполнить другое действие.'))
            body = (
                f'# Верификация | Hakumo\n-# HAKUMO · Support\n\n'
                f'| **Пользователь**\n{target.mention} `{target.id}`\n\n'
                f'| **Саппорт**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
                f'Выберите гендер:')
            return await interaction.response.send_message(
                view=GenderPanelView(target.id, interaction.user.id, body, 'verify'),
                ephemeral=True)
        if action == 'deny':
            await interaction.response.defer(ephemeral=True)
            return await do_deny(interaction, target, cfg)
        if action == 'undeny':
            await interaction.response.defer(ephemeral=True)
            return await do_undeny(interaction, target, cfg)
        if action == 'gender':
            if not _is_verified(target, cfg):
                return await interaction.response.send_message(
                    ephemeral=True,
                    **_v2_or_embed('Не верифицирован',
                                  f'{target.mention} ещё не верифицирован.'))
            body = (
                f'# Смена пола | Hakumo\n-# HAKUMO · Support\n\n'
                f'| **Пользователь**\n{target.mention} `{target.id}`\n\n'
                f'| **Сейчас**\n{_gender_label(_current_gender(target, cfg))}\n\n'
                f'Выберите новый пол:')
            return await interaction.response.send_message(
                view=GenderPanelView(target.id, interaction.user.id, body, 'swap'),
                ephemeral=True)


class GenderSelect(discord.ui.Select):
    def __init__(self, target_id: int, support_id: int, mode: str = 'verify'):
        self.target_id = target_id
        self.support_id = support_id
        self.mode = mode
        opts = [
            discord.SelectOption(label='Мальчик', value='male',
                                 emoji=EMO.emoji_for('s_male')),
            discord.SelectOption(label='Девочка', value='female',
                                 emoji=EMO.emoji_for('s_female')),
        ]
        super().__init__(placeholder='Гендер…', min_values=1, max_values=1,
                         options=opts)

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        if not interaction.guild or not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нет доступа.', ephemeral=True)
        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                return await interaction.response.send_message(
                    'Участник не найден.', ephemeral=True)
        gender = self.values[0]
        if self.mode == 'verify':
            body = (
                f'# Верификация | Hakumo\n-# HAKUMO · Support\n\n'
                f'| **Пользователь**\n{target.mention} `{target.id}`\n\n'
                f'| **Саппорт**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
                f'| **Гендер**\n{_gender_label(gender)}'
            )
            return await interaction.response.send_message(
                view=ConfirmPanelView(target.id, interaction.user.id, body,
                                      pending_gender=gender),
                ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await do_gender_swap(interaction, target, cfg, gender)


class ConfirmPanelView(discord.ui.LayoutView):
    """После выбора пола — карточка + select (без кнопок)."""

    def __init__(self, target_id: int, support_id: int, body: str,
                 pending_gender: str = 'female'):
        super().__init__(timeout=300)
        from services.v2_layouts import black_container
        from discord import ui as _ui
        self.pending_gender = pending_gender
        self.add_item(black_container(
            _ui.TextDisplay(body[:3500]),
            accent=_BLACK,
        ))
        row = _ui.ActionRow()
        row.add_item(ConfirmSelect(target_id, support_id))
        self.add_item(black_container(
            _ui.TextDisplay('**Далее**'),
            row,
            accent=_BLACK,
        ))


class ConfirmSelect(discord.ui.Select):
    def __init__(self, target_id: int, support_id: int):
        self.target_id = target_id
        self.support_id = support_id
        opts = [
            discord.SelectOption(label='Подтвердить', value='ok',
                                 emoji=EMO.emoji_for('s_verify'),
                                 description='Применить верификацию'),
            discord.SelectOption(label='Изменить выбор', value='change',
                                 emoji=EMO.emoji_for('s_gender'),
                                 description='Выбрать гендер заново'),
            discord.SelectOption(label='Отмена', value='cancel',
                                 description='Закрыть'),
        ]
        super().__init__(placeholder='Подтверждение…', min_values=1,
                         max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        if not interaction.guild or not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нет доступа.', ephemeral=True)
        act = self.values[0]
        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                return await interaction.response.send_message(
                    'Участник не найден.', ephemeral=True)
        if act == 'cancel':
            return await interaction.response.send_message(
                ephemeral=True, **_v2_or_embed('Отмена', 'Верификация отменена.'))
        if act == 'change':
            body = (
                f'# Верификация | Hakumo\n-# HAKUMO · Support\n\n'
                f'| **Пользователь**\n{target.mention} `{target.id}`\n\n'
                f'| **Саппорт**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
                f'Выберите гендер:')
            return await interaction.response.send_message(
                view=GenderPanelView(target.id, interaction.user.id, body, 'verify'),
                ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        g = getattr(self.view, 'pending_gender', None) or 'female'
        await do_verify(interaction, target, cfg, g)


class ReviewSelect(discord.ui.Select):
    """В ЛС: select вместо кнопки «оставить отзыв»."""

    def __init__(self, support_id: int):
        self.support_id = support_id
        opts = [
            discord.SelectOption(
                label='Оставить отзыв', value='review',
                emoji=EMO.emoji_for('s_review'),
                description='Откроется форма (до 140 символов)'),
        ]
        super().__init__(
            placeholder='Отзыв саппорту…', min_values=1, max_values=1,
            options=opts, custom_id=f'sup:revsel:{support_id}')

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        await interaction.response.send_modal(
            ReviewModal(self.support_id, int(cfg.get('review_max_chars', 140))))


class ReviewDMView(discord.ui.View):
    def __init__(self, support_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.add_item(ReviewSelect(support_id))


class AppealSelect(discord.ui.Select):
    def __init__(self, support_id: int):
        self.support_id = support_id
        opts = [
            discord.SelectOption(
                label='Отправить апелляцию', value='appeal',
                emoji=EMO.emoji_for('appeal'),
                description='Форма апелляции на недопуск'),
        ]
        super().__init__(
            placeholder='Апелляция…', min_values=1, max_values=1,
            options=opts, custom_id=f'sup:aplsel:{support_id}')

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AppealModal(self.support_id))


class AppealDMView(discord.ui.View):
    def __init__(self, support_id: int):
        super().__init__(timeout=None)
        self.add_item(AppealSelect(support_id))


class AppealDecideSelect(discord.ui.Select):
    def __init__(self, appeal_id: str):
        self.appeal_id = appeal_id
        opts = [
            discord.SelectOption(label='Одобрить', value='ok',
                                 description='Снять недопуск'),
            discord.SelectOption(label='Отклонить', value='no',
                                 description='Оставить недопуск'),
        ]
        super().__init__(
            placeholder='Решение…', min_values=1, max_values=1,
            options=opts, custom_id=f'sup:decide:{appeal_id}')

    async def callback(self, interaction: discord.Interaction):
        await resolve_appeal(interaction, self.appeal_id, self.values[0] == 'ok')


class AppealStaffView(discord.ui.View):
    def __init__(self, appeal_id: str):
        super().__init__(timeout=None)
        self.add_item(AppealDecideSelect(appeal_id))


# ── Modals ──────────────────────────────────────────────────────────────

class ReviewModal(discord.ui.Modal, title='Отзыв саппорту'):
    def __init__(self, support_id: int, max_chars: int = 140):
        super().__init__()
        self.support_id = support_id
        self.field = discord.ui.TextInput(
            label='Отзыв', style=discord.TextStyle.paragraph,
            max_length=max_chars, min_length=1, required=True,
            placeholder=f'До {max_chars} символов')
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = _cfg()
        text = str(self.field.value or '').strip()[:int(cfg.get('review_max_chars', 140))]
        guild = interaction.client.get_guild(CFG.gid(cfg))
        msg_id = None
        if guild:
            ch = await _ensure_channel(guild, cfg, 'reviews_channel_id', '・отзывы-support')
            if ch:
                body = (
                    f'| **От**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
                    f'| **Саппорт**\n<@{self.support_id}>\n\n> {text}')
                m = await ch.send(embed=_embed_fallback('⭐ Отзыв', body, 'Hakumo · Support reviews'))
                msg_id = m.id
        STORE.add_review(
            guild_id=CFG.gid(cfg), user_id=interaction.user.id,
            support_id=self.support_id, text=text, message_id=msg_id)
        STORE.pop_pending_review(interaction.user.id)
        await interaction.response.send_message(
            ephemeral=True, **_v2_or_embed('Спасибо', 'Отзыв отправлен.'))


class AppealModal(discord.ui.Modal, title='Апелляция на недопуск'):
    def __init__(self, support_id: int):
        super().__init__()
        self.support_id = support_id
        self.field = discord.ui.TextInput(
            label='Почему не согласны?', style=discord.TextStyle.paragraph,
            max_length=800, min_length=5, required=True)
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = _cfg()
        reason = str(self.field.value or '').strip()
        appeal = STORE.add_appeal(
            guild_id=CFG.gid(cfg), user_id=interaction.user.id,
            support_id=self.support_id, reason=reason)
        guild = interaction.client.get_guild(CFG.gid(cfg))
        if guild:
            ch = await _ensure_channel(guild, cfg, 'appeals_channel_id', '・апелляции-support')
            if ch:
                body = (
                    f'| **Участник**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
                    f'| **Выдал недопуск**\n<@{self.support_id}>\n\n'
                    f'| **ID**\n`{appeal["id"]}`\n\n> {reason}')
                m = await ch.send(
                    embed=_embed_fallback('📝 Апелляция · недопуск', body),
                    view=AppealStaffView(appeal['id']))
                data = STORE._load(STORE.APPEALS)
                for x in data.get('items') or []:
                    if x.get('id') == appeal['id']:
                        x['message_id'] = str(m.id)
                        STORE._save(STORE.APPEALS, data)
                        break
        await interaction.response.send_message(
            ephemeral=True,
            **_v2_or_embed('Апелляция', 'Отправлена. Ожидайте решения.'))


async def resolve_appeal(interaction: discord.Interaction, appeal_id: str, approve: bool):
    cfg = _cfg()
    member = interaction.user
    if not isinstance(member, discord.Member):
        g = interaction.client.get_guild(CFG.gid(cfg))
        member = g.get_member(interaction.user.id) if g else None
    if not member or not _is_appeal_reviewer(member, cfg):
        return await interaction.response.send_message(
            'Только старший саппорт / администратор.', ephemeral=True)
    it = STORE.get_appeal(appeal_id)
    if not it or it.get('status') != 'pending':
        return await interaction.response.send_message(
            'Апелляция уже рассмотрена или не найдена.', ephemeral=True)
    STORE.set_appeal_status(appeal_id, 'approved' if approve else 'rejected',
                            reviewer_id=interaction.user.id)
    guild = interaction.guild or interaction.client.get_guild(CFG.gid(cfg))
    if guild and approve:
        try:
            m = guild.get_member(int(it['user_id'])) or await guild.fetch_member(int(it['user_id']))
            await do_undeny_roles(m, cfg)
        except Exception as ex:
            log.info('appeal undeny: %s', ex)
    try:
        u = await interaction.client.fetch_user(int(it['user_id']))
        text = ('Ваша апелляция **одобрена**. Недопуск снят.'
                if approve else 'Ваша апелляция **не одобрена**.')
        await u.send(**_v2_or_embed('📝 Решение по апелляции', text))
    except Exception as ex:
        log.info('appeal dm: %s', ex)
    await interaction.response.send_message(
        ephemeral=True,
        **_v2_or_embed('Решение', 'Одобрено.' if approve else 'Отклонено.'))
    try:
        await interaction.message.edit(view=None)
    except Exception:
        pass


# ── Role actions ────────────────────────────────────────────────────────

async def do_verify(interaction, target: discord.Member, cfg: dict, gender: str):
    await interaction.followup.send(
        ephemeral=True, **_v2_or_embed('Обработка…', f'Верифицируем {target.mention}…'))
    male_id, female_id = _gender_roles(cfg)
    male = target.guild.get_role(male_id) if male_id else None
    female = target.guild.get_role(female_id) if female_id else None
    unverify = await _ensure_role(target.guild, cfg, 'unverify_role_id', 'unverify')
    rem, add = [], []
    if gender == 'male' and male:
        add.append(male)
        if female and female in target.roles:
            rem.append(female)
    elif gender == 'female' and female:
        add.append(female)
        if male and male in target.roles:
            rem.append(male)
    if unverify and unverify in target.roles:
        rem.append(unverify)
    try:
        if rem:
            await target.remove_roles(*rem, reason=f'verify by {interaction.user}')
        if add:
            await target.add_roles(*add, reason=f'verify by {interaction.user}')
    except Exception as ex:
        await interaction.followup.send(f'Ошибка ролей: {ex}', ephemeral=True)
        return
    STORE.bump_verify(target.guild.id, interaction.user.id)
    label = _gender_label(gender)
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed(
            'Верификация | Hakumo',
            f'| **Пользователь**\n{target.mention} `{target.id}`\n\n'
            f'| **Саппорт**\n{interaction.user.mention} `{interaction.user.id}`\n\n'
            f'| **Гендер**\n{label}\n\n'
            f'{target.mention}, пользователь верифицирован.'))
    # DM: 5 минут на отзыв — select, без кнопок
    window = int(cfg.get('review_window_seconds') or 300)
    mins = max(1, window // 60)
    try:
        body = (
            f'{target.mention}, вы успешно прошли верификацию.\n'
            f'У вас есть **{mins} минут**, чтобы оставить отзыв.\n\n'
            f'| **Саппорт**\n{interaction.user.mention}'
        )
        STORE.set_pending_review(
            user_id=target.id, support_id=interaction.user.id,
            guild_id=target.guild.id, expires_at=time.time() + window)
        await target.send(
            embed=_embed_fallback('Верификация | Hakumo', body),
            view=ReviewDMView(interaction.user.id, timeout=float(window)))
    except Exception as ex:
        log.info('verify dm: %s', ex)


async def do_deny(interaction, target: discord.Member, cfg: dict):
    ned = await _ensure_role(target.guild, cfg, 'nedopusk_role_id', 'недопуск')
    unverify = await _ensure_role(target.guild, cfg, 'unverify_role_id', 'unverify')
    male_id, female_id = _gender_roles(cfg)
    rem = []
    for rid in (male_id, female_id):
        r = target.guild.get_role(rid) if rid else None
        if r and r in target.roles:
            rem.append(r)
    try:
        if rem:
            await target.remove_roles(*rem, reason='недопуск')
        if unverify and unverify in target.roles:
            await target.remove_roles(unverify, reason='недопуск')
        if ned:
            await target.add_roles(ned, reason=f'недопуск by {interaction.user}')
        if target.voice and target.voice.channel:
            try:
                await target.move_to(None, reason='недопуск')
            except Exception:
                pass
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    STORE.bump_denial(target.guild.id, target.id, reason='недопуск')
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed('Недопуск',
                       f'{target.mention} ← {interaction.user.mention}'))
    try:
        body = (
            f'Вам выдал недопуск {interaction.user.mention}.\n'
            f'Если не согласны — отправьте апелляцию ниже.')
        await target.send(
            embed=_embed_fallback('🚫 Недопуск', body),
            view=AppealDMView(interaction.user.id))
    except Exception as ex:
        log.info('deny dm: %s', ex)


async def do_undeny_roles(member: discord.Member, cfg: dict):
    ned = await _ensure_role(member.guild, cfg, 'nedopusk_role_id', 'недопуск')
    unverify = await _ensure_role(member.guild, cfg, 'unverify_role_id', 'unverify')
    if ned and ned in member.roles:
        await member.remove_roles(ned, reason='снять недопуск')
    if unverify and unverify not in member.roles:
        await member.add_roles(unverify, reason='снять недопуск → unverify')


async def do_undeny(interaction, target: discord.Member, cfg: dict):
    try:
        await do_undeny_roles(target, cfg)
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed('Недопуск снят',
                       f'{target.mention}: недопуск снят, возвращён **unverify**.'))


async def do_gender_swap(interaction, target: discord.Member, cfg: dict, gender: str):
    male_id, female_id = _gender_roles(cfg)
    male = target.guild.get_role(male_id) if male_id else None
    female = target.guild.get_role(female_id) if female_id else None
    try:
        if gender == 'male':
            if female and female in target.roles:
                await target.remove_roles(female, reason='gender')
            if male and male not in target.roles:
                await target.add_roles(male, reason='gender')
        else:
            if male and male in target.roles:
                await target.remove_roles(male, reason='gender')
            if female and female not in target.roles:
                await target.add_roles(female, reason='gender')
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed(
            'Пол изменён',
            f'{target.mention} → **{_gender_label(gender)}**'))


# ── Cog ─────────────────────────────────────────────────────────────────

class SupportVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name='verify',
        description='Панель саппорта: верификация / недопуск / пол')
    @app_commands.describe(пользователь='ID, ник или упоминание')
    async def verify_cmd(self, interaction: discord.Interaction, пользователь: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        cfg = _cfg()
        if not _has_support(interaction.user, cfg):
            return await interaction.response.send_message(
                'Нужна роль Support.', ephemeral=True)
        target = await resolve_member(interaction.guild, пользователь)
        if target is None:
            return await interaction.response.send_message(
                f'Не нашёл «{пользователь}».', ephemeral=True)
        if target.bot:
            return await interaction.response.send_message('Нельзя на боте.', ephemeral=True)

        body = _member_info_body(target, interaction.user, cfg)
        banner_name = None
        file = None
        if _BANNER.is_file():
            banner_name = 'verify_banner.png'
            file = discord.File(_BANNER, filename=banner_name)
        try:
            view = VerifyPanelView(target.id, body, banner_name=banner_name)
            kw = {'view': view, 'ephemeral': True}
            if file is not None:
                kw['file'] = file
            await interaction.response.send_message(**kw)
        except Exception as ex:
            log.warning('V2 panel fail, fallback: %s', ex)
            v = discord.ui.View(timeout=300)
            v.add_item(ActionSelect(target.id))
            emb = _embed_fallback(
                f'Информация о {target.display_name}', body,
                footer=f'Запросил(а) {interaction.user.display_name}')
            if target.display_avatar:
                emb.set_thumbnail(url=target.display_avatar.url)
            await interaction.response.send_message(
                embed=emb, view=v, ephemeral=True,
                file=file if file else discord.utils.MISSING)

    @app_commands.command(name='norma', description='Дневная норма саппортов')
    async def norma_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        cfg = _cfg()
        if not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нужна роль Support.', ephemeral=True)
        need = int(cfg.get('daily_norma') or 10)
        role = interaction.guild.get_role(CFG.role_id(cfg, 'support_role_id'))
        members = list(role.members) if role else []
        # without members intent role.members may be empty — use query via guild.members cache + fetch
        if not members:
            rid = CFG.role_id(cfg, 'support_role_id')
            members = [m for m in interaction.guild.members
                       if any(r.id == rid for r in m.roles)]
        lines = []
        n = 0
        for m in sorted(members, key=lambda x: x.display_name.lower()):
            if m.bot:
                continue
            done = STORE.daily_verifies(interaction.guild.id, m.id)
            if done >= need:
                continue
            n += 1
            lines.append(f'{n}. {m.mention} — Не выполнил норму ({done}/{need})')
        if not lines:
            body = f'Все саппорты выполнили норму (**{need}**/день).'
        else:
            body = '\n'.join(lines[:40])
        await interaction.response.send_message(
            ephemeral=True,
            **_v2_or_embed('Дневная норма саппортов', body + '\n\n-# Страница 1/1'))

    top = app_commands.Group(name='top', description='Топы саппорта')

    @top.command(name='online', description='Топ по онлайну (войс)')
    async def top_online_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        cfg = _cfg()
        if not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нужна роль Support.', ephemeral=True)
        rows = STORE.top_online(interaction.guild.id)
        if not rows:
            body = 'Список пуст'
        else:
            body = '\n'.join(
                f'{i}. <@{r["user_id"]}> — {_fmt_seconds(r["seconds"])}'
                for i, r in enumerate(rows, 1))
        await interaction.response.send_message(
            ephemeral=True,
            **_v2_or_embed('Топ по онлайну', body + '\n\n-# Страница 1/1'))

    @top.command(name='support', description='Топ по верификациям')
    async def top_support_cmd(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        cfg = _cfg()
        if not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нужна роль Support.', ephemeral=True)
        rows = STORE.top_support(interaction.guild.id)
        if not rows:
            body = 'Список пуст'
        else:
            body = '\n'.join(
                f'{i}. <@{r["user_id"]}> — **{r["verifies"]}**'
                for i, r in enumerate(rows, 1))
        await interaction.response.send_message(
            ephemeral=True,
            **_v2_or_embed('Топ по саппорт', body + '\n\n-# Страница 1/1'))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            STORE.bump_rejoin(member.guild.id, member.id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member is None or getattr(member, 'bot', False):
            return
        cfg = _cfg()
        if not _has_support(member, cfg):
            return
        key = (int(member.guild.id), int(member.id))
        now = time.time()
        before_ch = getattr(before, 'channel', None)
        after_ch = getattr(after, 'channel', None)
        if before_ch and before_ch != after_ch:
            started = _VOICE_JOIN.pop(key, None)
            if started:
                STORE.add_voice_seconds(member.guild.id, member.id, now - started)
        if after_ch and after_ch != before_ch:
            _VOICE_JOIN[key] = now

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        if interaction.response.is_done():
            return
        cid = str((interaction.data or {}).get('custom_id') or '')
        m = re.match(r'^sup:revsel:(\d+)$', cid)
        if m:
            cfg = _cfg()
            return await interaction.response.send_modal(
                ReviewModal(int(m.group(1)), int(cfg.get('review_max_chars', 140))))
        m = re.match(r'^sup:aplsel:(\d+)$', cid)
        if m:
            return await interaction.response.send_modal(AppealModal(int(m.group(1))))
        m = re.match(r'^sup:decide:([0-9a-f]+)$', cid)
        if m:
            # values come from select
            vals = (interaction.data or {}).get('values') or []
            approve = (vals[0] == 'ok') if vals else False
            return await resolve_appeal(interaction, m.group(1), approve)
        # legacy button custom_ids (на всякий случай)
        m = re.match(r'^sup:review:(\d+)$', cid)
        if m:
            cfg = _cfg()
            return await interaction.response.send_modal(
                ReviewModal(int(m.group(1)), int(cfg.get('review_max_chars', 140))))
        m = re.match(r'^sup:appealbtn:(\d+)$', cid)
        if m:
            return await interaction.response.send_modal(AppealModal(int(m.group(1))))


async def setup(bot):
    await bot.add_cog(SupportVerify(bot))
