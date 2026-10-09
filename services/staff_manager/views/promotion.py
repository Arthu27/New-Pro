# -*- coding: utf-8 -*-
"""Повышение/понижение: экран «было → стало» + чёрное зеркальное подтверждение."""
from __future__ import annotations

import discord

from services.staff_manager.acl import get_allowed_actions, get_staff_info, resolve_actor, resolve_target
from services.staff_manager.bundles import (
    format_role_label, format_transition, get_promotion_requirements,
    get_role_bundle,
)
from services.staff_manager.config import get_config
from services.staff_manager.styles import DEMOTE, GOLD, PROMOTE
from services.staff_manager.store import load_menu_state
from services.staff_manager.texts import ROLE_DESC
from services.staff_manager.views.common import (
    black_container, mirror_confirm_row, mirror_container, opt_emoji, role_em,
)


def build_promotion_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
    mode: str = 'promote',  # promote | demote
) -> discord.ui.LayoutView:
    cfg = get_config() or {}
    info = get_staff_info(target)
    a_ctx = resolve_actor(actor.id, [r.id for r in actor.roles or []])
    t_ctx = resolve_target(target.id, [r.id for r in target.roles or []])
    allowed = get_allowed_actions(a_ctx, t_ctx)
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}
    sel_role = payload.get('role') or ''
    bypass = bool(payload.get('bypass_rules'))

    old_key = info.get('primary_key') or ''
    branch = info.get('primary_branch') or payload.get('branch') or ''
    accent = PROMOTE if mode == 'promote' else DEMOTE
    title = '# Повышение' if mode == 'promote' else '# Понижение'

    lines = [
        title,
        f'{target.mention}',
        f'Сейчас: {format_role_label(old_key, branch=branch) if old_key else "—"}',
    ]
    if sel_role:
        lines.append(f'### {format_transition(old_key, sel_role, branch=branch)}')
        bundle = get_role_bundle(sel_role, branch, cfg)
        extras = bundle.get('add_roles') or []
        if extras:
            names = []
            for rid in extras[:6]:
                r = target.guild.get_role(int(rid)) if target.guild else None
                names.append(r.mention if r else str(rid))
            lines.append('Набор добавит: ' + ', '.join(names))
        if mode == 'promote' and not bypass:
            ok_req, missing = get_promotion_requirements(
                sel_role, branch=branch,
                on_vacation=bool(info.get('on_vacation')), cfg=cfg,
            )
            if missing:
                lines.append('**Не хватает:**')
                for m in missing:
                    lines.append(f'• {m}')

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay('\n'.join(lines)), accent=accent))

    roles = allowed.get('roles') or []
    if roles:
        roles_sorted = sorted(roles, key=lambda r: -int(r.get('rank') or 0))
        opts = []
        for r in roles_sorted[:25]:
            key = r['key']
            label = f'{role_em(key, branch)} {r.get("name") or key}'
            opts.append(discord.SelectOption(
                label=label[:100],
                value=key,
                emoji=opt_emoji('role', key, r.get('emoji')),
                description=(ROLE_DESC.get(key) or '')[:100] or None,
                default=(key == sel_role),
            ))
        sel = discord.ui.Select(
            placeholder='Новая ступень',
            options=opts,
            custom_id=f'sm:promo:role:{token}',
            min_values=1, max_values=1,
        )

        async def _on_role(interaction: discord.Interaction, select=sel):
            await cog._on_role_select(interaction, token, select.values[0])

        sel.callback = _on_role  # type: ignore
        row = discord.ui.ActionRow()
        row.add_item(sel)
        view.add_item(black_container(
            discord.ui.TextDisplay('**Было → стало**'), row, accent=accent))

    # bypass для стафф админа
    if a_ctx.is_owner or a_ctx.is_staff_admin:
        brow = discord.ui.ActionRow()
        btn_b = discord.ui.Button(
            label='Повысить вне правил' if mode == 'promote' else 'Вне правил',
            style=discord.ButtonStyle.secondary,
            custom_id=f'sm:promo:bypass:{token}',
        )

        async def _bypass(interaction: discord.Interaction):
            await cog._set_bypass_and_reason(interaction, token)

        btn_b.callback = _bypass  # type: ignore
        brow.add_item(btn_b)
        view.add_item(black_container(
            discord.ui.TextDisplay('-# обход условий · нужна причина'),
            brow, accent=GOLD))

    async def _ok(interaction: discord.Interaction):
        from cogs.staff_manager import ReasonModal
        await interaction.response.send_modal(ReasonModal(cog, token))

    async def _no(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass

    view.add_item(mirror_container(
        discord.ui.TextDisplay('**Подтверждение**'),
        mirror_confirm_row(
            ok_id=f'sm:ok:{token}',
            cancel_id=f'sm:no:{token}',
            ok_callback=_ok,
            cancel_callback=_no,
        ),
        accent=accent,
    ))
    return view


def build_ceremony_text(
    *,
    target_mention: str,
    old_key: str,
    new_key: str,
    branch: str,
    actor_label: str,
    reason: str,
    promote: bool = True,
) -> str:
    transition = format_transition(old_key, new_key, branch=branch)
    if promote:
        return (
            f'# Церемония\n'
            f'{target_mention}\n'
            f'### {transition}\n'
            f'Повысил: {actor_label}\n'
            f'Причина: {reason or "—"}\n'
            f'🎉 Поздравляем!'
        )
    return (
        f'# Понижение\n'
        f'{target_mention}\n'
        f'### {transition}\n'
        f'Кем: {actor_label}\n'
        f'Причина: {reason or "—"}'
    )
