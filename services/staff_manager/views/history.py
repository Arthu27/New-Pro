# -*- coding: utf-8 -*-
"""История: лента по дням (не таблица)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord

from services.staff_manager.bundles import format_actor_label, format_transition
from services.staff_manager.config import get_config, role_emoji, branch_emoji
from services.staff_manager.store import list_actions_filtered, load_menu_state
from services.staff_manager.styles import ACTION_ICONS, HISTORY, STATUS_ICONS
from services.staff_manager.views.common import black_container, mirror_container


def _day_header(iso: str, now: datetime) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return '—'
    local = dt.astimezone(timezone.utc)
    today = now.date()
    if local.date() == today:
        return 'Сегодня'
    if local.date() == today - timedelta(days=1):
        return 'Вчера'
    months = (
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    )
    return f'{local.day} {months[local.month]}'


def _entry_block(row: dict, guild: discord.Guild | None) -> str:
    action = row.get('action') or ''
    icon = ACTION_ICONS.get(action, '•')
    transition = format_transition(
        row.get('old_key') or '', row.get('new_key') or '',
        branch=row.get('branch') or '',
    )
    be = branch_emoji(row.get('branch') or '') or '•'
    branch = row.get('branch') or '—'
    actor_key = row.get('actor_role_key') or ''
    actor_name = str(row.get('actor_id') or '')
    if guild:
        m = guild.get_member(int(row.get('actor_id') or 0))
        if m:
            actor_name = m.display_name
    actor = format_actor_label(actor_name, actor_key or None,
                               branch=row.get('actor_branch') or None)
    if not actor_key:
        # fallback: нейтральная иконка
        actor = f'• {actor_name}'
    reason = (row.get('reason') or '—').replace('\n', ' ')[:120]
    ok = bool(row.get('ok'))
    status = STATUS_ICONS['ok'] if ok else STATUS_ICONS['failed']
    try:
        ts = int(datetime.fromisoformat(row['created_at']).timestamp())
        time_s = f'<t:{ts}:R>'
    except Exception:
        time_s = ''
    return (
        f'{icon} **{transition}**\n'
        f'{be} {branch} · {actor}\n'
        f'-# {reason}\n'
        f'{time_s} · {status}'
    )


def build_history_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member | None = None,
    page: int = 0,
    per_page: int = 8,
) -> discord.ui.LayoutView:
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}
    filt_action = payload.get('hist_action') or ''
    filt_branch = payload.get('hist_branch') or ''
    filt_period = payload.get('hist_period') or '30'
    filt_ok = payload.get('hist_status')  # '1' / '0' / ''

    since = None
    now = datetime.now(timezone.utc)
    if filt_period == '1':
        since = (now - timedelta(days=1)).isoformat()
    elif filt_period == '7':
        since = (now - timedelta(days=7)).isoformat()
    elif filt_period == '30':
        since = (now - timedelta(days=30)).isoformat()

    status_ok = None
    if filt_ok == '1':
        status_ok = True
    elif filt_ok == '0':
        status_ok = False

    rows = list_actions_filtered(
        actor.guild.id,
        target_id=int(target.id) if target else None,
        action=filt_action or None,
        branch=filt_branch or None,
        status_ok=status_ok,
        since_iso=since,
        limit=per_page,
        offset=page * per_page,
    )

    view = discord.ui.LayoutView(timeout=None)
    title = '# История' + (
        f' · {target.display_name}' if target else '')
    view.add_item(mirror_container(
        discord.ui.TextDisplay(title),
        discord.ui.TextDisplay('-# лента по дням · не таблица'),
        accent=HISTORY,
    ))

    # фильтры
    cfg = get_config() or {}
    frow = discord.ui.ActionRow()
    period_opts = [
        discord.SelectOption(label='Сегодня', value='1', emoji='📅',
                             default=filt_period == '1'),
        discord.SelectOption(label='7 дней', value='7', emoji='🗓',
                             default=filt_period == '7'),
        discord.SelectOption(label='30 дней', value='30', emoji='📆',
                             default=filt_period == '30'),
        discord.SelectOption(label='Всё', value='all', emoji='📚',
                             default=filt_period == 'all'),
    ]
    psel = discord.ui.Select(
        placeholder='Период', options=period_opts,
        custom_id=f'sm:hist:p:{token}', min_values=1, max_values=1)

    async def _on_p(interaction: discord.Interaction, select=psel):
        await cog._history_filter(interaction, token, 'hist_period', select.values[0])

    psel.callback = _on_p  # type: ignore
    frow.add_item(psel)
    view.add_item(black_container(
        discord.ui.TextDisplay('**Фильтры**'), frow, accent=HISTORY))

    if not rows:
        view.add_item(black_container(
            discord.ui.TextDisplay('-# записей нет'), accent=HISTORY))
        return view

    last_day = None
    for row in rows:
        day = _day_header(row.get('created_at') or '', now)
        if day != last_day:
            if last_day is not None:
                view.add_item(discord.ui.Separator(
                    spacing=discord.SeparatorSpacing.large))
            view.add_item(black_container(
                discord.ui.TextDisplay(f'### {day}'), accent=HISTORY))
            last_day = day
        view.add_item(black_container(
            discord.ui.TextDisplay(_entry_block(row, actor.guild)),
            accent=HISTORY,
        ))

    # пагинация
    prow = discord.ui.ActionRow()
    prev = discord.ui.Button(
        label='◀', style=discord.ButtonStyle.secondary,
        custom_id=f'sm:hist:prev:{token}', disabled=page <= 0)
    nxt = discord.ui.Button(
        label='▶', style=discord.ButtonStyle.secondary,
        custom_id=f'sm:hist:next:{token}',
        disabled=len(rows) < per_page)

    async def _prev(interaction: discord.Interaction):
        await cog._history_page(interaction, token, max(0, page - 1))

    async def _next(interaction: discord.Interaction):
        await cog._history_page(interaction, token, page + 1)

    prev.callback = _prev  # type: ignore
    nxt.callback = _next  # type: ignore
    prow.add_item(prev)
    prow.add_item(nxt)
    view.add_item(black_container(
        discord.ui.TextDisplay(f'-# стр. {page + 1}'), prow, accent=HISTORY))
    return view
