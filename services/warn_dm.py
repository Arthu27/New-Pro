# -*- coding: utf-8 -*-
"""DM-шаблоны варна / снятия варна — отдельно для участника и стаффа."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import discord

from logger import get_logger

_log = get_logger('warn_dm')


def _ts() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_until(expires_at: str | None) -> str:
    if not expires_at:
        return '—'
    try:
        s = str(expires_at).replace('Z', '+00:00')
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
    except Exception:
        return str(expires_at)[:19]


def build_member_warn_dm(
    guild, moderator, *, reason: str, warn_id: int, active_count: int,
    expires_at: str | None = None,
) -> discord.Embed:
    """Жёлтый/оранжевый embed для обычного участника."""
    from services.warn_config import appeal_hint_member

    e = discord.Embed(
        title='⚠️ Предупреждение на сервере',
        color=0xF39C12,
        timestamp=_ts(),
    )
    until = _fmt_until(expires_at)
    e.description = (
        f'На сервере **{getattr(guild, "name", "сервер")}** вам выдали '
        f'предупреждение.\n\n'
        f'**Причина:** {reason or "Не указана"}\n'
        f'**Выдал:** {getattr(moderator, "display_name", moderator)}\n'
        f'**Варн №:** {warn_id}\n'
        f'**Активных варнов:** {active_count}\n'
        f'**Действует до:** {until}\n\n'
        f'Вам выдана роль **warn**. При накоплении предупреждений возможны '
        f'более строгие меры.\n\n'
        f'> {appeal_hint_member()}'
    )
    try:
        if getattr(guild, 'icon', None):
            e.set_thumbnail(url=guild.icon.url)
    except Exception:
        pass
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · участник')
    return e


def build_staff_warn_dm(
    guild, moderator, *, reason: str, warn_id: int, active_count: int,
    branch: str | None = None, role_label: str | None = None,
    expires_at: str | None = None,
) -> discord.Embed:
    """Строгий красный embed для сотрудника."""
    from services.warn_config import (
        appeal_hint_staff, staff_warn_review_threshold)

    thr = staff_warn_review_threshold()
    e = discord.Embed(
        title='Официальное предупреждение сотруднику',
        color=0x8B0000,
        timestamp=_ts(),
    )
    issuer = getattr(moderator, 'display_name', None) or str(moderator)
    until = _fmt_until(expires_at)
    e.description = (
        f'Вам вынесено **официальное предупреждение** на сервере '
        f'**{getattr(guild, "name", "сервер")}**.\n\n'
        f'**Ветка:** {branch or "—"}\n'
        f'**Должность / роль:** {role_label or "стафф"}\n'
        f'**Причина:** {reason or "Не указана"}\n'
        f'**Выдал:** {issuer} (куратор / администрация)\n'
        f'**Варн №:** {warn_id}\n'
        f'**Активных варнов в личном деле:** {active_count}\n'
        f'**Действует до:** {until}\n\n'
        f'Роль warn сотрудникам **не выдаётся** — предупреждение '
        f'зафиксировано только в личном деле.\n'
        f'При **{thr}** и более активных варнах вопрос о снятии с должности '
        f'выносится на рассмотрение.\n\n'
        f'> {appeal_hint_staff()}'
    )
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · staff record')
    return e


def build_member_expire_dm(
    guild, *, reason: str, warn_id: int, active_count: int,
) -> discord.Embed:
    e = discord.Embed(
        title='Срок предупреждения истёк',
        color=0x95A5A6,
        timestamp=_ts(),
    )
    e.description = (
        f'На сервере **{getattr(guild, "name", "сервер")}** истёк срок '
        f'предупреждения #{warn_id}.\n\n'
        f'**Было за:** {reason or "—"}\n'
        f'**Активных варнов осталось:** {active_count}\n\n'
        + ('Роль warn снята.' if active_count <= 0
           else 'Роль warn остаётся, пока есть активные варны.')
    )
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · участник')
    return e


def build_staff_expire_dm(
    guild, *, reason: str, warn_id: int, active_count: int,
    branch: str | None = None,
) -> discord.Embed:
    e = discord.Embed(
        title='Срок предупреждения в личном деле истёк',
        color=0x7F8C8D,
        timestamp=_ts(),
    )
    e.description = (
        f'Официальное предупреждение **#{warn_id}** истекло в вашем '
        f'личном деле на **{getattr(guild, "name", "сервер")}**.\n\n'
        f'**Ветка:** {branch or "—"}\n'
        f'**Было за:** {reason or "—"}\n'
        f'**Активных варнов осталось:** {active_count}'
    )
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · staff record')
    return e


def build_member_unwarn_dm(
    guild, moderator, *, reason: str, warn_id: int, active_count: int,
    removed_reason: str | None = None,
) -> discord.Embed:
    e = discord.Embed(
        title='Предупреждение снято',
        color=0x2ECC71,
        timestamp=_ts(),
    )
    e.description = (
        f'На сервере **{getattr(guild, "name", "сервер")}** с вас сняли '
        f'предупреждение #{warn_id}.\n\n'
        f'**Было за:** {reason or "—"}\n'
        f'**Снял:** {getattr(moderator, "display_name", moderator)}\n'
        + (f'**Комментарий:** {removed_reason}\n' if removed_reason else '')
        + f'**Активных варнов осталось:** {active_count}\n\n'
        + ('Роль warn снята.' if active_count <= 0
           else 'Роль warn остаётся, пока есть активные варны.')
    )
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · участник')
    return e


def build_staff_unwarn_dm(
    guild, moderator, *, reason: str, warn_id: int, active_count: int,
    branch: str | None = None, removed_reason: str | None = None,
) -> discord.Embed:
    e = discord.Embed(
        title='Предупреждение в личном деле снято',
        color=0x1A5276,
        timestamp=_ts(),
    )
    e.description = (
        f'Официальное предупреждение **#{warn_id}** снято из вашего '
        f'личного дела на **{getattr(guild, "name", "сервер")}**.\n\n'
        f'**Ветка:** {branch or "—"}\n'
        f'**Было за:** {reason or "—"}\n'
        f'**Снял:** {getattr(moderator, "display_name", moderator)}\n'
        + (f'**Комментарий:** {removed_reason}\n' if removed_reason else '')
        + f'**Активных варнов осталось:** {active_count}'
    )
    e.set_footer(text=f'{getattr(guild, "name", "Hakumo")} · staff record')
    return e


async def send_warn_dm(user, embed: discord.Embed, *,
                       guild=None, log_channel_hint: str = '') -> bool:
    """Отправить DM. Forbidden → лог, без падения. True если доставлено."""
    if user is None or embed is None:
        return False
    try:
        await user.send(embed=embed)
        return True
    except discord.Forbidden:
        _log.info(
            'DM warn Forbidden user=%s %s',
            getattr(user, 'id', '?'), log_channel_hint or '')
        try:
            from cogs.logs import send_action_log
            g = guild or getattr(user, 'guild', None)
            if g is not None:
                await send_action_log(
                    g, 'system', user, None,
                    reason='DM не доставлено (закрыты ЛС)',
                    extra=log_channel_hint or 'warn DM')
        except Exception as ex:
            _log.debug('DM fail log: %s', ex)
        return False
    except Exception as ex:
        _log.warning('DM warn fail: %s', ex)
        return False


def staff_role_label(member) -> str:
    """Краткое имя должности для DM стаффа."""
    try:
        from services.warn_acl import branches_of
        from services.warn_config import format_branches
        br = branches_of(member)
        if br:
            return format_branches(br)
    except Exception:
        pass
    try:
        roles = [
            r.name for r in (getattr(member, 'roles', None) or [])
            if not getattr(r, 'is_default', lambda: False)()]
        return ', '.join(roles[-3:]) if roles else 'стафф'
    except Exception:
        return 'стафф'
