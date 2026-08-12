# -*- coding: utf-8 -*-
"""MOD KIT — быстрые инструменты модератора (PRO).

- ⚡ Варн реакцией: мод ставит реакцию ⚠️ на сообщение → автор получает варн
  (через стандартный механизм warnings, с логом в -модерация). Одна реакция =
  один варн на сообщение, повторы не считаются.
- ☢️ /nuke — полное пересоздание канала (настройки/права/позиция сохраняются).
- 🧹 /raidcleanup — кик/бан всех, кто зашёл за последние N минут (антирейд).
- 🧽 /dehoist — чистка ников, «выпирающих» вверх списка (! " # …) и залго.
"""

from logger import get_logger

_log = get_logger("mod_kit")

import json
import os
import time
import unicodedata
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger("mod_kit")

REACT_EMOJIS = ('⚠️', '⚠')
REACT_PATH = 'data/modkit_reactwarn.json'

HOIST_ORD = ord('0')          # любой ASCII ниже '0' (пробел/знаки) — «выпиратель»
ZALGO_MIN = 3                 # столько combining-знаков = залго
FALLBACK_NAME = 'Очищенный'


# ─────────────────────────────────────────────────────────────
# Чистые функции (тестируются без discord)
# ─────────────────────────────────────────────────────────────
def _zalgo_count(name: str) -> int:
    return sum(1 for ch in name if unicodedata.category(ch) == 'Mn')


def is_hoist(name: str) -> bool:
    """Ник начинается с символа, поднимающего его вверх списка участников."""
    return bool(name) and ord(name[0]) < HOIST_ORD


def is_zalgo(name: str) -> bool:
    return _zalgo_count(name) >= ZALGO_MIN


def needs_clean(name: str) -> bool:
    return is_hoist(name) or is_zalgo(name)


def clean_name(name: str) -> str:
    """Срезать выпирающие символы с начала и залго-знаки."""
    out = ''.join(ch for ch in name if unicodedata.category(ch) != 'Mn')
    out = out.lstrip(''.join(chr(c) for c in range(0, HOIST_ORD)))
    out = out.strip()[:32].strip()
    return out or FALLBACK_NAME


def raid_candidates(members, now_ts: float, minutes: int):
    """Кто зашёл в окно [now - minutes*60, now]. Боты и админы — пропуск."""
    border = now_ts - max(1, minutes) * 60
    out = []
    for m in members:
        ja = getattr(m, 'joined_at', None)
        if ja is None or getattr(m, 'bot', False):
            continue
        try:
            ts = ja.replace(tzinfo=timezone.utc if ja.tzinfo is None else ja.tzinfo).timestamp()
        except Exception as _ex:
            _log.debug("raid_candidates(): подавлено: %s", _ex)
            continue
        if ts >= border:
            gp = getattr(m, 'guild_permissions', None)
            if gp is not None and getattr(gp, 'administrator', False):
                continue
            out.append(m)
    out.sort(key=lambda m: getattr(getattr(m, 'joined_at', None), 'timestamp', lambda: 0)())
    return out


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, type(default)):
                return data
    except Exception as _ex:
        _log.debug("_load_json(): подавлено: %s", _ex)
    return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def react_done(gid, mid) -> bool:
    return str(mid) in _load_json(REACT_PATH, {}).get(str(gid), [])


def react_mark(gid, mid):
    data = _load_json(REACT_PATH, {})
    lst = data.setdefault(str(gid), [])
    if str(mid) not in lst:
        lst.append(str(mid))
    data[str(gid)] = lst[-500:]          # окно памяти, чтобы файл не разрастался
    _save_json(REACT_PATH, data)


