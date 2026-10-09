# -*- coding: utf-8 -*-
"""/staff — Staff Manager (Components V2)."""
from __future__ import annotations

import asyncio
import os
import traceback
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from logger import get_logger
from services.staff_manager import (
    apply_staff_change, can_manage_staff, get_allowed_actions,
    resolve_actor, resolve_target, ensure_tables, get_staff_info,
)
from services.staff_manager.config import (
    reload_config, is_enabled, last_error, get_config, get_index,
    requires_consent, role_emoji, branch_emoji, ladder_by_key,
)
from services.staff_manager.store import (
    save_menu_state, load_menu_state, new_action_id, list_actions,
    create_consent, get_consent, claim_consent_decision, update_consent,
    expire_due_consents, pending_consent_for, list_consents,
    save_emoji_cache, get_emoji_cache, record_action,
)
from services.staff_manager.emojis import (
    ensure_role_emojis, ensure_action_emojis, emoji_str, partial_emoji,
)

_log = get_logger('staff_manager')

from services.staff_manager.texts import (
    ACTION_LABELS, ACTION_DESC, ROLE_DESC, BRANCH_DESC, REMOVAL_KINDS,
    PANEL_TITLE, PANEL_MEMBER, PANEL_ROLE_BRANCH, PANEL_VACATION,
    PANEL_MULTI, PANEL_DOUBLE, PANEL_QUEUE, PANEL_ACTION, PANEL_ROLE,
    PANEL_BRANCH, PANEL_REMOVAL_KIND, PANEL_CONFIRM,
    BTN_OK, BTN_CANCEL, BTN_REVOKE, BTN_REQUEST,
    PLACEHOLDER_ACTION, PLACEHOLDER_ROLE, PLACEHOLDER_BRANCH, PLACEHOLDER_REMOVAL,
    CONSENT_ACCEPT, CONSENT_DECLINE, REMOVE_DM_TITLE, REMOVE_DM_BODY,
    ERR_STALE, ERR_NOT_FOUND, ERR_PICK_REMOVAL, OK_DONE, OK_CONSENT_SENT,
)
from services.staff_manager.styles import ACTION_COLORS, MIRROR_BLACK, GOLD
from services.staff_manager.bundles import (
    format_actor_label, format_role_label, get_promotion_requirements,
)
from services.staff_manager.views.profile import build_profile_view
from services.staff_manager.views.history import build_history_view
from services.staff_manager.views.promotion import (
    build_promotion_view, build_ceremony_text,
)
from services.staff_manager.views.vacation import build_vacation_view
from services.staff_manager.views.transfer import build_transfer_view
from services.staff_manager.views.removal import build_removal_view
from services.staff_manager.views.consent import build_consent_view
from services.staff_manager.views.common import mirror_confirm_row, mirror_container

_BLACK = MIRROR_BLACK


def _member_role_ids(member) -> list:
    return [r.id for r in getattr(member, 'roles', []) or []]


def _is_staff_admin_or_owner(member: discord.Member) -> bool:
    cfg = get_config() or {}
    if int(member.id) in set(int(x) for x in (cfg.get('owner_ids') or [])):
        return True
    sa = int(cfg.get('staff_admin_role_id') or 0)
    return bool(sa and sa in _member_role_ids(member))


def _emoji_for_role_key(key: str) -> str:
    return emoji_str('role', key, role_emoji(key) or '•')


def _emoji_for_branch(key: str) -> str:
    return emoji_str('branch', key, branch_emoji(key) or '•')


def _black(*children):
    return discord.ui.Container(*children, accent_colour=discord.Colour(_BLACK))


def _opt_emoji(kind: str, key: str, fallback=None):
    pe = partial_emoji(kind, key, fallback)
    return pe


class ReasonModal(discord.ui.Modal, title='Причина'):
    reason = discord.ui.TextInput(
        label='Причина', style=discord.TextStyle.paragraph,
        required=True, max_length=400,
    )

    def __init__(self, cog: 'StaffManager', token: str):
        super().__init__()
        self.cog = cog
        self.token = token

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._confirm_with_reason(
            interaction, self.token, str(self.reason.value or '').strip())


class DeclineReasonModal(discord.ui.Modal, title='Причина отказа'):
    reason = discord.ui.TextInput(
        label='Почему отказываете? (необязательно)',
        style=discord.TextStyle.paragraph,
        required=False, max_length=400,
    )

    def __init__(self, cog: 'StaffManager', consent_id: str):
        super().__init__()
        self.cog = cog
        self.consent_id = consent_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._consent_decline(
            interaction, self.consent_id,
            str(self.reason.value or '').strip())


