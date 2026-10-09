# -*- coding: utf-8 -*-
"""/staff — Staff Manager (Components V2)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
from services.staff_manager import (
    apply_staff_change, can_manage_staff, get_allowed_actions,
    resolve_actor, resolve_target, ensure_tables,
)
from services.staff_manager.config import (
    reload_config, is_enabled, last_error, get_config,
)
from services.staff_manager.store import (
    save_menu_state, load_menu_state, new_action_id, list_actions,
)
from services import v2_layouts as V2

_log = get_logger('staff_manager')

ACTION_LABELS = {
    'assign': 'Назначить',
    'promote': 'Повысить',
    'demote': 'Понизить',
    'remove': 'Снять',
    'transfer': 'Перевести',
    'probation': 'Испытательный',
    'vacation': 'Отпуск',
    'history': 'История',
    'request': 'Заявка',
}


def _member_role_ids(member) -> list:
    return [r.id for r in getattr(member, 'roles', []) or []]


def _avatar_url(member) -> str:
    try:
        return str(member.display_avatar.url)
    except Exception:
        return ''


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


def build_panel_view(
    cog: 'StaffManager',
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
    accent: int = 0x5865F2,
) -> discord.ui.LayoutView:
    a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
    t_ctx = resolve_target(target.id, _member_role_ids(target))
    allowed = get_allowed_actions(a_ctx, t_ctx)
    cfg = get_config() or {}

    branch_label = '—'
    role_label = 'участник'
    color = accent
    if t_ctx.primary_branch:
        b = (cfg.get('branches') or {}).get(t_ctx.primary_branch) or {}
        branch_label = b.get('label') or t_ctx.primary_branch
        color = int(b.get('color') or accent)
    if t_ctx.primary_key:
        item = next(
            (x for x in (cfg.get('ladder') or []) if x['key'] == t_ctx.primary_key),
            None)
        role_label = (item or {}).get('name') or t_ctx.primary_key

    head = f'## {target.display_name}\n`{target.id}` · **{role_label}** · {branch_label}'
    if t_ctx.multi_branch:
        head += '\n⚠️ несколько веток'

    view = discord.ui.LayoutView(timeout=None)
    try:
        thumb = discord.ui.Thumbnail(media=_avatar_url(target))
        section = discord.ui.Section(
            discord.ui.TextDisplay(head),
            accessory=thumb,
        )
        container = discord.ui.Container(
            section, accent_colour=discord.Colour(color))
    except Exception:
        container = discord.ui.Container(
            discord.ui.TextDisplay(head),
            accent_colour=discord.Colour(color),
        )
    view.add_item(container)

    actions = [a for a in allowed.get('actions') or [] if a != 'request']
    if actions:
        sel = discord.ui.Select(
            placeholder='Действие',
            options=[
                discord.SelectOption(
                    label=ACTION_LABELS.get(a, a)[:100], value=a)
                for a in actions[:25]
            ],
            custom_id=f'sm:act:{token}',
            min_values=1, max_values=1,
        )

        async def _on_act(interaction: discord.Interaction, select=sel):
            await cog._on_action_select(interaction, token, select.values[0])

        sel.callback = _on_act  # type: ignore
        row = discord.ui.ActionRow()
        row.add_item(sel)
        view.add_item(row)

    roles = allowed.get('roles') or []
    if roles and any(a in actions for a in ('assign', 'promote', 'demote', 'transfer')):
        rsel = discord.ui.Select(
            placeholder='Роль',
            options=[
                discord.SelectOption(
                    label=f'{(r.get("emoji") or "")} {r["name"]}'.strip()[:100],
                    value=r['key'],
                )
                for r in roles[:25]
            ],
            custom_id=f'sm:role:{token}',
            min_values=1, max_values=1,
        )

        async def _on_role(interaction: discord.Interaction, select=rsel):
            await cog._on_role_select(interaction, token, select.values[0])

        rsel.callback = _on_role  # type: ignore
        row2 = discord.ui.ActionRow()
        row2.add_item(rsel)
        view.add_item(row2)

    branches = allowed.get('branches') or []
    if branches and ('transfer' in actions or 'assign' in actions):
        bsel = discord.ui.Select(
            placeholder='Ветка',
            options=[
                discord.SelectOption(
                    label=(b.get('label') or b['key'])[:100], value=b['key'])
                for b in branches[:25]
            ],
            custom_id=f'sm:br:{token}',
            min_values=1, max_values=1,
        )

        async def _on_br(interaction: discord.Interaction, select=bsel):
            await cog._on_branch_select(interaction, token, select.values[0])

        bsel.callback = _on_br  # type: ignore
        row3 = discord.ui.ActionRow()
        row3.add_item(bsel)
        view.add_item(row3)

    row_btn = discord.ui.ActionRow()
    btn_ok = discord.ui.Button(
        label='Ок', style=discord.ButtonStyle.success,
        custom_id=f'sm:ok:{token}')
    btn_no = discord.ui.Button(
        label='Отмена', style=discord.ButtonStyle.secondary,
        custom_id=f'sm:no:{token}')

    async def _ok(interaction: discord.Interaction):
        await interaction.response.send_modal(ReasonModal(cog, token))

    async def _no(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass

    btn_ok.callback = _ok  # type: ignore
    btn_no.callback = _no  # type: ignore
    row_btn.add_item(btn_ok)
    row_btn.add_item(btn_no)

    if allowed.get('can_request') and not roles:
        btn_req = discord.ui.Button(
            label='Заявка', style=discord.ButtonStyle.primary,
            custom_id=f'sm:req:{token}')

        async def _req(interaction: discord.Interaction):
            st = load_menu_state(token) or {}
            payload = st.get('payload') or {}
            payload['action'] = 'request'
            save_menu_state(
                token, st.get('guild_id') or interaction.guild_id,
                st.get('actor_id') or interaction.user.id,
                st.get('target_id') or target.id,
                'confirm', payload)
            await interaction.response.send_modal(ReasonModal(cog, token))

        btn_req.callback = _req  # type: ignore
        row_btn.add_item(btn_req)

    view.add_item(row_btn)
    return view


class StaffManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._started = False

    async def cog_load(self):
        ensure_tables()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._started:
            return
        self._started = True
        await self._boot_config()

    async def _boot_config(self):
        await self.bot.wait_until_ready()
        guild_role_ids = set()
        for g in self.bot.guilds:
            for r in g.roles:
                guild_role_ids.add(r.id)
        ok, err = reload_config(
            guild_role_ids=guild_role_ids if guild_role_ids else None)
        if not ok:
            _log.error('staff_manager DISABLED: %s', err)
        else:
            _log.info('staff_manager: online')

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
        token = new_action_id()[:16]
        save_menu_state(
            token, interaction.guild.id, actor.id, member.id,
            'card', {'action': '', 'role': '', 'branch': ''})
        view = build_panel_view(self, token=token, actor=actor, target=member)
        try:
            self.bot.add_view(view)
        except Exception:
            pass
        await interaction.response.send_message(view=view, ephemeral=True)

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
        view = build_panel_view(self, token=token, actor=actor, target=target)
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
        await interaction.response.defer()

    async def _on_branch_select(self, interaction, token, branch):
        st = load_menu_state(token)
        if not st:
            await interaction.response.send_message('устарело', ephemeral=True)
            return
        payload = st.get('payload') or {}
        payload['branch'] = branch
        save_menu_state(
            token, st['guild_id'], st['actor_id'], st['target_id'],
            'branch', payload)
        await interaction.response.defer()

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
            view = build_panel_view(self, token=token, actor=actor, target=target)
            try:
                await interaction.followup.send(view=view, ephemeral=True)
            except Exception:
                pass
            return

        if action == 'history':
            rows = list_actions(interaction.guild.id, target.id, limit=15)
            if not rows:
                await interaction.followup.send('пусто', ephemeral=True)
                return
            lines = [
                f'`{r.get("created_at","")[:19]}` {r.get("action")} '
                f'{r.get("old_key") or "—"}→{r.get("new_key") or "—"}'
                for r in rows
            ]
            await interaction.followup.send('\n'.join(lines)[:1800], ephemeral=True)
            return

        result = await apply_staff_change(
            guild=interaction.guild,
            actor_member=actor,
            target_member=target,
            action=action,
            new_role_key=role_key,
            new_branch=branch,
            reason=reason,
            source='discord',
        )
        if not result.ok:
            await interaction.followup.send(result.reason or 'отказ', ephemeral=True)
            return

        label = ACTION_LABELS.get(action, action)
        await interaction.followup.send(
            f'✅ {label} · {target.mention}'
            + (f' · `{role_key}`' if role_key else ''),
            ephemeral=True,
        )

        cfg = get_config() or {}
        ch_id = int(cfg.get('actions_channel_id') or cfg.get('log_channel_id') or 0)
        if ch_id:
            ch = interaction.guild.get_channel(ch_id)
            if ch and V2.v2_available():
                color = {
                    'promote': 0xF0CD7A, 'demote': 0xE67E22,
                    'remove': 0xE74C3C, 'assign': 0x2ECC71,
                    'transfer': 0x9B59B6,
                }.get(action, 0x5865F2)
                try:
                    lv = discord.ui.LayoutView(timeout=None)
                    lv.add_item(discord.ui.Container(
                        discord.ui.TextDisplay(
                            f'**{label}** · {target.mention} · {actor.mention}\n'
                            f'{role_key or "—"} · {reason}'
                        ),
                        accent_colour=discord.Colour(color),
                    ))
                    await ch.send(view=lv)
                except Exception as ex:
                    _log.debug('staff log: %s', ex)

        if result.alert_multi:
            _log.warning(
                'staff_manager ALERT multi-branch target=%s actor=%s',
                target.id, actor.id)


async def setup(bot):
    await bot.add_cog(StaffManager(bot))
