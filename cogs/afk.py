"""AFK sistemi — /afk причина ile AFK'ya gir, mention edilince bildir"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import os

OWNER_ID = int(os.getenv('OWNER_ID') or '0')

# AFK iken gelen etiketleri sakla — {user_id: [{from, msg, channel, guild, time}]}
_pending_mentions: dict = {}


class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {guild_id: {user_id: {"reason": str, "since": datetime, "owner_mode": bool}}}
        self._afk: dict = {}

    def _set(self, guild_id, user_id, reason, owner_mode=False):
        self._afk.setdefault(str(guild_id), {})[str(user_id)] = {
            "reason": reason,
            "since": datetime.now(timezone.utc).isoformat(),
            "owner_mode": owner_mode
        }

    def _get(self, guild_id, user_id):
        return self._afk.get(str(guild_id), {}).get(str(user_id))

    def _remove(self, guild_id, user_id):
        self._afk.get(str(guild_id), {}).pop(str(user_id), None)

    def _is_afk_anywhere(self, user_id):
        """Herhangi bir serverda AFK mı?"""
        for guild_data in self._afk.values():
            if str(user_id) in guild_data:
                return guild_data[str(user_id)]
        return None

    @app_commands.command(name="afk", description="AFK moduna gir")
    async def afk(self, interaction: discord.Interaction, причина: str = "AFK"):
        self._set(interaction.guild_id, interaction.user.id, причина)

        ts = int(datetime.now(timezone.utc).timestamp())
        e = discord.Embed(color=0x5865F2, timestamp=datetime.now(timezone.utc))
        e.set_author(
            name=f"{interaction.user.display_name} AFK'ya geçti",
            icon_url=interaction.user.display_avatar.url
        )
        e.description = (
            f"```\n😴  AFK MODU AKTİF\n```\n"
            f"> **Причина:** {причина}\n"
            f"> **Başlangıç:** <t:{ts}:R>\n\n"
            f"*Biri seni mention edince уведомление alacaklar.*"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        e.set_footer(text="AFK'dan çıkmak için: /afk-kaldir")
        await interaction.response.send_message(embed=e)

        # Nick'e 😴 add
        try:
            nick = interaction.user.display_name
            if not nick.startswith("😴"):
                await interaction.user.edit(nick=f"😴 {nick[:28]}")
        except Exception:
            pass

    @app_commands.command(name="afk-remove", description="Выйти из режима AFK")
    async def afk_kaldir(self, interaction: discord.Interaction):
        data = self._get(interaction.guild_id, interaction.user.id)
        if not data:
            await interaction.response.send_message("AFK modunda değilsin.", ephemeral=True)
            return
        self._remove(interaction.guild_id, interaction.user.id)
        # Nick'ten 😴 убрать
        try:
            nick = interaction.user.display_name
            if nick.startswith("😴 "):
                await interaction.user.edit(nick=nick[2:].strip() or None)
        except:
            pass
        # Baddyen mention'ları göster
        uid = interaction.user.id
        pending = _pending_mentions.pop(uid, [])
        if pending:
            lines = []
            for p in pending[-10:]:
                lines.append(f"• **{p['from']}** — {p['guild']} #{p['channel']}\n  > {p['msg'][:100]}")
            embed = discord.Embed(
                title=f'👋 Hoş geldin! {len(pending)} kişi seni etiketledi',
                description='\n\n'.join(lines),
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message('✅ AFK modu закрытьıldı! Kimse seni etiketlemedi.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        gid = message.guild.id
        uid = message.author.id

        # Сообщение atan kişi AFK'daysa — SADECE owner_mode=False ise otomatik убрать
        afk_data = self._get(gid, uid)
        if afk_data and not afk_data.get('owner_mode'):
            self._remove(gid, uid)
            since = datetime.fromisoformat(afk_data["since"])
            elapsed = datetime.now(timezone.utc) - since
            mins = int(elapsed.total_seconds() // 60)
            dur = f"{mins} minutes" if mins > 0 else "az önce"
            e = discord.Embed(color=0x2ED573, timestamp=datetime.now(timezone.utc))
            e.set_author(
                name=f"{message.author.display_name} AFK'dan döndü",
                icon_url=message.author.display_avatar.url
            )
            e.description = f"> Нетtu: **{dur}**\n> Причина: *{afk_data['reason']}*"
            await message.channel.send(embed=e, delete_after=8)
            # Nick'ten 😴 убрать
            try:
                nick = message.author.display_name
                if nick.startswith("😴 "):
                    await message.author.edit(nick=nick[2:].strip() or None)
            except Exception:
                pass
            return

        # Mention edilen biri AFK mı?
        for mentioned in message.mentions:
            if mentioned.bot or mentioned.id == message.author.id:
                continue
            data = self._get(gid, mentioned.id)
            if not data:
                continue

            since = datetime.fromisoformat(data["since"])
            elapsed = datetime.now(timezone.utc) - since
            mins = int(elapsed.total_seconds() // 60)
            dur = f"{mins} minutes" if mins > 0 else "az önce"

            # Owner mode — bot soracak
            if data.get('owner_mode') and OWNER_ID and mentioned.id == OWNER_ID:
                e = discord.Embed(color=0x5865F2, timestamp=datetime.now(timezone.utc))
                e.set_author(
                    name=f"{mentioned.display_name} şu an uyuyor 😴",
                    icon_url=mentioned.display_avatar.url
                )
                e.description = (
                    f"> **Причина:** {data['reason']}\n"
                    f"> **Нетtu:** {dur}\n\n"
                    f"Bunu Arthur'a iletebilirim. **Ne sormak istediniz?**\n"
                    f"-# Cevabınızı yazın, uyanınca ileteyim."
                )
                e.set_footer(text="Сообщениеınız Arthur'a iletilecek")
                sent = await message.channel.send(embed=e)

                # Mention'ı сохранить
                if OWNER_ID not in _pending_mentions:
                    _pending_mentions[OWNER_ID] = []
                _pending_mentions[OWNER_ID].append({
                    'from': message.author.display_name,
                    'from_id': message.author.id,
                    'msg': message.content,
                    'channel': message.channel.name,
                    'guild': message.guild.name,
                    'time': datetime.now(timezone.utc).isoformat(),
                    'channel_id': message.channel.id,
                })

                # Последнийraki messageı yakala — ne sormak istediklerini öğren
                def check(m):
                    return m.channel == message.channel and not m.author.bot and m.author.id != OWNER_ID

                try:
                    follow = await self.bot.wait_for('message', check=check, timeout=120)
                    # Сообщениеı owner'a DM at
                    owner = await self.bot.fetch_user(OWNER_ID)
                    dm_embed = discord.Embed(
                        color=0xf59e0b,
                        description=(
                            f'**{message.author.display_name}** seni etiketledi ve şunu sordu:\n\n'
                            f'> {follow.content[:500]}\n\n'
                            f'📍 {message.guild.name} — #{message.channel.name}'
                        )
                    )
                    dm_embed.set_author(
                        name='Uyurken seni etiketlediler 😴',
                        icon_url=message.author.display_avatar.url
                    )
                    await owner.send(embed=dm_embed)
                    # Каналa bildir
                    await message.channel.send(
                        f'✅ Сообщениеın Arthur\'a iletildi! Uyanınca cevap verecek.',
                        delete_after=10
                    )
                    # Pending'e add
                    _pending_mentions[OWNER_ID][-1]['follow_msg'] = follow.content
                except:
                    pass

            else:
                # Normal AFK уведомлениеi
                e = discord.Embed(color=0x5865F2, timestamp=datetime.now(timezone.utc))
                e.set_author(
                    name=f"{mentioned.display_name} şu an AFK 😴",
                    icon_url=mentioned.display_avatar.url
                )
                e.description = (
                    f"> **Причина:** {data['reason']}\n"
                    f"> **Нетtu:** {dur}"
                )
                e.set_footer(text="AFK modunda — message görmeyebilir")
                await message.channel.send(embed=e, delete_after=10)

                # Owner'a DM at
                if OWNER_ID and mentioned.id == OWNER_ID:
                    try:
                        owner = await self.bot.fetch_user(OWNER_ID)
                        dm_embed = discord.Embed(
                            color=0xf59e0b,
                            description=(
                                f'**{message.author.display_name}** seni etiketledi:\n\n'
                                f'> {message.content[:500]}\n\n'
                                f'📍 {message.guild.name} — #{message.channel.name}'
                            )
                        )
                        dm_embed.set_author(
                            name='Seni etiketlediler (AFK modundasın) 😴',
                            icon_url=message.author.display_avatar.url
                        )
                        await owner.send(embed=dm_embed)
                    except:
                        pass


async def setup(bot):
    await bot.add_cog(AFK(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