class VacationDateModal(discord.ui.Modal, title='Своя дата отпуска'):
    date_s = discord.ui.TextInput(
        label='Дата окончания (ДД.ММ.ГГГГ)',
        style=discord.TextStyle.short,
        required=True, max_length=10, placeholder='31.12.2026',
    )
    reason = discord.ui.TextInput(
        label='Причина', style=discord.TextStyle.paragraph,
        required=True, max_length=400,
    )

    def __init__(self, cog: 'StaffManager', token: str):
        super().__init__()
        self.cog = cog
        self.token = token

    async def on_submit(self, interaction: discord.Interaction):
        from datetime import datetime as _dt
        raw = str(self.date_s.value or '').strip()
        try:
            end = _dt.strptime(raw, '%d.%m.%Y').replace(tzinfo=timezone.utc)
        except Exception:
            await interaction.response.send_message(
                'Неверный формат даты. Нужен ДД.ММ.ГГГГ', ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        days = max(1, int((end - now).total_seconds() // 86400) + 1)
        st = load_menu_state(self.token) or {}
        payload = st.get('payload') or {}
        payload['vac_days'] = days
        payload['action'] = 'vacation'
        save_menu_state(
            self.token, st.get('guild_id') or interaction.guild_id,
            st.get('actor_id') or interaction.user.id,
            st.get('target_id') or 0, 'vac_custom', payload)
        await self.cog._confirm_with_reason(
            interaction, self.token, str(self.reason.value or '').strip())


class VacationExtendModal(discord.ui.Modal, title='Продлить отпуск'):
    choice = discord.ui.TextInput(
        label='На сколько? (7 / 14 / 30)',
        style=discord.TextStyle.short,
        required=True, max_length=3, placeholder='7',
    )

    def __init__(self, cog: 'StaffManager', token: str):
        super().__init__()
        self.cog = cog
        self.token = token

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(str(self.choice.value or '0').strip())
        except Exception:
            days = 0
        if days not in (7, 14, 30):
            await interaction.response.send_message(
                'Можно 7, 14 или 30 дней', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        st = load_menu_state(self.token)
        if not st or not interaction.guild:
            await interaction.followup.send('устарело', ephemeral=True)
            return
        from services.staff_manager.store import active_vacation_for, update_vacation
        from services.staff_manager.vacation import check_vacation_limits
        target = interaction.guild.get_member(int(st['target_id']))
        if not target:
            await interaction.followup.send('не найден', ephemeral=True)
            return
        vac = active_vacation_for(interaction.guild.id, target.id)
        if not vac:
            await interaction.followup.send('нет активного отпуска', ephemeral=True)
            return
        a_ctx = resolve_actor(interaction.user.id, _member_role_ids(interaction.user))
        ok, missing = check_vacation_limits(
            guild_id=interaction.guild.id, user_id=target.id, days=days,
            for_self=int(interaction.user.id) == int(target.id),
            is_admin=bool(a_ctx.is_owner or a_ctx.is_staff_admin),
        )
        if not ok:
            await interaction.followup.send(
                'Нельзя продлить:\n• ' + '\n• '.join(missing), ephemeral=True)
            return
        try:
            end = datetime.fromisoformat(vac['end_at'])
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            new_end = end + timedelta(days=days)
            update_vacation(
                vac['id'], end_at=new_end.isoformat(),
                extensions_count=int(vac.get('extensions_count') or 0) + 1)
            await interaction.followup.send(
                f'✅ Продлено на {days} дн. · до `{new_end.date()}`',
                ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(f'❌ {ex}', ephemeral=True)


def build_panel_view(
    cog: 'StaffManager',
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
    accent: int = 0x000000,
    step_hint: str = '',
) -> discord.ui.LayoutView:
    """UI как /modpanel: чёрные блоки + селекты, без большой картинки."""
    a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
    t_ctx = resolve_target(target.id, _member_role_ids(target))
    info = get_staff_info(target)
    allowed = get_allowed_actions(a_ctx, t_ctx)
    cfg = get_config() or {}
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}

    sel_act = payload.get('action') or ''
    sel_role = payload.get('role') or ''
    sel_branch = payload.get('branch') or ''
    sel_kind = payload.get('removal_kind') or ''

    re = _emoji_for_role_key(info.get('primary_key') or '')
    be = _emoji_for_branch(info.get('primary_branch') or '')
    role_label = info.get('role_label') or 'участник'
    branch_label = info.get('branch_label') or '—'

    needs_role = sel_act in ('assign', 'promote', 'demote', 'transfer')
    needs_branch = sel_act in ('transfer',) or (
        sel_act == 'assign' and not t_ctx.primary_branch)
    needs_kind = sel_act == 'remove'
    step_total = 1 + int(needs_role) + int(needs_branch or (sel_act == 'assign' and len(allowed.get('branches') or []) > 1)) + int(needs_kind) + 1
    step_n = 1
    if sel_act:
        step_n = 2
    if sel_act and (not needs_role or sel_role):
        if needs_branch and not sel_branch:
            step_n = 2
        elif needs_kind and not sel_kind:
            step_n = 2
        else:
            step_n = min(step_total, 3)

    status_lines = [
        PANEL_MEMBER.format(mention=target.mention),
        PANEL_ROLE_BRANCH.format(
            role_emoji=re, role=role_label,
            branch_emoji=be, branch=branch_label),
    ]
    if info.get('on_vacation'):
        status_lines.append(PANEL_VACATION)
    if info.get('on_probation'):
        pr = info.get('probation') or {}
        try:
            from services.staff_manager.probation import probation_display
            disp = probation_display(pr)
            status_lines.append(
                f'-# 🕘 испытательный · осталось **{disp.get("days_left", "?")}** дн. '
                f'(до `{str(disp.get("end_at") or "")[:10]}`)')
        except Exception:
            status_lines.append('-# 🕘 испытательный срок')
    if t_ctx.multi_branch:
        status_lines.append(PANEL_MULTI)
    if len(info.get('ladder_role_ids') or []) > 1 or len(info.get('entry_role_ids') or []) > 1:
        status_lines.append(PANEL_DOUBLE)
    # набор роли (кратко)
    try:
        from services.staff_manager.bundles import get_role_bundle
        pk = info.get('primary_key') or ''
        pb = info.get('primary_branch') or ''
        if pk and pb:
            extras = get_role_bundle(pk, pb, cfg).get('add_roles') or []
            if extras:
                have = set(_member_role_ids(target))
                parts = []
                for rid in extras[:6]:
                    role = target.guild.get_role(int(rid)) if target.guild else None
                    mark = '✅' if int(rid) in have else '❌'
                    parts.append(f'{mark} {role.name if role else rid}')
                status_lines.append('-# Набор: ' + ' · '.join(parts))
    except Exception:
        pass

    tail = ''
    if sel_act:
        tail += f' · **{ACTION_LABELS.get(sel_act, sel_act)}**'
    if sel_role:
        # показываем человекочитаемое имя, не ключ
        rname = next(
            (x.get('name') for x in (cfg.get('ladder') or [])
             if x.get('key') == sel_role), sel_role)
        tail += f' · {_emoji_for_role_key(sel_role)} {rname}'
    if sel_branch:
        blab = ((cfg.get('branches') or {}).get(sel_branch) or {}).get(
            'label') or sel_branch
        tail += f' · {_emoji_for_branch(sel_branch)} {blab}'
    if sel_kind:
        tail += f' · {REMOVAL_KINDS.get(sel_kind, sel_kind)}'
    status_lines.append(PANEL_QUEUE.format(
        step=min(step_n, step_total), total=max(step_total, 1), tail=tail))

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(_black(
        discord.ui.TextDisplay(PANEL_TITLE),
        discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
        discord.ui.TextDisplay('\n'.join(status_lines)),
    ))

    actions = [a for a in allowed.get('actions') or [] if a != 'request']
    if actions:
        opts = []
        for a in actions[:25]:
            em = _opt_emoji('action', a)
            opts.append(discord.SelectOption(
                label=ACTION_LABELS.get(a, a)[:100],
                value=a,
                emoji=em,
                description=(ACTION_DESC.get(a) or '')[:100] or None,
                default=(a == sel_act),
            ))
        sel = discord.ui.Select(
            placeholder=PLACEHOLDER_ACTION,
            options=opts,
            custom_id=f'sm:act:{token}',
            min_values=1, max_values=1,
        )

        async def _on_act(interaction: discord.Interaction, select=sel):
            await cog._on_action_select(interaction, token, select.values[0])

        sel.callback = _on_act  # type: ignore
        row = discord.ui.ActionRow()
        row.add_item(sel)
        view.add_item(_black(discord.ui.TextDisplay(PANEL_ACTION), row))

    roles = allowed.get('roles') or []
    # куратор выше ассистента в списке (rank DESC)
    if sel_act in ('assign', 'promote', 'demote', 'transfer') and roles:
        roles_sorted = sorted(roles, key=lambda r: -int(r.get('rank') or 0))
        ropts = []
        for r in roles_sorted[:25]:
            key = r['key']
            em = _opt_emoji('role', key, r.get('emoji'))
            # label = только имя; кастомный emoji — в поле emoji (иначе виден <:id:>)
            ropts.append(discord.SelectOption(
                label=str(r.get('name') or key)[:100],
                value=key,
                emoji=em,
                description=(ROLE_DESC.get(key) or '')[:100] or None,
                default=(key == sel_role),
            ))
        rsel = discord.ui.Select(
            placeholder=PLACEHOLDER_ROLE,
            options=ropts,
            custom_id=f'sm:role:{token}',
            min_values=1, max_values=1,
        )

        async def _on_role(interaction: discord.Interaction, select=rsel):
            await cog._on_role_select(interaction, token, select.values[0])

        rsel.callback = _on_role  # type: ignore
        row2 = discord.ui.ActionRow()
        row2.add_item(rsel)
        view.add_item(_black(discord.ui.TextDisplay(PANEL_ROLE), row2))

    branches = allowed.get('branches') or []
    show_branch = (
        sel_act == 'transfer'
        or (sel_act == 'assign' and (not t_ctx.primary_branch or len(branches) > 1))
    )
    if show_branch and branches:
        bopts = []
        for b in branches[:25]:
            em = _opt_emoji('branch', b['key'], b.get('emoji'))
            bopts.append(discord.SelectOption(
                label=(b.get('label') or b['key'])[:100],
                value=b['key'],
                emoji=em,
                description=(BRANCH_DESC.get(b['key']) or '')[:100] or None,
                default=(b['key'] == sel_branch),
            ))
        bsel = discord.ui.Select(
            placeholder=PLACEHOLDER_BRANCH,
            options=bopts,
            custom_id=f'sm:br:{token}',
            min_values=1, max_values=1,
        )

        async def _on_br(interaction: discord.Interaction, select=bsel):
            await cog._on_branch_select(interaction, token, select.values[0])

        bsel.callback = _on_br  # type: ignore
        row3 = discord.ui.ActionRow()
        row3.add_item(bsel)
        view.add_item(_black(discord.ui.TextDisplay(PANEL_BRANCH), row3))

    if sel_act == 'remove':
        ksel = discord.ui.Select(
            placeholder=PLACEHOLDER_REMOVAL,
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
            save_menu_state(
                token, st2['guild_id'], st2['actor_id'], st2['target_id'],
                'removal_kind', payload2)
            actor2 = interaction.guild.get_member(interaction.user.id)
            target2 = interaction.guild.get_member(int(st2['target_id']))
            if actor2 and target2:
                view2 = build_panel_view(
                    cog, token=token, actor=actor2, target=target2)
                await interaction.response.edit_message(view=view2)
            else:
                await interaction.response.defer()

        ksel.callback = _on_rk  # type: ignore
        rowk = discord.ui.ActionRow()
        rowk.add_item(ksel)
        view.add_item(_black(discord.ui.TextDisplay(PANEL_REMOVAL_KIND), rowk))

    # испытательный — выбор срока (или снять, если уже идёт)
    if sel_act == 'probation':
        if info.get('on_probation'):
            view.add_item(_black(discord.ui.TextDisplay(
                '**Испытательный уже идёт**\n'
                '-# «Подтвердить» + причина = снять досрочно')))
        else:
            presets = cfg.get('probation_presets') or []
            sel_days = str(payload.get('probation_days') or '')
            popts = []
            for p in presets[:25]:
                d = int(p.get('days') or 0)
                if d <= 0:
                    continue
                em = p.get('emoji') or None
                if em in ('✦', '✧', '•', None):
                    em = None
                popts.append(discord.SelectOption(
                    label=str(p.get('label') or f'{d} дн.')[:100],
                    value=str(d),
                    emoji=em,
                    description=f'{d} дн.'[:100],
                    default=(str(d) == sel_days),
                ))
            if popts:
                psel = discord.ui.Select(
                    placeholder='Срок испытательного',
                    options=popts,
                    custom_id=f'sm:prob:days:{token}',
                    min_values=1, max_values=1,
                )

                async def _on_pd(interaction: discord.Interaction, select=psel):
                    st2 = load_menu_state(token)
                    if not st2 or not interaction.guild:
                        await interaction.response.send_message(
                            'устарело', ephemeral=True)
                        return
                    payload2 = st2.get('payload') or {}
                    payload2['action'] = 'probation'
                    payload2['probation_days'] = int(select.values[0])
                    save_menu_state(
                        token, st2['guild_id'], st2['actor_id'], st2['target_id'],
                        'probation_days', payload2)
                    actor2 = interaction.guild.get_member(interaction.user.id)
                    target2 = interaction.guild.get_member(int(st2['target_id']))
                    if actor2 and target2:
                        view2 = build_panel_view(
                            cog, token=token, actor=actor2, target=target2)
                        await interaction.response.edit_message(view=view2)
                    else:
                        await interaction.response.defer()

                psel.callback = _on_pd  # type: ignore
                rowp = discord.ui.ActionRow()
                rowp.add_item(psel)
                view.add_item(_black(
                    discord.ui.TextDisplay('**Срок испытательного**'), rowp))
                if sel_days:
                    view.add_item(_black(discord.ui.TextDisplay(
                        f'-# выбран срок: **{sel_days}** дн. · '
                        'дальше «Подтвердить» + причина')))
                else:
                    view.add_item(_black(discord.ui.TextDisplay(
                        '-# сначала выберите срок выше, потом «Подтвердить»')))

    async def _ok(interaction: discord.Interaction):
        await interaction.response.send_modal(ReasonModal(cog, token))

    async def _no(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass

    # чёрные «зеркальные» кнопки — не классический зелёный/красный
    row_btn = mirror_confirm_row(
        ok_id=f'sm:ok:{token}',
        cancel_id=f'sm:no:{token}',
        ok_callback=_ok,
        cancel_callback=_no,
    )

    pend = pending_consent_for(actor.guild.id, target.id) if actor.guild else None
    if pend and int(pend.get('initiator_id') or 0) == actor.id:
        btn_cancel = discord.ui.Button(
            label=BTN_REVOKE, style=discord.ButtonStyle.secondary,
            custom_id=f'sm:cx:{pend["id"]}')

        async def _cx(interaction: discord.Interaction, cid=pend['id']):
            await cog._consent_cancel(interaction, cid)

        btn_cancel.callback = _cx  # type: ignore
        row_btn.add_item(btn_cancel)

    if allowed.get('can_request') and 'assign' not in actions and 'promote' not in actions:
        btn_req = discord.ui.Button(
            label=BTN_REQUEST, style=discord.ButtonStyle.primary,
            emoji=_opt_emoji('action', 'request'),
            custom_id=f'sm:req:{token}')

        async def _req(interaction: discord.Interaction):
            st2 = load_menu_state(token) or {}
            payload2 = st2.get('payload') or {}
            payload2['action'] = 'request'
            save_menu_state(
                token, st2.get('guild_id') or interaction.guild_id,
                st2.get('actor_id') or interaction.user.id,
                st2.get('target_id') or target.id,
                'confirm', payload2)
            await interaction.response.send_modal(ReasonModal(cog, token))

        btn_req.callback = _req  # type: ignore
        row_btn.add_item(btn_req)

    view.add_item(_black(discord.ui.TextDisplay(PANEL_CONFIRM), row_btn))
    return view


class ConsentAcceptButton(discord.ui.Button):
    def __init__(self, cog: 'StaffManager', consent_id: str):
        super().__init__(
            label=CONSENT_ACCEPT, style=discord.ButtonStyle.secondary,
            custom_id=f'sm:cya:{consent_id}')
        self.cog = cog
        self.consent_id = consent_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog._consent_accept(interaction, self.consent_id)


class ConsentDeclineButton(discord.ui.Button):
    def __init__(self, cog: 'StaffManager', consent_id: str):
        super().__init__(
            label=CONSENT_DECLINE, style=discord.ButtonStyle.secondary,
            custom_id=f'sm:cno:{consent_id}')
        self.cog = cog
        self.consent_id = consent_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            DeclineReasonModal(self.cog, self.consent_id))


class ConsentPersistentView(discord.ui.LayoutView):
    """Persistent V2 view для DM/fallback согласия — чёрное зеркало."""

    def __init__(self, cog: 'StaffManager', consent_id: str, body: str,
                 color: int = MIRROR_BLACK):
        super().__init__(timeout=None)
        self.add_item(mirror_container(
            discord.ui.TextDisplay(body), accent=color or MIRROR_BLACK))
        row = discord.ui.ActionRow()
        row.add_item(ConsentAcceptButton(cog, consent_id))
        row.add_item(ConsentDeclineButton(cog, consent_id))
        self.add_item(row)


def _screen_for_action(cog, *, token, actor, target, action: str):
    """Отдельный билдер на каждый экран — не универсальный шаблон."""
    action = (action or '').strip().lower()
    if action in ('promote', 'demote'):
        return build_promotion_view(
            cog, token=token, actor=actor, target=target, mode=action)
    if action == 'vacation':
        return build_vacation_view(
            cog, token=token, actor=actor, target=target)
    if action == 'transfer':
        return build_transfer_view(
            cog, token=token, actor=actor, target=target)
    if action == 'remove' or action == 'self_leave':
        return build_removal_view(
            cog, token=token, actor=actor, target=target)
    if action == 'history':
        return build_history_view(
            cog, token=token, actor=actor, target=target)
    if action in ('assign',):
        return build_panel_view(
            cog, token=token, actor=actor, target=target)
    return build_profile_view(
        cog, token=token, actor=actor, target=target)


class StaffManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._started = False

    async def cog_load(self):
        ensure_tables()
        # persistent consent buttons через custom_id prefix — регистрируем
        # динамически при boot по pending, плюс Interaction listener ниже

    async def cog_unload(self):
        if self._expire_loop.is_running():
            self._expire_loop.cancel()
        if getattr(self, '_vacation_loop', None) and self._vacation_loop.is_running():
            self._vacation_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._started:
            return
        self._started = True
        await self._boot_config()
        await self._discover_emojis()
        await self._reregister_consent_views()
        if not self._expire_loop.is_running():
            self._expire_loop.start()
        if not self._vacation_loop.is_running():
            self._vacation_loop.start()
            # пропущенное при старте — сразу
            try:
                from services.staff_manager.vacation import process_due_vacations
                n = await process_due_vacations(self.bot)
                if n:
                    _log.info('vacation catch-up ended=%s', n)
            except Exception as ex:
                _log.error('vacation catch-up: %s', ex)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles == after.roles:
            return
        try:
            info = get_staff_info(after)
            from services.staff_manager.store import upsert_staff_profile
            upsert_staff_profile(
                guild_id=after.guild.id,
                user_id=after.id,
                branch=info.get('primary_branch') or '',
                role_key=info.get('primary_key') or '',
                status='active' if info.get('is_staff') else 'removed',
            )
            from services import members_cache as MC
            MC.upsert_member(after)
        except Exception as ex:
            _log.debug('on_member_update staff sync: %s', ex)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Persistent consent / menu custom_id без заранее зарегистрированного view."""
        if interaction.type != discord.InteractionType.component:
            return
        try:
            data = getattr(interaction, 'data', None) or {}
            cid = str(data.get('custom_id') or '')
        except Exception:
            return
        if not cid.startswith('sm:c'):
            return
        # уже обработано привязанным callback
        if interaction.response.is_done():
            return
        if cid.startswith('sm:cya:'):
            await self._consent_accept(interaction, cid.split(':', 2)[-1])
        elif cid.startswith('sm:cno:'):
            await interaction.response.send_modal(
                DeclineReasonModal(self, cid.split(':', 2)[-1]))
        elif cid.startswith('sm:cx:'):
            await self._consent_cancel(interaction, cid.split(':', 2)[-1])

    async def _boot_config(self):
        await self.bot.wait_until_ready()
        main_gid = int(os.environ.get('MAIN_GUILD_ID') or 0)

        async def _collect_ids() -> set:
            ids: set = set()
            for g in self.bot.guilds:
                if main_gid and int(g.id) != main_gid:
                    continue
                # дождаться ролей, если кэш ещё пуст (только @everyone)
                if len(g.roles) <= 1:
                    try:
                        await g.fetch_roles()
                    except Exception:
                        pass
                for r in g.roles:
                    ids.add(int(r.id))
            return ids

        guild_role_ids = await _collect_ids()
        ok, err = reload_config(
            guild_role_ids=guild_role_ids if guild_role_ids else None)
        # кэш ролей иногда пуст на первом on_ready — не глушим модуль
        if not ok and err and 'не найдена на сервере' in err:
            _log.warning(
                'staff_manager: кэш ролей неполный (%s ids), повтор без '
                'guild-check: %s', len(guild_role_ids), err[:200])
            await asyncio.sleep(2)
            guild_role_ids = await _collect_ids()
            ok, err = reload_config(
                guild_role_ids=guild_role_ids if len(guild_role_ids) > 10 else None)
        if not ok:
            _log.error('staff_manager DISABLED: %s', err)
        else:
            _log.info('staff_manager: online')

    async def _discover_emojis(self):
        cfg = get_config() or {}
        if not cfg:
            return
        try:
            await ensure_action_emojis(self.bot)
        except Exception as ex:
            _log.warning('action emojis: %s', ex)
        for g in self.bot.guilds:
            try:
                got = await ensure_role_emojis(self.bot, g)
                _log.info('staff emojis ready guild=%s n=%s', g.id, len(got))
            except Exception as ex:
                _log.error('ensure_role_emojis: %s\n%s', ex, traceback.format_exc())

    async def _reregister_consent_views(self):
        for g in self.bot.guilds:
            for c in list_consents(g.id, status='pending', limit=100):
                try:
                    view = ConsentPersistentView(
                        self, c['id'],
                        '⏳ Ожидание ответа…', 0x9B59B6)
                    self.bot.add_view(view)
                except Exception as ex:
                    _log.debug('reregister consent: %s', ex)

    @tasks.loop(minutes=5)
    async def _expire_loop(self):
        try:
            expired = expire_due_consents()
            for c in expired:
                await self._notify_consent_expired(c)
        except Exception as ex:
            _log.error('expire consents: %s\n%s', ex, traceback.format_exc())

    @_expire_loop.before_loop
    async def _before_expire(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=2)
    async def _vacation_loop(self):
        try:
            from services.staff_manager.vacation import process_due_vacations
            await process_due_vacations(self.bot)
        except Exception as ex:
            _log.error('vacation loop: %s\n%s', ex, traceback.format_exc())
        try:
            from services.staff_manager.probation import process_due_probations
            n = process_due_probations()
            if n:
                _log.info('probation auto-ended n=%s', n)
        except Exception as ex:
            _log.error('probation loop: %s\n%s', ex, traceback.format_exc())

    @_vacation_loop.before_loop
    async def _before_vacation(self):
        await self.bot.wait_until_ready()

    async def _notify_consent_expired(self, c: dict):
        guild = self.bot.get_guild(int(c['guild_id']))
        if not guild:
            return
        initiator = guild.get_member(int(c['initiator_id']))
        if initiator:
            try:
                await initiator.send(
                    f'⏱ Срок согласия на перевод истёк '
                    f'(цель <@{c["target_id"]}>).')
            except Exception:
                pass

    # ── slash ──────────────────────────────────────────────────────────

    @app_commands.command(name='staff', description='Стафф')
    @app_commands.describe(member='Участник')
    async def staff(
        self, interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not is_enabled():
            await interaction.response.send_message(
                last_error() or 'нет конфига', ephemeral=True)
            return
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('только сервер', ephemeral=True)
            return

        actor = interaction.user
        await interaction.response.defer(ephemeral=True)
        # тихий автосинк набора (без сообщений в чат)
        try:
            await self._sync_member_bundle(interaction.guild, actor, member)
            member = interaction.guild.get_member(member.id) or member
        except Exception as ex:
            _log.warning('sync_bundle on /staff: %s', ex)

        token = new_action_id()[:16]
        save_menu_state(
            token, interaction.guild.id, actor.id, member.id,
            'card', {'action': '', 'role': '', 'branch': ''})
        view = build_panel_view(self, token=token, actor=actor, target=member)
        try:
            self.bot.add_view(view)
        except Exception:
            pass
        try:
            await interaction.followup.send(view=view, ephemeral=True)
        except discord.HTTPException as ex:
            _log.error('staff panel send failed: %s', ex)
            await interaction.followup.send(
                f'Не удалось открыть панель: {ex}', ephemeral=True)

    # ── menu callbacks ─────────────────────────────────────────────────

    async def _sync_member_bundle(self, guild, actor, member):
        """Довыдать недостающие роли набора текущей ступени (без смены лестницы)."""
        info = get_staff_info(member)
        key = info.get('primary_key') or ''
        branch = info.get('primary_branch') or ''
        if not key or not branch or info.get('on_vacation'):
            return None
        from services.staff_manager.bundles import get_role_bundle
        bundle = get_role_bundle(key, branch)
        need = [int(r) for r in (bundle.get('add_roles') or []) if int(r or 0)]
        have = set(_member_role_ids(member))
        missing = [r for r in need if r not in have]
        if not missing:
            return None
        result = await apply_staff_change(
            guild=guild,
            actor_member=actor,
            target_member=member,
            action='sync_bundle',
            new_role_key=key,
            new_branch=branch,
            reason='auto sync ROLE_BUNDLES',
            source='auto_sync',
            skip_acl=True,
        )
        if result.ok and result.added:
            _log.info(
                'auto sync_bundle target=%s added=%s',
                member.id, result.added)
        elif not result.ok:
            _log.warning(
                'auto sync_bundle failed target=%s: %s',
                member.id, result.reason)
        return result

    async def _on_action_select(self, interaction, token, action):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['action'] = action
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'action', payload)
        target = interaction.guild.get_member(int(st['target_id']))
        actor = interaction.guild.get_member(interaction.user.id)
        if not target or not actor:
            await interaction.response.send_message('не найден', ephemeral=True)
            return
        # история / отпуск — отдельные экраны; остальное — select-панель
        if action in ('history', 'vacation'):
            view = _screen_for_action(
                self, token=token, actor=actor, target=target, action=action)
        else:
            view = build_panel_view(
                self, token=token, actor=actor, target=target)
        await interaction.response.edit_message(view=view)

    async def _open_action_screen(self, interaction, token, action):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['action'] = action
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'action', payload)
        target = interaction.guild.get_member(int(st['target_id']))
        actor = interaction.guild.get_member(interaction.user.id)
        if not target or not actor:
            await interaction.response.send_message('не найден', ephemeral=True)
            return
        # права перепроверяются
        a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
        t_ctx = resolve_target(target.id, _member_role_ids(target))
        ok, why = can_manage_staff(a_ctx, t_ctx, action)
        if not ok and action not in ('history',):
            await interaction.response.send_message(why, ephemeral=True)
            return
        view = _screen_for_action(
            self, token=token, actor=actor, target=target, action=action)
        await interaction.response.edit_message(view=view)

    async def _on_role_select(self, interaction, token, role_key):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['role'] = role_key
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'role', payload)
        target = interaction.guild.get_member(int(st['target_id']))
        actor = interaction.guild.get_member(interaction.user.id)
        if not target or not actor:
            await interaction.response.defer()
            return
        view = build_panel_view(
            self, token=token, actor=actor, target=target)
        await interaction.response.edit_message(view=view)

    async def _on_branch_select(self, interaction, token, branch):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['branch'] = branch
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'branch', payload)
        target = interaction.guild.get_member(int(st['target_id']))
        actor = interaction.guild.get_member(interaction.user.id)
        if not target or not actor:
            await interaction.response.defer()
            return
        action = payload.get('action') or 'transfer'
        if action == 'transfer':
            view = _screen_for_action(
                self, token=token, actor=actor, target=target, action=action)
        else:
            view = build_panel_view(
                self, token=token, actor=actor, target=target)
        await interaction.response.edit_message(view=view)

    async def _set_bypass_and_reason(self, interaction, token):
        st = load_menu_state(token)
        if not st:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['bypass_rules'] = True
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'bypass', payload)
        await interaction.response.send_modal(ReasonModal(self, token))

    async def _history_filter(self, interaction, token, key, value):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload[key] = value
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'history', payload)
        actor = interaction.guild.get_member(interaction.user.id)
        tid = int(st.get('target_id') or 0)
        target = interaction.guild.get_member(tid) if tid else None
        if not actor:
            await interaction.response.defer()
            return
        view = build_history_view(
            self, token=token, actor=actor, target=target, page=0)
        await interaction.response.edit_message(view=view)

    async def _history_page(self, interaction, token, page):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        actor = interaction.guild.get_member(interaction.user.id)
        tid = int(st.get('target_id') or 0)
        target = interaction.guild.get_member(tid) if tid else None
        if not actor:
            await interaction.response.defer()
            return
        view = build_history_view(
            self, token=token, actor=actor, target=target, page=page)
        await interaction.response.edit_message(view=view)

    async def _vacation_preset(self, interaction, token, preset_key):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['action'] = 'vacation'
        payload['vac_preset'] = preset_key
        cfg = get_config() or {}
        days = 0
        for p in (cfg.get('vacation_presets') or []):
            if p.get('key') == preset_key:
                days = int(p.get('days') or 0)
                break
        payload['vac_days'] = days
        if preset_key == 'custom':
            # модалка даты — через reason modal с форматом
            save_menu_state(
                token, st['guild_id'], st['actor_id'], st['target_id'],
                'vac_custom', payload)
            await interaction.response.send_modal(
                VacationDateModal(self, token))
            return
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'vac_preset', payload)
        target = interaction.guild.get_member(int(st['target_id']))
        actor = interaction.guild.get_member(interaction.user.id)
        if not target or not actor:
            await interaction.response.defer()
            return
        view = build_vacation_view(
            self, token=token, actor=actor, target=target)
        await interaction.response.edit_message(view=view)

    async def _vacation_end_now(self, interaction, token):
        st = load_menu_state(token)
        if not st or not interaction.guild:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from services.staff_manager.vacation import end_vacation
        actor = interaction.guild.get_member(interaction.user.id)
        target = interaction.guild.get_member(int(st['target_id']))
        if not actor or not target:
            await interaction.followup.send('не найден', ephemeral=True)
            return
        ok, why, alerts = await end_vacation(
            guild=interaction.guild, actor_member=actor,
            target_member=target, end_kind='early', reason='early_return')
        msg = ('✅ С возвращением!' if ok else f'❌ {why}')
        if alerts:
            msg += '\n' + '\n'.join(alerts)
        await interaction.followup.send(msg, ephemeral=True)

    async def _vacation_extend_menu(self, interaction, token):
        st = load_menu_state(token)
        if not st:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        await interaction.response.send_modal(VacationExtendModal(self, token))

    async def _confirm_with_reason(self, interaction, token, reason):
        if not interaction.guild:
            await interaction.response.send_message('только сервер', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        st = load_menu_state(token)
        if not st:
            await interaction.followup.send('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        action = payload.get('action') or ''
        role_key = payload.get('role') or None
        branch = payload.get('branch') or None
        removal_kind = payload.get('removal_kind') or None
        actor = interaction.guild.get_member(interaction.user.id)
        target = interaction.guild.get_member(int(st['target_id']))
        if not actor or not target:
            await interaction.followup.send('не найден', ephemeral=True)
            return

        a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
        t_ctx = resolve_target(target.id, _member_role_ids(target))
        ok, why = can_manage_staff(
            a_ctx, t_ctx, action, new_role_key=role_key, new_branch=branch)
        if not ok:
            await interaction.followup.send(why, ephemeral=True)
            return

        if action == 'history':
            view = build_history_view(
                self, token=token, actor=actor, target=target)
            await interaction.followup.send(view=view, ephemeral=True)
            return

        if action == 'remove' and not removal_kind:
            await interaction.followup.send(
                'Выберите тип снятия в меню', ephemeral=True)
            return

        if action == 'probation':
            from services.staff_manager.probation import (
                start_probation, end_probation,
            )
            # если уже на испытательном — кнопка подтверждения снимает досрочно
            if t_ctx and get_staff_info(target).get('on_probation'):
                ok, why = end_probation(
                    guild_id=interaction.guild.id,
                    actor_id=actor.id,
                    user_id=target.id,
                    end_kind='early',
                    reason=reason or 'досрочно',
                )
                await interaction.followup.send(
                    ('✅ Испытательный снят' if ok else f'❌ {why}'),
                    ephemeral=True)
                return
            days = int(payload.get('probation_days') or 0)
            if days <= 0:
                await interaction.followup.send(
                    'Выберите срок испытательного в меню', ephemeral=True)
                return
            ok, status, row = start_probation(
                guild_id=interaction.guild.id,
                actor_member=actor,
                target_member=target,
                days=days,
                reason=reason,
                source='manual',
            )
            if not ok:
                await interaction.followup.send(f'❌ {status}', ephemeral=True)
                return
            await interaction.followup.send(
                f'🕘 Испытательный · {target.mention} · **{days}** дн. '
                f'(до `{str((row or {}).get("end_at") or "")[:10]}`)',
                ephemeral=True)
            return

        if action == 'vacation':
            from services.staff_manager.vacation import start_vacation
            days = int(payload.get('vac_days') or 0)
            if days <= 0:
                await interaction.followup.send(
                    'Выберите срок отпуска', ephemeral=True)
                return
            ok, status, vac = await start_vacation(
                guild=interaction.guild, actor_member=actor,
                target_member=target, days=days, reason=reason,
                force_approve=bool(payload.get('bypass_rules')),
            )
            if not ok:
                await interaction.followup.send(f'❌ {status}', ephemeral=True)
                return
            if status == 'pending':
                await interaction.followup.send(
                    f'⏳ Заявка на отпуск ({days} дн.) отправлена на одобрение.',
                    ephemeral=True)
                return
            await interaction.followup.send(
                f'🏝 Отпуск · {target.mention} · {days} дн.', ephemeral=True)
            await self._announce_vacation_card(
                interaction.guild, target, actor, vac, days, reason)
            return

        # условия повышения (кроме bypass Стафф админ/владелец)
        if action == 'promote' and role_key and not payload.get('bypass_rules'):
            t_info = get_staff_info(target)
            ok_req, missing = get_promotion_requirements(
                role_key,
                branch=branch or t_info.get('primary_branch'),
                on_vacation=bool(t_info.get('on_vacation')),
            )
            if missing and not (a_ctx.is_owner or a_ctx.is_staff_admin):
                await interaction.followup.send(
                    'Нельзя повысить:\n• ' + '\n• '.join(missing),
                    ephemeral=True)
                return
            if missing and (a_ctx.is_owner or a_ctx.is_staff_admin):
                await interaction.followup.send(
                    '⚠ Условия не выполнены. Нужна кнопка «Повысить вне правил» '
                    'и причина.\n• ' + '\n• '.join(missing),
                    ephemeral=True)
                return

        if payload.get('bypass_rules'):
            reason = f'[вне правил] {reason}'

        # consent gate
        if requires_consent(action):
            await self._start_consent(
                interaction, actor, target, action, role_key, branch, reason)
            return

        old_key = t_ctx.primary_key or ''
        result = await apply_staff_change(
            guild=interaction.guild,
            actor_member=actor,
            target_member=target,
            action=action,
            new_role_key=role_key,
            new_branch=branch,
            reason=reason,
            source='discord',
            removal_kind=removal_kind,
        )
        if not result.ok:
            await interaction.followup.send(
                f'❌ {result.reason or "отказ"}', ephemeral=True)
            await self._log_staff_action(
                interaction.guild, action, actor, target, role_key, reason,
                ok=False, err=result.reason)
            return

        label = ACTION_LABELS.get(action, action)
        info = result.staff_info or get_staff_info(
            interaction.guild.get_member(target.id) or target)
        actor_label = format_actor_label(
            actor.display_name, a_ctx.primary_key,
            branch=a_ctx.primary_branch)
        await interaction.followup.send(
            f'✅ {label} · {target.mention}'
            + (f' · {format_role_label(info.get("primary_key") or role_key or "", branch=info.get("primary_branch"))}')
            + (f' · {info.get("branch_label") or ""}'),
            ephemeral=True,
        )
        await self._log_staff_action(
            interaction.guild, action, actor, target, role_key, reason, ok=True)
        if action in ('promote', 'demote', 'assign') and role_key:
            await self._announce_ceremony(
                interaction.guild, target, actor, old_key, role_key,
                info.get('primary_branch') or branch or '',
                reason, promote=(action == 'promote'),
                actor_label=actor_label)
        if action in ('promote', 'assign') and role_key:
            try:
                from services.staff_manager.probation import (
                    maybe_start_after_promote,
                )
                fresh = interaction.guild.get_member(target.id) or target
                prow = maybe_start_after_promote(
                    guild_id=interaction.guild.id,
                    actor_member=actor,
                    target_member=fresh,
                    new_role_key=role_key,
                    branch=info.get('primary_branch') or branch or '',
                )
                if prow:
                    days = int(prow.get('days') or 0)
                    end_at = str(prow.get('end_at') or '')[:10]
                    _log.info(
                        'probation auto start target=%s days=%s',
                        target.id, days)
                    try:
                        await interaction.followup.send(
                            f'🕘 Авто испытательный · {target.mention} · '
                            f'**{days}** дн. (до `{end_at}`)',
                            ephemeral=True,
                        )
                    except Exception:
                        pass
            except Exception as ex:
                _log.warning('probation auto: %s', ex)
        if action == 'remove':
            await self._dm_removed(target, actor, removal_kind, reason, info)
        if result.alert_multi:
            _log.warning(
                'staff_manager ALERT multi-branch target=%s actor=%s',
                target.id, actor.id)

    async def _start_consent(
        self, interaction, actor, target, action, role_key, branch, reason,
    ):
        cfg = get_config() or {}
        t_info = get_staff_info(target)
        to_rid = 0
        if branch and role_key:
            to_rid = int(
                ((get_index() or {}).get('by_branch_key') or {}).get(
                    (branch, role_key), 0) or 0)
        from_rid = 0
        if t_info.get('primary_key') and t_info.get('primary_branch'):
            from_rid = int(
                ((get_index() or {}).get('by_branch_key') or {}).get(
                    (t_info['primary_branch'], t_info['primary_key']), 0) or 0)

        c = create_consent(
            guild_id=interaction.guild.id,
            target_id=target.id,
            initiator_id=actor.id,
            action=action,
            from_branch=t_info.get('primary_branch') or '',
            from_role_id=from_rid,
            to_branch=branch or '',
            to_role_id=to_rid,
            to_role_key=role_key or '',
            reason=reason,
            expire_hours=int(cfg.get('consent_expire_hours') or 48),
        )
        if not c:
            await interaction.followup.send(
                'У человека уже есть pending-запрос согласия', ephemeral=True)
            return

        hours = int(cfg.get('consent_expire_hours') or 48)
        re = _emoji_for_role_key(role_key or '')
        be = _emoji_for_branch(branch or '')
        body = (
            f'## {re} Предложение: {ACTION_LABELS.get(action, action)}\n'
            f'От: {actor.mention} (`{actor.id}`)\n'
            f'Из: **{t_info.get("role_label") or "—"}** / '
            f'{t_info.get("branch_label") or "—"}\n'
            f'В: **{re} {role_key or "—"}** / {be} {branch or "—"}\n'
            f'Причина: {reason}\n'
            f'Срок: **{hours}ч** · <t:{int(datetime.now(timezone.utc).timestamp()) + hours * 3600}:R>'
        )
        view = ConsentPersistentView(self, c['id'], body, 0x9B59B6)
        try:
            self.bot.add_view(view)
        except Exception:
            pass

        dm_ok = False
        try:
            msg = await target.send(view=view)
            update_consent(c['id'], dm_message_id=msg.id)
            dm_ok = True
        except Exception as ex:
            _log.info('consent DM failed target=%s: %s', target.id, ex)

        if not dm_ok:
            fb = int(cfg.get('consent_fallback_channel_id') or 0)
            ch = interaction.guild.get_channel(fb) if fb else None
            if ch:
                try:
                    msg = await ch.send(
                        content=target.mention,
                        view=ConsentPersistentView(
                            self, c['id'],
                            body + '\n\n_(DM закрыты — ответ здесь; '
                                   'кнопки только для упоминаемого)_',
                            0x9B59B6),
                    )
                    update_consent(c['id'], channel_message_id=msg.id)
                except Exception as ex:
                    _log.error('consent fallback: %s\n%s', ex, traceback.format_exc())
                    await interaction.followup.send(
                        f'❌ Не удалось доставить запрос согласия: {ex}',
                        ephemeral=True)
                    claim_consent_decision(c['id'], 'failed')
                    return
            else:
                await interaction.followup.send(
                    '❌ DM закрыты и CONSENT_FALLBACK_CHANNEL_ID не задан',
                    ephemeral=True)
                claim_consent_decision(c['id'], 'failed')
                return

        await interaction.followup.send(
            f'⏳ Запрос согласия отправлен {target.mention}. '
            f'Ждём ответ (id `{c["id"][:8]}…`).',
            ephemeral=True,
        )
        await self._log_staff_action(
            interaction.guild, f'consent_pending:{action}', actor, target,
            role_key, reason, ok=True)

    async def _consent_accept(self, interaction: discord.Interaction, consent_id: str):
        c = get_consent(consent_id)
        if not c:
            if not interaction.response.is_done():
                await interaction.response.send_message('запрос не найден', ephemeral=True)
            return
        if int(interaction.user.id) != int(c['target_id']):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    'Только тот, кому предложен перевод, может нажать',
                    ephemeral=True)
            return
        if c.get('status') != 'pending':
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f'Уже обработано: {c.get("status")}', ephemeral=True)
            return
        # expiry check
        try:
            exp = datetime.fromisoformat(c['expires_at'])
            if datetime.now(timezone.utc) > exp:
                claim_consent_decision(consent_id, 'expired')
                if not interaction.response.is_done():
                    await interaction.response.send_message('срок истёк', ephemeral=True)
                return
        except Exception:
            pass

        claimed = claim_consent_decision(consent_id, 'accepted')
        if not claimed:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    'Уже принято/отклонено', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = self.bot.get_guild(int(c['guild_id'])) or interaction.guild
        if not guild:
            update_consent(consent_id, status='failed')
            await interaction.followup.send('сервер не найден', ephemeral=True)
            return
        initiator = guild.get_member(int(c['initiator_id']))
        target = guild.get_member(int(c['target_id']))
        if not initiator or not target:
            update_consent(consent_id, status='failed')
            await interaction.followup.send('участник не найден', ephemeral=True)
            return

        # re-check ACL
        a_ctx = resolve_actor(initiator.id, _member_role_ids(initiator))
        t_ctx = resolve_target(target.id, _member_role_ids(target))
        ok, why = can_manage_staff(
            a_ctx, t_ctx, c['action'],
            new_role_key=c.get('to_role_key'),
            new_branch=c.get('to_branch'),
        )
        if not ok:
            update_consent(consent_id, status='failed')
            await interaction.followup.send(
                f'❌ Права инициатора больше не позволяют: {why}', ephemeral=True)
            try:
                await initiator.send(
                    f'Согласие принято, но действие отклонено ACL: {why}')
            except Exception:
                pass
            return

        result = await apply_staff_change(
            guild=guild,
            actor_member=initiator,
            target_member=target,
            action=c['action'],
            new_role_key=c.get('to_role_key'),
            new_branch=c.get('to_branch'),
            reason=c.get('reason') or '',
            source='consent',
        )
        if not result.ok:
            update_consent(consent_id, status='failed')
            await interaction.followup.send(
                f'❌ Не удалось применить: {result.reason}', ephemeral=True)
            try:
                await initiator.send(
                    f'Согласие принято, но смена ролей не удалась: {result.reason}')
            except Exception:
                pass
            return

        await interaction.followup.send('✅ Принято. Роли обновлены.', ephemeral=True)
        try:
            await initiator.send(
                f'✅ {target.mention} принял(а) перевод → '
                f'`{c.get("to_role_key")}` / `{c.get("to_branch")}`')
        except Exception:
            pass
        await self._log_staff_action(
            guild, c['action'], initiator, target,
            c.get('to_role_key'), c.get('reason') or '', ok=True,
            extra='consent accepted')

    async def _consent_decline(
        self, interaction: discord.Interaction, consent_id: str, decline_reason: str,
    ):
        c = get_consent(consent_id)
        if not c:
            await interaction.response.send_message('не найдено', ephemeral=True)
            return
        if int(interaction.user.id) != int(c['target_id']):
            await interaction.response.send_message(
                'Только адресат может отказаться', ephemeral=True)
            return
        claimed = claim_consent_decision(consent_id, 'declined')
        if not claimed:
            await interaction.response.send_message(
                f'Уже: {c.get("status")}', ephemeral=True)
            return
        if decline_reason:
            update_consent(consent_id, decline_reason=decline_reason)
        await interaction.response.send_message('Ок, отказ зафиксирован.', ephemeral=True)
        guild = self.bot.get_guild(int(c['guild_id']))
        if guild:
            initiator = guild.get_member(int(c['initiator_id']))
            if initiator:
                try:
                    await initiator.send(
                        f'✖️ <@{c["target_id"]}> отказался от перевода.'
                        + (f' Причина: {decline_reason}' if decline_reason else ''))
                except Exception:
                    pass
            await self._log_staff_action(
                guild, 'consent_declined', initiator or interaction.user,
                guild.get_member(int(c['target_id'])) or interaction.user,
                c.get('to_role_key'), decline_reason or c.get('reason') or '',
                ok=True)

    async def _consent_cancel(self, interaction: discord.Interaction, consent_id: str):
        c = get_consent(consent_id)
        if not c:
            await interaction.response.send_message('не найдено', ephemeral=True)
            return
        if int(interaction.user.id) != int(c['initiator_id']):
            if not _is_staff_admin_or_owner(interaction.user):
                await interaction.response.send_message('не ваш запрос', ephemeral=True)
                return
        claimed = claim_consent_decision(consent_id, 'cancelled')
        if not claimed:
            await interaction.response.send_message(
                f'Уже: {c.get("status")}', ephemeral=True)
            return
        await interaction.response.send_message('Запрос отозван.', ephemeral=True)

    async def _announce_ceremony(
        self, guild, target, actor, old_key, new_key, branch, reason,
        *, promote=True, actor_label='',
    ):
        cfg = get_config() or {}
        ch_id = int(cfg.get('actions_channel_id') or cfg.get('log_channel_id') or 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        text = build_ceremony_text(
            target_mention=target.mention,
            old_key=old_key or '', new_key=new_key or '',
            branch=branch or '',
            actor_label=actor_label or format_actor_label(
                actor.display_name, None),
            reason=reason or '',
            promote=promote,
        )
        text += f'\n<t:{int(datetime.now(timezone.utc).timestamp())}:F>'
        try:
            lv = discord.ui.LayoutView(timeout=None)
            lv.add_item(mirror_container(
                discord.ui.TextDisplay(text),
                accent=GOLD if promote else ACTION_COLORS.get('demote', 0xE67E22),
            ))
            await ch.send(view=lv)
        except Exception as ex:
            _log.error('ceremony: %s\n%s', ex, traceback.format_exc())

    async def _announce_vacation_card(
        self, guild, target, actor, vac, days, reason,
    ):
        cfg = get_config() or {}
        ch_id = int(cfg.get('actions_channel_id') or cfg.get('log_channel_id') or 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        info = get_staff_info(target)
        a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
        text = (
            f'# 🏝 Открытка: отпуск\n'
            f'**{target.display_name}** {target.mention}\n'
            f'{format_role_label(info.get("primary_key") or "", branch=info.get("primary_branch"))}'
            f' · {_emoji_for_branch(info.get("primary_branch") or "")} '
            f'{info.get("branch_label") or "—"}\n'
            f'Срок: **{days}** дн.\n'
            f'Поставил: {format_actor_label(actor.display_name, a_ctx.primary_key)}\n'
            f'{reason or "—"}\n'
            f'<t:{int(datetime.now(timezone.utc).timestamp())}:F>'
        )
        try:
            lv = discord.ui.LayoutView(timeout=None)
            lv.add_item(mirror_container(
                discord.ui.TextDisplay(text), accent=0x1ABC9C))
            await ch.send(view=lv)
        except Exception as ex:
            _log.error('vacation card: %s\n%s', ex, traceback.format_exc())

    async def _dm_removed(self, target, actor, kind, reason, info):
        kind_l = REMOVAL_KINDS.get(kind or '', kind or '')
        body = (
            f'{REMOVE_DM_TITLE}\n'
            + REMOVE_DM_BODY.format(
                role=info.get('role_label') or 'стаффа',
                branch=info.get('branch_label') or '—',
                kind=kind_l,
                actor=actor.mention,
                reason=reason,
            )
        )
        try:
            view = discord.ui.LayoutView(timeout=None)
            view.add_item(discord.ui.Container(
                discord.ui.TextDisplay(body),
                accent_colour=discord.Colour(0xE74C3C),
            ))
            await target.send(view=view)
        except Exception as ex:
            _log.info('remove DM failed: %s', ex)

    async def _log_staff_action(
        self, guild, action, actor, target, role_key, reason,
        *, ok=True, err='', extra='',
    ):
        cfg = get_config() or {}
        ch_id = int(cfg.get('actions_channel_id') or cfg.get('log_channel_id') or 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        color = ACTION_COLORS.get(action, 0x5865F2 if ok else 0xE74C3C)
        if not ok:
            color = 0xE74C3C
        label = ACTION_LABELS.get(action, action)
        re = _emoji_for_role_key(role_key or '')
        text = (
            f'**{"✅" if ok else "❌"} {label}** · {target.mention} · {actor.mention}\n'
            f'{re} `{role_key or "—"}` · {reason}'
            + (f'\n_{extra}_' if extra else '')
            + (f'\n`{err}`' if err else '')
            + f'\n<t:{int(datetime.now(timezone.utc).timestamp())}:F>'
        )
        try:
            lv = discord.ui.LayoutView(timeout=None)
            lv.add_item(discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_colour=discord.Colour(color),
            ))
            await ch.send(view=lv)
        except Exception as ex:
            _log.error('staff log: %s\n%s', ex, traceback.format_exc())


def _hierarchy_note(bot_member, role) -> str:
    if role is None:
        return 'роль не найдена'
    if not bot_member.guild_permissions.manage_roles:
        return 'нет Manage Roles — выдайте право боту'
    if role.managed:
        return 'managed-роль — Discord запрещает выдачу'
    if role >= bot_member.top_role:
        return (
            f'роль бота ниже (bot pos {bot_member.top_role.position} ≤ '
            f'{role.position}) — поднимите роль бота выше «{role.name}»'
        )
    return ''


async def setup(bot):
    await bot.add_cog(StaffManager(bot))
