# -*- coding: utf-8 -*-
"""Support-бот: /verify — верификация, недопуск, пол (V2 чёрный UI)."""
from __future__ import annotations

import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger('support_verify')

from services import support_bot_config as CFG
from services import support_store as STORE
from services import support_emojis as EMO


def _cfg():
    return CFG.load_config()


def _has_support(member, cfg: dict) -> bool:
    if member is None:
        return False
    perms = getattr(member, 'guild_permissions', None)
    if perms and getattr(perms, 'administrator', False):
        return True
    ids = {CFG.role_id(cfg, 'support_role_id'),
           CFG.role_id(cfg, 'support_lead_role_id')}
    ids.discard(0)
    return any(getattr(r, 'id', None) in ids for r in getattr(member, 'roles', []))


def _is_appeal_reviewer(member, cfg: dict) -> bool:
    if member is None:
        return False
    perms = getattr(member, 'guild_permissions', None)
    if perms and getattr(perms, 'administrator', False):
        return True
    lead = CFG.role_id(cfg, 'support_lead_role_id')
    if lead and any(getattr(r, 'id', None) == lead for r in getattr(member, 'roles', [])):
        return True
    for r in getattr(member, 'roles', []):
        n = (getattr(r, 'name', '') or '').lower()
        if 'administrator' in n or 'owner' in n:
            return True
    return False


def _gender_roles(cfg: dict):
    return CFG.role_id(cfg, 'male_role_id'), CFG.role_id(cfg, 'female_role_id')


def _is_verified(member, cfg: dict) -> bool:
    male, female = _gender_roles(cfg)
    ids = {getattr(r, 'id', None) for r in getattr(member, 'roles', [])}
    return bool((male and male in ids) or (female and female in ids))


def _current_gender(member, cfg: dict) -> Optional[str]:
    male, female = _gender_roles(cfg)
    ids = {getattr(r, 'id', None) for r in getattr(member, 'roles', [])}
    if male and male in ids:
        return 'male'
    if female and female in ids:
        return 'female'
    return None


async def resolve_member(guild: discord.Guild, query: str) -> Optional[discord.Member]:
    q = (query or '').strip()
    if not q:
        return None
    if q.startswith('<@') and q.endswith('>'):
        q = q.strip('<@!>')
    if q.isdigit():
        mid = int(q)
        m = guild.get_member(mid)
        if m:
            return m
        try:
            return await guild.fetch_member(mid)
        except Exception:
            return None
    qn = q.lower().lstrip('@')
    exact, starts, contains = [], [], []
    for m in guild.members:
        names = {
            (m.name or '').lower(),
            (m.display_name or '').lower(),
            (getattr(m, 'global_name', None) or '').lower(),
            (m.nick or '').lower() if m.nick else '',
        }
        names.discard('')
        if qn in names:
            exact.append(m)
        elif any(n.startswith(qn) for n in names):
            starts.append(m)
        elif any(qn in n for n in names):
            contains.append(m)
    for bucket in (exact, starts, contains):
        if len(bucket) == 1:
            return bucket[0]
        if len(bucket) > 1:
            return sorted(bucket, key=lambda x: x.id)[0]
    return None


async def _ensure_role(guild: discord.Guild, cfg: dict, key: str,
                       name: str) -> Optional[discord.Role]:
    rid = CFG.role_id(cfg, key)
    if rid:
        r = guild.get_role(rid)
        if r:
            return r
    for r in guild.roles:
        if (r.name or '').lower() == name.lower():
            cfg[key] = str(r.id)
            CFG.save_config(cfg)
            return r
    if not cfg.get('create_missing'):
        return None
    try:
        r = await guild.create_role(name=name, reason='support-bot: seed')
        cfg[key] = str(r.id)
        CFG.save_config(cfg)
        return r
    except Exception as ex:
        log.warning('create role %s: %s', name, ex)
        return None


