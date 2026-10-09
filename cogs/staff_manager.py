# -*- coding: utf-8 -*-
"""/staff · /staff_diagnose · /staff_selftest — Staff Manager (Components V2)."""
from __future__ import annotations

import traceback
from datetime import datetime, timezone

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

_log = get_logger('staff_manager')

ACTION_LABELS = {
    'assign': 'Назначить',
    'promote': 'Повысить',
    'demote': 'Понизить',
    'remove': 'Снять с должности',
    'transfer': 'Перевести',
    'probation': 'Испытательный',
    'vacation': 'Отпуск',
    'history': 'История',
    'request': 'Заявка',
    'self_leave': 'Уйти по собственному',
}

REMOVAL_KINDS = {
    'own': 'По собственному желанию',
    'inactive': 'Неактивность',
    'violation': 'Нарушение',
    'probation': 'По итогам испытательного',
    'other': 'Другое',
}

ACTION_COLORS = {
    'promote': 0xF0CD7A,
    'demote': 0xE67E22,
    'remove': 0xE74C3C,
    'assign': 0x2ECC71,
    'transfer': 0x9B59B6,
    'self_leave': 0xE74C3C,
}


def _member_role_ids(member) -> list:
    return [r.id for r in getattr(member, 'roles', []) or []]


def _avatar_url(member) -> str:
    try:
        return str(member.display_avatar.url)
    except Exception:
        return ''


def _is_staff_admin_or_owner(member: discord.Member) -> bool:
    cfg = get_config() or {}
    if int(member.id) in set(int(x) for x in (cfg.get('owner_ids') or [])):
        return True
    sa = int(cfg.get('staff_admin_role_id') or 0)
    return bool(sa and sa in _member_role_ids(member))


def _emoji_for_role_key(key: str) -> str:
    return role_emoji(key) or '•'


def _emoji_for_branch(key: str) -> str:
    return branch_emoji(key) or '•'


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


