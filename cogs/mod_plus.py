"""
Mod Plus — набор «быстрых» инструментов модератора:

• /snipe [канал]      — последнее УДАЛЁННОЕ сообщение канала (кто/что/когда),
                        включая вложения. Классика против «написал и стёр».
• /editsnipe [канал]  — последнее ОТРЕДАКТИРОВАННОЕ сообщение (каким было).
• /stick <текст>      — «липкое» сообщение: бот держит его последней строкой
                        канала (пересылает при новых сообщениях).
• /unstick [канал]    — отклеить.
• /sticklist          — все липкие сообщения сервера.
• /panic on|off|status — паника-кнопка рейда: мгновенно запрещает @everyone
                        писать во ВСЕХ текстовых каналах (с сохранением и
                        точным восстановлением прежних прав), опционально
                        поднимает уровень проверки сервера.
• /ghostmute <юзер> [время] [причина] — «тихий мут»: сообщения нарушителя
                        мгновенно и НЕЗАМЕТНО исчезают — он думает, что его
                        видно, а чат чист. Без таймаута и лишнего шума.
• /ghostunmute <юзер> — снять тихий мут.
• /ghostlist          — все «призраки» сервера.

Хранение: data/modplus_sticky_{gid}.json, data/modplus_panic_{gid}.json,
data/modplus_ghost_{gid}.json.
Snipe-буфер — только в памяти (перезапуск очищает, это ок: свежие события).
"""

from logger import get_logger

_log = get_logger("mod_plus")

import json
import os
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger("mod_plus")
from json_store import load_json as _js_load, save_json as _js_save

GOLD = 0xD4AF37
RED = 0xE74C3C
GREEN = 0x2ECC71

STICKY_REPOST_COOLDOWN = 3.0   # сек между пересылками липкого сообщения
GHOST_LOG_INTERVAL = 60.0      # сек между отчётами о призраке в мод-лог
GHOST_MAX_DAYS = 90            # максимальная длительность тихого мута
_SNYPE_EMPTY = '*(текста не было — только вложение)*'


def _sticky_path(gid): return f'data/modplus_sticky_{gid}.json'
def _panic_path(gid): return f'data/modplus_panic_{gid}.json'
def _ghost_path(gid): return f'data/modplus_ghost_{gid}.json'


def _load_json(path, default):
    return _js_load(path, default, log=_log)


def _save_json(path, data):
    # атомарно + кеш — дальше читаем уже не с диска
    ok = _js_save(path, data, log=_log)
    if not ok:
        log.warning(f"[MOD+] запись {path}: см. json_store warning")
    return ok


def _now():
    return datetime.now(timezone.utc)


# ════════════════════════ GHOST MUTE (тихий мут) ════════════════════════
def ghost_entry_active(entry) -> bool:
    """Запись ещё действует? until=None — бессрочно."""
    until = (entry or {}).get('until')
    if not until:
        return True
    try:
        return datetime.fromisoformat(until) > _now()
    except (TypeError, ValueError):
        return True  # кривая дата ≠ повод отпустить — считаем активной


def ghost_entries(gid) -> dict:
    """Загрузить призраков сервера, попутно сняв истёкшие сроки (лениво)."""
    path = _ghost_path(gid)
    data = _load_json(path, {})
    expired = [uid for uid, e in data.items() if not ghost_entry_active(e)]
    if expired:
        for uid in expired:
            data.pop(uid, None)
        _save_json(path, data)
    return data


def ghost_add(gid, uid, reason='', by='', until=None) -> dict:
    """Добавить/обновить призрака. until — ISO-строка или None (бессрочно)."""
    path = _ghost_path(gid)
    data = _load_json(path, {})
    entry = {
        'user_id': int(uid),
        'reason': (reason or '')[:300],
        'by': by or '',
        'set_at': _now().isoformat(),
        'until': until,
        'suppressed': 0,
    }
    data[str(uid)] = entry
    _save_json(path, data)
    return entry