async def _ensure_channel(guild: discord.Guild, cfg: dict, key: str,
                          name: str) -> Optional[discord.TextChannel]:
    cid = CFG.role_id(cfg, key)
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            return ch
    needle = name.lstrip('・').lower()
    for ch in guild.text_channels:
        n = (ch.name or '')
        if n == name or n.lstrip('・').lower() == needle:
            cfg[key] = str(ch.id)
            CFG.save_config(cfg)
            return ch
    if not cfg.get('create_missing'):
        return None
    cat_id = CFG.role_id(cfg, 'staff_log_category_id')
    cat = guild.get_channel(cat_id) if cat_id else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_messages=True),
    }
    for rk in ('support_role_id', 'support_lead_role_id'):
        role = guild.get_role(CFG.role_id(cfg, rk))
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)
    try:
        ch = await guild.create_text_channel(
            name,
            category=cat if isinstance(cat, discord.CategoryChannel) else None,
            overwrites=overwrites, reason='support-bot: seed')
        cfg[key] = str(ch.id)
        CFG.save_config(cfg)
        return ch
    except Exception as ex:
        log.warning('create channel %s: %s', name, ex)
        return None


async def ensure_infra(guild: discord.Guild) -> dict:
    cfg = _cfg()
    await _ensure_role(guild, cfg, 'unverify_role_id', 'unverify')
    await _ensure_role(guild, cfg, 'nedopusk_role_id', 'недопуск')
    await _ensure_channel(guild, cfg, 'reviews_channel_id', '・отзывы-support')
    await _ensure_channel(guild, cfg, 'appeals_channel_id', '・апелляции-support')
    return _cfg()


def _embed_fallback(title: str, body: str, footer: str = 'Hakumo · Support'):
    e = discord.Embed(color=0x000000)
    e.description = f'## {title}\n{body}'
    e.set_footer(text=footer)
    return e


def _v2_or_embed(title: str, body: str, footer: str = 'Hakumo · Support'):
    from services.v2_layouts import V2_AVAILABLE, notice_layout_view
    if V2_AVAILABLE:
        v = notice_layout_view(
            title=title, body=body, footer=footer,
            accent=0x000000, brand='HAKUMO')
        if v is not None:
            return {'view': v}
    return {'embed': _embed_fallback(title, body, footer)}


async def _send_ephemeral(interaction: discord.Interaction, title: str, body: str,
                          view: discord.ui.View | None = None):
    kw = {'ephemeral': True, **_v2_or_embed(title, body)}
    # If we need selects/buttons, prefer classic View+embed for reliability
    # with selects; V2 LayoutView+select is used in VerifyPanelView.
    if view is not None and 'view' not in kw:
        kw['view'] = view
    elif view is not None and isinstance(view, VerifyPanelView):
        kw = {'ephemeral': True, 'view': view}
    if interaction.response.is_done():
        await interaction.followup.send(**kw)
    else:
        await interaction.response.send_message(**kw)


# ── Panel view (ephemeral actions) ──────────────────────────────────────

class VerifyPanelView(discord.ui.LayoutView):
    """V2 чёрная панель /verify с селектом действий."""

    def __init__(self, target_id: int, body: str):
        super().__init__(timeout=300)
        from services.v2_layouts import black_container, SeparatorSpacing, V2_AVAILABLE
        from discord import ui as _ui
        if not V2_AVAILABLE:
            raise RuntimeError('V2 unavailable')
        self.target_id = target_id
        self.add_item(black_container(
            _ui.TextDisplay('# 🎯 Support · /verify\n-# HAKUMO'),
            _ui.Separator(spacing=SeparatorSpacing.large),
            _ui.TextDisplay(body[:3500]),
            _ui.Separator(),
            _ui.TextDisplay('-# Hakumo · Support'),
            accent=0x000000,
        ))
        row = _ui.ActionRow()
        row.add_item(ActionSelect(target_id))
        self.add_item(row)


class GenderPanelView(discord.ui.LayoutView):
    def __init__(self, target_id: int, body: str, mode: str):
        super().__init__(timeout=300)
        from services.v2_layouts import black_container, SeparatorSpacing
        from discord import ui as _ui
        self.add_item(black_container(
            _ui.TextDisplay('# Гендерка\n-# HAKUMO'),
            _ui.Separator(spacing=SeparatorSpacing.large),
            _ui.TextDisplay(body[:3500]),
            accent=0x000000,
        ))
        row = _ui.ActionRow()
        row.add_item(GenderSelect(target_id, mode=mode))
        self.add_item(row)


