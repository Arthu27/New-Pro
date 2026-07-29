import discord
from discord.ext import commands
import re, json, os
from collections import defaultdict
import time
from datetime import timedelta

DIV = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LOG_CHANNEL_ID = 1491145640900558979  # Наказание messageları bu channela gider

def _load_cfg(guild_id):
    f = f'data/automod_{guild_id}.json'
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except Exception:
            pass
    return {}

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = defaultdict(list)
        self.duplicate_tracker = defaultdict(list)
        self.link_pattern = re.compile(r'https?://\S+|www\.\S+')
        self.invite_pattern = re.compile(r'discord\.gg/\S+|discord\.com/invite/\S+')

    async def _get_log_ch(self, guild):
        """Наказание messageları için log channelını döndür."""
        ch = guild.get_channel(LOG_CHANNEL_ID)
        if ch:
            return ch
        # Fallback: mod-log channelı
        return discord.utils.get(guild.text_channels, name="mod-log")

    async def _purge_user(self, channel, member, limit=5):
        """Пользователя son N messageını удалить."""
        try:
            deleted = 0
            async for msg in channel.history(limit=100):
                if msg.author.id == member.id and deleted < limit:
                    try:
                        await msg.delete()
                        deleted += 1
                    except Exception:
                        pass
        except Exception:
            pass

    async def _punish(self, message, title, desc, color, action=None, duration_min=5):
        """
        Наказание uygula:
        - Tetikleyen messageı удалить
        - Наказание embed'ini LOG channelına отправить (chatte gösterme)
        - action: 'timeout' | None
        """
        member = message.author
        channel = message.channel
        guild = message.guild

        # Tetikleyen messageı удалить
        try:
            await message.delete()
        except Exception:
            pass

        # Мут uygula
        if action == 'timeout':
            try:
                await member.timeout(
                    discord.utils.utcnow() + timedelta(minutes=duration_min),
                    reason=title
                )
            except Exception:
                pass

        # Наказание embed'ini log channelına отправить
        log_ch = await self._get_log_ch(guild)
        if log_ch:
            e = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;31m⚡ OTOMATİK MODERASYON\u001b[0m\n```\n"
                f"{DIV}\n\n{desc}\n\n{DIV}"
            )
            e.set_thumbnail(url=member.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=f"{member.mention}\n`{member.id}`", inline=True)
            e.add_field(name="📺 Канал", value=channel.mention, inline=True)
            if action == 'timeout':
                e.add_field(name="⏳ Наказание", value=f"```{duration_min} minutes мут```", inline=True)
            e.set_footer(text="🤖 Aether AutoMod")
            await log_ch.send(embed=e)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        # Модератор, admin ve server sahibi bypass
        if (message.author.guild_permissions.moderate_members or
            message.author.guild_permissions.administrator or
            message.author.id == message.guild.owner_id):
            return

        guild_id = str(message.guild.id)
        cfg = _load_cfg(guild_id)

        # Config yoksa hiçbir şey yapma
        if not cfg:
            return

        # Muaf channel kontroleü
        exempt = cfg.get('exempt_channels', [])
        if str(message.channel.id) in exempt:
            return

        # Запрещённое kelimeler — sadece panel'de kelime varsa çalışır
        panel_words = cfg.get('banned_words', [])
        if panel_words:
            if await self._check_bad_words(message, panel_words):
                return

        # Spam koruması — sadece message удалить, timeout atma
        if cfg.get('spam_protection', False):
            if await self._check_spam(message, cfg):
                return

        # Caps filtresi
        if cfg.get('caps_filter', False):
            if await self._check_caps(message):
                return

        # Link filtresi
        if cfg.get('link_filter', False):
            if await self._check_links(message):
                return

        # Davet filtresi
        if cfg.get('invite_filter', False):
            if await self._check_invites(message):
                return

        # Mention spam
        if cfg.get('mention_spam', False):
            if await self._check_mention_spam(message):
                return

        # Duplicate
        if cfg.get('duplicate_filter', False):
            if await self._check_duplicate(message):
                return

        # Emoji spam
        if cfg.get('emoji_filter', False):
            await self._check_emoji_spam(message)

    async def _check_bad_words(self, message, banned):
        content_lower = message.content.lower()
        for word in banned:
            if word.lower() in content_lower:
                await self._punish(
                    message,
                    "🚫  YASAKLI KELİME",
                    f"{message.author.mention} запрещённое kelime использовано!\n**📋 Причина:** `{word}` kelimesi запрещено",
                    0xe74c3c
                )
                return True
        return False

    async def _check_spam(self, message, cfg):
        uid = message.author.id
        now = time.time()
        threshold = int(cfg.get('spam_threshold', 5))
        self.spam_tracker[uid] = [t for t in self.spam_tracker[uid] if now - t < 5]
        self.spam_tracker[uid].append(now)
        if len(self.spam_tracker[uid]) >= threshold:
            self.spam_tracker[uid].clear()
            try:
                await message.delete()
            except Exception:
                pass
            try:
                warn_msg = await message.channel.send(
                    f"{message.author.mention} çok hızlı message atıyorsun, yavaşla!",
                    delete_after=5
                )
            except Exception:
                pass
            return True
        return False

    async def _check_caps(self, message):
        if len(message.content) < 10:
            return False
        ratio = sum(1 for c in message.content if c.isupper()) / len(message.content)
        if ratio > 0.7:
            await self._punish(
                message,
                "🔠  CAPS LOCK UYARISI",
                f"{message.author.mention} aşırı büyük harf kullanma!\n**📋 Причина:** CAPS filtresi ihlali",
                0xf39c12
            )
            return True
        return False

    async def _check_links(self, message):
        if not self.link_pattern.search(message.content):
            return False
        await self._punish(
            message,
            "🔗  LİNK ENGELLENDİ",
            f"{message.author.mention} link paylaşma правоn yok!\n**📋 Причина:** Link filtresi ihlali",
            0xe67e22
        )
        return True

    async def _check_invites(self, message):
        if not self.invite_pattern.search(message.content):
            return False
        await self._punish(
            message,
            "📨  DAVET LİNKİ ENGELLENDİ",
            f"{message.author.mention} davet linki paylaşamazsın!\n**📋 Причина:** Davet filtresi ihlali",
            0xe74c3c
        )
        return True

    async def _check_duplicate(self, message):
        uid = message.author.id
        content = message.content.lower()
        if len(content) < 5:
            return False
        now = time.time()
        self.duplicate_tracker[uid] = [(t, c) for t, c in self.duplicate_tracker[uid] if now - t < 30]
        count = sum(1 for _, c in self.duplicate_tracker[uid] if c == content)
        if count >= 5:
            self.duplicate_tracker[uid].clear()
            await self._punish(
                message,
                "🔁  TEKRAR MESAJ UYARISI",
                f"{message.author.mention} aynı messageı tekrarlama!\n**⏳ Наказание:** 10 minutes мут",
                0xe74c3c,
                action='timeout',
                duration_min=10
            )
            return True
        self.duplicate_tracker[uid].append((now, content))
        return False

    async def _check_mention_spam(self, message):
        # Reply mention'ı sayma (yanıt atarken otomatik 1 mention geliyor)
        reply_id = message.reference.resolved.author.id if (message.reference and message.reference.resolved) else None
        mentions = [m for m in message.mentions if m.id != reply_id]
        count = len(mentions) + len(message.role_mentions)
        if count >= 8:
            await self._punish(
                message,
                "📢  TOPLU MENTİON UYARISI",
                f"{message.author.mention} toplu mention запрещеноtır!\n**⏳ Наказание:** 15 minutes мут",
                0xe74c3c,
                action='timeout',
                duration_min=15
            )
            return True
        return False

    async def _check_emoji_spam(self, message):
        count = len(re.findall(r'<:\w+:\d+>|[\U0001F600-\U0001F64F]', message.content))
        if count >= 10:
            await self._punish(
                message,
                "😵  EMOJİ SPAM UYARISI",
                f"{message.author.mention} çok fazla emoji kullanma!\n**📋 Причина:** Emoji spam ihlali",
                0xf39c12
            )
            return True
        return False


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