def ghost_remove(gid, uid):
    """Снять призрака. Возвращает запись или None, если его не было."""
    path = _ghost_path(gid)
    data = _load_json(path, {})
    entry = data.pop(str(uid), None)
    if entry is not None:
        _save_json(path, data)
    return entry


def parse_ghost_duration(text):
    """'30м', '2ч', '1д 12ч' → секунды. None/пусто — бессрочно.
    Возвращает (seconds|None, error|None)."""
    if not (text or '').strip():
        return None, None
    from cogs.temp_moderation import parse_duration
    sec = parse_duration(text)
    if not sec:
        return None, 'Не понял время. Формат: `30м`, `2ч`, `1д 12ч`, `1 нед`'
    if sec > GHOST_MAX_DAYS * 86400:
        return None, f'Слишком надолго — максимум {GHOST_MAX_DAYS} дней'
    return sec, None


class ModPlus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id -> dict записи; только оперативная память
        self._snipe_deleted = {}
        self._snipe_edited = {}
        self._last_sticky_repost = {}   # channel_id -> ts (анти-баунс)
        self._ghost_last_log = {}       # (gid, uid) -> ts последнего отчёта в мод-лог
        self._ghost_perm_warn = {}      # ('perm', gid) -> ts (троттлинг варнингов о правах)

    # ════════════════════════ SNIPE ════════════════════════
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        try:
            if not message.guild or getattr(message.author, 'bot', False):
                return
            self._snipe_deleted[message.channel.id] = {
                'author': str(message.author),
                'author_id': getattr(message.author, 'id', 0),
                'avatar': str(getattr(message.author.display_avatar, 'url', '')),
                'content': (message.content or '')[:1800],
                'attachments': [getattr(a, 'url', '') for a in (message.attachments or [])][:4],
                'ts': _now().isoformat(),
                'channel_id': message.channel.id,
                'channel_name': getattr(message.channel, 'name', '?'),
            }
        except Exception as _ex:
            _log.debug("on_message_delete(): подавлено: %s", _ex)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        try:
            if not before.guild or getattr(before.author, 'bot', False):
                return
            if (before.content or '') == (after.content or ''):
                return  # правка эмбеда/супресс ссылок — не интересно
            self._snipe_edited[before.channel.id] = {
                'author': str(before.author),
                'author_id': getattr(before.author, 'id', 0),
                'avatar': str(getattr(before.author.display_avatar, 'url', '')),
                'before': (before.content or '')[:900],
                'after': (after.content or '')[:900],
                'ts': _now().isoformat(),
                'channel_id': before.channel.id,
                'channel_name': getattr(before.channel, 'name', '?'),
                'jump_url': getattr(after, 'jump_url', ''),
            }
        except Exception as _ex:
            _log.debug("on_message_edit(): подавлено: %s", _ex)

    def _snipe_embed(self, entry, kind):
        e = discord.Embed(color=GOLD if kind == 'del' else 0x3498DB,
                          timestamp=_now())
        title = '🕵️ Последнее удалённое сообщение' if kind == 'del' else '✏️ Последняя правка'
        e.set_author(name=f"{title} · #{entry.get('channel_name', '?')}",
                     icon_url=entry.get('avatar') or None)
        if kind == 'del':
            content = entry.get('content') or _SNYPE_EMPTY
            e.description = f"**{entry['author']}:**\n>>> {content}"
            for u in (entry.get('attachments') or [])[:1]:
                if u:
                    e.set_image(url=u)
            left = ', '.join(u for u in (entry.get('attachments') or [])[1:] if u)
            if left:
                e.add_field(name='Остальные вложения', value=left[:1000], inline=False)
        else:
            e.description = f"**{entry['author']}** изменил сообщение"
            e.add_field(name='Было', value=f">>> {entry.get('before') or _SNYPE_EMPTY}"[:1024], inline=False)
            e.add_field(name='Стало', value=f">>> {entry.get('after') or _SNYPE_EMPTY}"[:1024], inline=False)
            if entry.get('jump_url'):
                e.add_field(name='Ссылка', value=f"[Перейти к сообщению]({entry['jump_url']})", inline=False)
        ts = entry.get('ts', '')
        if ts:
            try:
                t = int(datetime.fromisoformat(ts).timestamp())
                e.description = (e.description or '') + f"\n\n*🕐 поймано <t:{t}:R>*"
            except Exception as _ex:
                _log.debug("_snipe_embed(): подавлено: %s", _ex)
        return e

    @app_commands.command(name='snipe', description='Показать последнее удалённое сообщение канала')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(channel='Канал (по умолчанию текущий)')
    async def snipe(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        ch = channel or interaction.channel
        entry = self._snipe_deleted.get(ch.id)
        if not entry:
            await interaction.response.send_message(
                f"🕳️ В #{getattr(ch, 'name', '?')} пока ничего не поймали — буфер пуст.",
                ephemeral=True)
            return
        await interaction.response.send_message(embed=self._snipe_embed(entry, 'del'))

    @app_commands.command(name='editsnipe', description='Показать последнюю правку сообщения в канале')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(channel='Канал (по умолчанию текущий)')
    async def editsnipe(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        ch = channel or interaction.channel
        entry = self._snipe_edited.get(ch.id)
        if not entry:
            await interaction.response.send_message(
                f"🕳️ В #{getattr(ch, 'name', '?')} правок не поймали — буфер пуст.",
                ephemeral=True)
            return
        await interaction.response.send_message(embed=self._snipe_embed(entry, 'edit'))

    # ════════════════════════ STICKY ════════════════════════
    def _stickies(self, gid: int) -> dict:
        return _load_json(_sticky_path(gid), {})

    def _save_stickies(self, gid: int, data: dict):
        _save_json(_sticky_path(gid), data)

    async def _repost_sticky(self, guild, channel, entry):
        """Удалить старое липкое и отправить свежим последним сообщением."""
        old_id = entry.get('msg_id')
        if old_id:
            try:
                old = await channel.fetch_message(int(old_id))
                await old.delete()
            except Exception as _ex:
                _log.debug("_repost_sticky(): подавлено: %s", _ex)
        e = discord.Embed(description=f"📌 {entry['text']}", color=GOLD)
        e.set_footer(text='Липкое сообщение · /unstick чтобы отклеить')
        msg = await channel.send(embed=e)
        entry['msg_id'] = msg.id
        entry['bumped_at'] = _now().isoformat()
        self._save_stickies(guild.id, self._get_stickies_for_save(guild.id, channel.id, entry))

    def _get_stickies_for_save(self, gid, cid, entry):
        data = self._stickies(gid)
        data[str(cid)] = entry
        return data

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if not message.guild or message.author.bot:
                return
            # сначала призраки: их сообщения исчезают, липкое на них не реагируем
            if await self._handle_ghost_message(message):
                return
            entry = self._stickies(message.guild.id).get(str(message.channel.id))
            if not entry:
                return
            now = time.monotonic()
            last = self._last_sticky_repost.get(message.channel.id, 0)
            if now - last < STICKY_REPOST_COOLDOWN:
                return  # анти-баунс при флуде: липкое не чаще раза в 3 сек
            self._last_sticky_repost[message.channel.id] = now
            await self._repost_sticky(message.guild, message.channel, dict(entry))
        except discord.Forbidden as _ex:
            _log.debug("on_message(): подавлено: %s", _ex)
        except Exception as e:
            log.warning(f"[MOD+] sticky repost: {e}")

    @app_commands.command(name='stick', description='Закрепить «липкое» сообщение внизу канала')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(text='Текст липкого сообщения', channel='Канал (по умолчанию текущий)')
    async def stick(self, interaction: discord.Interaction, text: str,
                    channel: discord.TextChannel = None):
        ch = channel or interaction.channel
        text = (text or '').strip()
        if not text or len(text) > 1900:
            await interaction.response.send_message('⚠️ Текст пустой или длиннее 1900 символов.',
                                                    ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)  # удаление+пересылка могут занять >3 сек
        data = self._stickies(interaction.guild.id)
        old = data.get(str(ch.id))
        if old and old.get('msg_id'):  # убрать прежнее липкое, если было
            try:
                msg = await ch.fetch_message(int(old['msg_id']))
                await msg.delete()
            except Exception as _ex:
                _log.debug("stick(): подавлено: %s", _ex)
        entry = {'text': text, 'msg_id': None,
                 'author_id': interaction.user.id, 'set_at': _now().isoformat()}
        data[str(ch.id)] = entry
        self._save_stickies(interaction.guild.id, data)
        # сразу показываем свежим сообщением
        await self._repost_sticky(interaction.guild, ch, entry)
        await interaction.followup.send(f"📌 Липкое закреплено в {ch.mention}.", ephemeral=True)

    @app_commands.command(name='unstick', description='Отклеить липкое сообщение в канале')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(channel='Канал (по умолчанию текущий)')
    async def unstick(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        ch = channel or interaction.channel
        data = self._stickies(interaction.guild.id)
        entry = data.pop(str(ch.id), None)
        if not entry:
            await interaction.response.send_message(f"ℹ️ В {ch.mention} нет липкого сообщения.",
                                                    ephemeral=True)
            return
        if entry.get('msg_id'):
            try:
                msg = await ch.fetch_message(int(entry['msg_id']))
                await msg.delete()
            except Exception as _ex:
                _log.debug("unstick(): подавлено: %s", _ex)
        self._save_stickies(interaction.guild.id, data)
        await interaction.response.send_message(f"🗑️ Липкое убрано из {ch.mention}.", ephemeral=True)

    @app_commands.command(name='sticklist', description='Список липких сообщений сервера')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticklist(self, interaction: discord.Interaction):
        data = self._stickies(interaction.guild.id)
        if not data:
            await interaction.response.send_message('📌 Липких сообщений нет.', ephemeral=True)
            return
        lines = []
        for cid, entry in data.items():
            ch = interaction.guild.get_channel(int(cid))
            lines.append(f"• {ch.mention if ch else f'`#{cid}`'} — {(entry.get('text') or '')[:80]}")
        e = discord.Embed(title='📌 Липкие сообщения', description='\n'.join(lines)[:4000],
                          color=GOLD)
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── Управление из веб-панели (вызывается через bot.loop) ───────────
    async def repost_remote(self, guild, channel_id):
        """Панель создала/обновила липкое — мгновенно переслать его в канал."""
        ch = guild.get_channel(int(channel_id))
        entry = self._stickies(guild.id).get(str(channel_id))
        if not ch or not entry:
            return False
        await self._repost_sticky(guild, ch, dict(entry))
        return True

    async def delete_sticky_message_remote(self, guild, channel_id, msg_id):
        """Панель удалила липкое — убрать последнее сообщение бота из канала."""
        ch = guild.get_channel(int(channel_id))
        if not ch or not msg_id:
            return False
        try:
            msg = await ch.fetch_message(int(msg_id))
            await msg.delete()
            return True
        except Exception:
            return False

    # ════════════════════════ GHOST MUTE ════════════════════════
    def _warn_no_delete_perm(self, message):
        """Прав на удаление нет — предупредить в консоль, но не чаще раза в 5 мин."""
        key = message.guild.id
        now = time.monotonic()
        if now - self._ghost_perm_warn.get(key, -1e9) < 300:
            return
        self._ghost_perm_warn[key] = now
        log.warning(f'[MOD+] ghost: нет прав «Управление сообщениями» на сервере '
                    f'{message.guild.id} — дайте боту право, иначе тихий мут не работает')

    async def _handle_ghost_message(self, message) -> bool:
        """Если автор — призрак: тихо убрать сообщение, посчитать, доложить в мод-лог.

        Возвращает True, если сообщение поглощено (дальше его не обрабатываем).
        """
        gid = message.guild.id
        data = _load_json(_ghost_path(gid), {})
        entry = data.get(str(message.author.id))
        if entry is None:
            return False
        if not ghost_entry_active(entry):
            # срок вышел — ленивый авто-съём, это сообщение пропускаем
            data.pop(str(message.author.id), None)
            _save_json(_ghost_path(gid), data)
            return False
        try:
            await message.delete()
        except discord.NotFound:
            return True   # уже удалено — считаем поглощённым
        except discord.Forbidden:
            self._warn_no_delete_perm(message)
            return True   # sticky/прочее на это сообщение всё равно не реагируют
        except Exception as e:
            log.warning(f'[MOD+] ghost delete: {e}')
            return True
        entry['suppressed'] = int(entry.get('suppressed') or 0) + 1
        # счётчик на диск порциями — не переписывать файл на каждое сообщение
        if entry['suppressed'] == 1 or entry['suppressed'] % 10 == 0:
            data[str(message.author.id)] = entry
            _save_json(_ghost_path(gid), data)
        await self._ghost_modlog(message, entry)
        return True

    async def _ghost_modlog(self, message, entry):
        """Отчёт в мод-лог: что призрак пытался написать.

        С троттлингом GHOST_LOG_INTERVAL на юзера — флуд призрака не ДДоСит лог,
        но модеры видят его активность (первое сообщение после паузы + счётчик).
        """
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if now - self._ghost_last_log.get(key, -1e9) < GHOST_LOG_INTERVAL:
            return
        self._ghost_last_log[key] = now
        try:
            from cogs import logs as _logs
            ch = await _logs.ensure_log_channel(message.guild, 'mod')
            if not ch:
                return
            content = (message.content or '').strip()
            if not content and getattr(message, 'attachments', None):
                content = f'[вложений: {len(message.attachments)}]'
            e = _logs._styled_log_embed(
                message.guild, 'mod', '👻 Тихий мут: сообщение скрыто',
                fields=[
                    ('Призрак', f'{message.author.mention} (`{message.author.id}`)'),
                    ('Канал', message.channel.mention),
                    ('Скрытое сообщение', (content or _SNYPE_EMPTY)[:900]),
                    ('Подавлено всего', str(entry.get('suppressed', 1))),
                ],
                color=0x9B59B6,
                note='Снять: /ghostunmute — он ничего не заметил.')
            await _logs._safe_send(ch, embed=e)
        except Exception as e:
            log.warning(f'[MOD+] ghost modlog: {e}')

    def _ghost_refusal(self, interaction, user):
        """Причина отказа в тихом муте или None, если всё чисто."""
        if getattr(user, 'bot', False):
            return '🤖 Ботов призраками не делаем — у них и так всё честно.'
        if user.id == interaction.user.id:
            return 'Себя замутить нельзя 🙂'
        owner_id = getattr(interaction.guild, 'owner_id', None)
        if owner_id and user.id == owner_id:
            return 'Владельца сервера тихо мутить нельзя.'
        perms = getattr(user, 'guild_permissions', None)
        if perms is not None and perms.manage_messages:
            return ('У него права модератора — тихий мут на состав не работает '
                    '(бот не удалит сообщения модераторов).')
        return None

    @app_commands.command(name='ghostmute',
                          description='Тихий мут: сообщения юзера мгновенно и незаметно исчезают')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user='Кого прячем',
                           duration='Время: 30м, 2ч, 1д 12ч (пусто — бессрочно)',
                           reason='Причина (видна только составу)')
    async def ghostmute(self, interaction: discord.Interaction, user: discord.Member,
                        duration: str = None, reason: str = None):
        refusal = self._ghost_refusal(interaction, user)
        if refusal:
            await interaction.response.send_message(f'⚠️ {refusal}', ephemeral=True)
            return
        sec, err = parse_ghost_duration(duration)
        if err:
            await interaction.response.send_message(f'⚠️ {err}', ephemeral=True)
            return
        until = (_now() + timedelta(seconds=sec)).isoformat() if sec else None
        ghost_add(interaction.guild.id, user.id, reason or '—',
                  by=str(interaction.user), until=until)
        if until:
            from cogs.temp_moderation import format_duration
            term_txt = f'{format_duration(sec)} (до {until[:16].replace("T", " ")})'
        else:
            term_txt = 'бессрочно'
        e = discord.Embed(title='👻 Тихий мут включён', color=0x9B59B6, timestamp=_now())
        e.add_field(name='Кто', value=f'{user.mention} (`{user.id}`)', inline=True)
        e.add_field(name='Срок', value=term_txt, inline=True)
        e.add_field(name='Причина', value=reason or '—', inline=False)
        e.set_footer(text='Его сообщения теперь исчезают мгновенно — он не узнает')
        await interaction.response.send_message(embed=e, ephemeral=True)
        log_e = discord.Embed(title='👻 Тихий мут включён', color=0x9B59B6, timestamp=_now())
        log_e.add_field(name='Кто', value=f'{user.mention} (`{user.id}`)', inline=True)
        log_e.add_field(name='Модератор', value=str(interaction.user), inline=True)
        log_e.add_field(name='Срок', value=term_txt, inline=True)
        log_e.add_field(name='Причина', value=reason or '—', inline=False)
        await self._notify_mod_log(interaction.guild, log_e)

    @app_commands.command(name='ghostunmute', description='Снять тихий мут')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user='Кого возвращаем')
    async def ghostunmute(self, interaction: discord.Interaction, user: discord.Member):
        entry = ghost_remove(interaction.guild.id, user.id)
        if not entry:
            await interaction.response.send_message(
                'Он не был призраком — проверь `/ghostlist`.', ephemeral=True)
            return
        e = discord.Embed(title='👻 Тихий мут снят', color=GREEN, timestamp=_now())
        e.add_field(name='Кто', value=f'{user.mention} (`{user.id}`)', inline=True)
        e.add_field(name='Было скрыто сообщений',
                    value=str(entry.get('suppressed') or 0), inline=True)
        e.add_field(name='Причина мута была', value=(entry.get('reason') or '—')[:300],
                    inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)
        log_e = discord.Embed(title='👻 Тихий мут снят', color=GREEN, timestamp=_now())
        log_e.add_field(name='Кто', value=f'{user.mention} (`{user.id}`)', inline=True)
        log_e.add_field(name='Модератор', value=str(interaction.user), inline=True)
        await self._notify_mod_log(interaction.guild, log_e)

    @app_commands.command(name='ghostlist', description='Все «призраки» сервера (тихий мут)')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ghostlist(self, interaction: discord.Interaction):
        data = ghost_entries(interaction.guild.id)
        e = discord.Embed(title='👻 Призраки сервера', color=GOLD, timestamp=_now())
        if not data:
            e.description = 'Призраков нет — все видят, что пишут 😌'
        else:
            lines = []
            for uid, entry in list(data.items())[:15]:
                member = interaction.guild.get_member(int(uid))
                name = str(member) if member else f'ID `{uid}`'
                until = entry.get('until')
                term = f'до {until[:16].replace("T", " ")}' if until else 'бессрочно'
                lines.append(f'• **{name}** — {term} · скрыто: '
                             f'{entry.get("suppressed") or 0} · {entry.get("reason") or "—"}')
            e.description = '\n'.join(lines)
            if len(data) > 15:
                e.set_footer(text=f'…и ещё {len(data) - 15}')
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ════════════════════════ PANIC ════════════════════════
    panic = app_commands.Group(name='panic', description='Паника-кнопка локдауна сервера')

    async def _notify_mod_log(self, guild, embed):
        """Крикнуть в лог-канал модерации (сам себя создаст при нужде)."""
        try:
            from cogs.logs import ensure_log_channel
            ch = await ensure_log_channel(guild, 'mod')
            if ch:
                await ch.send(embed=embed)
        except Exception as e:
            log.warning(f"[MOD+] panic: не удалось написать в лог: {e}")

    async def panic_enable_core(self, guild, reason, boost_verification=False, by=''):
        """Ядро локдауна: закрыть каналы, сохранить прежние права, отчитаться.
        Возвращает (state, done, failed) или (None, 0, 0), если уже активен.
        Используется и slash-командой, и веб-панелью."""
        state_path = _panic_path(guild.id)
        if os.path.exists(state_path):
            return None, 0, 0
        state = {'active': True, 'reason': (reason or '')[:300],
                 'by': by, 'started_at': _now().isoformat(),
                 'channels': {}, 'verification': None}

        done, failed = 0, 0
        everyone = guild.default_role
        for ch in guild.text_channels:
            try:
                current = ch.overwrites_for(everyone).send_messages  # None/True/False
                state['channels'][str(ch.id)] = {'send_messages':
                                                 None if current is None else bool(current)}
                await ch.set_permissions(everyone, send_messages=False,
                                         reason=f'PANIC локдаун: {reason}')
                done += 1
            except Exception as e:
                failed += 1
                log.warning(f"[MOD+] panic: #{getattr(ch, 'name', '?')}: {e}")

        if boost_verification:
            try:
                cur = guild.verification_level
                if cur.value < discord.VerificationLevel.high.value:
                    state['verification'] = cur.value  # int — надёжно для восстановления
                    await guild.edit(verification_level=discord.VerificationLevel.high,
                                     reason=f'PANIC локдаун: {reason}')
            except Exception as e:
                log.warning(f"[MOD+] panic: verification: {e}")

        _save_json(state_path, state)

        e = discord.Embed(title='🚨 PANIC: локдаун включён', color=RED, timestamp=_now())
        e.description = f"**Причина:** {reason}"
        e.add_field(name='Закрыто каналов', value=f'`{done}`', inline=True)
        e.add_field(name='Не удалось', value=f'`{failed}`', inline=True)
        e.add_field(name='Проверка сервера',
                    value='`поднята до High`' if state['verification'] is not None else '`не менялась`',
                    inline=True)
        e.add_field(name='Откат', value='`/panic off` или кнопка в панели — вернёт прежние права.',
                    inline=False)
        e.set_footer(text=f'Включил: {by or "?"}')
        await self._notify_mod_log(guild, e)
        log.warning(f"[MOD+] PANIC ON ({guild.name}): {done} каналов, by {by}")
        return state, done, failed

    async def panic_disable_core(self, guild, by=''):
        """Ядро отката локдауна. (state, done, failed) или (None, 0, 0)."""
        state_path = _panic_path(guild.id)
        state = _load_json(state_path, None)
        if not state:
            return None, 0, 0

        done, failed = 0, 0
        everyone = guild.default_role
        for cid, prev in (state.get('channels') or {}).items():
            ch = guild.get_channel(int(cid))
            if not ch:
                continue
            try:
                await ch.set_permissions(everyone, send_messages=prev.get('send_messages'),
                                         reason='PANIC откат локдауна')
                done += 1
            except Exception as e:
                failed += 1
                log.warning(f"[MOD+] panic off: #{cid}: {e}")

        if state.get('verification') is not None:
            try:
                lvl = discord.VerificationLevel(int(state['verification']))
                await guild.edit(verification_level=lvl, reason='PANIC откат локдауна')
            except Exception as e:
                log.warning(f"[MOD+] panic off: verification: {e}")

        try:
            os.remove(state_path)
        except Exception as _ex:
            _log.debug("panic_disable_core(): подавлено: %s", _ex)

        e = discord.Embed(title='✅ PANIC: локдаун снят', color=GREEN, timestamp=_now())
        e.description = f"Длился с: `{state.get('started_at', '?')}`\nПричина была: {state.get('reason', '—')}"
        e.add_field(name='Восстановлено каналов', value=f'`{done}`', inline=True)
        e.add_field(name='Не удалось', value=f'`{failed}`', inline=True)
        e.set_footer(text=f'Снял: {by or "?"}')
        await self._notify_mod_log(guild, e)
        log.warning(f"[MOD+] PANIC OFF ({guild.name}): восстановлено {done}, by {by}")
        return state, done, failed

    @panic.command(name='on', description='ЛОКДАУН: запретить @everyone писать во всех текстовых каналах')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(reason='Причина локдауна',
                           confirm='Подтверждение (True) — защита от случайного запуска',
                           boost_verification='Также поднять уровень проверки сервера до High')
    async def panic_on(self, interaction: discord.Interaction, reason: str = 'Антирейд-локдаун',
                       confirm: bool = False, boost_verification: bool = False):
        if not confirm:
            await interaction.response.send_message(
                '⚠️ **Локдаун ВСЕХ текстовых каналов.** Запустите снова с параметром '
                '`confirm: True`. Откат — `/panic off`.', ephemeral=True)
            return
        if os.path.exists(_panic_path(interaction.guild.id)):
            await interaction.response.send_message(
                '🚨 Локдаун уже активен. Сначала `/panic off`, если хотите перезапустить.',
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        state, done, failed = await self.panic_enable_core(
            interaction.guild, reason, boost_verification=boost_verification,
            by=str(interaction.user))

        e = discord.Embed(title='🚨 PANIC: локдаун включён', color=RED, timestamp=_now())
        e.description = f"**Причина:** {reason}"
        e.add_field(name='Закрыто каналов', value=f'`{done}`', inline=True)
        e.add_field(name='Не удалось', value=f'`{failed}`', inline=True)
        e.add_field(name='Откат', value='`/panic off`', inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @panic.command(name='off', description='Откатить локдаун — вернуть прежние права каналам')
    @app_commands.checks.has_permissions(administrator=True)
    async def panic_off(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state, done, failed = await self.panic_disable_core(interaction.guild,
                                                            by=str(interaction.user))
        if state is None:
            await interaction.followup.send('ℹ️ Локдаун не активен — нечего откатывать.',
                                            ephemeral=True)
            return

        e = discord.Embed(title='✅ PANIC: локдаун снят', color=GREEN, timestamp=_now())
        e.description = f"Длился с: `{state.get('started_at', '?')}`\nПричина была: {state.get('reason', '—')}"
        e.add_field(name='Восстановлено каналов', value=f'`{done}`', inline=True)
        e.add_field(name='Не удалось', value=f'`{failed}`', inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @panic.command(name='status', description='Активен ли локдаун и когда включён')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panic_status(self, interaction: discord.Interaction):
        state = _load_json(_panic_path(interaction.guild.id), None)
        if not state:
            await interaction.response.send_message('🟢 Локдаун не активен.', ephemeral=True)
            return
        e = discord.Embed(title='🚨 Локдаун АКТИВЕН', color=RED, timestamp=_now())
        _by = state.get('by')
        _by_txt = f'<@{_by}>' if str(_by or '').isdigit() else f'`{_by or "?"}'
        e.add_field(name='Включён', value=f"`{state.get('started_at', '?')}`", inline=True)
        e.add_field(name='Кем', value=_by_txt, inline=True)
        e.add_field(name='Каналов под замком', value=f"`{len(state.get('channels') or {})}`",
                    inline=True)
        e.add_field(name='Причина', value=state.get('reason', '—'), inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModPlus(bot))
    log.info("[MOD+] Ког загружен (snipe / sticky / ghost / panic)")
