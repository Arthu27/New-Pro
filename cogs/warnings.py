# -*- coding: utf-8 -*-
"""Warnings Cog — единая роль warn + счётчик в SQLite.

Старые уровни warn_1 / warn_2 / warn_3 удалены.
Счётчик = число active-записей в таблице warns.
Роль warn (WARN_ROLE_ID) выдаётся только обычным участникам;
стаффу — никогда (только запись в БД).
"""

from logger import get_logger

_log = get_logger('warnings')

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import os
import json
import io

from cogs.embed_utils import mod_dm_embed, DIVIDER
from logger import get_logger

log = get_logger('warnings')


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ ДОСЬЕ (!pw) + карточка в стиле ticket-panel
# ═══════════════════════════════════════════════════════════════════
try:
    from cogs import _card_style as CS
    from cogs._menu_bg import load_menu_bg
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False


def _load_base_bg(w, h):
    try:
        from cogs._menu_bg import _load_base_bg as _lb
        return _lb(w, h)
    except Exception:
        img = Image.new('RGB', (w, h), (18, 18, 20))
        return img


def generate_pw_card(display_name, user_id, avatar_url, warns, cases, notes,
                     score, score_text, member=None):
    """Сгенерировать карточку-досье в стиле ticket-panel."""
    W, H = 1200, 600
    try:
        bg = load_menu_bg(W, H, 'teal')
        bg = bg.convert('RGB')
    except Exception:
        bg = _load_base_bg(W, H).convert('RGB')
    d = ImageDraw.Draw(bg, 'RGBA')

    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rounded_rectangle((30, 30, W - 30, H - 30), radius=28, fill=(10, 10, 14, 190))
    bg = Image.alpha_composite(bg.convert('RGBA'), ov).convert('RGB')
    d = ImageDraw.Draw(bg, 'RGBA')

    try:
        f_title = CS.font(True, 52)
    except Exception:
        f_title = ImageFont.load_default() if _PIL_OK else None
    try:
        f_big = CS.font(True, 44)
        f_mid = CS.font(True, 28)
        f_txt = CS.font(False, 24)
        f_small = CS.font(False, 18)
    except Exception:
        f_big = f_mid = f_txt = f_small = f_title

    d.text((70, 55), 'ДОСЬЕ ПОЛЬЗОВАТЕЛЯ', font=f_title, fill=(222, 28, 42, 255))
    d.line([(70, 120), (W - 70, 120)], fill=(222, 28, 42, 200), width=3)

    d.text((70, 145), display_name or 'Неизвестно', font=f_big, fill=(255, 255, 255, 255))
    d.text((70, 200), f'ID: {user_id}', font=f_mid, fill=(205, 205, 208, 255))

    x1 = 70
    y = 265
    d.text((x1, y), 'ПРЕДУПРЕЖДЕНИЯ', font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f'{warns}', font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), 'МЬЮТЫ / НАКАЗАНИЯ', font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f'{cases}', font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), 'ЗАМЕТКИ', font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f'{notes}', font=f_big, fill=(255, 255, 255, 255))

    x2 = W // 2 + 60
    d.text((x2, 265), 'ОЦЕНКА', font=f_txt, fill=(222, 28, 42, 255))
    score_color = (
        (46, 204, 113, 255) if score >= 60
        else (243, 156, 18, 255) if score >= 30
        else (231, 76, 60, 255))
    d.text((x2, 305), f'{score}/100',
           font=CS.font(True, 72) if _PIL_OK else f_big, fill=score_color)

    bar_w, bar_h = 480, 22
    bx, by = x2, 400
    d.rounded_rectangle((bx, by, bx + bar_w, by + bar_h), radius=11, fill=(60, 60, 66, 255))
    fill_w = int(bar_w * max(0, min(100, score)) / 100)
    if fill_w > 0:
        d.rounded_rectangle((bx, by, bx + fill_w, by + bar_h),
                            radius=11, fill=score_color)
    d.text((x2, 435), score_text, font=f_mid, fill=(255, 255, 255, 255))
    d.text((70, H - 70), 'Hakumo Модерация • Досье', font=f_small, fill=(150, 150, 155, 255))

    buf = io.BytesIO()
    bg.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


def _compute_score(warns, cases):
    score = 100
    score -= warns * 12
    for c in cases:
        act = str(c.get('action', '')).lower()
        if act == 'ban':
            score -= 25
        elif act in ('timeout', 'mute_chat', 'vmute', 'kick'):
            score -= 18
        elif act == 'warn':
            score -= 12
    return max(0, min(100, score))


