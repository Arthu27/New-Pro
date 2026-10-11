# -*- coding: utf-8 -*-
"""Состав: сводка по веткам + блок «🏝 В отпуске»."""
from __future__ import annotations

import discord

from services.staff_manager.bundles import format_role_label
from services.staff_manager.config import get_config, branch_emoji
from services.staff_manager.store import list_vacations
from services.staff_manager.styles import BLACK
from services.staff_manager.views.common import black_container, mirror_container


def build_roster_view(
    cog,
    *,
    guild: discord.Guild,
    by_branch: dict | None = None,
) -> discord.ui.LayoutView:
    """by_branch: {branch_key: [{user_id, role_key, name}, ...]}."""
    cfg = get_config() or {}
    by_branch = by_branch or {}
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay('# Состав стаффа\n-# сводка по веткам'),
        accent=BLACK,
    ))

    for bkey, bcfg in (cfg.get('branches') or {}).items():
        members = by_branch.get(bkey) or []
        be = branch_emoji(bkey) or '•'
        lines = [f'### {be} {bcfg.get("label") or bkey} · {len(members)}']
        # группировка по роли
        by_role: dict = {}
        for m in members:
            by_role.setdefault(m.get('role_key') or '?', []).append(m)
        for rk, people in sorted(by_role.items(), key=lambda x: x[0]):
            names = ', '.join(
                (p.get('name') or str(p.get('user_id')))[:32]
                for p in people[:12]
            )
            more = f' +{len(people) - 12}' if len(people) > 12 else ''
            lines.append(
                f'{format_role_label(rk, branch=bkey)} · {names}{more}')
        if not members:
            lines.append('-# пусто')
        view.add_item(black_container(
            discord.ui.TextDisplay('\n'.join(lines)), accent=BLACK))

    vacs = list_vacations(guild.id, status='active', limit=30)
    if vacs:
        lines = ['### 🏝 В отпуске']
        for v in vacs:
            snap = v.get('role_snapshot') or {}
            rk = snap.get('role_key') if isinstance(snap, dict) else ''
            uid = int(v.get('user_id') or 0)
            m = guild.get_member(uid)
            name = m.display_name if m else str(uid)
            end = str(v.get('end_at') or '')[:10]
            lines.append(
                f'{format_role_label(rk or "", branch=v.get("branch"))} '
                f'**{name}** · до `{end}` · {branch_emoji(v.get("branch") or "") or ""}'
            )
        view.add_item(black_container(
            discord.ui.TextDisplay('\n'.join(lines)), accent=0x1ABC9C))
    return view
