"""
Starboard — зал славы (звёздная доска).

Панель (/starboard) сохраняет настройки в data/starboard_settings_{gid}.json:
  {channel_id, emoji (по умолч. ⭐), min_stars (по умолч. 3)}

Сообщение, набравшее нужное число реакций-звёзд, публикуется в канал
зала славы; при изменении числа звёзд счётчик обновляется.
"""
import os
import json
import discord
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("starboard")

GOLD = 0xD4AF37


def _settings_path(gid): return f'data/starboard_settings_{gid}.json'
def _posted_path(gid): return f'data/starboard_posted_{gid}.json'


class Starboard(commands.Cog):
    """Публикует звёздные сообщения в канал зала славы."""

    def __init__(self, bot):
        self.bot = bot

    # ────────────────────────────────────────────────────────────
    def _settings(self, guild_id: int) -> dict:
        cfg = {'channel_id': 0, 'emoji': '⭐', 'min_stars': 3}
        try:
            with open(_settings_path(guild_id), 'r', encoding='utf-8') as f:
                cfg.update(json.load(f) or {})
        except Exception:
            pass
        try:
            cfg['min_stars'] = max(1, int(cfg.get('min_stars', 3)))
        except Exception:
            cfg['min_stars'] = 3
        return cfg

    def _posted(self, guild_id: int) -> dict:
        try:
            with open(_posted_path(guild_id), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_posted(self, guild_id: int, data: dict):
        try:
            os.makedirs('data', exist_ok=True)
            tmp = _posted_path(guild_id) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _posted_path(guild_id))
        except Exception as e:
            log.error(f"[STARBOARD] ошибка записи posted: {e}")

    # ────────────────────────────────────────────────────────────
    async def _star_count(self, message: discord.Message, emoji: str) -> int:
        total = 0
        for r in message.reactions:
            if str(r.emoji) != emoji:
                continue
            cnt = r.count
            try:
                async for u in r.users():
                    if u.bot or u.id == message.author.id:
                        cnt -= 1
            except Exception:
                pass
            total += max(0, cnt)
        return total

    def _board_embed(self, message: discord.Message) -> discord.Embed:
        e = discord.Embed(color=GOLD, timestamp=message.created_at or datetime.now(timezone.utc))
        e.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        content = (message.content or '').strip()
        e.description = (content[:1800] + "\n" if content else "") + f"[Перейти к сообщению]({message.jump_url})"
        for a in message.attachments or []:
            ct = (a.content_type or '')
            if ct.startswith('image/') or (a.filename or '').lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                e.set_image(url=a.url)
                break
        return e

    # ────────────────────────────────────────────────────────────
    async def _handle(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        cfg = self._settings(guild.id)
        board_id = int(cfg.get('channel_id', 0) or 0)
        emoji = str(cfg.get('emoji') or '⭐')
        if not board_id or str(payload.emoji) != emoji:
            return
        if payload.channel_id == board_id:
            return  # посты самой доски не считаем
        channel = guild.get_channel(payload.channel_id)
        board = guild.get_channel(board_id)
        if channel is None or board is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return
        if message.author.bot:
            return

        count = await self._star_count(message, emoji)
        posted = self._posted(guild.id)
        board_msg_id = posted.get(str(message.id))
        head = f"{emoji} **{count}** | {channel.mention}"

        if board_msg_id:
            try:
                bm = await board.fetch_message(int(board_msg_id))
                await bm.edit(content=head, embed=self._board_embed(message))
            except Exception:
                posted.pop(str(message.id), None)
                self._save_posted(guild.id, posted)
            return

        if count < cfg['min_stars']:
            return
        try:
            bm = await board.send(content=head, embed=self._board_embed(message))
            posted[str(message.id)] = bm.id
            if len(posted) > 500:  # реестр не разрастаемся
                posted.pop(next(iter(posted.keys())), None)
            self._save_posted(guild.id, posted)
            log.info(f"[STARBOARD] {guild.name}: сообщение {message.id} в зале славы ({count}{emoji})")
        except Exception as e:
            log.warning(f"[STARBOARD] {guild.name}: публикация: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id:
            await self._handle(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id:
            await self._handle(payload)


async def setup(bot):
    await bot.add_cog(Starboard(bot))
    log.info("[STARBOARD] Ког загружен")
