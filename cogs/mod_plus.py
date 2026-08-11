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

Хранение: data/modplus_sticky_{gid}.json, data/modplus_panic_{gid}.json.
Snipe-буфер — только в памяти (перезапуск очищает, это ок: свежие события).
"""
import json
import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger("mod_plus")

GOLD = 0xD4AF37
RED = 0xE74C3C
GREEN = 0x2ECC71

STICKY_REPOST_COOLDOWN = 3.0   # сек между пересылками липкого сообщения
_SNYPE_EMPTY = '*(текста не было — только вложение)*'


def _sticky_path(gid): return f'data/modplus_sticky_{gid}.json'
def _panic_path(gid): return f'data/modplus_panic_{gid}.json'


def _load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f) or default
    except Exception:
        return default


def _save_json(path, data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # атомарно: ни одного полу-записанного файла
        return True
    except Exception as e:
        log.warning(f"[MOD+] запись {path}: {e}")
        return False


def _now():
    return datetime.now(timezone.utc)


class ModPlus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id -> dict записи; только оперативная память
        self._snipe_deleted = {}
        self._snipe_edited = {}
        self._last_sticky_repost = {}   # channel_id -> ts (анти-баунс)

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
        except Exception:
            pass

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
        except Exception:
            pass

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
            except Exception:
                pass
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
            except Exception:
                pass  # уже удалено/нет доступа — просто шлём новое
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
            entry = self._stickies(message.guild.id).get(str(message.channel.id))
            if not entry:
                return
            now = time.monotonic()
            last = self._last_sticky_repost.get(message.channel.id, 0)
            if now - last < STICKY_REPOST_COOLDOWN:
                return  # анти-баунс при флуде: липкое не чаще раза в 3 сек
            self._last_sticky_repost[message.channel.id] = now
            await self._repost_sticky(message.guild, message.channel, dict(entry))
        except discord.Forbidden:
            pass  # нет прав писать/удалять в канале — молчим
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
            except Exception:
                pass
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
            except Exception:
                pass
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
        state_path = _panic_path(interaction.guild.id)
        if os.path.exists(state_path):
            await interaction.response.send_message(
                '🚨 Локдаун уже активен. Сначала `/panic off`, если хотите перезапустить.',
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        state = {'active': True, 'reason': (reason or '')[:300],
                 'by': interaction.user.id, 'started_at': _now().isoformat(),
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
                    value='`поднята до High`' if state['verification'] else '`не менялась`',
                    inline=True)
        e.add_field(name='Откат', value='`/panic off` — вернёт всем прежние права.', inline=False)
        e.set_footer(text=f'Включил: {interaction.user}')
        await self._notify_mod_log(guild, e)
        await interaction.followup.send(embed=e, ephemeral=True)
        log.warning(f"[MOD+] PANIC ON ({guild.name}): {done} каналов, by {interaction.user}")

    @panic.command(name='off', description='Откатить локдаун — вернуть прежние права каналам')
    @app_commands.checks.has_permissions(administrator=True)
    async def panic_off(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        state_path = _panic_path(guild.id)
        state = _load_json(state_path, None)
        if not state:
            await interaction.followup.send('ℹ️ Локдаун не активен — нечего откатывать.',
                                            ephemeral=True)
            return

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
        except Exception:
            pass

        e = discord.Embed(title='✅ PANIC: локдаун снят', color=GREEN, timestamp=_now())
        e.description = f"Длился с: `{state.get('started_at', '?')}`\nПричина была: {state.get('reason', '—')}"
        e.add_field(name='Восстановлено каналов', value=f'`{done}`', inline=True)
        e.add_field(name='Не удалось', value=f'`{failed}`', inline=True)
        e.set_footer(text=f'Снял: {interaction.user}')
        await self._notify_mod_log(guild, e)
        await interaction.followup.send(embed=e, ephemeral=True)
        log.warning(f"[MOD+] PANIC OFF ({guild.name}): восстановлено {done}, by {interaction.user}")

    @panic.command(name='status', description='Активен ли локдаун и когда включён')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panic_status(self, interaction: discord.Interaction):
        state = _load_json(_panic_path(interaction.guild.id), None)
        if not state:
            await interaction.response.send_message('🟢 Локдаун не активен.', ephemeral=True)
            return
        e = discord.Embed(title='🚨 Локдаун АКТИВЕН', color=RED, timestamp=_now())
        e.add_field(name='Включён', value=f"`{state.get('started_at', '?')}`", inline=True)
        e.add_field(name='Кем', value=f"<@{state.get('by', 0)}>", inline=True)
        e.add_field(name='Каналов под замком', value=f"`{len(state.get('channels') or {})}`",
                    inline=True)
        e.add_field(name='Причина', value=state.get('reason', '—'), inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModPlus(bot))
    log.info("[MOD+] Ког загружен (snipe / sticky / panic)")
