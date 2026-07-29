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
    """Giveaway kazanan DM embed'i — minimalizm stil."""
    e = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
    e.description = (
        f"## Tebrikler!\n"
        f"### Siz sizoyunmı в розыгрыш\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Сервер:** {guild_name}\n"
        f"**Награда:** {prize}\n\n"
        f"Iletişime geçin с управление сервер для al награда.\n"
        f"Teşekkürler для ucastie!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    e.set_image(url=GIF_GIVEAWAY_WIN)
    if guild_icon_url:
        e.set_footer(text=f"{guild_name} · Розыгрыши", icon_url=guild_icon_url)
    else:
        e.set_footer(text=f"{guild_name} · Розыгрыши")
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
                await interaction.response.send_message('❌ Giveaway не найден!', ephemeral=True)
                return
            
            with open(self.participants_file, 'r', encoding='utf-8') as f:
                giveaways = json.load(f)
            
            if self.gw_id not in giveaways:
                await interaction.response.send_message('❌ Giveaway не найден!', ephemeral=True)
                return
            
            gw = giveaways[self.gw_id]
            if gw.get('status') != 'active':
                await interaction.response.send_message('❌ Giveaway bitti!', ephemeral=True)
                return
            
            participants = gw.setdefault('participants', [])
            user_id = str(interaction.user.id)
            
            if user_id in participants:
                await interaction.response.send_message('✅ Zaten присоединился!', ephemeral=True)
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
                await interaction.response.send_message(f'🎉 Присоединился! ({count}/{gw["winners"]})', ephemeral=True)

    @discord.ui.button(label='⏰ Bitir', style=discord.ButtonStyle.red, emoji='⏰')
    async def end(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok!', ephemeral=True)
            return
        
        async with asyncio.Lock():
            if not os.path.exists(self.participants_file):
                await interaction.response.send_message('❌ Giveaway yok!', ephemeral=True)
                return
            
            with open(self.participants_file, 'r', encoding='utf-8') as f:
                giveaways = json.load(f)
            
            if self.gw_id not in giveaways or giveaways[self.gw_id].get('status') != 'active':
                await interaction.response.send_message('❌ Активен розыгрыш yok!', ephemeral=True)
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
            embed = discord.Embed(color=0xe74c3c, timestamp=datetime.utcnow())
            embed.description = (
                f"## Розыгрыш завершено\n"
                f"### Нет участников\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"E ne текст ki, nikto не ucastvoval в розыгрыш.\n\n"
                f"Obyazatelno ucastvuyte в sleduyusem розыгрыш!\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction.guild.icon:
                embed.set_footer(text=f"{interaction.guild.name} · Розыгрыши", icon_url=interaction.guild.icon.url)
            else:
                embed.set_footer(text=f"{interaction.guild.name} · Розыгрыши")
            await interaction.followup.send(embed=embed)
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

        embed = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
        embed.description = (
            f"## Розыгрыш завершено\n"
            f"### Kazananlar obyavleni!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Награда:** {gw['prize']}\n\n"
            f"**Kazananlar:**\n" + "\n".join([f"• {w}" for w in win_users]) +
            f"\n\nTebrikler! Iletişime geçin с управление для al награда.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        embed.set_image(url=GIF_GIVEAWAY_WIN)
        if interaction.guild.icon:
            embed.set_footer(text=f"{interaction.guild.name} · Розыгрыши", icon_url=interaction.guild.icon.url)
        else:
            embed.set_footer(text=f"{interaction.guild.name} · Розыгрыши")
        await interaction.followup.send(embed=embed)
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
        """JSON'lardan активен giveaway'leri загрузить"""
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
                                    embed = discord.Embed(color=0xe74c3c, timestamp=datetime.utcnow())
                                    embed.description = (
                                        f"## Розыгрыш завершено\n"
                                        f"### Нет участников\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                        f"E ne текст ki, nikto не ucastvoval в розыгрыш.\n\n"
                                        f"Obyazatelno ucastvuyte в sleduyusem розыгрыш!\n\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    )
                                    if guild.icon:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши", icon_url=guild.icon.url)
                                    else:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши")
                                    await channel.send(embed=embed)
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
                                    embed = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
                                    embed.description = (
                                        f"## Розыгрыш завершено\n"
                                        f"### Kazananlar obyavleni!\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                        f"**Награда:** {gw['prize']}\n\n"
                                        f"**Kazananlar:**\n" + "\n".join([f"• {m}" for m in win_users_mentions]) +
                                        f"\n\nTebrikler! Iletişime geçin с управление для al награда.\n\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    )
                                    embed.set_image(url=GIF_GIVEAWAY_WIN)
                                    if icon_url:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши", icon_url=icon_url)
                                    else:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши")
                                    await channel.send(embed=embed)
                                    await channel.send(embed=embed)
                                else:
                                    embed = discord.Embed(color=0xE74C3C, timestamp=datetime.utcnow())
                                    embed.description = (
                                        f"## Розыгрыш завершено\n"
                                        f"### Kazananlar pokinuli сервер\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                        f"Все vibrannie kazananlar pokinuli сервер!\n\n"
                                        f"Ispolzuyte команды `reroll` для выбрать novih pobediteley.\n\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                                    )
                                    if guild.icon:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши", icon_url=guild.icon.url)
                                    else:
                                        embed.set_footer(text=f"{guild.name} · Розыгрыши")
                                    await channel.send(embed=embed)
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
            
            # Сообщение GiveawayView mü? Контроль et
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
                description='Bu на сервере пока bir розыгрыш yapılmamış.',
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        with open(f, 'r') as fp:
            data = json.load(fp)
        
        if gw_id not in data or data[gw_id].get('status') != 'ended':
            embed = discord.Embed(
                title='❌ Неверный Giveaway ID',
                description="Пожалуйста bitmiş bir розыгрыш ID'si girin.",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        gw = data[gw_id]
        participants = gw.get('participants', [])
        if not participants:
            embed = discord.Embed(
                title='❌ Katılımcı Нет',
                description='Bu розыгрыш katılımcı yoktu.',
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
        
        embed = discord.Embed(color=0xF39C12, timestamp=datetime.utcnow())
        embed.description = (
            f"## Reroll завершено\n"
            f"### Новый kazananlar vibrani!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Награда:** {gw['prize']}\n\n"
            f"**Новый kazananlar:**\n" + "\n".join([f"• {w}" for w in win_users]) +
            f"\n\nTebrikler! Iletişime geçin с управление для al награда.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        embed.set_image(url=GIF_GIVEAWAY_WIN)
        if ctx.guild.icon:
            embed.set_footer(text=f"{ctx.guild.name} · Розыгрыши", icon_url=ctx.guild.icon.url)
        else:
            embed.set_footer(text=f"{ctx.guild.name} · Розыгрыши")
        await ctx.send(embed=embed)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))