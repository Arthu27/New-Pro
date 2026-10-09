# -*- coding: utf-8 -*-
"""Перевод: цепочка шагов со статусами каждого этапа."""
from __future__ import annotations

import discord

from services.staff_manager.acl import get_allowed_actions, get_staff_info, resolve_actor, resolve_target
from services.staff_manager.bundles import format_role_label, format_transition
from services.staff_manager.config import get_config
from services.staff_manager.store import load_menu_state
from services.staff_manager.styles import TRANSFER
from services.staff_manager.texts import BRANCH_DESC, ROLE_DESC
from services.staff_manager.views.common import (
    black_container, branch_em, mirror_confirm_row, mirror_container,
    opt_emoji, role_em,
)


def _step(done: bool, current: bool, label: str) -> str:
    if done:
        return f'✅ {label}'
    if current:
        return f'▶ **{label}**'
    return f'○ {label}'


def build_transfer_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
) -> discord.ui.LayoutView:
    info = get_staff_info(target)
    a_ctx = resolve_actor(actor.id, [r.id for r in actor.roles or []])
    t_ctx = resolve_target(target.id, [r.id for r in target.roles or []])
    allowed = get_allowed_actions(a_ctx, t_ctx)
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}
    sel_branch = payload.get('branch') or ''
    sel_role = payload.get('role') or ''
    cfg = get_config() or {}

    step1 = bool(sel_branch)
    step2 = bool(sel_role)
    chain = [
        _step(step1, not step1, 'Ветка назначения'),
        _step(step2, step1 and not step2, 'Роль в новой ветке'),
        _step(False, step1 and step2, 'Согласие цели'),
        _step(False, False, 'Применение ролей'),
    ]
    old = format_role_label(
        info.get('primary_key') or '', branch=info.get('primary_branch'))
    new = (
        format_transition(
            info.get('primary_key') or '', sel_role, branch=sel_branch)
        if sel_role else '—'
    )
    body = (
        f'# 🟣 Перевод\n'
        f'{target.mention}\n'
        f'Из: {old} · {branch_em(info.get("primary_branch") or "")} '
        f'{info.get("branch_label") or "—"}\n'
        f'В: {new}\n\n'
        + '\n'.join(chain)
    )

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay(body), accent=TRANSFER))

    branches = allowed.get('branches') or list(
        {'key': k, 'label': v.get('label'), 'emoji': None}
        for k, v in (cfg.get('branches') or {}).items()
    )
    # get_allowed may return dicts
    if branches and isinstance(branches[0], str):
        branches = [
            {'key': b, 'label': ((cfg.get('branches') or {}).get(b) or {}).get('label') or b}
            for b in branches
        ]

    if not step1 and branches:
        opts = []
        for b in branches[:25]:
            key = b['key'] if isinstance(b, dict) else b
            lab = (b.get('label') if isinstance(b, dict) else None) or key
            opts.append(discord.SelectOption(
                label=str(lab)[:100], value=key,
                emoji=opt_emoji('branch', key),
                description=(BRANCH_DESC.get(key) or '')[:100] or None,
            ))
        sel = discord.ui.Select(
            placeholder='Куда переводим',
            options=opts, custom_id=f'sm:tr:br:{token}',
            min_values=1, max_values=1)

        async def _on_br(interaction: discord.Interaction, select=sel):
            await cog._on_branch_select(interaction, token, select.values[0])

        sel.callback = _on_br  # type: ignore
        row = discord.ui.ActionRow()
        row.add_item(sel)
        view.add_item(black_container(
            discord.ui.TextDisplay('**Шаг 1 · ветка**'), row, accent=TRANSFER))

    if step1 and not step2:
        roles = allowed.get('roles') or cfg.get('ladder') or []
        opts = []
        for r in roles[:25]:
            key = r['key']
            opts.append(discord.SelectOption(
                label=str(r.get('name') or key)[:100], value=key,
                emoji=opt_emoji('role', key, r.get('emoji')),
                description=(ROLE_DESC.get(key) or '')[:100] or None,
            ))
        if opts:
            sel = discord.ui.Select(
                placeholder='Роль после перевода',
                options=opts, custom_id=f'sm:tr:role:{token}',
                min_values=1, max_values=1)

            async def _on_r(interaction: discord.Interaction, select=sel):
                await cog._on_role_select(interaction, token, select.values[0])

            sel.callback = _on_r  # type: ignore
            row = discord.ui.ActionRow()
            row.add_item(sel)
            view.add_item(black_container(
                discord.ui.TextDisplay('**Шаг 2 · роль**'), row, accent=TRANSFER))

    if step1 and step2:
        async def _ok(interaction: discord.Interaction):
            from cogs.staff_manager import ReasonModal
            await interaction.response.send_modal(ReasonModal(cog, token))

        async def _no(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

        view.add_item(mirror_container(
            discord.ui.TextDisplay('**Шаг 3 · отправить на согласие**'),
            mirror_confirm_row(
                ok_id=f'sm:ok:{token}', cancel_id=f'sm:no:{token}',
                ok_label='Отправить', ok_callback=_ok, cancel_callback=_no,
            ),
            accent=TRANSFER,
        ))
    return view