# ─────────────────────────────────────────────────────────────
# Ког
# ─────────────────────────────────────────────────────────────
class ModKit(commands.Cog):
    """Быстрые инструменты модератора."""

    GOLD = 0xD4AF37

    def __init__(self, bot):
        self.bot = bot

    def _now(self) -> int:
        return int(time.time())

    def _card(self, title: str, desc: str, color=None) -> discord.Embed:
        e = discord.Embed(title=title, description=desc,
                          color=color if color is not None else self.GOLD,
                          timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
        e.set_footer(text='Aether ModKit')
        return e

    async def _modlog(self, guild, title, fields, color=None):
        """Карточка в -модерация (best-effort)."""
        try:
            from cogs import logs
            ch = await logs.ensure_log_channel(guild, 'модерация')
            if not ch:
                return
            emb = logs._styled_log_embed(guild, 'модерация', title, fields=fields, color=color)
            await logs._safe_send(ch, embed=emb)
        except Exception as e:
            log.warning(f'ModKit: не удалось записать лог: {e}')

    # ── ⚡ варн реакцией ──────────────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        try:
            if payload.guild_id is None or self.bot.user is None:
                return
            if payload.user_id == self.bot.user.id:
                return
            if str(payload.emoji) not in REACT_EMOJIS:
                return
            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return
            member = payload.member or guild.get_member(payload.user_id)
            if member is None or member.bot:
                return
            if not member.guild_permissions.manage_messages:
                return                                # ⚠️ от обычных — не команда
            if react_done(guild.id, payload.message_id):
                return                                # по сообщению уже выдан варн

            channel = guild.get_channel(payload.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            target = getattr(message, 'author', None)
            if target is None or getattr(target, 'bot', False):
                return
            if getattr(target, 'guild_permissions', None) and target.guild_permissions.manage_messages:
                return                                # модов не варним
            if target.id == guild.owner_id:
                return

            wc = self.bot.get_cog('warnings')
            if wc is None or not hasattr(wc, 'add_warning'):
                log.error('ModKit: ког warnings не найден — реакт-варн пропущен')
                return
            snippet = (getattr(message, 'content', '') or '').strip().replace('\n', ' ')
            reason = '⚡-варн за сообщение' + (f': «{snippet[:90]}»' if snippet else '')
            await wc.add_warning(target, member, reason)
            react_mark(guild.id, payload.message_id)
            try:
                await message.add_reaction('✅')      # метка «варн зафиксирован»
            except Exception as _ex:
                _log.debug("on_raw_reaction_add(): подавлено: %s", _ex)
            log.info(f'ModKit: ⚡-варн {target} от {member} (сообщение {payload.message_id})')
        except Exception as e:
            log.error(f'ModKit: ошибка ⚡-варна: {e}')

    # ── ☢️ /nuke ──────────────────────────────────────────────
    @app_commands.command(name='nuke', description='Пересоздать канал начисто (все сообщения будут удалены)')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel='Какой канал пересоздать (по умолчанию текущий)',
                           confirm='Подтвердите: True — пересоздать безвозвратно')
    async def nuke(self, interaction: discord.Interaction,
                   channel: discord.TextChannel = None, confirm: bool = False):
        ch = channel or interaction.channel
        if not confirm:
            return await interaction.response.send_message(
                embed=self._card('☢️ Пересоздание канала',
                                 f'Канал {ch.mention} будет **удалён и создан заново** — все сообщения исчезнут.\n'
                                 'Права, категория и позиция сохранятся.\n\n'
                                 'Если уверены — повторите с `подтверждение: True`.', 0xE67E22),
                ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            new_ch = await ch.clone(reason=f'Nuke: {interaction.user}')
            try:
                await new_ch.edit(position=ch.position)
            except Exception as _ex:
                _log.debug("nuke(): подавлено: %s", _ex)
            old_name = ch.name
            await ch.delete(reason=f'Nuke: {interaction.user}')
            card = self._card('☢️ Канал пересоздан',
                              f'Канал **#{old_name}** начисто пересоздан модератором '
                              f'{interaction.user.mention}. Прежняя история удалена.')
            await new_ch.send(embed=card)
            await self._modlog(interaction.guild, 'Канал пересоздан (nuke)',
                               [('Канал', f'#{old_name}'), ('Модератор', str(interaction.user))])
            await interaction.followup.send(
                embed=self._card('✅ Готово', f'Канал **#{old_name}** пересоздан, сообщение-карточка отправлена.'),
                ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=self._card('⛔ Нет прав', 'Боту не хватает прав «Управление каналами».', 0xE74C3C),
                ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                embed=self._card('❌ Ошибка', f'Не удалось пересоздать канал: `{e}`', 0xE74C3C),
                ephemeral=True)

    # ── 🧹 /raidcleanup ───────────────────────────────────────
    @app_commands.command(name='raidcleanup',
                          description='Кик/бан всех, кто зашёл за последние N минут (антирейд)')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(minutes='Окно в минутах: кто зашёл позже этого срока',
                           action='Что сделать: кик (мягко) или бан (жёстко)',
                           confirm='Подтвердить массовое действие')
    @app_commands.choices(action=[
        app_commands.Choice(name='кик', value='kick'),
        app_commands.Choice(name='бан', value='ban'),
    ])
    async def raidcleanup(self, interaction: discord.Interaction,
                          minutes: app_commands.Range[int, 1, 1440] = 10,
                          action: app_commands.Choice[str] = None,
                          confirm: bool = False):
        act = action.value if isinstance(action, app_commands.Choice) else (action or 'kick')
        cands = raid_candidates(list(interaction.guild.members), time.time(), minutes)
        if not confirm:
            preview = '\n'.join(f'• {m.display_name} (`{m.id}`)' for m in cands[:8]) or '— никого'
            more = f'\n• …и ещё {len(cands) - 8}' if len(cands) > 8 else ''
            return await interaction.response.send_message(
                embed=self._card('🧹 Raid cleanup — предпросмотр',
                                 f'За последние **{minutes} мин** зашло кандидатов: **{len(cands)}** '
                                 f'(боты и админы пропущены).\n\n{preview}{more}\n\n'
                                 f'Действие при подтверждении: **{"кик" if act == "kick" else "бан"}**. '
                                 'Повторите с `подтверждение: True`.', 0xE67E22),
                ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        reason = f'Raid cleanup ({minutes} мин): {interaction.user}'
        ok, fail = 0, 0
        for m in cands:
            try:
                if act == 'ban':
                    await interaction.guild.ban(m, reason=reason, delete_message_days=1)
                else:
                    await m.kick(reason=reason)
                ok += 1
            except Exception:
                fail += 1
        card = self._card('🧹 Raid cleanup выполнен',
                          f'Окно: **{minutes} мин** · Действие: **{"бан" if act == "ban" else "кик"}**\n'
                          f'Обработано: **{ok}** · Не удалось: **{fail}**\n'
                          f'Модератор: {interaction.user.mention}')
        await self._modlog(interaction.guild, 'Raid cleanup',
                           [('Окно', f'{minutes} мин'), ('Действие', act),
                            ('Кандидатов', len(cands)), ('Успешно', ok), ('Ошибок', fail)],
                           color=0xE74C3C if act == 'ban' else 0xE67E22)
        await interaction.followup.send(embed=card, ephemeral=True)

    # ── 🧽 /dehoist ───────────────────────────────────────────
    @app_commands.command(name='dehoist',
                          description='Починить ники, «выпирающие» вверх списка (!, #, залго)')
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(simulate='True — только показать, кого переименуем (по умолчанию да)')
    async def dehoist(self, interaction: discord.Interaction, simulate: bool = True):
        flagged = []
        for m in interaction.guild.members:
            if m.bot:
                continue
            disp = m.display_name
            if not needs_clean(disp):
                continue
            new = clean_name(disp)
            if new != disp:
                flagged.append((m, new))
        if simulate:
            preview = '\n'.join(f'• `{m.display_name}` → **{n}**' for m, n in flagged[:10]) or '— чисто!'
            more = f'\n• …и ещё {len(flagged) - 10}' if len(flagged) > 10 else ''
            return await interaction.response.send_message(
                embed=self._card('🧽 Dehoist — симуляция',
                                 f'Найдено «выпирающих»/залго ников: **{len(flagged)}**\n\n{preview}{more}\n\n'
                                 'Применить: повторите с `симуляция: False`.'),
                ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, fail = 0, 0
        for m, new in flagged:
            try:
                await m.edit(nick=new, reason=f'Dehoist: {interaction.user}')
                ok += 1
            except Exception:
                fail += 1
        card = self._card('🧽 Dehoist завершён',
                          f'Переименовано: **{ok}** · Не удалось (права/иерархия): **{fail}**\n'
                          f'Модератор: {interaction.user.mention}')
        await self._modlog(interaction.guild, 'Dehoist ников',
                           [('Найдено', len(flagged)), ('Переименовано', ok), ('Ошибок', fail)])
        await interaction.followup.send(embed=card, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModKit(bot))