def build_panel_view(
    cog: 'StaffManager',
    *,
    token: str,
    actor: discord.Member,
    target: discord.Member,
    accent: int = 0x5865F2,
    step_hint: str = '',
) -> discord.ui.LayoutView:
    a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
    t_ctx = resolve_target(target.id, _member_role_ids(target))
    info = get_staff_info(target)
    allowed = get_allowed_actions(a_ctx, t_ctx)
    cfg = get_config() or {}
    st = load_menu_state(token) or {}
    payload = st.get('payload') or {}

    branch_label = info.get('branch_label') or '—'
    role_label = info.get('role_label') or 'участник'
    re = info.get('role_emoji') or ''
    be = info.get('branch_emoji') or ''
    color = accent
    if t_ctx.primary_branch:
        b = (cfg.get('branches') or {}).get(t_ctx.primary_branch) or {}
        color = int(b.get('color') or accent)

    head = (
        f'## {re} {target.display_name}\n'
        f'`{target.id}` · **{re} {role_label}** · {be} {branch_label}'
    )
    if info.get('on_vacation'):
        head += '\n🏖 в отпуске'
    if t_ctx.multi_branch:
        head += '\n⚠️ несколько веток'
    if step_hint:
        head = f'{step_hint}\n{head}'
    sel_act = payload.get('action') or ''
    sel_role = payload.get('role') or ''
    sel_branch = payload.get('branch') or ''
    if sel_act or sel_role or sel_branch:
        head += (
            f'\n\nВыбрано: **{ACTION_LABELS.get(sel_act, sel_act) or "—"}**'
            f' · `{sel_role or "—"}` · `{sel_branch or "—"}`'
        )

    view = discord.ui.LayoutView(timeout=None)
    try:
        thumb = discord.ui.Thumbnail(media=_avatar_url(target))
        section = discord.ui.Section(
            discord.ui.TextDisplay(head),
            accessory=thumb,
        )
        container = discord.ui.Container(
            section,
            discord.ui.Separator(),
            accent_colour=discord.Colour(color),
        )
    except Exception:
        container = discord.ui.Container(
            discord.ui.TextDisplay(head),
            accent_colour=discord.Colour(color),
        )
    view.add_item(container)

    actions = [a for a in allowed.get('actions') or []
               if a not in ('request',)]
    if actions:
        sel = discord.ui.Select(
            placeholder='Шаг 1 · Действие',
            options=[
                discord.SelectOption(
                    label=ACTION_LABELS.get(a, a)[:100],
                    value=a,
                    emoji='✅' if a == sel_act else None,
                    description={
                        'remove': 'Снять все стафф-роли',
                        'transfer': 'Нужно согласие человека',
                        'assign': 'Первое назначение в ветку',
                    }.get(a),
                )
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
            placeholder='Шаг 2 · Роль',
            options=[
                discord.SelectOption(
                    label=f'{r["name"]}'[:100],
                    value=r['key'],
                    emoji=(r.get('emoji') or None),
                    description=f'ранг {r.get("rank")}',
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
    need_branch = (
        ('transfer' in actions)
        or ('assign' in actions and not t_ctx.primary_branch)
        or (sel_act in ('transfer', 'assign'))
    )
    if branches and need_branch:
        bsel = discord.ui.Select(
            placeholder='Шаг 2 · Ветка',
            options=[
                discord.SelectOption(
                    label=(b.get('label') or b['key'])[:100],
                    value=b['key'],
                    emoji=(b.get('emoji') or None),
                )
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

    if sel_act == 'remove':
        ksel = discord.ui.Select(
            placeholder='Тип снятия',
            options=[
                discord.SelectOption(label=v, value=k)
                for k, v in REMOVAL_KINDS.items()
            ],
            custom_id=f'sm:rk:{token}',
            min_values=1, max_values=1,
        )

        async def _on_rk(interaction: discord.Interaction, select=ksel):
            st2 = load_menu_state(token)
            if not st2:
                await interaction.response.send_message('устарело', ephemeral=True)
                return
            payload2 = st2.get('payload') or {}
            payload2['removal_kind'] = select.values[0]
            save_menu_state(
                token, st2['guild_id'], st2['actor_id'], st2['target_id'],
                'removal_kind', payload2)
            await interaction.response.defer()

        ksel.callback = _on_rk  # type: ignore
        rowk = discord.ui.ActionRow()
        rowk.add_item(ksel)
        view.add_item(rowk)

    row_btn = discord.ui.ActionRow()
    btn_ok = discord.ui.Button(
        label='Подтвердить', style=discord.ButtonStyle.success,
        emoji='✅', custom_id=f'sm:ok:{token}')
    btn_no = discord.ui.Button(
        label='Отмена', style=discord.ButtonStyle.danger,
        emoji='✖️', custom_id=f'sm:no:{token}')

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

    # отозвать pending согласие на эту цель
    pend = pending_consent_for(actor.guild.id, target.id) if actor.guild else None
    if pend and int(pend.get('initiator_id') or 0) == actor.id:
        btn_cancel = discord.ui.Button(
            label='Отозвать запрос', style=discord.ButtonStyle.secondary,
            emoji='↩️', custom_id=f'sm:cx:{pend["id"]}')

        async def _cx(interaction: discord.Interaction, cid=pend['id']):
            await cog._consent_cancel(interaction, cid)

        btn_cancel.callback = _cx  # type: ignore
        row_btn.add_item(btn_cancel)

    if allowed.get('can_request') and not roles:
        btn_req = discord.ui.Button(
            label='Заявка', style=discord.ButtonStyle.primary,
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

    view.add_item(row_btn)
    return view


class ConsentAcceptButton(discord.ui.Button):
    def __init__(self, cog: 'StaffManager', consent_id: str):
        super().__init__(
            label='Принять', style=discord.ButtonStyle.success,
            emoji='✅', custom_id=f'sm:cya:{consent_id}')
        self.cog = cog
        self.consent_id = consent_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog._consent_accept(interaction, self.consent_id)


class ConsentDeclineButton(discord.ui.Button):
    def __init__(self, cog: 'StaffManager', consent_id: str):
        super().__init__(
            label='Отказаться', style=discord.ButtonStyle.danger,
            emoji='✖️', custom_id=f'sm:cno:{consent_id}')
        self.cog = cog
        self.consent_id = consent_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            DeclineReasonModal(self.cog, self.consent_id))


class ConsentPersistentView(discord.ui.LayoutView):
    """Persistent V2 view для DM/fallback согласия."""

    def __init__(self, cog: 'StaffManager', consent_id: str, body: str,
                 color: int = 0x9B59B6):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(body),
            accent_colour=discord.Colour(color),
        ))
        row = discord.ui.ActionRow()
        row.add_item(ConsentAcceptButton(cog, consent_id))
        row.add_item(ConsentDeclineButton(cog, consent_id))
        self.add_item(row)


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

    async def _discover_emojis(self):
        cfg = get_config() or {}
        if not cfg:
            return
        for g in self.bot.guilds:
            for item in cfg.get('ladder') or []:
                key = item['key']
                cached = get_emoji_cache(g.id, 'role', key)
                if cached:
                    continue
                emoji = await self._find_emoji(g, key, item.get('emoji') or '')
                save_emoji_cache(g.id, 'role', key, emoji, 'boot')
                _log.info('emoji role.%s = %s', key, emoji)
            for bkey in (cfg.get('branches') or {}):
                cached = get_emoji_cache(g.id, 'branch', bkey)
                if cached:
                    continue
                emoji = await self._find_emoji(
                    g, bkey, (cfg.get('branch_emojis') or {}).get(bkey) or '')
                save_emoji_cache(g.id, 'branch', bkey, emoji, 'boot')

    async def _find_emoji(self, guild, name: str, fallback: str) -> str:
        # 1) role display_icon / unicode — через конфиг roles
        idx = get_index() or {}
        by_role = idx.get('by_role') or {}
        for rid, info in by_role.items():
            if info.get('key') == name:
                role = guild.get_role(int(rid))
                if role is not None:
                    ue = getattr(role, 'unicode_emoji', None)
                    if ue:
                        return str(ue)
        # 2) guild emoji по имени
        needle = name.lower().replace(' ', '')
        for em in guild.emojis:
            if needle in (em.name or '').lower():
                return str(em)
        return fallback or '•'

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

    @app_commands.command(
        name='staff_diagnose',
        description='Диагностика Staff Manager (роли / иерархия)')
    async def staff_diagnose(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('только сервер', ephemeral=True)
            return
        if not _is_staff_admin_or_owner(interaction.user):
            await interaction.response.send_message('нет доступа', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        me = guild.me
        cfg = get_config() or {}
        lines = [
            f'## Staff diagnose',
            f'discord.py `{discord.__version__}`',
            f'бот top: **{me.top_role.name}** pos `{me.top_role.position}`',
            f'Manage Roles: `{"✅" if me.guild_permissions.manage_roles else "❌ НЕТ — выдайте право"}`',
            f'intents.members: `{"✅" if self.bot.intents.members else "❌ ВКЛЮЧИТЕ Privileged Intent"}`',
            f'конфиг: `{"✅" if is_enabled() else "❌ " + (last_error() or "")}`',
            '',
        ]
        # channels
        for label, kid in (
            ('log', cfg.get('log_channel_id')),
            ('actions', cfg.get('actions_channel_id')),
            ('consent_fallback', cfg.get('consent_fallback_channel_id')),
        ):
            kid = int(kid or 0)
            if not kid:
                lines.append(f'канал {label}: `не задан`')
                continue
            ch = guild.get_channel(kid)
            lines.append(
                f'канал {label}: '
                + ('✅ ' + getattr(ch, 'mention', str(kid)) if ch else
                   f'❌ {kid} не найден / нет доступа')
            )
        lines.append('')
        lines.append('### Роли лестницы и entry')

        seen = set()
        for bkey, b in (cfg.get('branches') or {}).items():
            be = _emoji_for_branch(bkey)
            lines.append(f'\n**{be} {b.get("label") or bkey}**')
            entry = int(b.get('entry_role_id') or 0)
            for label, rid in [('entry', entry)] + [
                (k, int(v or 0)) for k, v in (b.get('roles') or {}).items()
            ]:
                if rid in seen and label != 'entry':
                    # shared — кратко
                    role = guild.get_role(rid)
                    can = '✅' if role and not _hierarchy_note(me, role) else '❌'
                    note = _hierarchy_note(me, role) if role else 'нет на сервере'
                    lines.append(
                        f'· `{label}` shared `{rid}` {can} {note or ""}')
                    continue
                seen.add(rid)
                role = guild.get_role(rid)
                if role is None:
                    lines.append(
                        f'· ❌ `{label}` id `{rid}` — **не найдена**. '
                        f'Обновите конфиг.')
                    continue
                note = _hierarchy_note(me, role)
                ok = '✅' if not note else '❌'
                cnt = len(role.members) if self.bot.intents.members else '?'
                lines.append(
                    f'· {ok} `{label}` **{role.name}** id `{rid}` '
                    f'pos `{role.position}` managed=`{role.managed}` '
                    f'members=`{cnt}`'
                    + (f'\n  → {note}' if note else '')
                )

        # chunk send
        text = '\n'.join(lines)
        view = discord.ui.LayoutView(timeout=120)
        # Discord text display ~4000; chunk
        chunk = text[:3800]
        view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(chunk),
            accent_colour=discord.Colour(0x5865F2),
        ))
        await interaction.followup.send(view=view, ephemeral=True)
        if len(text) > 3800:
            view2 = discord.ui.LayoutView(timeout=120)
            view2.add_item(discord.ui.Container(
                discord.ui.TextDisplay(text[3800:7600]),
                accent_colour=discord.Colour(0x5865F2),
            ))
            await interaction.followup.send(view=view2, ephemeral=True)

    @app_commands.command(
        name='staff_selftest',
        description='Самотест Staff Manager на себе')
    @app_commands.describe(mode='dry-run (по умолчанию) или live')
    @app_commands.choices(mode=[
        app_commands.Choice(name='dry-run', value='dry'),
        app_commands.Choice(name='live', value='live'),
    ])
    async def staff_selftest(
        self, interaction: discord.Interaction,
        mode: app_commands.Choice[str] | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('только сервер', ephemeral=True)
            return
        if not _is_staff_admin_or_owner(interaction.user):
            await interaction.response.send_message('нет доступа', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        mode_v = (mode.value if mode else 'dry')
        actor = interaction.user
        a_ctx = resolve_actor(actor.id, _member_role_ids(actor))
        # dry: ACL table against fictional targets
        checks = []
        cfg = get_config() or {}
        branches = list((cfg.get('branches') or {}).keys())
        b0 = branches[0] if branches else ''
        fake = resolve_target(999001, [])
        for act in ('assign', 'promote', 'demote', 'remove', 'transfer', 'history'):
            ok, why = can_manage_staff(
                a_ctx, fake, act,
                new_role_key='master' if act != 'remove' else None,
                new_branch=b0 if act in ('assign', 'transfer') else None,
            )
            checks.append(
                f'{"✅" if ok else "❌"} `{act}` → '
                f'{"разрешено" if ok else "отказ"} · {why or "—"}'
            )
        allowed = get_allowed_actions(a_ctx, fake)
        checks.append(
            f'📋 меню actions: `{", ".join(allowed.get("actions") or []) or "—"}`'
        )
        checks.append(
            f'📋 меню roles: `'
            f'{", ".join(r["key"] for r in allowed.get("roles") or []) or "—"}`'
        )

        live_lines = []
        if mode_v == 'live':
            test_rid = int(cfg.get('selftest_role_id') or 0)
            if not test_rid:
                live_lines.append('❌ SELFTEST_ROLE_ID не задан в конфиге')
            else:
                role = interaction.guild.get_role(test_rid)
                if role is None:
                    live_lines.append(f'❌ тестовая роль {test_rid} не найдена')
                else:
                    # НЕ трогаем настоящие стафф-роли: прямой add/remove test role
                    # через тот же verify-паттерн, не через assign ladder
                    had = test_rid in _member_role_ids(actor)
                    try:
                        if not had:
                            await actor.add_roles(role, reason='staff_selftest')
                        fresh = await interaction.guild.fetch_member(actor.id)
                        have = test_rid in {r.id for r in fresh.roles}
                        live_lines.append(
                            f'{"✅" if have else "❌"} роль `{role.name}` '
                            f'после add: {"есть" if have else "нет"}')
                        if have:
                            await fresh.remove_roles(role, reason='staff_selftest')
                            fresh2 = await interaction.guild.fetch_member(actor.id)
                            gone = test_rid not in {r.id for r in fresh2.roles}
                            live_lines.append(
                                f'{"✅" if gone else "❌"} после remove: '
                                f'{"снята" if gone else "всё ещё есть"}')
                        if had:
                            # вернуть если была
                            await actor.add_roles(role, reason='staff_selftest restore')
                            live_lines.append('↩️ исходная тестовая роль восстановлена')
                    except Exception as ex:
                        live_lines.append(f'❌ live: {ex}')
                        _log.error('selftest live: %s\n%s', ex, traceback.format_exc())

            # consent path dry on SELFTEST_USER_ID
            su = int(cfg.get('selftest_user_id') or 0)
            if su:
                live_lines.append(
                    f'ℹ️ SELFTEST_USER_ID={su}: согласие проверяйте вручную '
                    f'через /staff → Перевести')
            else:
                live_lines.append('ℹ️ SELFTEST_USER_ID не задан — skip consent live')

        body = '## `/staff_selftest` · ' + (
            'live' if mode_v == 'live' else 'dry-run') + '\n\n'
        body += '### ACL\n' + '\n'.join(checks)
        if live_lines:
            body += '\n\n### Live\n' + '\n'.join(live_lines)
        view = discord.ui.LayoutView(timeout=120)
        view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(body[:3900]),
            accent_colour=discord.Colour(
                0x2ECC71 if '❌' not in body else 0xE74C3C),
        ))
        await interaction.followup.send(view=view, ephemeral=True)

    # ── menu callbacks ─────────────────────────────────────────────────

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
        view = build_panel_view(
            self, token=token, actor=actor, target=target,
            step_hint='Шаг 1 из 3 · Действие')
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
            rows = list_actions(interaction.guild.id, target.id, limit=15)
            if not rows:
                await interaction.followup.send('пусто', ephemeral=True)
                return
            lines = [
                f'`{r.get("created_at","")[:19]}` {r.get("action")} '
                f'{r.get("old_key") or "—"}→{r.get("new_key") or "—"} '
                f'{"✅" if r.get("ok") else "❌"}'
                for r in rows
            ]
            await interaction.followup.send('\n'.join(lines)[:1800], ephemeral=True)
            return

        if action == 'remove' and not removal_kind:
            await interaction.followup.send(
                'Выберите тип снятия в меню', ephemeral=True)
            return

        # consent gate
        if requires_consent(action):
            await self._start_consent(
                interaction, actor, target, action, role_key, branch, reason)
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
        await interaction.followup.send(
            f'✅ {label} · {target.mention}'
            + (f' · `{info.get("role_label") or role_key or "—"}`' )
            + (f' · {info.get("branch_label") or ""}'),
            ephemeral=True,
        )
        await self._log_staff_action(
            interaction.guild, action, actor, target, role_key, reason, ok=True)
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

    async def _dm_removed(self, target, actor, kind, reason, info):
        kind_l = REMOVAL_KINDS.get(kind or '', kind or '')
        body = (
            f'## Снятие с должности\n'
            f'Вы сняты с **{info.get("role_label") or "стаффа"}** '
            f'в ветке **{info.get("branch_label") or "—"}**.\n'
            f'Тип: {kind_l}\n'
            f'Кем: {actor.mention}\n'
            f'Причина: {reason}'
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
