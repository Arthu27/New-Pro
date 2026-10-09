# -*- coding: utf-8 -*-
"""Согласие на перевод: отдельный экран с иконками ролей."""
from __future__ import annotations

import discord

from services.staff_manager.bundles import format_actor_label, format_transition
from services.staff_manager.config import branch_emoji
from services.staff_manager.styles import CONSENT
from services.staff_manager.texts import CONSENT_ACCEPT, CONSENT_DECLINE
from services.staff_manager.views.common import black_container, mirror_container


def build_consent_view(
    cog,
    *,
    consent_id: str,
    body: str | None = None,
    actor_name: str = '',
    actor_role_key: str = '',
    from_key: str = '',
    to_key: str = '',
    from_branch: str = '',
    to_branch: str = '',
    reason: str = '',
    hours: int = 48,
) -> discord.ui.LayoutView:
    if not body:
        body = (
            f'# Предложение: перевод\n'
            f'От: {format_actor_label(actor_name, actor_role_key)}\n'
            f'Из: {format_transition(from_key, "", branch=from_branch)} · '
            f'{branch_emoji(from_branch) or ""} {from_branch}\n'
            f'В: {format_transition("", to_key, branch=to_branch)} · '
            f'{branch_emoji(to_branch) or ""} {to_branch}\n'
            f'Причина: {reason or "—"}\n'
            f'Срок: **{hours}ч**'
        )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay(body), accent=CONSENT))

    row = discord.ui.ActionRow()
    btn_ok = discord.ui.Button(
        label=CONSENT_ACCEPT, style=discord.ButtonStyle.secondary,
        emoji='✦', custom_id=f'sm:cya:{consent_id}')
    btn_no = discord.ui.Button(
        label=CONSENT_DECLINE, style=discord.ButtonStyle.secondary,
        emoji='✧', custom_id=f'sm:cno:{consent_id}')

    async def _ok(interaction: discord.Interaction):
        await cog._consent_accept(interaction, consent_id)

    async def _no(interaction: discord.Interaction):
        from cogs.staff_manager import DeclineReasonModal
        await interaction.response.send_modal(
            DeclineReasonModal(cog, consent_id))

    btn_ok.callback = _ok  # type: ignore
    btn_no.callback = _no  # type: ignore
    row.add_item(btn_ok)
    row.add_item(btn_no)
    view.add_item(black_container(
        discord.ui.TextDisplay('**Решение**'), row, accent=CONSENT))
    return view