class ActionSelect(discord.ui.Select):
    def __init__(self, target_id: int):
        self.target_id = target_id
        opts = [
            discord.SelectOption(
                label='Верифицировать', value='verify',
                emoji=EMO.emoji_for('s_verify'),
                description='Гендерка + снять unverify'),
            discord.SelectOption(
                label='Выдать недопуск', value='deny',
                emoji=EMO.emoji_for('s_deny'),
                description='Роль недопуск + кик из войса'),
            discord.SelectOption(
                label='Снять недопуск', value='undeny',
                emoji=EMO.emoji_for('s_undeny'),
                description='Снять недопуск → unverify'),
            discord.SelectOption(
                label='Сменить пол', value='gender',
                emoji=EMO.emoji_for('s_gender'),
                description='Мужской ↔ Женский'),
        ]
        super().__init__(placeholder='Выберите действие…', min_values=1,
                         max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        if not _has_support(interaction.user, cfg) or not interaction.guild:
            return await interaction.response.send_message('Нет доступа.', ephemeral=True)
        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                return await interaction.response.send_message(
                    'Участник не найден.', ephemeral=True)
        action = self.values[0]
        if action == 'verify':
            if _is_verified(target, cfg):
                return await interaction.response.send_message(
                    ephemeral=True,
                    **_v2_or_embed(
                        'Уже верифицирован',
                        f'Этот пользователь верифицирован {target.mention}.\n'
                        f'Снова введите `/verify`, чтобы выполнить другое действие.'))
            body = f'Цель: {target.mention}\nВыберите гендерку:'
            try:
                await interaction.response.send_message(
                    view=GenderPanelView(target.id, body, 'verify'), ephemeral=True)
            except Exception:
                v = discord.ui.View(timeout=300)
                v.add_item(GenderSelect(target.id, mode='verify'))
                await interaction.response.send_message(
                    embed=_embed_fallback('Гендерка', body), view=v, ephemeral=True)
            return
        if action == 'deny':
            await interaction.response.defer(ephemeral=True)
            await do_deny(interaction, target, cfg)
            return
        if action == 'undeny':
            await interaction.response.defer(ephemeral=True)
            await do_undeny(interaction, target, cfg)
            return
        if action == 'gender':
            if not _is_verified(target, cfg):
                return await interaction.response.send_message(
                    ephemeral=True,
                    **_v2_or_embed(
                        'Не верифицирован',
                        f'{target.mention} ещё не верифицирован.'))
            body = (
                f'Цель: {target.mention}\n'
                f'Сейчас: **{_current_gender(target, cfg) or "—"}**\n'
                f'Выберите новый пол:')
            try:
                await interaction.response.send_message(
                    view=GenderPanelView(target.id, body, 'swap'), ephemeral=True)
            except Exception:
                v = discord.ui.View(timeout=300)
                v.add_item(GenderSelect(target.id, mode='swap'))
                await interaction.response.send_message(
                    embed=_embed_fallback('Смена пола', body), view=v, ephemeral=True)


class GenderSelect(discord.ui.Select):
    def __init__(self, target_id: int, mode: str = 'verify'):
        self.target_id = target_id
        self.mode = mode
        opts = [
            discord.SelectOption(label='Мужская', value='male',
                                 emoji=EMO.emoji_for('s_male')),
            discord.SelectOption(label='Женская', value='female',
                                 emoji=EMO.emoji_for('s_female')),
        ]
        super().__init__(placeholder='Гендерка…', min_values=1, max_values=1,
                         options=opts)

    async def callback(self, interaction: discord.Interaction):
        cfg = _cfg()
        if not interaction.guild or not _has_support(interaction.user, cfg):
            return await interaction.response.send_message('Нет доступа.', ephemeral=True)
        target = interaction.guild.get_member(self.target_id)
        if target is None:
            try:
                target = await interaction.guild.fetch_member(self.target_id)
            except Exception:
                return await interaction.response.send_message(
                    'Участник не найден.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if self.mode == 'verify':
            await do_verify(interaction, target, cfg, self.values[0])
        else:
            await do_gender_swap(interaction, target, cfg, self.values[0])


# ── Modals ──────────────────────────────────────────────────────────────

class ReviewModal(discord.ui.Modal, title='Отзыв саппорту'):
    def __init__(self, support_id: int, max_chars: int = 140):
        super().__init__()
        self.support_id = support_id
        self.field = discord.ui.TextInput(
            label='Отзыв', style=discord.TextStyle.paragraph,
            max_length=max_chars, min_length=1, required=True,
            placeholder=f'До {max_chars} символов')
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = _cfg()
        text = str(self.field.value or '').strip()[:int(cfg.get('review_max_chars', 140))]
        guild = interaction.client.get_guild(CFG.gid(cfg))
        msg_id = None
        if guild:
            ch = await _ensure_channel(guild, cfg, 'reviews_channel_id', '・отзывы-support')
            if ch:
                body = (
                    f'**От:** {interaction.user.mention} (`{interaction.user.id}`)\n'
                    f'**Саппорт:** <@{self.support_id}>\n\n> {text}')
                kw = _v2_or_embed('⭐ Отзыв', body, 'Hakumo · Support reviews')
                m = await ch.send(**kw)
                msg_id = m.id
        STORE.add_review(
            guild_id=CFG.gid(cfg), user_id=interaction.user.id,
            support_id=self.support_id, text=text, message_id=msg_id)
        await interaction.response.send_message('Спасибо за отзыв!', ephemeral=True)


class AppealModal(discord.ui.Modal, title='Апелляция на недопуск'):
    def __init__(self, support_id: int):
        super().__init__()
        self.support_id = support_id
        self.field = discord.ui.TextInput(
            label='Почему не согласны?', style=discord.TextStyle.paragraph,
            max_length=800, min_length=5, required=True)
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = _cfg()
        reason = str(self.field.value or '').strip()
        appeal = STORE.add_appeal(
            guild_id=CFG.gid(cfg), user_id=interaction.user.id,
            support_id=self.support_id, reason=reason)
        guild = interaction.client.get_guild(CFG.gid(cfg))
        if guild:
            ch = await _ensure_channel(guild, cfg, 'appeals_channel_id', '・апелляции-support')
            if ch:
                body = (
                    f'**Участник:** {interaction.user.mention} (`{interaction.user.id}`)\n'
                    f'**Выдал недопуск:** <@{self.support_id}>\n'
                    f'**ID:** `{appeal["id"]}`\n\n> {reason}')
                v = discord.ui.View(timeout=None)
                v.add_item(AppealApproveButton(appeal['id']))
                v.add_item(AppealRejectButton(appeal['id']))
                # Prefer V2 card + classic buttons via follow-up pattern:
                # send V2 text then buttons — Discord can't mix easily; use embed+view
                m = await ch.send(embed=_embed_fallback('📝 Апелляция · недопуск', body), view=v)
                data = STORE._load(STORE.APPEALS)
                for x in data.get('items') or []:
                    if x.get('id') == appeal['id']:
                        x['message_id'] = str(m.id)
                        STORE._save(STORE.APPEALS, data)
                        break
        await interaction.response.send_message(
            'Апелляция отправлена. Ожидайте решения.', ephemeral=True)


class AppealApproveButton(discord.ui.Button):
    def __init__(self, appeal_id: str):
        super().__init__(label='Одобрить', style=discord.ButtonStyle.success,
                         custom_id=f'sup:appr:{appeal_id}')

    async def callback(self, interaction: discord.Interaction):
        await resolve_appeal(interaction, self.custom_id.split(':')[-1], True)


class AppealRejectButton(discord.ui.Button):
    def __init__(self, appeal_id: str):
        super().__init__(label='Отклонить', style=discord.ButtonStyle.danger,
                         custom_id=f'sup:rej:{appeal_id}')

    async def callback(self, interaction: discord.Interaction):
        await resolve_appeal(interaction, self.custom_id.split(':')[-1], False)


async def resolve_appeal(interaction: discord.Interaction, appeal_id: str, approve: bool):
    cfg = _cfg()
    member = interaction.user
    if not isinstance(member, discord.Member):
        g = interaction.client.get_guild(CFG.gid(cfg))
        member = g.get_member(interaction.user.id) if g else None
    if not member or not _is_appeal_reviewer(member, cfg):
        return await interaction.response.send_message(
            'Только старший саппорт / администратор.', ephemeral=True)
    it = STORE.get_appeal(appeal_id)
    if not it or it.get('status') != 'pending':
        return await interaction.response.send_message(
            'Апелляция уже рассмотрена или не найдена.', ephemeral=True)
    STORE.set_appeal_status(appeal_id, 'approved' if approve else 'rejected',
                            reviewer_id=interaction.user.id)
    guild = interaction.guild or interaction.client.get_guild(CFG.gid(cfg))
    if guild and approve:
        try:
            m = guild.get_member(int(it['user_id'])) or await guild.fetch_member(int(it['user_id']))
            await do_undeny_roles(m, cfg)
        except Exception as ex:
            log.info('appeal undeny: %s', ex)
    try:
        u = await interaction.client.fetch_user(int(it['user_id']))
        text = ('Ваша апелляция **одобрена**. Недопуск снят.'
                if approve else 'Ваша апелляция **не одобрена**.')
        await u.send(**_v2_or_embed('📝 Решение по апелляции', text))
    except Exception as ex:
        log.info('appeal dm: %s', ex)
    await interaction.response.send_message(
        f'Решение: **{"одобрено" if approve else "отклонено"}**.', ephemeral=True)
    try:
        await interaction.message.edit(view=None)
    except Exception:
        pass


# ── Role actions ────────────────────────────────────────────────────────

async def do_verify(interaction, target: discord.Member, cfg: dict, gender: str):
    await interaction.followup.send(
        ephemeral=True, **_v2_or_embed('Обработка…', f'Верифицируем {target.mention}…'))
    male_id, female_id = _gender_roles(cfg)
    male = target.guild.get_role(male_id) if male_id else None
    female = target.guild.get_role(female_id) if female_id else None
    unverify = await _ensure_role(target.guild, cfg, 'unverify_role_id', 'unverify')
    rem, add = [], []
    if gender == 'male' and male:
        add.append(male)
        if female and female in target.roles:
            rem.append(female)
    elif gender == 'female' and female:
        add.append(female)
        if male and male in target.roles:
            rem.append(male)
    if unverify and unverify in target.roles:
        rem.append(unverify)
    try:
        if rem:
            await target.remove_roles(*rem, reason=f'verify by {interaction.user}')
        if add:
            await target.add_roles(*add, reason=f'verify by {interaction.user}')
    except Exception as ex:
        await interaction.followup.send(f'Ошибка ролей: {ex}', ephemeral=True)
        return
    label = 'Мужская' if gender == 'male' else 'Женская'
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed('Пользователь верифицирован',
                       f'{target.mention} · пол: **{label}**\n'
                       f'Саппорт: {interaction.user.mention}'))
    # DM: review CTA
    try:
        body = (
            f'Вас верифицировал {interaction.user.mention}.\n'
            f'Оставьте отзыв саппортику (макс. {cfg.get("review_max_chars", 140)} символов).')
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(
            label='Оставить отзыв', style=discord.ButtonStyle.secondary,
            emoji=EMO.emoji_for('s_review'),
            custom_id=f'sup:review:{interaction.user.id}'))
        await target.send(embed=_embed_fallback('⭐ Оставьте отзыв', body), view=v)
    except Exception as ex:
        log.info('verify dm: %s', ex)


