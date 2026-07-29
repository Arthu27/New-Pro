import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
from datetime import datetime, timedelta
import asyncio
import random
from typing import Dict, List
from cogs.embed_utils import _divider, now_ts

GIF_GIVEAWAY_WIN = "https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"


def _win_dm_embed(prize: str, guild_name: str, guild_icon_url: str) -> discord.Embed:
    """Giveaway kazanan DM embed'i."""
    e = discord.Embed(title="🎉  ÇEKİLİŞİ KAZANDIN!", color=0x2ECC71, timestamp=datetime.utcnow())
    e.description = (
        f"```ansi\n\u001b[1;32m🏆 KAZANAN SENSİN!\u001b[0m\n```\n"
        f"{_divider()}\n\n"
        f"Tebrikler! **{guild_name}** serversundaki çekilişi kazandın! 🎊\n\n"
        "> Ödülünü almak için server администраторleriyle iletişime geç.\n"
        "> Katıldığın için çok teşekkürler!\n\n"
        f"{_divider()}"
    )
    e.add_field(name="🏆 Ödül", value=f"```{prize}```", inline=True)
    e.add_field(name="💡 Как получить?", value="*Серверdaki bir right_btnyle iletişime geçerek ödülünü talep edebilirsin.*", inline=False)
    e.set_image(url=GIF_GIVEAWAY_WIN)
    e.set_footer(text=f"{guild_name} • Giveaway Sistemi", icon_url=guild_icon_url)
    return e