def _score_text(score):
    if score >= 80:
        return 'Хорошо'
    if score >= 50:
        return 'Удовлетворительно'
    if score >= 25:
        return 'Плохо'
    return 'Очень плохо'


def load_warn_config(guild_id):
    """Конфиг авто-наказаний по числу варнов (панель → пороги)."""
    f = f'data/warn_config_{guild_id}.json'
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    return {'steps': []}


def duration_to_minutes(duration, unit):
    if unit == 'hour':
        return duration * 60
    if unit == 'day':
        return duration * 1440
    return duration


def _target_branch(member) -> str | None:
    """Первая ветка стаффа-цели (для записи в БД)."""
    try:
        from services.warn_acl import branches_of
        br = branches_of(member)
        return sorted(br)[0] if br else None
    except Exception:
        return None


def build_warn_embed(member, *, active_count=None, history=None, branch=None):
    """Красивый embed для /modpanel: аватар, ник, ID, варны, история."""
    from services import warn_store as WS
    from services.warn_config import format_branches
    from services.warn_acl import branches_of, _is_staff_target

    guild = getattr(member, 'guild', None)
    if active_count is None:
        active_count = WS.count_active(guild.id, member.id) if guild else 0
    if history is None and guild is not None:
        history = WS.list_warns(guild.id, member.id, limit=5)

    is_staff = False
    try:
        is_staff = bool(_is_staff_target(guild, member))
    except Exception:
        is_staff = False

    if branch is None and is_staff:
        try:
            branch = format_branches(branches_of(member))
        except Exception:
            branch = None

    e = discord.Embed(color=0x2B2D31, timestamp=datetime.now(timezone.utc))
    title = 'Панель варна · стафф' if is_staff else 'Панель модерации'
    e.title = title
    lines = [
        f'**{getattr(member, "display_name", member)}**',
        f'`{member.id}`',
        f'Активных варнов: **{active_count}**',
    ]
    if is_staff and branch:
        lines.append(f'Ветка: **{branch}**')
    if history:
        lines.append('')
        lines.append('**Последние варны**')
        for w in history[:5]:
            ts = str(w.get('created_at') or w.get('timestamp') or '')[:16]
            mid = w.get('moderator_id') or w.get('mod_id') or '?'
            reason = (w.get('reason') or '—')[:80]
            mark = '' if w.get('active', 1) else ' · снят'
            lines.append(
                f'#{w.get("id")} · <@{mid}> · {reason}\n'
                f'-# {ts}{mark}')
    else:
        lines.append('')
        lines.append('_Активных записей нет._')
    e.description = '\n'.join(lines)
    try:
        e.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass
    if guild is not None:
        e.set_footer(text=guild.name)
    return e


async def _log_warn_to_channel(guild, user, moderator, reason, warn_id, total,
                               *, branch=None, is_staff=False,
                               punishment_result=None):
    """Лог варна в канал наказаний."""
    try:
        from cogs.logs import send_action_log
        extra = f'Варн #{warn_id} · всего {total}'
        if is_staff:
            extra += f'\nЦель: стафф'
        if branch:
            extra += f'\nВетка: {branch}'
        if punishment_result:
            extra += f'\nАвто-наказание: {punishment_result}'
        await send_action_log(
            guild, 'warn', user, moderator,
            reason=reason or 'Не указана', extra=extra)
    except Exception as _ex:
        _log.debug('_log_warn_to_channel: %s', _ex)


async def _log_punish_to_channel(guild, user, punishment_result, total):
    if not punishment_result:
        return
    try:
        from cogs.logs import send_action_log
        await send_action_log(
            guild, 'warn', user, None,
            extra=f'Авто-наказание: {punishment_result}\nВарнов всего: {total}')
    except Exception as _ex:
        _log.debug('_log_punish_to_channel: %s', _ex)


class warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._board_loop_started = False
        try:
            from services import warn_store as WS
            WS.ensure_table()
        except Exception as e:
            log.warning('warn_store init: %s', e)

    # ── совместимость: список активных варнов (как раньше) ──────────
    def _get_warns(self, guild_id: int, user_id: int) -> list:
        """Активные варны пользователя (новые сверху → переворачиваем
        в хронологический порядок для совместимости со старым кодом)."""
        try:
            from services import warn_store as WS
            rows = WS.list_warns(guild_id, user_id, active_only=True)
            return list(reversed(rows))
        except Exception as e:
            log.debug('_get_warns: %s', e)
            return []

    def _active_count(self, guild_id: int, user_id: int) -> int:
        try:
            from services import warn_store as WS
            return WS.count_active(guild_id, user_id)
        except Exception:
            return len(self._get_warns(guild_id, user_id))

    async def send_dm(self, user, embed):
        try:
            await user.send(embed=embed)
        except Exception as _ex:
            _log.debug('send_dm: %s', _ex)

    async def apply_warn_punishment(self, guild, member, warn_count):
        """Авто-наказание по порогам (warn_config) — без ролей warn_N."""
        cfg = load_warn_config(str(guild.id))
        steps = cfg.get('steps') or cfg.get('thresholds') or []
        if not steps:
            return None

        matched = None
        for step in sorted(steps, key=lambda x: x['count']):
            if warn_count >= step['count']:
                matched = step
        if not matched:
            return None

        action = matched.get('action', 'mute')
        duration = matched.get('duration', 10)
        unit = matched.get('unit', 'minute')
        minutes = duration_to_minutes(duration, unit)

        try:
            from services import punish_roles as PR
            if action in ('mute', 'timeout'):
                try:
                    from services import mute_state
                    await mute_state.clear_voice_mute(guild, member)
                except Exception as _mse:
                    log.debug('авто-мут: очистка войс-мута: %s', _mse)
                rid = PR.role_for(guild.id, 'mute')
                role = guild.get_role(rid) if rid else None
                if role is not None:
                    import time as _time
                    await member.add_roles(
                        role, reason=f'Авто: {warn_count} предупреждений')
                    PR.add_temp(guild.id, member.id, role.id,
                                _time.time() + max(60, minutes * 60))
                    return f'Мут: роль «{role.name}» {minutes} мин'
                until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                await member.timeout(
                    until, reason=f'Авто-наказание: {warn_count} предупреждений')
                return f'Мут {minutes} мин'
            elif action == 'vmute':
                vrid = PR.role_for(guild.id, 'vmute')
                vrole = guild.get_role(vrid) if vrid else None
                if vrole is not None:
                    import time as _time
                    await member.add_roles(
                        vrole,
                        reason=f'Авто: {warn_count} предупреждений (войс-мут)')
                    PR.add_temp(guild.id, member.id, vrole.id,
                                _time.time() + max(60, minutes * 60))
                    try:
                        voice = getattr(member, 'voice', None)
                        if (voice is not None
                                and getattr(voice, 'channel', None) is not None
                                and not getattr(voice, 'mute', False)):
                            await member.edit(
                                mute=True,
                                reason=f'Авто войс-мут: {warn_count} предупреждений')
                    except Exception as _ve:
                        log.debug('авто войс-мут: %s', _ve)
                    return f'Войс-мут: роль «{vrole.name}» {minutes} мин'
                voice = getattr(member, 'voice', None)
                if voice is not None and getattr(voice, 'channel', None) is not None:
                    await member.edit(
                        mute=True,
                        reason=f'Авто войс-мут: {warn_count} предупреждений')
                    return f'Войс-мут {minutes} мин'
                return ('Войс-мут: участник не в голосовом канале '
                        'и роль войс-мута не назначена')
            elif action == 'kick':
                await member.kick(
                    reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Кик'
            elif action == 'ban':
                rid = PR.role_for(guild.id, 'ban')
                role = guild.get_role(rid) if rid else None
                if role is not None:
                    await member.add_roles(
                        role, reason=f'Авто: {warn_count} предупреждений')
                    try:
                        from services.channel_routes import get_route
                        cid = int(get_route(guild.id, 'ban_appeal_channel') or 0)
                        iso = guild.get_channel(cid) if cid else None
                        if iso is not None:
                            await iso.set_permissions(
                                member, view_channel=True, send_messages=True)
                    except Exception as _ex:
                        log.debug('бан-ролью: %s', _ex)
                    return f'Бан: роль «{role.name}» + апелляция'
                await member.ban(
                    reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Бан'
        except Exception as e:
            log.error('Ошибка авто-наказания: %s', e)
        return None

    # ── ядро выдачи варна (через services.warn_actions) ─────────────
    async def _issue_warn(self, guild, user, moderator, reason: str = None,
                          *, check_acl: bool = True, interaction=None,
                          reason_code: str = None, reason_type: str = None,
                          detail: str = None, source: str = 'discord'):
        """Запись в БД + sync роли + лог + DM + авто-наказание.

        Возвращает (warn_id, total, punishment_result) или (0, total, None)
        при отказе.
        """
        from services import warn_store as WS
        from services import warn_actions as WA

        # лимиты стаффа (до записи)
        try:
            _sl_uid = getattr(moderator, 'id', 0)
            try:
                from config import Config as _Cfg
                _sl_bot_owner = _sl_uid in _Cfg.all_owner_ids()
            except Exception:
                _sl_bot_owner = False
            if (guild and not _sl_bot_owner
                    and _sl_uid != getattr(guild, 'owner_id', 0)):
                from services.staff_limits import check_limit as _sl_check
                _sl_roles = []
                try:
                    _sl_roles = [
                        r.id for r in (getattr(moderator, 'roles', None) or [])
                        if getattr(r, 'id', None) != getattr(guild, 'id', None)]
                except Exception:
                    _sl_roles = []
                _sl_ok, _sl_used, _sl_lim = _sl_check(
                    guild.id, moderator.id, 'warn', 1, role_ids=_sl_roles)
                if not _sl_ok:
                    if interaction is not None:
                        from cogs.embed_utils import error_embed as _err
                        await interaction.followup.send(
                            embed=_err(
                                f'Лимит варнов исчерпан: {_sl_lim} '
                                f'(уже {_sl_used}).'),
                            ephemeral=True)
                    return (0, WS.count_active(guild.id, user.id), None)
        except Exception as _ex:
            _log.debug('_issue_warn staff_limit: %s', _ex)

        ok, msg, payload = await WA.issue_warn(
            guild, user, moderator,
            reason=reason, reason_code=reason_code, reason_type=reason_type,
            detail=detail, source=source, check_acl=check_acl,
            apply_auto_punish=False)
        if not ok or not payload:
            if interaction is not None:
                from cogs.embed_utils import error_embed as _err
                try:
                    await interaction.followup.send(
                        embed=_err(msg or 'Нет права на варн.'),
                        ephemeral=True)
                except Exception:
                    pass
            return (0, WS.count_active(guild.id, user.id), None)

        warn_id = int(payload['warn_id'])
        total = int(payload['total'])
        is_staff = bool(payload.get('is_staff'))

        try:
            from services.panel_notify import notify_panel_event as _np
            if interaction is not None:
                _np(interaction, 'warn',
                    f'Предупреждение: {user.display_name}',
                    f'Модератор: {moderator.display_name} · Всего: {total} · '
                    f'Причина: {payload.get("reason") or "Не указана"}')
        except Exception as _ex:
            _log.debug('panel_notify: %s', _ex)

        punishment_result = None
        if not is_staff:
            try:
                punishment_result = await self.apply_warn_punishment(
                    guild, user, total)
            except Exception as _pun_e:
                log.warning('Авто-наказание не применено: %s', _pun_e)
            if punishment_result:
                await _log_punish_to_channel(
                    guild, user, punishment_result, total)
        return warn_id, total, punishment_result

    async def add_warn(self, interaction, user: discord.Member,
                       reason: str = None, *, reason_code: str = None,
                       reason_type: str = None, detail: str = None):
        """Ядро /warn и контекстных меню."""
        return await self._issue_warn(
            interaction.guild, user, interaction.user, reason,
            check_acl=True, interaction=interaction,
            reason_code=reason_code, reason_type=reason_type, detail=detail)

    async def add_warning(self, user: discord.Member,
                          moderator: discord.Member, reason: str = None,
                          *, reason_code: str = None, reason_type: str = None,
                          detail: str = None, source: str = 'discord'):
        """Путь AI / панели / автофильтра (без interaction)."""
        guild = user.guild
        try:
            from services.warn_acl import _is_bot_actor
            is_bot = _is_bot_actor(moderator)
        except Exception:
            is_bot = bool(getattr(moderator, 'bot', False))
        return await self._issue_warn(
            guild, user, moderator, reason,
            check_acl=not is_bot, interaction=None,
            reason_code=reason_code, reason_type=reason_type,
            detail=detail, source=source)

    async def remove_last_warning(self, user, moderator, *,
                                  removed_reason: str = None,
                                  source: str = 'discord'):
        """Снять последний активный варн (soft) + sync роли."""
        from services import warn_actions as WA
        ok, msg, payload = await WA.remove_warn(
            user.guild, user, moderator,
            removed_reason=removed_reason, source=source, check_acl=False)
        if not ok or not payload:
            return None, 0
        return payload.get('removed'), int(payload.get('total') or 0)

    # ── /warnings ───────────────────────────────────────────────────
    @app_commands.command(name='warnings',
                          description='Предупреждения пользователя')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction, user: discord.Member):
        from services import warn_store as WS
        active = WS.count_active(interaction.guild.id, user.id)
        history = WS.list_warns(interaction.guild.id, user.id, limit=8)

        e = discord.Embed(
            color=discord.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc))
        if not history:
            e.description = (
                f'## Предупреждения\n'
                f'**{user.display_name}** · `{user.id}`\n\n'
                f'Предупреждений нет.\n\n{DIVIDER}')
        else:
            desc = (
                f'## Предупреждения\n'
                f'**{user.display_name}** · `{user.id}`\n'
                f'Активных: **{active}**\n\n')
            for w in history:
                mark = '' if w.get('active') else ' · снят'
                ts = str(w.get('created_at') or '')[:10]
                desc += (
                    f'**#{w["id"]}** — {w["reason"]}{mark}\n'
                    f'-# {ts} · <@{w.get("moderator_id")}>\n\n')
            desc += DIVIDER
            e.description = desc
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f'{interaction.guild.name}')
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /unwarn ─────────────────────────────────────────────────────
    @app_commands.command(
        name='unwarn',
        description='Снять последнее предупреждение у пользователя')
    async def unwarn(self, interaction, user: discord.Member):
        try:
            from services.permission_acl import check_action as _acl, \
                allowed_roles_for_action as _allowed
            if not _acl(interaction.guild_id, interaction.user, 'unwarn'):
                _legacy = (not _allowed(interaction.guild_id, 'unwarn')
                           and not _allowed(interaction.guild_id, 'warn'))
                _ok = _legacy and getattr(
                    getattr(interaction.user, 'guild_permissions', None),
                    'moderate_members', False)
                if not _ok:
                    await interaction.response.send_message(
                        '🚫 Снятие варнов тебе не выдано '
                        '(панель → Доступ → «Снять варн»).',
                        ephemeral=True)
                    return
        except Exception as _acl_e:
            log.debug('unwarn acl: %s', _acl_e)

        try:
            from services.warn_acl import manual_warn_check
            # снятие — те же ветковые правила для стаффа
            ok, deny = manual_warn_check(
                interaction.guild, interaction.user, user)
            if not ok:
                # для unwarn обычных участников — иерархия отдельно
                pass
        except Exception:
            pass

        try:
            from services.staff_hierarchy import check as _hchk
            _hok, _hdeny, _a, _t = _hchk(
                interaction.guild, interaction.user, user, 'unwarn')
            if not _hok:
                await interaction.response.send_message(
                    _hdeny, ephemeral=True)
                return
        except Exception as _hex:
            log.debug('unwarn hierarchy: %s', _hex)

        # для стаффа — ветка
        try:
            from services.warn_acl import _is_staff_target, manual_warn_check
            if _is_staff_target(interaction.guild, user):
                ok, deny = manual_warn_check(
                    interaction.guild, interaction.user, user)
                if not ok:
                    await interaction.response.send_message(
                        deny or 'Нет права снять варн.', ephemeral=True)
                    return
        except Exception as _ex:
            log.debug('unwarn staff branch: %s', _ex)

        removed, total = await self.remove_last_warning(
            user, interaction.user)
        if not removed:
            e = discord.Embed(
                color=discord.Color.dark_grey(),
                timestamp=datetime.now(timezone.utc))
            e.description = (
                f'## Снятие предупреждения\n'
                f'**{user.display_name}** · `{user.id}`\n\n'
                f'У пользователя нет предупреждений.\n\n{DIVIDER}')
            e.set_footer(text=f'{interaction.guild.name}')
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        e = discord.Embed(
            color=discord.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc))
        e.description = (
            f'## Снятие предупреждения\n'
            f'**{user.display_name}** · `{user.id}`\n\n'
            f'Снято: **#{removed.get("id")}** — '
            f'{removed.get("reason", "Не указана")}\n'
            f'Осталось: **{total}**\n'
            f'Модератор: {interaction.user.mention}\n\n{DIVIDER}')
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f'{interaction.guild.name}')
        await interaction.response.send_message(embed=e, ephemeral=True)

    def _collect_mod_data(self, guild_id, user_id):
        warns = self._get_warns(guild_id, user_id)
        cases = []
        notes = []
        try:
            md = {}
            if os.path.exists('data/mod_data.json'):
                with open('data/mod_data.json', 'r', encoding='utf-8') as f:
                    md = json.load(f)
            for c in md.get('cases', {}).get(str(guild_id), []):
                if str(c.get('user_id', '')) == str(user_id):
                    cases.append(c)
        except Exception as _ex:
            _log.debug('_collect_mod_data cases: %s', _ex)
        try:
            ad = {}
            if os.path.exists('data/mod_advanced_data.json'):
                with open('data/mod_advanced_data.json', 'r',
                          encoding='utf-8') as f:
                    ad = json.load(f)
            for c in ad.get('case', {}).get(str(guild_id), []):
                if str(c.get('user_id', '')) == str(user_id):
                    cases.append(c)
            for n in ad.get('notes', {}).get(str(guild_id), {}).get(
                    str(user_id), []):
                notes.append(n)
        except Exception as _ex:
            _log.debug('_collect_mod_data notes: %s', _ex)
        return warns, cases, notes

    # ── события: sync роли + members_cache + сводка канала warn ─────
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            from services.warn_role import sync_guild_active_warns
            for guild in list(self.bot.guilds):
                try:
                    n = await sync_guild_active_warns(guild)
                    if n:
                        log.info(
                            'warn sync on_ready guild=%s members=%s',
                            guild.id, n)
                except Exception as e:
                    log.debug('warn sync guild %s: %s', guild.id, e)
        except Exception as e:
            log.warning('on_ready warn sync: %s', e)
        # members_cache — только в фоне: полный sync на main гильдии
        # иначе вешает event-loop и бот не заходит в войс.
        try:
            import asyncio as _aio
            from services import members_cache as MC
            from config import Config
            main_gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)

            async def _bg_members_cache():
                for guild in list(self.bot.guilds):
                    if main_gid and int(guild.id) != main_gid:
                        continue
                    try:
                        await MC.sync_guild(guild)
                    except Exception as e:
                        log.debug('members_cache sync %s: %s', guild.id, e)

            self.bot.loop.create_task(
                _bg_members_cache(), name='members-cache-sync')
        except Exception as e:
            log.debug('members_cache on_ready: %s', e)
        try:
            from services.warn_board import update_warn_board
            from config import Config
            main_gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
            for guild in list(self.bot.guilds):
                if main_gid and int(guild.id) != main_gid:
                    continue
                try:
                    await update_warn_board(guild, force=True)
                except Exception as e:
                    log.debug('warn board on_ready %s: %s', guild.id, e)
        except Exception as e:
            log.debug('warn board on_ready: %s', e)
        if not getattr(self, '_board_loop_started', False):
            try:
                self._warn_board_loop.start()
                self._board_loop_started = True
            except Exception as e:
                log.debug('warn board loop start: %s', e)

    @tasks.loop(minutes=3)
    async def _warn_board_loop(self):
        try:
            from services.warn_board import update_warn_board
            from config import Config
            gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
            for guild in list(self.bot.guilds):
                if gid and int(guild.id) != gid:
                    continue
                try:
                    await update_warn_board(guild, force=False)
                except Exception as e:
                    log.debug('warn board loop %s: %s', guild.id, e)
        except Exception as e:
            log.debug('warn board loop: %s', e)

    @_warn_board_loop.before_loop
    async def _warn_board_before(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            from services.warn_role import sync_warn_role
            await sync_warn_role(member)
        except Exception as e:
            log.debug('on_member_join warn sync: %s', e)
        try:
            from services import members_cache as MC
            MC.upsert_member(member.guild.id, member)
        except Exception as e:
            log.debug('on_member_join cache: %s', e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            from services import members_cache as MC
            MC.mark_left(member.guild.id, member.id)
        except Exception as e:
            log.debug('on_member_remove cache: %s', e)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Стал/перестал быть стаффом или вручную трогали роль warn."""
        try:
            from services import members_cache as MC
            MC.upsert_member(after.guild.id, after)
        except Exception:
            pass
        try:
            before_ids = {
                getattr(r, 'id', None)
                for r in (getattr(before, 'roles', None) or [])}
            after_ids = {
                getattr(r, 'id', None)
                for r in (getattr(after, 'roles', None) or [])}
            nick_chg = (
                getattr(before, 'display_name', None)
                != getattr(after, 'display_name', None))
            if before_ids == after_ids and not nick_chg:
                return
            from services.warn_role import sync_warn_role
            await sync_warn_role(after)
        except Exception as e:
            log.debug('on_member_update warn sync: %s', e)


# ═══════════════════════════════════════════════════════════════════
#  История варнов (пагинация) — persistent view
# ═══════════════════════════════════════════════════════════════════
WARN_HISTORY_PAGE = 5


class WarnHistoryView(discord.ui.View):
    """Пагинация истории варнов. custom_id → работает после рестарта."""

    def __init__(self, guild_id: int, user_id: int, page: int = 0,
                 requester_id: int = 0):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)
        self.user_id = int(user_id)
        self.page = max(0, int(page or 0))
        self.requester_id = int(requester_id or 0)
        self._rebuild_buttons()

    def _rebuild_buttons(self):
        self.clear_items()
        prev_btn = discord.ui.Button(
            label='◀', style=discord.ButtonStyle.secondary,
            custom_id=f'warnhist:{self.guild_id}:{self.user_id}:'
                      f'{self.page - 1}:{self.requester_id}',
            disabled=self.page <= 0)
        next_btn = discord.ui.Button(
            label='▶', style=discord.ButtonStyle.secondary,
            custom_id=f'warnhist:{self.guild_id}:{self.user_id}:'
                      f'{self.page + 1}:{self.requester_id}')
        self.add_item(prev_btn)
        self.add_item(next_btn)

    @staticmethod
    async def build_embed(guild, user, page: int = 0):
        from services import warn_store as WS
        from services.warn_acl import _is_staff_target, branches_of
        from services.warn_config import format_branches

        all_rows = WS.list_warns(guild.id, user.id)
        active = WS.count_active(guild.id, user.id)
        total_pages = max(1, (len(all_rows) + WARN_HISTORY_PAGE - 1)
                          // WARN_HISTORY_PAGE)
        page = max(0, min(page, total_pages - 1))
        chunk = all_rows[page * WARN_HISTORY_PAGE:
                         (page + 1) * WARN_HISTORY_PAGE]

        e = discord.Embed(
            title=f'История варнов · {user.display_name}',
            color=0x2B2D31,
            timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=user.display_avatar.url)
        head = [f'`{user.id}`', f'Активных: **{active}** · всего записей: **{len(all_rows)}**']
        try:
            if _is_staff_target(guild, user):
                head.append(f'Ветка: **{format_branches(branches_of(user))}**')
        except Exception:
            pass
        body = []
        for w in chunk:
            mark = '' if w.get('active') else ' · снят'
            ts = str(w.get('created_at') or '')[:16]
            body.append(
                f'**#{w["id"]}**{mark} — {w.get("reason", "—")}\n'
                f'-# {ts} · <@{w.get("moderator_id")}>')
        e.description = '\n'.join(head) + '\n\n' + (
            '\n\n'.join(body) if body else '_Пусто._')
        e.set_footer(text=f'Стр. {page + 1}/{total_pages} · {guild.name}')
        return e, page, total_pages


class WarnHistoryDispatcher(discord.ui.View):
    """Один persistent view: ловит warnhist:* кнопки после рестарта."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label='hist', style=discord.ButtonStyle.secondary,
        custom_id='warnhist:dispatcher', disabled=True)
    async def _noop(self, interaction, button):
        pass


async def handle_warn_history_button(interaction: discord.Interaction):
    """Разбор custom_id warnhist:gid:uid:page:requester."""
    cid = getattr(interaction, 'data', {}) or {}
    custom = ''
    try:
        custom = str(cid.get('custom_id') or '')
    except Exception:
        custom = ''
    if not custom.startswith('warnhist:'):
        return False
    parts = custom.split(':')
    if len(parts) < 4:
        return False
    try:
        gid = int(parts[1])
        uid = int(parts[2])
        page = int(parts[3])
        req = int(parts[4]) if len(parts) > 4 else 0
    except (TypeError, ValueError):
        return False

    if req and getattr(interaction.user, 'id', 0) != req:
        await interaction.response.send_message(
            'Это меню другого модератора.', ephemeral=True)
        return True

    guild = interaction.guild
    if guild is None or int(guild.id) != gid:
        await interaction.response.send_message(
            'Сервер не совпадает.', ephemeral=True)
        return True
    user = guild.get_member(uid)
    if user is None:
        try:
            user = await interaction.client.fetch_user(uid)
        except Exception:
            user = None
    if user is None:
        await interaction.response.send_message(
            'Участник не найден.', ephemeral=True)
        return True

    # права: тот же ACL, что на просмотр/варн
    try:
        from services.warn_acl import can_issue_manual_warn
        if not can_issue_manual_warn(interaction.user, user, guild):
            # разрешаем просмотр и тем, у кого есть unwarn/warn ACL
            from services.permission_acl import check_action as _acl
            if not (_acl(guild.id, interaction.user, 'warn')
                    or _acl(guild.id, interaction.user, 'unwarn')):
                await interaction.response.send_message(
                    'Нет прав на просмотр истории варнов.', ephemeral=True)
                return True
    except Exception:
        pass

    embed, page, total_pages = await WarnHistoryView.build_embed(
        guild, user, page)
    view = WarnHistoryView(gid, uid, page, req or interaction.user.id)
    # отключить next на последней
    if page >= total_pages - 1 and len(view.children) > 1:
        view.children[1].disabled = True
    try:
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
    except Exception:
        try:
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True)
        except Exception:
            pass
    return True