async def do_deny(interaction, target: discord.Member, cfg: dict):
    ned = await _ensure_role(target.guild, cfg, 'nedopusk_role_id', 'недопуск')
    unverify = await _ensure_role(target.guild, cfg, 'unverify_role_id', 'unverify')
    male_id, female_id = _gender_roles(cfg)
    rem = []
    for rid in (male_id, female_id):
        r = target.guild.get_role(rid) if rid else None
        if r and r in target.roles:
            rem.append(r)
    try:
        if rem:
            await target.remove_roles(*rem, reason='недопуск')
        if unverify and unverify in target.roles:
            await target.remove_roles(unverify, reason='недопуск')
        if ned:
            await target.add_roles(ned, reason=f'недопуск by {interaction.user}')
        if target.voice and target.voice.channel:
            try:
                await target.move_to(None, reason='недопуск')
            except Exception:
                pass
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed('Недопуск выдан',
                       f'{target.mention} ← {interaction.user.mention}'))
    try:
        body = (
            f'Вам выдал недопуск {interaction.user.mention}.\n'
            f'Если не согласны — отправьте апелляцию.')
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(
            label='Апелляция', style=discord.ButtonStyle.danger,
            emoji=EMO.emoji_for('appeal'),
            custom_id=f'sup:appealbtn:{interaction.user.id}'))
        await target.send(embed=_embed_fallback('🚫 Недопуск', body), view=v)
    except Exception as ex:
        log.info('deny dm: %s', ex)


