# -*- coding: utf-8 -*-
"""Отпуск: «открытка» со сроком, остатком, кнопками возврата/продления."""
from __future__ import annotations

from datetime import datetime, timezone

import discord

from services.staff_manager.acl import get_staff_info, resolve_actor
from services.staff_manager.bundles import format_role_label
from services.staff_manager.config import get_config
from services.staff_manager.store import active_vacation_for, load_menu_state
from services.staff_manager.styles import VACATION
from services.staff_manager.vacation import vacation_display
from services.staff_manager.views.common import (
    black_container, branch_em, mirror_confirm_row, mirror_container, opt_emoji,
)


def build_vacation_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
) -> discord.ui.LayoutView:
    cfg = get_config() or {}
    info = get_staff_info(target)
    vac = active_vacation_for(target.guild.id, target.id) if target.guild else None
    a_ctx = resolve_actor(actor.id, [r.id for r in actor.roles or []])
    is_self = int(actor.id) == int(target.id)
    can_manage = bool(
        a_ctx.is_owner or a_ctx.is_staff_admin
        or (info.get('primary_branch') in a_ctx.responsible_branches)
        or is_self
    )

    view = discord.ui.LayoutView(timeout=None)

    if vac:
        disp = vacation_display(vac, cfg)
        left = int(disp.get('days_left') or 0)
        # прогресс-бар текстом
        try:
            start = datetime.fromisoformat(vac['start_at'])
            end = datetime.fromisoformat(vac['end_at'])
            now = datetime.now(timezone.utc)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            total = max(1, (end - start).total_seconds())
            done = min(1.0, max(0.0, (now - start).total_seconds() / total))
            filled = int(round(done * 10))
            bar = '█' * filled + '░' * (10 - filled)
        except Exception:
            bar = '░░░░░░░░░░'
        body = (
            f'# 🏝 Отпуск\n'
            f'**{target.display_name}** {target.mention}\n'
            f'{format_role_label(disp.get("role_key") or "", branch=disp.get("branch"))}'
            f' · {branch_em(disp.get("branch") or "")} {disp.get("branch_label")}\n'
            f'с `{str(disp.get("start_at") or "")[:10]}` '
            f'по `{str(disp.get("end_at") or "")[:10]}`\n'
            f'`{bar}` осталось **{left}** дн.\n'
            f'-# {disp.get("reason") or "—"}'
        )
        view.add_item(mirror_container(
            discord.ui.TextDisplay(body), accent=VACATION))

        if can_manage:
            row = discord.ui.ActionRow()
            btn_back = discord.ui.Button(
                label='Вернуться сейчас',
                style=discord.ButtonStyle.secondary,
                emoji='↩',
                custom_id=f'sm:vac:end:{token}',
            )
            btn_ext = discord.ui.Button(
                label='Продлить',
                style=discord.ButtonStyle.secondary,
                emoji='➕',
                custom_id=f'sm:vac:ext:{token}',
            )

            async def _end(interaction: discord.Interaction):
                await cog._vacation_end_now(interaction, token)

            async def _ext(interaction: discord.Interaction):
                await cog._vacation_extend_menu(interaction, token)

            btn_back.callback = _end  # type: ignore
            btn_ext.callback = _ext  # type: ignore
            row.add_item(btn_back)
            row.add_item(btn_ext)
            view.add_item(black_container(
                discord.ui.TextDisplay('**Управление**'), row, accent=VACATION))
        return view

    # выбор срока
    presets = cfg.get('vacation_presets') or []
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}
    sel = payload.get('vac_preset') or ''

    lines = [
        '# 🏝 Уйти в отпуск',
        f'{target.mention}',
        f'{format_role_label(info.get("primary_key") or "", branch=info.get("primary_branch"))}'
        f' · {branch_em(info.get("primary_branch") or "")} '
        f'{info.get("branch_label") or "—"}',
        '-# выберите срок',
    ]
    view.add_item(mirror_container(
        discord.ui.TextDisplay('\n'.join(lines)), accent=VACATION))

    opts = []
    for p in presets[:25]:
        opts.append(discord.SelectOption(
            label=str(p.get('label') or p.get('key'))[:100],
            value=str(p.get('key')),
            emoji=p.get('emoji') or '📅',
            description=(f'{p.get("days")} дн.' if p.get('days') else 'своя дата')[:100],
            default=(p.get('key') == sel),
        ))
    if opts:
        s = discord.ui.Select(
            placeholder='Срок отпуска',
            options=opts,
            custom_id=f'sm:vac:preset:{token}',
            min_values=1, max_values=1,
        )

        async def _on_p(interaction: discord.Interaction, select=s):
            await cog._vacation_preset(interaction, token, select.values[0])

        s.callback = _on_p  # type: ignore
        row = discord.ui.ActionRow()
        row.add_item(s)
        view.add_item(black_container(
            discord.ui.TextDisplay('**Срок**'), row, accent=VACATION))

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
        accent=VACATION,
    ))
    return view