class PWCategorySelect(discord.ui.Select):
    def __init__(self, cog, user, warns, cases, notes):
        self.cog = cog
        self.user = user
        self.warns = warns
        self.cases = cases
        self.notes = notes
        options = [
            discord.SelectOption(
                label='Предупреждения', value='warns',
                description='Все предупреждения и причины'),
            discord.SelectOption(
                label='Наказания', value='cases',
                description='Мьюты, баны, кики и причины'),
            discord.SelectOption(
                label='Заметки', value='notes',
                description='Заметки модераторов'),
            discord.SelectOption(
                label='Оценка', value='score',
                description='Общая характеристика /100'),
        ]
        super().__init__(
            placeholder='Выберите раздел досье...',
            options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        e = discord.Embed(
            title=f'📋 Досье: {self.user.display_name}',
            color=0x3498DB,
            timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=self.user.display_avatar.url)
        e.set_footer(text=f'{interaction.guild.name} • Hakumo Модерация')

        if choice == 'warns':
            if not self.warns:
                e.description = 'У пользователя нет предупреждений.'
            else:
                desc = f'**Всего: {len(self.warns)}**\n\n'
                for w in reversed(self.warns[-10:]):
                    desc += (
                        f'**#{w.get("id")}** — {w.get("reason", "?")}\n'
                        f'-# {str(w.get("timestamp", ""))[:10]} · '
                        f'{w.get("mod", "?")}\n\n')
                e.description = desc
        elif choice == 'cases':
            if not self.cases:
                e.description = 'Нет записей о наказаниях.'
            else:
                desc = f'**Всего: {len(self.cases)}**\n\n'
                for c in reversed(self.cases[-10:]):
                    act = str(c.get('action', '?')).upper()
                    desc += (
                        f'**{act}** — {c.get("reason", "?")}\n'
                        f'-# {str(c.get("timestamp", ""))[:10]}\n\n')
                e.description = desc
        elif choice == 'notes':
            if not self.notes:
                e.description = 'Заметок нет.'
            else:
                desc = f'**Всего: {len(self.notes)}**\n\n'
                for n in reversed(self.notes[-10:]):
                    desc += (
                        f'**•** {n.get("note", "?")}\n'
                        f'-# {str(n.get("timestamp", ""))[:10]} · '
                        f'{n.get("mod", "?")}\n\n')
                e.description = desc
        else:
            score = _compute_score(len(self.warns), self.cases)
            st = _score_text(score)
            color = 0x2ECC71 if score >= 60 else 0xF39C12 if score >= 30 else 0xE74C3C
            e.color = color
            e.description = (
                f'**Оценка: {score}/100 — {st}**\n\n'
                f'• Предупреждения: **{len(self.warns)}** (каждое −12)\n'
                f'• Наказания: **{len(self.cases)}** (мут/кик −18, бан −25)\n\n'
                'Шкала:\n• 80–100 — Хорошо\n• 50–79 — Удовлетворительно\n'
                '• 25–49 — Плохо\n• 0–24 — Очень плохо')

        await interaction.response.edit_message(
            embed=e,
            view=PWView(self.cog, self.user, self.warns, self.cases, self.notes))


class PWView(discord.ui.View):
    def __init__(self, cog, user, warns, cases, notes):
        super().__init__(timeout=300)
        self.add_item(PWCategorySelect(cog, user, warns, cases, notes))


async def setup(bot):
    await bot.add_cog(warnings(bot))
    # Persistent: кнопки истории + сводки канала warn после рестарта
    try:
        @bot.listen('on_interaction')
        async def _warn_hist_router(interaction):
            try:
                data = getattr(interaction, 'data', None) or {}
                cid = str(data.get('custom_id') or '')
                if cid.startswith('warnhist:'):
                    await handle_warn_history_button(interaction)
                elif cid.startswith('warnboard:'):
                    from services.warn_board import handle_board_button
                    await handle_board_button(interaction)
            except Exception as e:
                log.debug('warnhist/board router: %s', e)
    except Exception as e:
        log.debug('warnhist listen: %s', e)
    log.info('Warnings загружен (единая роль warn + SQLite + board)')
