"""
Reaction Roles Cog
Reaction roles cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime

from logger import get_logger
log = get_logger("reaction_roles_cog")



class ReactionRolesCog(commands.Cog):
    """Reaction roles cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
        self.reaction_roles = {}  # message_id -> {emoji -> role_id}
    
    @commands.command(name='reactionrole', aliases=['reactionrol'])
    @commands.has_permissions(administrator=True)
    async def reactionrole(self, ctx, message_id: int, emoji: str, role: discord.Role):
        """Reaction role добавить"""
        if message_id not in self.reaction_roles:
            self.reaction_roles[message_id] = {}
        
        self.reaction_roles[message_id][emoji] = role.id
        
        # Mesaja reaction добавить
        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.add_reaction(emoji)
            
            embed = discord.Embed(
                title=" Reaction Role Eklendi",
                description=f"**Сообщение ID:** {message_id}\n**Emoji:** {emoji}\n**Роль:** {role.mention}",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f" Ошибка: {e}")
    
    @commands.command(name='removereactionrole', aliases=['reactionrolkaldır'])
    @commands.has_permissions(administrator=True)
    async def removereactionrole(self, ctx, message_id: int):
        """Reaction role kaldır"""
        if message_id in self.reaction_roles:
            del self.reaction_roles[message_id]
            
            embed = discord.Embed(
                title=" Reaction Role Kaldırıldı",
                description=f"**Сообщение ID:** {message_id}",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(" Reaction role не найдено!")
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Reaction eklendiğinde"""
        if payload.user_id == self.bot.user.id:
            return
        
        if payload.message_id not in self.reaction_roles:
            return
        
        emoji = str(payload.emoji)
        if emoji not in self.reaction_roles[payload.message_id]:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(self.reaction_roles[payload.message_id][emoji])
        
        if member and role:
            await member.add_roles(role, reason="Reaction role")
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Reaction kaldırıldığında"""
        if payload.user_id == self.bot.user.id:
            return
        
        if payload.message_id not in self.reaction_roles:
            return
        
        emoji = str(payload.emoji)
        if emoji not in self.reaction_roles[payload.message_id]:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(self.reaction_roles[payload.message_id][emoji])
        
        if member and role:
            await member.remove_roles(role, reason="Reaction role removed")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" ReactionRolesCog loaded")


async def setup(bot):
    await bot.add_cog(ReactionRolesCog(bot))
