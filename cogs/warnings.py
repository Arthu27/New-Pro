"""
Warnings Cog
Система предупреждений — database (SQLite)
Тёмная тема, русский язык
"""

from logger import get_logger

_log = get_logger("warnings")

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import os
import json
import io

from cogs.embed_utils import mod_dm_embed, DIVIDER
from logger import get_logger
from db import GuildData

log = get_logger("warnings")


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
        img = Image.new("RGB", (w, h), (18, 18, 20))
        return img


def generate_pw_card(display_name, user_id, avatar_url, warns, cases, notes,
                     score, score_text, member=None):
    """Сгенерировать карточку-досье в стиле ticket-panel (profile_bg_pro)."""
    W, H = 1200, 600
    # Фон как у ticket-panel (teal на основе profile_bg_pro)
    try:
        bg = load_menu_bg(W, H, "teal")
        bg = bg.convert("RGB")
    except Exception:
        bg = _load_base_bg(W, H).convert("RGB")
    d = ImageDraw.Draw(bg, "RGBA")

    # Полупрозрачная тёмная панель для читаемости
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rounded_rectangle((30, 30, W - 30, H - 30), radius=28, fill=(10, 10, 14, 190))
    bg = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(bg, "RGBA")

    # Шапка
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

    # Заголовок
    d.text((70, 55), "ДОСЬЕ ПОЛЬЗОВАТЕЛЯ", font=f_title, fill=(222, 28, 42, 255))
    d.line([(70, 120), (W - 70, 120)], fill=(222, 28, 42, 200), width=3)

    # Имя
    d.text((70, 145), display_name or "Неизвестно", font=f_big, fill=(255, 255, 255, 255))
    d.text((70, 200), f"ID: {user_id}", font=f_mid, fill=(205, 205, 208, 255))

    # Левая колонка: статистика
    x1 = 70
    y = 265
    d.text((x1, y), "ПРЕДУПРЕЖДЕНИЯ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{warns}", font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), "МЬЮТЫ / НАКАЗАНИЯ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{cases}", font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), "ЗАМЕТКИ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{notes}", font=f_big, fill=(255, 255, 255, 255))

    # Правая колонка: оценка
    x2 = W // 2 + 60
    d.text((x2, 265), "ОЦЕНКА", font=f_txt, fill=(222, 28, 42, 255))
    score_color = (46, 204, 113, 255) if score >= 60 else (243, 156, 18, 255) if score >= 30 else (231, 76, 60, 255)
    d.text((x2, 305), f"{score}/100", font=CS.font(True, 72) if _PIL_OK else f_big, fill=score_color)

    # Прогресс-бар
    bar_w = 480
    bar_h = 22
    bx, by = x2, 400
    d.rounded_rectangle((bx, by, bx + bar_w, by + bar_h), radius=11, fill=(60, 60, 66, 255))
    fill_w = int(bar_w * max(0, min(100, score)) / 100)
    if fill_w > 0:
        d.rounded_rectangle((bx, by, bx + fill_w, by + bar_h), radius=11, fill=score_color)
    d.text((x2, 435), score_text, font=f_mid, fill=(255, 255, 255, 255))

    # Подпись
    d.text((70, H - 70), "Hakumo Модерация • Досье", font=f_small, fill=(150, 150, 155, 255))

    buf = io.BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def _compute_score(warns, cases):
    """Скоринг /100: старт 100, -12 за warn, -18 за mute/наказание, -25 за ban."""
    score = 100
    score -= warns * 12
    for c in cases:
        act = str(c.get("action", "")).lower()
        if act == "ban":
            score -= 25
        elif act in ("timeout", "mute_chat", "vmute", "kick"):
            score -= 18
        elif act == "warn":
            score -= 12
    return max(0, min(100, score))


def _score_text(score):
    if score >= 80:
        return "Хорошо"
    if score >= 50:
        return "Удовлетворительно"
    if score >= 25:
        return "Плохо"
    return "Очень плохо"