class GiveawayView(View):
    def __init__(self, gw_id: str, guild_id: str):
        super().__init__(timeout=None)
        self.gw_id = gw_id
        self.guild_id = guild_id
        self.participants_file = f'data/giveaways_{guild_id}.json'

    @discord.ui.button(label='🎉 Katıl', style=discord.ButtonStyle.green, emoji='🎉')
    async def join(self, interaction: discord.Interaction, button: Button):
        if interaction.user.bot:
            return
        
        async with asyncio.Lock():
            if not os.path.exists(self.participants_file):
                await interaction.response.send_message('❌ Giveaway bulunamadı!', ephemeral=True)
                return
            
            with open(self.participants_file, 'r', encoding='utf-8') as f:
                giveaways = json.load(f)
            
            if self.gw_id not in giveaways:
                await interaction.response.send_message('❌ Giveaway bulunamadı!', ephemeral=True)
                return
            
            gw = giveaways[self.gw_id]
            if gw.get('status') != 'active':
                await interaction.response.send_message('❌ Giveaway bitti!', ephemeral=True)
                return
            
            participants = gw.setdefault('participants', [])
            user_id = str(interaction.user.id)
            
            if user_id in participants:
                await interaction.response.send_message('✅ Zaten katıldın!', ephemeral=True)
            else:
                participants.append(user_id)
                # User info add
                gw.setdefault('user_info', {})[user_id] = {
                    'name': interaction.user.display_name,
                    'avatar': str(interaction.user.display_avatar.url)
                }
                with open(self.participants_file, 'w', encoding='utf-8') as f:
                    json.dump(giveaways, f, indent=2, ensure_ascii=False)
                
                count = len(participants)
                embed = interaction.message.embeds[0]
                embed.set_field_at(0, name='👥 Katılımcı', value=f'{count}/{gw["winners"]}', inline=True)
                await interaction.message.edit(embed=embed)
                await interaction.response.send_message(f'🎉 Katıldın! ({count}/{gw["winners"]})', ephemeral=True)

    @discord.ui.button(label='⏰ Bitir', style=discord.ButtonStyle.red, emoji='⏰')
    async def end(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok!', ephemeral=True)
            return
        
        async with asyncio.Lock():
            if not os.path.exists(self.participants_file):
                await interaction.response.send_message('❌ Giveaway yok!', ephemeral=True)
                return
            
            with open(self.participants_file, 'r', encoding='utf-8') as f:
                giveaways = json.load(f)
            
            if self.gw_id not in giveaways or giveaways[self.gw_id].get('status') != 'active':
                await interaction.response.send_message('❌ Активен çekiliş yok!', ephemeral=True)
                return
            
            giveaways[self.gw_id]['status'] = 'ended'
            with open(self.participants_file, 'w', encoding='utf-8') as f:
                json.dump(giveaways, f, indent=2)
            
            await self._select_winner(interaction, giveaways[self.gw_id])
            await interaction.message.delete()

    async def _select_winner(self, interaction, gw):
        participants = gw.get('participants', [])
        winners_count = gw.get('winners', 1)
        if not participants:
            embed = discord.Embed(
                title='😔 Giveaway Bitti - Katılımcı Нет',
                description='❌ Maalesef hiç katılımcı yoktu...\n\n🍀 Последнийraki çekilişe mutlaka katıl!',
                color=0xe74c3c
            )
            embed.set_thumbnail(url='https://media.discordapp.net/attachments/1107038411895881788/1110305847399120916/gifty.gif')
            embed.set_footer(text='Giveaway Sistemi')
            await interaction.followup.send(embed=embed)
            return
        
        winners = random.sample(participants, min(winners_count, len(participants)))
        win_users = []
        for uid in winners:
            user = await interaction.guild.fetch_member(int(uid))
            if user:
                win_users.append(user.mention)
                try:
                    icon = interaction.guild.icon.url if interaction.guild.icon else None
                    await user.send(embed=_win_dm_embed(gw["prize"], interaction.guild.name, icon))
                except:
                    pass

        embed = discord.Embed(
            title="🎉  ÇEKİLİŞ BİTTİ — KAZANANLAR AÇIKLANDI!",
            color=0x2ECC71,
            timestamp=datetime.utcnow()
        )
        embed.description = (
            f"```ansi\n\u001b[1;32m🏆 KAZANANLAR BELLİ OLDU!\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"🏆 **Ödül:** `{gw['prize']}`\n\n"
            "**Kazananlar:**\n" + "\n".join([f"🥇 {w}" for w in win_users]) +
            f"\n\n> Tebrikler! Ödülünüzü almak için right_btnlerle iletişime geçin.\n\n"
            f"{_divider()}"
        )
        embed.set_image(url=GIF_GIVEAWAY_WIN)
        embed.set_footer(text=f"{interaction.guild.name} • Giveaway Sistemi")
        await interaction.followup.send(embed=embed)

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways: Dict[str, Dict] = {}
        self.load_giveaways.start()

    def cog_unload(self):
        self.load_giveaways.cancel()

    @tasks.loop(minutes=1)
    async def load_giveaways(self):
        """JSON'lardan активна giveaway'leri загрузить"""
        for guild in self.bot.guilds:
            f = f'data/giveaways_{guild.id}.json'
            if os.path.exists(f):
                try:
                    with open(f, 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                    for gw_id, gw in data.items():
                        if gw.get('status') == 'active':
                            ends_at = datetime.fromisoformat(gw['ends_at'])
                            if datetime.utcnow() > ends_at:
                                channel = guild.get_channel(int(gw['channel_id']))
                                if not channel:
                                    continue

                                # Mark as ended first to prevent re-processing
                                gw['status'] = 'ended'
                                with open(f, 'w', encoding='utf-8') as fp_write:
                                    json.dump(data, fp_write, indent=2, ensure_ascii=False)

                                participants = gw.get('participants', [])
                                winners_count = gw.get('winners', 1)

                                if not participants:
                                    embed = discord.Embed(
                                        title='😔 Giveaway Bitti - Katılımcı Нет',
                                        description='❌ Maalesef hiç katılımcı yoktu...\n\n🍀 Последнийraki çekilişe mutlaka katıl!',
                                        color=0xe74c3c
                                    )
                                    embed.set_thumbnail(url='https://media.discordapp.net/attachments/1107038411895881788/1110305847399120916/gifty.gif')
                                    embed.set_footer(text='Giveaway Sistemi')
                                    await channel.send(embed=embed)
                                    continue

                                winners_ids = random.sample(participants, min(winners_count, len(participants)))
                                win_users_mentions = []
                                icon_url = guild.icon.url if guild.icon else None
                                for uid in winners_ids:
                                    try:
                                        user_id = int(uid)
                                        user = await guild.fetch_member(user_id)
                                        win_users_mentions.append(user.mention)
                                        try:
                                            await user.send(embed=_win_dm_embed(gw["prize"], guild.name, icon_url))
                                        except discord.Forbidden:
                                            pass
                                    except (discord.NotFound, ValueError):
                                        print(f"[WARN] Invalid participant ID skipped: {uid}")
                                        pass

                                if win_users_mentions:
                                    embed = discord.Embed(
                                        title="🎉  ÇEKİLİŞ BİTTİ — KAZANANLAR AÇIKLANDI!",
                                        color=0x2ECC71,
                                        timestamp=datetime.utcnow()
                                    )
                                    embed.description = (
                                        f"```ansi\n\u001b[1;32m🏆 KAZANANLAR BELLİ OLDU!\u001b[0m\n```\n"
                                        f"{_divider()}\n\n"
                                        f"🏆 **Ödül:** `{gw['prize']}`\n\n"
                                        "**Kazananlar:**\n" + "\n".join([f"🥇 {m}" for m in win_users_mentions]) +
                                        f"\n\n> Tebrikler! Ödülünüzü almak için right_btnlerle iletişime geçin.\n\n"
                                        f"{_divider()}"
                                    )
                                    embed.set_image(url=GIF_GIVEAWAY_WIN)
                                    embed.set_footer(text=f"{guild.name} • Giveaway Sistemi", icon_url=icon_url)
                                    await channel.send(embed=embed)
                                else:
                                    embed = discord.Embed(
                                        title="😔  Giveaway Bitti — Kazananlar Ayrıldı",
                                        description="Kazanan oyuncuların hepsi serverdan ayrılmış!\n\n🔄 Lütfen `rerolel` командаu kullanarak yeni kazananlar выбратьin.",
                                        color=0xE74C3C
                                    )
                                    embed.set_footer(text="Giveaway Sistemi")
                                    await channel.send(embed=embed)
                except Exception as e:
                    print(f'Giveaway load error: {e}')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != '🎉' or payload.user_id == self.bot.user.id:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        f = f'data/giveaways_{guild.id}.json'
        if not os.path.exists(f):
            return
        
        try:
            channel = self.bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            
            # Сообщение GiveawayView mü? Kontrole et
            if msg.embeds and 'GIVEAWAY' in msg.embeds[0].title:
                user_id = str(payload.user_id)
                for gw_id, gw in data.items():
                    if gw.get('message_id') == str(payload.message_id) and gw.get('status') == 'active':
                        participants = gw.setdefault('participants', [])
                        if user_id not in participants:
                            participants.append(user_id)
                            gw.setdefault('user_info', {})[user_id] = {'name': 'Unknown'}
                            with open(f, 'w') as fp:
                                json.dump(data, fp, indent=2)
                            
                            count = len(participants)
                            embed = msg.embeds[0]
                            embed.set_field_at(0, name='👥 Katılımcı', value=f'{count}/{gw["winners"]}', inline=True)
                            await msg.edit(embed=embed)
                        break
        except:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.emoji.name != '🎉':
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        f = f'data/giveaways_{guild.id}.json'
        if not os.path.exists(f):
            return
        
        try:
            channel = self.bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            
            user_id = str(payload.user_id)
            for gw_id, gw in data.items():
                if gw.get('message_id') == str(payload.message_id) and gw.get('status') == 'active':
                    participants = gw.setdefault('participants', [])
                    if user_id in participants:
                        participants.remove(user_id)
                        gw['user_info'].pop(user_id, None)
                        with open(f, 'w') as fp:
                            json.dump(data, fp, indent=2)
                        
                        count = len(participants)
                        embed = msg.embeds[0]
                        embed.set_field_at(0, name='👥 Katılımcı', value=f'{count}/{gw["winners"]}', inline=True)
                        await msg.edit(embed=embed)
                    break
        except:
            pass

    @commands.command(name='rerolel')
    @commands.has_permissions(administrator=True)
    async def rerolel(self, ctx, gw_id: str):
        f = f'data/giveaways_{ctx.guild.id}.json'
        if not os.path.exists(f):
            embed = discord.Embed(
                title='❌ Giveaway Не найдено',
                description='Bu serverda henüz bir çekiliş yapılmamış.',
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        with open(f, 'r') as fp:
            data = json.load(fp)
        
        if gw_id not in data or data[gw_id].get('status') != 'ended':
            embed = discord.Embed(
                title='❌ Geçersiz Giveaway ID',
                description="Lütfen bitmiş bir çekiliş ID'si girin.",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        gw = data[gw_id]
        participants = gw.get('participants', [])
        if not participants:
            embed = discord.Embed(
                title='❌ Katılımcı Нет',
                description='Bu çekilişte katılımcı yoktu.',
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        winners = random.sample(participants, gw['winners'])
        win_users = []
        for uid in winners:
            user = await ctx.guild.fetch_member(int(uid))
            if user:
                win_users.append(user.mention)
        
        embed = discord.Embed(
            title="🎰  REROLL — YENİ KAZANANLAR SEÇİLDİ!",
            color=0xF39C12,
            timestamp=datetime.utcnow()
        )
        embed.description = (
            f"```ansi\n\u001b[1;33m🔄 REROLL YAPILDI\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"🏆 **Ödül:** `{gw['prize']}`\n\n"
            "**Новый Kazananlar:**\n" + "\n".join([f"🥇 {w}" for w in win_users]) +
            f"\n\n> Tebrikler! Ödülünüzü almak için right_btnlerle iletişime geçin.\n\n"
            f"{_divider()}"
        )
        embed.set_image(url=GIF_GIVEAWAY_WIN)
        embed.set_footer(text=f"{ctx.guild.name} • Giveaway Sistemi")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))