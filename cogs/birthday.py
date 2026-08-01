import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timezone
from cogs.embed_utils import _divider, now_ts

GIF_BIRTHDAY = "https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_birthdays.start()
        self.remove_birthday_roles.start()

    def cog_unload(self):
        self.check_birthdays.cancel()
        self.remove_birthday_roles.cancel()

    def get_data(self, guild_id):
        f = f'data/birthdays_{guild_id}.json'
        if not os.path.exists(f):
            return {}
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)

    def save_data(self, guild_id, data):
        os.makedirs('data', exist_ok=True)
        with open(f'data/birthdays_{guild_id}.json', 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)

    def get_settings(self, guild_id):
        f = f'data/birthday_settings_{guild_id}.json'
        if not os.path.exists(f):
            return {'channel_id': None, 'role_id': None, 'message': ' {user} сегодня рождение день! Все kutlu olsun! '}
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        now = datetime.now(timezone.utc)
        if now.hour != 9:
            return
        today = f"{now.month:02d}-{now.day:02d}"
        for guild in self.bot.guilds:
            data = self.get_data(guild.id)
            settings = self.get_settings(guild.id)
            if not settings.get('channel_id'):
                continue
            channel = guild.get_channel(int(settings['channel_id']))
            if not channel:
                continue
            for user_id, info in data.items():
                if info.get('date') != today:
                    continue
                # Сегодня zaten kutlandı mı?
                if info.get('celebrated') == str(now.year):
                    continue
                member = guild.get_member(int(user_id))
                if not member:
                    continue
                age_str = ""
                age = None
                if info.get('year'):
                    age = now.year - info['year']
                    age_str = f" ({age} yaşında)"

                embed = discord.Embed(
                    title=f" День рождения Kutlaması!",
                    color=0xFF69B4,
                    timestamp=now
                )
                embed.description = (
                    f"```ansi\n\u001b[1;35m РОЖДЕНИЕ ДЕНЬ!\u001b[0m\n```\n{_divider()}\n\n"
                    f" {member.mention} сегодня рождение день{age_str}!\n\n"
                    f"> Все рождение день diladdrini bekleme! \n\n"
                    f"{_divider()}"
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_image(url=GIF_BIRTHDAY)
                embed.add_field(name=" День рождения", value=f"```{info['date'].replace('-', '/')}```", inline=True)
                if age:
                    embed.add_field(name=" Возраст", value=f"```{age}```", inline=True)
                embed.add_field(name=" Kutla!", value="*вниз рождение день messageını bırak!* ", inline=False)
                embed.set_footer(text=f"Aether • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                await channel.send(content=f" {member.mention}", embed=embed)

                # Рождение день роль ver
                if settings.get('role_id'):
                    role = guild.get_role(int(settings['role_id']))
                    if role:
                        try:
                            await member.add_roles(role, reason="Роль именинника")
                        except Exception:
                            pass

                # Economy hediyesi ver
                if settings.get('gift_coins', 0) > 0:
                    await self._give_birthday_coins(guild.id, user_id, settings['gift_coins'])

                # Kutlandı как işaretle
                info['celebrated'] = str(now.year)
                self.save_data(guild.id, data)

    @tasks.loop(hours=1)
    async def remove_birthday_roles(self):
        """Рождение день geçince роль geri al."""
        now = datetime.now(timezone.utc)
        today = f"{now.month:02d}-{now.day:02d}"
        for guild in self.bot.guilds:
            settings = self.get_settings(guild.id)
            if not settings.get('role_id'):
                continue
            role = guild.get_role(int(settings['role_id']))
            if not role:
                continue
            data = self.get_data(guild.id)
            for user_id, info in data.items():
                if info.get('date') == today:
                    continue  # Сегодня рождение день, роль tut
                member = guild.get_member(int(user_id))
                if member and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="День рождения закончился")
                    except Exception:
                        pass

    async def _give_birthday_coins(self, guild_id, user_id, amount):
        """Economy sistemine рождение день hediyesi add."""
        f = f'data/economy_{guild_id}.json'
        try:
            econ = {}
            if os.path.exists(f):
                with open(f, 'r', encoding='utf-8') as fp:
                    econ = json.load(fp)
            econ.setdefault(str(user_id), {})['balance'] = econ.get(str(user_id), {}).get('balance', 0) + amount
            with open(f, 'w', encoding='utf-8') as fp:
                json.dump(econ, fp, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @remove_birthday_roles.before_loop
    async def before_remove_roles(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='birthday', description='Сохранить день рождение')
    @app_commands.describe(gun='День (1-31)', ay='Ay (1-12)', yil='Yıl (opsiyonel)')
    async def set_birthday(self, interaction: discord.Interaction, gun: int, ay: int, yil: int = None):
        if not (1 <= gun <= 31 and 1 <= ay <= 12):
            await interaction.response.send_message(' Неверный дата!', ephemeral=True)
            return
        data = self.get_data(interaction.guild_id)
        entry = {'date': f'{ay:02d}-{gun:02d}', 'name': interaction.user.display_name}
        if yil:
            entry['year'] = yil
        data[str(interaction.user.id)] = entry
        self.save_data(interaction.guild_id, data)

        e = discord.Embed(title=" День рождения Сохранено!", color=0xFF69B4, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;35m ЗАПИСЬ ЗАВЕРШЕНО\u001b[0m\n```\n{_divider()}\n\n"
            f"Рождение день успешно сохранено! O день seni kutlayacağız. \n\n{_divider()}"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        e.add_field(name=" Дата", value=f"```{gun}/{ay}{f'/{yil}' if yil else ''}```", inline=True)
        e.add_field(name=" Пользователь", value=interaction.user.mention, inline=True)
        e.add_field(name=" Информация", value="*Рождение день geldiğinde на сервере announcelacak!*", inline=False)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name='birthdays', description='Показать priblijayusiesya день рождение')
    async def list_birthdays(self, interaction: discord.Interaction):
        data = self.get_data(interaction.guild_id)
        if not data:
            await interaction.response.send_message(' Пока запись рождение день yok!', ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        today_num = now.month * 100 + now.day
        entries = []
        for uid, info in data.items():
            try:
                m, d = map(int, info['date'].split('-'))
                num = m * 100 + d
                diff = num - today_num
                if diff < 0:
                    diff += 1200
                member = interaction.guild.get_member(int(uid))
                name = member.display_name if member else info.get('name', uid)
                entries.append((diff, d, m, name, uid))
            except Exception:
                continue
        entries.sort()

        e = discord.Embed(title=" Yaklaşan День рождения", color=0xFF69B4, timestamp=now)
        e.description = f"```ansi\n\u001b[1;35m РОЖДЕНИЕ ДЕНЬ TAKVİMİ\u001b[0m\n```\n{_divider()}"
        for diff, d, m, name, uid in entries[:15]:
            if diff == 0:
                label = " **СЕГОДНЯ!**"
            elif diff <= 7:
                label = f"⏰ {diff} день после"
            else:
                label = f" {diff} день после"
            e.add_field(name=f" {name}", value=f"`{d:02d}/{m:02d}` — {label}", inline=False)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='dogumgunu-удалить', description='Удалить zapis день рождение')
    async def delete_birthday(self, interaction: discord.Interaction):
        data = self.get_data(interaction.guild_id)
        uid = str(interaction.user.id)
        if uid not in data:
            await interaction.response.send_message(' Запись рождение день yok.', ephemeral=True)
            return
        del data[uid]
        self.save_data(interaction.guild_id, data)
        await interaction.response.send_message(' Ваша дата рождения удалена из базы.', ephemeral=True)

    @commands.command(name='dogumgunu-kur')
    @commands.has_permissions(administrator=True)
    async def setup_birthday(self, ctx, channel: discord.TextChannel, role: discord.Role = None):
        settings = self.get_settings(ctx.guild.id)
        settings['channel_id'] = str(channel.id)
        if role:
            settings['role_id'] = str(role.id)
        os.makedirs('data', exist_ok=True)
        with open(f'data/birthday_settings_{ctx.guild.id}.json', 'w', encoding='utf-8') as fp:
            json.dump(settings, fp, indent=2, ensure_ascii=False)

        e = discord.Embed(title=" День рождения Система Kuruldu!", color=0x2ECC71, timestamp=datetime.now(timezone.utc))
        e.description = f"```ansi\n\u001b[1;32m СИСТЕМА АКТИВЕН\u001b[0m\n```\n{_divider()}"
        e.add_field(name=" Канал", value=channel.mention, inline=True)
        e.add_field(name=" Роль", value=role.mention if role else "```Нет```", inline=True)
        e.set_footer(text=f"Aether • {ctx.guild.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=e)

    @app_commands.command(name='dogumgunu-настройк', description="Настройк система день рождение (Менеджер)")
    @app_commands.describe(
        channel='Kutlama канал',
        role='Рождение день роль (opsiyonel)',
        hediye_coin='Рождение день verilecek coin miktarı'
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_birthday_slash(self, interaction: discord.Interaction,
                                    channel: discord.TextChannel,
                                    role: discord.Role = None,
                                    hediye_coin: int = 0):
        settings = self.get_settings(interaction.guild_id)
        settings['channel_id'] = str(channel.id)
        if role:
            settings['role_id'] = str(role.id)
        settings['gift_coins'] = hediye_coin
        os.makedirs('data', exist_ok=True)
        with open(f'data/birthday_settings_{interaction.guild_id}.json', 'w', encoding='utf-8') as fp:
            json.dump(settings, fp, indent=2, ensure_ascii=False)

        e = discord.Embed(title=" День рождения Система Kuruldu!", color=0x2ECC71, timestamp=datetime.now(timezone.utc))
        e.add_field(name=" Канал", value=channel.mention, inline=True)
        e.add_field(name=" Роль", value=role.mention if role else "`Нет`", inline=True)
        e.add_field(name=" Бонусные монеты", value=f"`{hediye_coin}`" if hediye_coin else "`Нет`", inline=True)
        e.set_footer(text=f"Aether • {interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Birthday(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788), discord.Object(id=1498837105915330562)])