def load_warn_config(guild_id):
    """Загрузить конфигурацию наказаний (пока JSON, потом DB)"""
    import json, os
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


async def _log_warn_to_channel (guild ,user ,moderator ,reason ,warn_id ,total ,punishment_result=None ):
    """Записать варн в канал «Наказания» (⚖・наказания → -модерация → …).

    Заказ владельца: варны и наказания по варнам — отдельным каналом,
    не вперемешку с остальной модерацией. Канал не выбран в панели —
    система сама вернётся к поиску по имени/наследию.
    Fail-safe: любые ошибки глушим, варн уже сохранён.
    """
    try :
        from cogs .logs import ensure_log_channel ,_safe_send
        ch =await ensure_log_channel (guild ,'наказания')
        if not ch :
            return
        e =discord .Embed (color =0xE74C3C ,timestamp =datetime .now (timezone .utc ))
        e .description =(
        "## Предупреждение\n"
        f"**{user.display_name}** · `{user.id}`\n\n"
        f"Варн: **#{warn_id}** · Всего: **{total}**\n"
        f"Модератор: **{moderator.display_name}**\n"
        f"Причина: {reason or 'Не указана'}"
        + (f"\n\n⚖️ Авто-наказание: **{punishment_result}**" if punishment_result else "")
        )
        e .set_footer (text =f"{guild.name}")
        await _safe_send (ch ,embed =e )
    except Exception as _ex:
        _log.debug("_log_warn_to_channel(): подавлено: %s", _ex)


async def _log_punish_to_channel (guild ,user ,punishment_result ,total ):
    """Отдельная запись об авто-наказании по варнам (⚖・наказания).

    Лестница сработала — персонал видит это в канале наказаний сразу,
    даже если сам варн писался другим путём (панель/AI/реакция).
    Fail-safe: ошибки глушим.
    """
    if not punishment_result :
        return
    try :
        from cogs .logs import ensure_log_channel ,_safe_send
        ch =await ensure_log_channel (guild ,'наказания')
        if not ch :
            return
        e =discord .Embed (color =0xE67E22 ,timestamp =datetime .now (timezone .utc ))
        e .description =(
        "## Авто-наказание\n"
        f"**{user.display_name}** · `{user.id}`\n\n"
        f"Варнов всего: **{total}**\n"
        f"Применено: **{punishment_result}**"
        )
        e .set_footer (text =f"{guild.name}")
        await _safe_send (ch ,embed =e )
    except Exception as _ex:
        _log.debug("_log_punish_to_channel(): подавлено: %s", _ex)


class warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData("warnings")

    def _get_warns(self, guild_id: int, user_id: int) -> list:
        return self.db.get(guild_id, str(user_id), [])

    def _save_warns(self, guild_id: int, user_id: int, warns: list):
        self.db.set(guild_id, str(user_id), warns)
        self._mirror_warns_json(guild_id, user_id, warns)

    def _clear_warns(self, guild_id: int, user_id: int):
        self.db.set(guild_id, str(user_id), [])
        self._mirror_warns_json(guild_id, user_id, [])

    def _mirror_warns_json(self, guild_id: int, user_id: int, warns: list):
        """Зеркалирует предупреждения в data/warnings.json — этот файл читает веб-панель.
        SQLite (GuildData) остаётся основным хранилищем; сбой зеркала не ломает модерацию."""
        try:
            path = 'data/warnings.json'
            os.makedirs('data', exist_ok=True)
            data = {}
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            if not isinstance(data, dict):
                data = {}
            gid, uid = str(guild_id), str(user_id)
            if warns:
                if not isinstance(data.get(gid), dict):
                    data[gid] = {}
                data[gid][uid] = warns[-25:]
            else:
                if isinstance(data.get(gid), dict):
                    data[gid].pop(uid, None)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            log.error(f"Зеркалирование предупреждений в JSON: {e}")

    async def _sync_warn_level_roles(self, guild, member, warn_count):
        """Роль уровня варна (панель → «Роли наказаний»).

        Выдаёт роль ближайшего уровня (≤ warn_count) и снимает роли
        предыдущих уровней; при снятии варна уровень падает — роль
        пересчитывается. Нет выбранных warn-ролей — вообще ничего не делает.
        """
        try:
            from services import punish_roles as PR
            add_id, remove_ids = PR.level_transition(guild.id, warn_count)
            if not add_id and not remove_ids:
                return
            have = {getattr(r, 'id', None)
                    for r in (getattr(member, 'roles', None) or [])}
            for rid in remove_ids:
                if rid not in have:
                    continue
                role = guild.get_role(rid)
                if role is None:
                    continue
                await member.remove_roles(
                    role, reason=f'Уровень варнов изменился ({warn_count})')
                log.info('[WARNS] снята роль уровня %s с %s (варнов: %s)',
                         role.name, member, warn_count)
            if add_id and add_id not in have:
                role = guild.get_role(add_id)
                if role is None:
                    return
                await member.add_roles(
                    role, reason=f'Уровень варнов: {warn_count}')
                log.info('[WARNS] выдана роль уровня %s → %s (варнов: %s)',
                         role.name, member, warn_count)
        except Exception as _ex:
            log.debug('[WARNS] роли уровней варна: %s', _ex)

    async def send_dm(self, user, embed):
        # DM — best-effort: закрытые ЛС/сетевой сбой не роняют команду
        try:
            await user.send(embed=embed)
        except Exception as _ex:
            _log.debug("send_dm(): подавлено: %s", _ex)

    async def apply_warn_punishment(self, guild, member, warn_count):
        """Автоматическое наказание по количеству предупреждений"""
        cfg = load_warn_config(str(guild.id))
        # Панель сохраняет ключ 'thresholds', старые данные — 'steps'; принимаем оба
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
            # Роли наказаний (панель → «Настройки модерации») главнее
            # таймаута/бана: владелец сам выбрал, какими роли наказывать.
            from services import punish_roles as PR
            if action in ('mute', 'timeout'):
                # чат-мут/таймаут глушат чат (таймаут — ещё и голос): снимаем
                # любой висящий отдельный войс-мут, чтобы не было двух ограничений
                try:
                    from services import mute_state
                    await mute_state.clear_voice_mute(guild, member)
                except Exception as _mse:
                    log.debug('авто-мут: очистка войс-мута: %s', _mse)
                rid = PR.role_for(guild.id, 'mute')
                role = guild.get_role(rid) if rid else None
                if role is not None:
                    import time as _time
                    await member.add_roles(role, reason=f'Авто: {warn_count} предупреждений')
                    PR.add_temp(guild.id, member.id, role.id,
                                _time.time() + max(60, minutes * 60))
                    return f'Мут: роль «{role.name}» {minutes} мин'
                until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                await member.timeout(until, reason=f'Авто-наказание: {warn_count} предупреждений')
                return f'Мут {minutes} мин'
            elif action == 'vmute':
                # Войс-мут — ОТДЕЛЬНО от чат-мута: глушим ТОЛЬКО микрофон.
                # Чат-мут/таймаут не трогаем (и не снимаем — это другое ограничение).
                vrid = PR.role_for(guild.id, 'vmute')
                vrole = guild.get_role(vrid) if vrid else None
                if vrole is not None:
                    import time as _time
                    await member.add_roles(vrole, reason=f'Авто: {warn_count} предупреждений (войс-мут)')
                    PR.add_temp(guild.id, member.id, vrole.id,
                                _time.time() + max(60, minutes * 60))
                    # роль войс-мута сама глушит микрофон в голосовом канале
                    try:
                        voice = getattr(member, 'voice', None)
                        if voice is not None and getattr(voice, 'channel', None) is not None \
                                and not getattr(voice, 'mute', False):
                            await member.edit(mute=True, reason=f'Авто войс-мут: {warn_count} предупреждений')
                    except Exception as _ve:
                        log.debug('авто войс-мут: server-mute: %s', _ve)
                    return f'Войс-мут: роль «{vrole.name}» {minutes} мин'
                # роли нет — нативный server-mute (работает, только если участник в голосе)
                voice = getattr(member, 'voice', None)
                if voice is not None and getattr(voice, 'channel', None) is not None:
                    await member.edit(mute=True, reason=f'Авто войс-мут: {warn_count} предупреждений')
                    return f'Войс-мут {minutes} мин'
                # вне голоса нативный server-mute поставить нельзя — мягкий фоллбэк:
                # ставим роль войс-мута не выйдет (её нет), сообщаем модерации
                return 'Войс-мут: участник не в голосовом канале и роль войс-мута не назначена'
            elif action == 'kick':
                await member.kick(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Кик'
            elif action == 'ban':
                rid = PR.role_for(guild.id, 'ban')
                role = guild.get_role(rid) if rid else None
                if role is not None:
                    # «бан» ролью: участник остаётся на сервере, апелляция —
                    # в канале апелляции (если выбран)
                    await member.add_roles(role, reason=f'Авто: {warn_count} предупреждений')
                    try:
                        from services.channel_routes import get_route
                        cid = int(get_route(guild.id, 'ban_appeal_channel') or 0)
                        iso = guild.get_channel(cid) if cid else None
                        if iso is not None:
                            await iso.set_permissions(
                                member, view_channel=True, send_messages=True)
                    except Exception as _ex:
                        log.debug(f'бан-ролью: канал апелляции не открыт: {_ex}')
                    return f'Бан: роль «{role.name}» + апелляция'
                await member.ban(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Бан'
        except Exception as e:
            log.error(f'Ошибка авто-наказания: {e}')
        return None

    # ── /warn ────────────────────────────────────────────────────────────
    async def add_warn(self, interaction, user: discord.Member, reason: str = None):
        """Общее ядро warn: запись + DM + автоматическое наказание.

        Команду /warn И контекстные меню правого клика (mod_tools) используют её.
        Ответ НЕ отправляет — отвечает вызывающая сторона.
        Возвращает: (warn_id, total, punishment_result)
        """
        guild = interaction.guild

        # Лимиты стаффа (владельца не трогаем): пер-рольные лимиты на варны
        try:
            _sl_uid = getattr(interaction.user, 'id', 0)
            try:
                from config import Config as _Cfg
                _sl_bot_owner = _sl_uid in _Cfg.all_owner_ids()
            except Exception:
                _sl_bot_owner = False
            if guild and not _sl_bot_owner and _sl_uid != getattr(guild, 'owner_id', 0):
                from services.staff_limits import check_limit as _sl_check
                _sl_roles = []
                try:
                    _sl_roles = [r.id for r in (getattr(interaction.user, 'roles', None) or [])
                                 if getattr(r, 'id', None) != getattr(guild, 'id', None)]
                except Exception:
                    _sl_roles = []
                _sl_ok, _sl_used, _sl_lim = _sl_check(guild.id, interaction.user.id,
                                                      'warn', 1, role_ids=_sl_roles)
                if not _sl_ok:
                    from cogs.embed_utils import error_embed as _err
                    await interaction.followup.send(
                        embed=_err(f'Лимит варнов исчерпан: {_sl_lim} '
                                   f'(уже {_sl_used}). Период настраивается в «Лимитах команды».'),
                        ephemeral=True)
                    return (0, len(self._get_warns(guild.id, user.id)), None)
        except Exception as _ex:
            _log.debug("add_warn() staff_limit: %s", _ex)

        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(interaction.user),
            "mod_id": str(interaction.user.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # Роли уровня варна: вырос уровень — предыдущая роль слетает сама
        guild = interaction.guild
        await self._sync_warn_level_roles(guild, user, total)

        # Лимиты: фиксируем успешный варн в дневном счётчике
        try:
            from services.staff_limits import record_hit as _sl_rec
            _sl_rec(guild.id, interaction.user.id, 'warn', 1)
        except Exception as _ex:
            _log.debug("add_warn() record: %s", _ex)

        # Уведомление панели о варне (веб/Discord/email — в фоне)
        try:
            from services.panel_notify import notify_panel_event as _np
            _np(interaction, 'warn',
                f"Предупреждение: {user.display_name}",
                f"Модератор: {interaction.user.display_name} · Всего: {total} · Причина: {reason or 'Не указана'}")
        except Exception as _ex:
            _log.debug("add_warn(): подавлено: %s", _ex)

        # Лог в Discord-канал (-модерация) — чтобы варн был виден персоналу
        await _log_warn_to_channel (guild ,user ,interaction .user ,reason ,warn_id ,total )

        # DM пользователю
        # чтение кастомного текста DM — в рабочем потоке (файл не блокирует loop)
        from services.async_io import load_json_async
        dm_file = f'data/warn_dm_{guild.id}.json'
        dm_cfg = await load_json_async(dm_file, {}, log=_log) or {}
        custom_dm = dm_cfg.get('message')

        if custom_dm:
            msg = custom_dm.replace('{user}', user.display_name).replace('{reason}', reason or 'Не указана').replace('{mod}', interaction.user.display_name).replace('{сервер}', guild.name)
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"{msg}\n\n"
                f"Сервер: **{guild.name}**\n"
                f"Модератор: **{interaction.user.display_name}**\n"
                f"Всего предупреждений: **{total}**\n"
                f"Причина: {reason or 'Не указана'}"
            )
            dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_embed.set_footer(text=f"{guild.name}")
            await self.send_dm(user, dm_embed)
        else:
            await self.send_dm(user, mod_dm_embed("warn", guild, interaction.user, reason))

        # Авто-наказание: его сбой не должен ломать сам варн —
        # предупреждение уже записано и модератор ждёт подтверждение
        try:
            punishment_result = await self.apply_warn_punishment(guild, user, total)
        except Exception as _pun_e:
            log.warning(f"[WARN] Авто-наказание не применено: {_pun_e}")
            punishment_result = None
        if punishment_result:
            await _log_punish_to_channel(guild, user, punishment_result, total)
        return warn_id, total, punishment_result

    # ── /warnings ────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="Предупреждения пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction, user: discord.Member):
        warns = self._get_warns(interaction.guild.id, user.id)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))

        if not warns:
            e.description = (
                "## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                "Предупреждений нет.\n\n"
                f"{DIVIDER}"
            )
        else:
            desc = (
                "## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n"
                f"Всего: **{len(warns)}**\n\n"
            )
            for w in warns[-8:]:
                desc += f"**#{w['id']}** — {w['reason']}\n-# {w['timestamp'][:10]} · {w.get('mod', '?')}\n\n"
            desc += DIVIDER
            e.description = desc

        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /unwarn ─────────────────────────────────────────────────────────
    @app_commands.command(name="unwarn", description="Снять последнее предупреждение у пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction, user: discord.Member):
        """Снять последнее предупреждение у пользователя"""
        warns = self._get_warns(interaction.guild.id, user.id)
        if not warns:
            e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            e.description = (
                "## Снятие предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                "У пользователя нет предупреждений.\n\n"
                f"{DIVIDER}"
            )
            e.set_footer(text=f"{interaction.guild.name}")
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        removed = warns.pop()
        self._save_warns(interaction.guild.id, user.id, warns)
        total = len(warns)

        # сняли варн — уровень упал: пересчитать роль уровня (снять/выдать)
        await self._sync_warn_level_roles(interaction.guild, user, total)

        # Канал «Наказания»: снятие варна тоже туда (полная картина по варнам)
        try:
            from cogs.logs import ensure_log_channel, _safe_send
            _uch = await ensure_log_channel(interaction.guild, 'наказания')
            if _uch:
                _ue = discord.Embed(color=0x2ECC71, timestamp=datetime.now(timezone.utc))
                _ue.description = (
                    "## Предупреждение снято\n"
                    f"**{user.display_name}** · `{user.id}`\n\n"
                    f"Снято: **#{removed.get('id')}** — {removed.get('reason', 'Не указана')}\n"
                    f"Осталось: **{total}**\n"
                    f"Модератор: {interaction.user.mention}"
                )
                _ue.set_footer(text=f"{interaction.guild.name}")
                await _safe_send(_uch, embed=_ue)
        except Exception as _ulog_e:
            log.debug(f"[WARNS] лог снятия: {_ulog_e}")

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        e.description = (
            "## Снятие предупреждения\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Снято: **#{removed.get('id')}** — {removed.get('reason', 'Не указана')}\n"
            f"Осталось: **{total}**\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── add_warning (для AI-модератора, без interaction) ─────────────────
    async def add_warning(self, user: discord.Member, moderator: discord.Member, reason: str = None):
        """Добавить предупреждение без interaction"""
        guild = user.guild
        # Лимиты стаффа: этот путь используют ⚡-варн реакцией и AI-модератор —
        # без гейта они обходили бы дневной лимит варнов.
        try:
            from services.staff_limits import check_action
            _ok, _deny = check_action(guild, moderator, 'warn')
            if not _ok:
                _log.info("add_warning(): лимит варнов — пропуск (%s)", _deny)
                return (0, len(self._get_warns(guild.id, user.id)), None)
        except Exception as _ex:
            _log.debug("add_warning() staff_limit: %s", _ex)
        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(moderator),
            "mod_id": str(moderator.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # Роли уровня варна (путь панели/AI-модератора — тот же переезд)
        await self._sync_warn_level_roles(user.guild, user, total)

        # Лимиты: фиксируем успешный варн в дневном счётчике
        try:
            from services.staff_limits import record_hit as _sl_rec
            _sl_rec(guild.id, moderator.id, 'warn', 1)
        except Exception as _ex:
            _log.debug("add_warning() record: %s", _ex)

        # Уведомление панели о варне от AI-модератора (веб/webhook/email — в фоне)
        try:
            import asyncio as _asyncio
            from services.notification_dispatcher import notify_event as _ne
            _loop = _asyncio.get_running_loop()
            _loop.run_in_executor(None, lambda: _ne('warn',
                f"Предупреждение: {user.display_name}",
                f"Модератор: {moderator.display_name} · Всего: {total} · Причина: {reason or 'Не указана'}"))
        except Exception as _ex:
            _log.debug("add_warning(): подавлено: %s", _ex)

        # Лог в Discord-канал (-модерация)
        await _log_warn_to_channel (guild ,user ,moderator ,reason ,warn_id ,total )

        # DM
        try:
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"**Сервер:** {guild.name}\n"
                f"**Причина:** {reason or 'Не указана'}\n"
                f"**Модератор:** {moderator.display_name}\n"
                f"**Всего предупреждений:** {total}"
            )
            if guild.icon:
                dm_embed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url)
            await user.send(embed=dm_embed)
        except Exception as _ex:
            _log.debug("add_warning(): подавлено: %s", _ex)

        try:
            _pun_res = await self.apply_warn_punishment(guild, user, total)
            if _pun_res:
                await _log_punish_to_channel(guild, user, _pun_res, total)
        except Exception as _pun_e:
            log.warning(f"[WARN] Авто-наказание не применено: {_pun_e}")
        return warn_id, total

    # ── !pw — полное досье пользователя ────────────────────────────────
    def _collect_mod_data(self, guild_id, user_id):
        """Собрать все данные о пользователе: warns + случаи + заметки."""
        warns = self._get_warns(guild_id, user_id)
        cases = []
        notes = []
        # mod_data.json (ban/kick/timeout/mute от moderation)
        try:
            md = {}
            if os.path.exists("data/mod_data.json"):
                with open("data/mod_data.json", "r", encoding="utf-8") as f:
                    md = json.load(f)
            for c in md.get("cases", {}).get(str(guild_id), []):
                if str(c.get("user_id", "")) == str(user_id):
                    cases.append(c)
        except Exception as _ex:
            _log.debug("_collect_mod_data(): подавлено: %s", _ex)
        # mod_advanced_data.json (case + notes от advanced_mod)
        try:
            ad = {}
            if os.path.exists("data/mod_advanced_data.json"):
                with open("data/mod_advanced_data.json", "r", encoding="utf-8") as f:
                    ad = json.load(f)
            for c in ad.get("case", {}).get(str(guild_id), []):
                if str(c.get("user_id", "")) == str(user_id):
                    cases.append(c)
            for n in ad.get("notes", {}).get(str(guild_id), {}).get(str(user_id), []):
                notes.append(n)
        except Exception as _ex:
            _log.debug("_collect_mod_data(): подавлено: %s", _ex)
        return warns, cases, notes


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ для !pw (категории досье)
# ═══════════════════════════════════════════════════════════════════
class PWCategorySelect(discord.ui.Select):
    """Выбор категории досье."""

    def __init__(self, cog, user, warns, cases, notes):
        self.cog = cog
        self.user = user
        self.warns = warns
        self.cases = cases
        self.notes = notes
        options = [
            discord.SelectOption(label="Предупреждения", value="warns", description="Все предупреждения и причины"),
            discord.SelectOption(label="Наказания", value="cases", description="Мьюты, баны, кики и причины"),
            discord.SelectOption(label="Заметки", value="notes", description="Заметки модераторов"),
            discord.SelectOption(label="Оценка", value="score", description="Общая характеристика /100"),
        ]
        super().__init__(placeholder="Выберите раздел досье...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        e = discord.Embed(
            title=f"📋 Досье: {self.user.display_name}",
            color=0x3498DB,
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=self.user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name} • Hakumo Модерация")

        if choice == "warns":
            if not self.warns:
                e.description = "У пользователя нет предупреждений."
            else:
                desc = f"**Всего: {len(self.warns)}**\n\n"
                for w in reversed(self.warns[-10:]):
                    desc += f"**#{w.get('id')}** — {w.get('reason','?')}\n-# {str(w.get('timestamp',''))[:10]} · {w.get('mod','?')}\n\n"
                e.description = desc
        elif choice == "cases":
            if not self.cases:
                e.description = "Нет записей о наказаниях."
            else:
                desc = f"**Всего: {len(self.cases)}**\n\n"
                for c in reversed(self.cases[-10:]):
                    act = str(c.get("action", "?")).upper()
                    desc += f"**{act}** — {c.get('reason','?')}\n-# {str(c.get('timestamp',''))[:10]}\n\n"
                e.description = desc
        elif choice == "notes":
            if not self.notes:
                e.description = "Заметок нет."
            else:
                desc = f"**Всего: {len(self.notes)}**\n\n"
                for n in reversed(self.notes[-10:]):
                    desc += f"**•** {n.get('note','?')}\n-# {str(n.get('timestamp',''))[:10]} · {n.get('mod','?')}\n\n"
                e.description = desc
        else:  # score
            score = _compute_score(len(self.warns), self.cases)
            st = _score_text(score)
            color = 0x2ECC71 if score >= 60 else 0xF39C12 if score >= 30 else 0xE74C3C
            e.color = color
            e.description = (
                f"**Оценка: {score}/100 — {st}**\n\n"
                f"• Предупреждения: **{len(self.warns)}** (каждое −12)\n"
                f"• Наказания: **{len(self.cases)}** (мут/кик −18, бан −25)\n\n"
                "Шкала:\n• 80–100 — Хорошо\n• 50–79 — Удовлетворительно\n• 25–49 — Плохо\n• 0–24 — Очень плохо"
            )

        await interaction.response.edit_message(embed=e, view=PWView(self.cog, self.user, self.warns, self.cases, self.notes))


class PWView(discord.ui.View):
    """View для досье — select меню категорий."""

    def __init__(self, cog, user, warns, cases, notes):
        super().__init__(timeout=300)
        self.add_item(PWCategorySelect(cog, user, warns, cases, notes))


async def setup(bot):
    await bot.add_cog(warnings(bot))
    log.info("Warnings загружен (database)")