async def do_undeny_roles(member: discord.Member, cfg: dict):
    ned = await _ensure_role(member.guild, cfg, 'nedopusk_role_id', 'недопуск')
    unverify = await _ensure_role(member.guild, cfg, 'unverify_role_id', 'unverify')
    if ned and ned in member.roles:
        await member.remove_roles(ned, reason='снять недопуск')
    if unverify and unverify not in member.roles:
        await member.add_roles(unverify, reason='снять недопуск → unverify')


async def do_undeny(interaction, target: discord.Member, cfg: dict):
    try:
        await do_undeny_roles(target, cfg)
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed('Недопуск снят',
                       f'{target.mention}: недопуск снят, возвращён **unverify**.'))


async def do_gender_swap(interaction, target: discord.Member, cfg: dict, gender: str):
    male_id, female_id = _gender_roles(cfg)
    male = target.guild.get_role(male_id) if male_id else None
    female = target.guild.get_role(female_id) if female_id else None
    try:
        if gender == 'male':
            if female and female in target.roles:
                await target.remove_roles(female, reason='gender')
            if male and male not in target.roles:
                await target.add_roles(male, reason='gender')
        else:
            if male and male in target.roles:
                await target.remove_roles(male, reason='gender')
            if female and female not in target.roles:
                await target.add_roles(female, reason='gender')
    except Exception as ex:
        await interaction.followup.send(f'Ошибка: {ex}', ephemeral=True)
        return
    await interaction.followup.send(
        ephemeral=True,
        **_v2_or_embed(
            'Пол изменён',
            f'{target.mention} → **{"Мужская" if gender == "male" else "Женская"}**'))


