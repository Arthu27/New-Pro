# -*- coding: utf-8 -*-
"""Экран профиля: карточка с аватаром + набор роли + условия повышения."""
from __future__ import annotations

import discord

from services.staff_manager.acl import (
    get_allowed_actions, get_staff_info, resolve_actor, resolve_target,
)
from services.staff_manager.bundles import (
    format_role_label, get_promotion_requirements, get_role_bundle,
    role_description,
)
from services.staff_manager.config import get_config, ladder_by_key
from services.staff_manager.styles import BLACK, VACATION
from services.staff_manager.texts import PANEL_TITLE
from services.staff_manager.views.common import (
    black_container, branch_em, mirror_container, role_em,
)


def build_profile_view(
    cog,
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
) -> discord.ui.LayoutView:
    cfg = get_config() or {}
    info = get_staff_info(target)
    a_ctx = resolve_actor(actor.id, [r.id for r in actor.roles or []])
    t_ctx = resolve_target(target.id, [r.id for r in target.roles or []])
    allowed = get_allowed_actions(a_ctx, t_ctx)

    re = role_em(info.get('primary_key') or '', info.get('primary_branch'))
    be = branch_em(info.get('primary_branch') or '')
    accent = VACATION if info.get('on_vacation') else BLACK

    lines = [
        f'# {target.display_name}',
        f'{target.mention}',
        f'{re} **{info.get("role_label") or "участник"}** · '
        f'{be} {info.get("branch_label") or "—"}',
    ]
    if info.get('on_vacation'):
        vac = info.get('vacation') or {}
        lines.append(f'🏝 в отпуске до `{str(vac.get("end_at") or "")[:10]}`')

    # набор роли
    key = info.get('primary_key') or ''
    branch = info.get('primary_branch') or ''
    if key:
        bundle = get_role_bundle(key, branch, cfg)
        extras = bundle.get('add_roles') or []
        desc = role_description(key, cfg)
        lines.append('### Набор роли')
        if desc:
            lines.append(f'-# {desc}')
        if extras:
            names = []
            for rid in extras[:8]:
                role = target.guild.get_role(int(rid)) if target.guild else None
                names.append(role.name if role else str(rid))
            lines.append('Доп. роли: ' + ', '.join(names))
        else:
            lines.append('-# дополнительных ролей нет')

        # условия следующего повышения
        ladder = cfg.get('ladder') or []
        cur_rank = int((ladder_by_key(key, cfg) or {}).get('rank') or 0)
        nxt = next((x for x in ladder if int(x.get('rank') or 0) > cur_rank), None)
        if nxt:
            ok_req, missing = get_promotion_requirements(
                nxt['key'], branch=branch, days_in_role=0,
                active_warns=0, on_probation=False,
                on_vacation=bool(info.get('on_vacation')), cfg=cfg,
            )
            lines.append(
                f'### Следующая ступень · {format_role_label(nxt["key"], branch=branch)}')
            req = get_role_bundle(nxt['key'], branch, cfg).get('requires') or {}
            md = int(req.get('min_days_in_role') or 0)
            if md:
                lines.append(f'-# нужно минимум {md} дн. в текущей роли')
            if missing:
                for m in missing:
                    lines.append(f'• {m}')
            elif ok_req:
                lines.append('-# условия выполнены')

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(mirror_container(
        discord.ui.TextDisplay(PANEL_TITLE),
        discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
        discord.ui.TextDisplay('\n'.join(lines)),
        accent=accent,
    ))

    # действия как кнопки (не единый select-шаблон профиля)
    row = discord.ui.ActionRow()
    acts = [a for a in (allowed.get('actions') or []) if a != 'request']
    labels = {
        'history': 'История', 'vacation': 'Отпуск', 'promote': 'Повысить',
        'demote': 'Понизить', 'remove': 'Снять', 'transfer': 'Перевод',
        'assign': 'Назначить', 'self_leave': 'Уйти',
    }
    for a in acts[:4]:
        btn = discord.ui.Button(
            label=labels.get(a, a)[:80],
            style=discord.ButtonStyle.secondary,
            custom_id=f'sm:prof:{a}:{token}',
        )

        async def _go(interaction: discord.Interaction, act=a):
            await cog._open_action_screen(interaction, token, act)

        btn.callback = _go  # type: ignore
        row.add_item(btn)
    if row.children:
        view.add_item(black_container(
            discord.ui.TextDisplay('**Действия**'), row, accent=accent))
    return view
