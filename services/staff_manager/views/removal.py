# -*- coding: utf-8 -*-
"""Снятие с должности: отдельный экран с типом и чёрным подтверждением."""
from __future__ import annotations

import discord

from services.staff_manager.acl import get_staff_info
from services.staff_manager.bundles import format_role_label
from services.staff_manager.store import load_menu_state
from services.staff_manager.styles import REMOVE
from services.staff_manager.texts import REMOVAL_KINDS
from services.staff_manager.views.common import (
    black_container, branch_em, mirror_confirm_row, mirror_container,
)


def build_removal_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
) -> discord.ui.LayoutView:
    info = get_staff_info(target)
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}
    sel_kind = payload.get('removal_kind') or ''

    body = (
        f'# 🔴 Снятие с должности\n'
        f'{target.mention}\n'
        f'{format_role_label(info.get("primary_key") or "", branch=info.get("primary_branch"))}'
        f' · {branch_em(info.get("primary_branch") or "")} '
        f'{info.get("branch_label") or "—"}\n'
        f'-# будут сняты все стафф-роли и набор; 👑 и 🌺 не трогаем'
    )
    if sel_kind:
        body += f'\nТип: **{REMOVAL_KINDS.get(sel_kind, sel_kind)}**'

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay(body), accent=REMOVE))

    ksel = discord.ui.Select(
        placeholder='Тип снятия',
        options=[
            discord.SelectOption(
                label=v, value=k, default=(k == sel_kind))
            for k, v in REMOVAL_KINDS.items()
        ],
        custom_id=f'sm:rk:{token}',
        min_values=1, max_values=1,
    )

    async def _on_rk(interaction: discord.Interaction, select=ksel):
        st2 = load_menu_state(token)
        if not st2 or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload2 = st2.get('payload') or {}
        payload2['removal_kind'] = select.values[0]
        payload2['action'] = 'remove'
        from services.staff_manager.store import save_menu_state
        save_menu_state(
            token, st2['guild_id'], st2['actor_id'], st2['target_id'],
            'removal_kind', payload2)
        view2 = build_removal_view(
            cog, token=token, actor=interaction.user,  # type: ignore
            target=target)
        # refresh actor as Member
        actor2 = interaction.guild.get_member(interaction.user.id) or actor
        target2 = interaction.guild.get_member(int(st2['target_id'])) or target
        view2 = build_removal_view(
            cog, token=token, actor=actor2, target=target2)
        await interaction.response.edit_message(view=view2)

    ksel.callback = _on_rk  # type: ignore
    row = discord.ui.ActionRow()
    row.add_item(ksel)
    view.add_item(black_container(
        discord.ui.TextDisplay('**Тип**'), row, accent=REMOVE))

    async def _ok(interaction: discord.Interaction):
        from cogs.staff_manager import ReasonModal
        await interaction.response.send_modal(ReasonModal(cog, token))

    async def _no(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

    view.add_item(mirror_container(
        discord.ui.TextDisplay('**Подтверждение**'),
        mirror_confirm_row(
            ok_id=f'sm:ok:{token}', cancel_id=f'sm:no:{token}',
            ok_callback=_ok, cancel_callback=_no,
        ),
        accent=REMOVE,
    ))
    return view