# ── Cog ─────────────────────────────────────────────────────────────────

class SupportVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name='verify',
        description='Панель саппорта: верификация / недопуск / пол')
    @app_commands.describe(пользователь='ID, ник или упоминание')
    async def verify_cmd(self, interaction: discord.Interaction, пользователь: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                'Только на сервере.', ephemeral=True)
        cfg = _cfg()
        if not _has_support(interaction.user, cfg):
            return await interaction.response.send_message(
                'Нужна роль Support.', ephemeral=True)
        target = await resolve_member(interaction.guild, пользователь)
        if target is None:
            return await interaction.response.send_message(
                f'Не нашёл «{пользователь}».', ephemeral=True)
        if target.bot:
            return await interaction.response.send_message('Нельзя на боте.', ephemeral=True)
        bits = []
        if _is_verified(target, cfg):
            bits.append(f'верифицирован ({_current_gender(target, cfg)})')
        ned = CFG.role_id(cfg, 'nedopusk_role_id')
        if ned and any(r.id == ned for r in target.roles):
            bits.append('недопуск')
        st = ', '.join(bits) if bits else 'без статуса'
        body = (
            f'**Цель:** {target.mention} (`{target.id}`)\n'
            f'**Ник:** `{target.display_name}`\n'
            f'**Статус:** {st}\n\nВыберите действие:')
        try:
            await interaction.response.send_message(
                view=VerifyPanelView(target.id, body), ephemeral=True)
        except Exception as ex:
            log.warning('V2 panel fail, fallback: %s', ex)
            v = discord.ui.View(timeout=300)
            v.add_item(ActionSelect(target.id))
            await interaction.response.send_message(
                embed=_embed_fallback('🎯 Support · /verify', body),
                view=v, ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        if interaction.response.is_done():
            return
        cid = str((interaction.data or {}).get('custom_id') or '')
        # Only handle persistent DM / appeal buttons
        m = re.match(r'^sup:review:(\d+)$', cid)
        if m:
            cfg = _cfg()
            return await interaction.response.send_modal(
                ReviewModal(int(m.group(1)), int(cfg.get('review_max_chars', 140))))
        m = re.match(r'^sup:appealbtn:(\d+)$', cid)
        if m:
            return await interaction.response.send_modal(AppealModal(int(m.group(1))))
        m = re.match(r'^sup:appr:([0-9a-f]+)$', cid)
        if m:
            return await resolve_appeal(interaction, m.group(1), True)
        m = re.match(r'^sup:rej:([0-9a-f]+)$', cid)
        if m:
            return await resolve_appeal(interaction, m.group(1), False)


async def setup(bot):
    await bot.add_cog(SupportVerify(bot))
