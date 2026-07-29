import discord
from discord.ext import commands
import json
import os
import random
import time

class AutoRoleLevel(commands.Cog):
    """Система XP + автоматическая выдача ролей по уровню"""

    def __init__(self, bot):
        self.bot = bot
        self._cooldowns = {}  # user_id → last_xp_time

    def _xp_file(self, guild_id):
        return f'data/xp_{guild_id}.json'

    def _level_roles_file(self, guild_id):
        return f'data/level_roles_{guild_id}.json'

    def _load_xp(self, guild_id):
        f = self._xp_file(guild_id)
        if not os.path.exists(f):
            return {}
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except:
            return {}

    def _save_xp(self, guild_id, data):
        os.makedirs('data', exist_ok=True)
        with open(self._xp_file(guild_id), 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2)

    def _get_level_roles(self, guild_id):
        f = self._level_roles_file(guild_id)
        if not os.path.exists(f):
            return {}
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except:
            return {}

    @staticmethod
    def _level_from_xp(xp):
        """XP'den level hesapla: her level için gereken XP artar"""
        level = 0
        required = 100
        while xp >= required:
            xp -= required
            level += 1
            required = int(required * 1.15)
        return level

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        uid = str(message.author.id)
        now = time.time()

        # Cooldown: 60 saniyede bir XP kazan (spam koruması)
        last = self._cooldowns.get(uid, 0)
        if now - last < 60:
            return
        self._cooldowns[uid] = now

        # XP ver (15-25 arası rastgele)
        xp_gain = random.randint(15, 25)

        xp_data = self._load_xp(message.guild.id)
        user_data = xp_data.get(uid, {'xp': 0, 'level': 0})

        old_xp = user_data.get('xp', 0)
        old_level = user_data.get('level', 0)
        new_xp = old_xp + xp_gain
        new_level = self._level_from_xp(new_xp)

        user_data['xp'] = new_xp
        user_data['level'] = new_level
        xp_data[uid] = user_data
        self._save_xp(message.guild.id, xp_data)

        # Level atladıysa уведомление отправить
        if new_level > old_level:
            try:
                await message.channel.send(
                    f'🎉 {message.author.mention}, **уровень {new_level}** достигнут!',
                    delete_after=10
                )
            except:
                pass

        # Otomatik role kontroleü
        level_roles = self._get_level_roles(message.guild.id)
        if not level_roles:
            return

        member = message.author
        for required_level, role_id in level_roles.items():
            if new_level >= int(required_level):
                role = message.guild.get_role(int(role_id))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f'Уровень {required_level} — авто-role')
                    except:
                        pass

    # ── Серверya girişte role kontroleü ──────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return
        uid = str(member.id)
        xp_data = self._load_xp(member.guild.id)
        user_data = xp_data.get(uid)
        if not user_data:
            return

        level = user_data.get('level', 0)
        level_roles = self._get_level_roles(member.guild.id)
        if not level_roles:
            return

        for required_level, role_id in level_roles.items():
            if level >= int(required_level):
                role = member.guild.get_role(int(role_id))
                if role:
                    try:
                        await member.add_roles(role, reason=f'Уровень {required_level} — авто-role при входе')
                    except:
                        pass

    # ── Командаlar ───────────────────────────────────────────────────────────────
    @commands.command(name='level-role-add')
    @commands.has_permissions(administrator=True)
    async def add_level_role(self, ctx, level: int, role: discord.Role):
        """Назначить role за определённый уровень. Использование: !level-role-add 5 @Роль"""
        f = self._level_roles_file(ctx.guild.id)
        os.makedirs('data', exist_ok=True)
        data = {}
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)

        data[str(level)] = str(role.id)

        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2)

        await ctx.send(f'✅ Role {role.mention} назначена за уровень **{level}**!')

    @commands.command(name='level-role-remove')
    @commands.has_permissions(administrator=True)
    async def remove_level_role(self, ctx, level: int):
        """Убрать role за уровень"""
        f = self._level_roles_file(ctx.guild.id)
        if not os.path.exists(f):
            await ctx.send('❌ Роли за уровни не настроены!')
            return

        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        removed = data.pop(str(level), None)

        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2)

        if removed:
            await ctx.send(f'✅ Role за уровень **{level}** удалена!')
        else:
            await ctx.send(f'❌ Уровень **{level}** не найден!')

    @commands.command(name='level-roles')
    async def list_level_roles(self, ctx):
        """Список ролей за уровни"""
        data = self._get_level_roles(ctx.guild.id)
        if not data:
            await ctx.send('❌ Роли за уровни ещё не настроены! Используйте `!level-role-add <уровень> @role`')
            return

        embed = discord.Embed(title='🏆 Роли за уровни', color=0xFFD700)
        for level, role_id in sorted(data.items(), key=lambda x: int(x[0])):
            role = ctx.guild.get_role(int(role_id))
            embed.add_field(
                name=f'Уровень {level}',
                value=role.mention if role else f'Удалённая role ({role_id})',
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name='rank')
    async def rank(self, ctx, member: discord.Member = None):
        """Показать уровень и XP пользователя"""
        member = member or ctx.author
        uid = str(member.id)
        xp_data = self._load_xp(ctx.guild.id)
        user_data = xp_data.get(uid, {'xp': 0, 'level': 0})

        xp = user_data.get('xp', 0)
        level = user_data.get('level', 0)

        # XP для следующего уровня
        next_level_xp = 100
        for i in range(level):
            next_level_xp = int(next_level_xp * 1.15)

        embed = discord.Embed(color=0xc8922a)
        embed.set_author(name=f'Статистика {member.display_name}', icon_url=member.display_avatar.url)
        embed.add_field(name='🏅 Уровень', value=f'```{level}```', inline=True)
        embed.add_field(name='⭐ XP', value=f'```{xp}```', inline=True)
        embed.add_field(name='📈 До след. уровня', value=f'```{next_level_xp - (xp - sum(int(100 * 1.15**i) for i in range(level)))} XP```', inline=True)
        await ctx.send(embed=embed)

    @commands.command(name='top-level', aliaголос=['top-xp', 'xp-top'])
    async def top_level(self, ctx):
        """Топ-10 по уровню"""
        xp_data = self._load_xp(ctx.guild.id)
        if not xp_data:
            await ctx.send('❌ Данные XP пусты!')
            return

        sorted_users = sorted(xp_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)[:10]
        medals = ['🥇', '🥈', '🥉']

        lines = []
        for i, (uid, data) in enumerate(sorted_users):
            medal = medals[i] if i < 3 else f'`#{i+1}`'
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'ID: {uid}'
            lines.append(f'{medal} **{name}** — Уровень {data.get("level", 0)} • {data.get("xp", 0)} XP')

        embed = discord.Embed(title='🏆 Топ-10 по уровню', description='\n'.join(lines), color=0xFFD700)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoRoleLevel(bot))
