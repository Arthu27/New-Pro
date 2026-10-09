# -*- coding: utf-8 -*-
"""Заявки: тикет с кнопками решения и иконками рассматривающих."""
from __future__ import annotations

import discord

from services.staff_manager.bundles import format_actor_label, format_role_label
from services.staff_manager.styles import REQUEST
from services.staff_manager.views.common import (
    black_container, mirror_container,
)


def build_requests_view(
    cog,
    *,
    ticket: dict,
    actor: discord.Member,
) -> discord.ui.LayoutView:
    """ticket: id, action, target_name, role_key, branch, reason, requester_*, status."""
    tid = ticket.get('id') or ''
    body = (
        f'# 🎫 Заявка\n'
        f'Тип: **{ticket.get("action") or "—"}**\n'
        f'Участник: **{ticket.get("target_name") or ticket.get("target_id")}**\n'
        f'Роль: {format_role_label(ticket.get("role_key") or "", branch=ticket.get("branch"))}\n'
        f'Ветка: {ticket.get("branch") or "—"}\n'
        f'От: {format_actor_label(ticket.get("requester_name") or "?", ticket.get("actor_role_key"))}\n'
        f'Причина: {ticket.get("reason") or "—"}\n'
        f'Статус: `{ticket.get("status") or "pending"}`'
    )
    if ticket.get('decided_by_name'):
        body += (
            f'\nРешил: {format_actor_label(ticket["decided_by_name"], ticket.get("decided_by_role_key"))}'
        )

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay(body), accent=REQUEST))

    if ticket.get('status') == 'pending':
        row = discord.ui.ActionRow()
        btn_ok = discord.ui.Button(
            label='Одобрить', style=discord.ButtonStyle.secondary,
            custom_id=f'sm:req:ok:{tid}')
        btn_no = discord.ui.Button(
            label='Отклонить', style=discord.ButtonStyle.secondary,
            custom_id=f'sm:req:no:{tid}')

        async def _ok(interaction: discord.Interaction):
            await cog._request_decide(interaction, tid, accept=True)

        async def _no(interaction: discord.Interaction):
            await cog._request_decide(interaction, tid, accept=False)

        btn_ok.callback = _ok  # type: ignore
        btn_no.callback = _no  # type: ignore
        row.add_item(btn_ok)
        row.add_item(btn_no)
        view.add_item(black_container(
            discord.ui.TextDisplay('**Решение**'), row, accent=REQUEST))
    return view
