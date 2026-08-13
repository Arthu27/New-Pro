"""Мини-игры"""
import discord
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
import random
from cogs.embed_utils import _divider
from config import Config 

_DICE = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}


class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_guesses = {}

    def _footer(self, interaction):
        return f"Aether • {interaction.guild.name}"

    @app_commands.command(name='coinflip', description='Подбросить монету')
    async def coin_flip(self, interaction: discord.Interaction, выбор: str = None):
        """Подбросить монету — угадаешь, победишь"""
        result = random.choice(['Орёл', 'Решка'])
        e = discord.Embed(title="🪙 Монетка", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;33m МОНЕТА ПОДБРОШЕНА\u001b[0m\n```\n{_divider()}\n\n"
            f"# {'🟡 Орёл' if result == 'Орёл' else '🟠 Решка'}\n\n{_divider()}"
        )
        e.add_field(name="Результат", value=f"```{result}```", inline=True)
        if выбор:
            norm = выбор.lower().strip()
            user_pick = 'Орёл' if norm in ['орёл', 'orel', 'орел'] else 'Решка' if norm in ['решка', 'reshka'] else None
            correct = user_pick is not None and user_pick == result
            e.add_field(name="Твой выбор", value=f"```{выбор.capitalize()}```", inline=True)
            e.add_field(name="Статус", value=f"```{'✅ Верно!' if correct else '❌ Неверно!'}```", inline=True)
            e.color = 0x2ECC71 if correct else 0xE74C3C
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='dice', description='Бросить кость')
    @app_commands.describe(количество='Сколько костей (1-5)')
    async def roll_dice(self, interaction: discord.Interaction, количество: int = 1):
        """Бросить кость — от 1 до 5 костей"""
        n = max(1, min(5, количество))
        results = [random.randint(1, 6) for _ in range(n)]
        e = discord.Embed(title="🎲 Бросок кости!", color=0x9B59B6, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;35m РЕЗУЛЬТАТ КОСТИ\u001b[0m\n```\n{_divider()}\n\n"
            f"# {' '.join(_DICE[r] for r in results)}\n\n{_divider()}"
        )
        e.add_field(name="Результат", value=f"```{' | '.join(str(r) for r in results)}```", inline=True)
        if n > 1:
            e.add_field(name="Сумма", value=f"```{sum(results)}```", inline=True)
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='rps', description='Сыграть в камень-ножницы-бумага')
    @app_commands.choices(выбор=[
        app_commands.Choice(name='Камень', value='камень'),
        app_commands.Choice(name='Бумага', value='бумага'),
        app_commands.Choice(name='Ножницы', value='ножницы'),
    ])
    async def rps(self, interaction: discord.Interaction, выбор: str):
        """Камень-ножницы-бумага против бота"""
        choices = ['камень', 'бумага', 'ножницы']
        emojis = {'камень': '🪨', 'бумага': '📄', 'ножницы': '✂️'}
        names = {'камень': 'Камень', 'бумага': 'Бумага', 'ножницы': 'Ножницы'}
        bot_choice = random.choice(choices)
        wins = {'камень': 'ножницы', 'бумага': 'камень', 'ножницы': 'бумага'}
        if выбор == bot_choice:
            result, color, badge, ansi = 'Ничья!', 0xF39C12, "НИЧЬЯ", "\u001b[1;33m"
        elif wins[выбор] == bot_choice:
            result, color, badge, ansi = 'Победа!', 0x2ECC71, "ПОБЕДА", "\u001b[1;32m"
        else:
            result, color, badge, ansi = 'Поражение!', 0xE74C3C, "ПОРАЖЕНИЕ", "\u001b[1;31m"
        e = discord.Embed(title="🪨📄✂️ Камень-ножницы-бумага", color=color, timestamp=datetime.now(timezone.utc))
        e.description = f"```ansi\n{ansi}{badge}\u001b[0m\n```\n{_divider()}"
        e.add_field(name="Твой выбор", value=f"# {emojis[выбор]} {names[выбор]}", inline=True)
        e.add_field(name="Выбор бота", value=f"# {emojis[bot_choice]} {names[bot_choice]}", inline=True)
        e.add_field(name="Результат", value=f"```{result}```", inline=False)
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='guess-start', description='Запустить игру «Угадай число» (1-100)')
    async def start_guess(self, interaction: discord.Interaction):
        """Загадай число от 1 до 100 — пусть друзья угадывают"""
        gid = interaction.guild_id
        if gid in self.active_guesses:
            await interaction.response.send_message('Игра уже активна! Продолжай через `/guess [число]`.', ephemeral=True)
            return
        number = random.randint(1, 100)
        self.active_guesses[gid] = {'number': number, 'attempts': 0, 'started_by': interaction.user.id}
        e = discord.Embed(title="🔢 Игра «Угадай число» началась!", color=0x3498DB, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;34m ИГРА НАЧАЛАСЬ\u001b[0m\n```\n{_divider()}\n\n"
            "Я загадал число от 1 до 100!\n"
            f"Угадай через `/guess [число]`.\n\n{_divider()}"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        e.add_field(name="Диапазон", value="```1 — 100```", inline=True)
        e.add_field(name="Начал", value=interaction.user.mention, inline=True)
        e.add_field(name="Подсказка", value="*Следи за подсказками больше/меньше!*", inline=False)
        e.set_footer(text=self._footer(interaction), icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='guess', description='Угадать число')
    @app_commands.describe(число='Твоя догадка (1-100)')
    async def guess(self, interaction: discord.Interaction, число: int):
        """Угадай загаданное число"""
        gid = interaction.guild_id
        if gid not in self.active_guesses:
            await interaction.response.send_message('Нет активной игры! Запусти через `/guess-start`.', ephemeral=True)
            return
        game = self.active_guesses[gid]
        game['attempts'] += 1
        number = game['number']
        if число == number:
            del self.active_guesses[gid]
            e = discord.Embed(title="🎉 ВЕРНАЯ ДОГАДКА!", color=0x2ECC71, timestamp=datetime.now(timezone.utc))
            e.description = (
                f"```ansi\n\u001b[1;32m ПОБЕДА!\u001b[0m\n```\n{_divider()}\n\n"
                f"{interaction.user.mention} угадал число! 🎯\n\n{_divider()}"
            )
            e.add_field(name="Число", value=f"```{number}```", inline=True)
            e.add_field(name="Попытки", value=f"```{game['attempts']} попыток```", inline=True)
        elif число < number:
            e = discord.Embed(title="📈 Больше!", color=0xF39C12, timestamp=datetime.now(timezone.utc))
            e.description = f"```ansi\n\u001b[1;33m БОЛЬШЕ\u001b[0m\n```\n{_divider()}"
            e.add_field(name="Твоя догадка", value=f"```{число}```", inline=True)
            e.add_field(name="Попытка", value=f"```{game['attempts']}. попытка```", inline=True)
            e.add_field(name="Подсказка", value="*Число больше, иди вверх!*", inline=False)
        else:
            e = discord.Embed(title="📉 Меньше!", color=0xF39C12, timestamp=datetime.now(timezone.utc))
            e.description = f"```ansi\n\u001b[1;33m МЕНЬШЕ\u001b[0m\n```\n{_divider()}"
            e.add_field(name="Твоя догадка", value=f"```{число}```", inline=True)
            e.add_field(name="Попытка", value=f"```{game['attempts']}. попытка```", inline=True)
            e.add_field(name="Подсказка", value="*Число меньше, иди вниз!*", inline=False)
        e.set_footer(text=self._footer(interaction), icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='8ball', description='Магический шар - задай вопрос!')
    @app_commands.describe(вопрос='Твой вопрос')
    async def magic_8ball(self, interaction: discord.Interaction, вопрос: str):
        """Магический шар — отвечает на вопросы да/нет"""
        responses = [
            ('Определённо да!', 0x2ECC71),
            ('Да, так и есть.', 0x2ECC71),
            ('Скорее всего да.', 0x2ECC71),
            ('Можешь верить.', 0x2ECC71),
            ('Пока трудно сказать.', 0xF39C12),
            ('Спроси ещё раз.', 0xF39C12),
            ('Сейчас не могу ответить.', 0xF39C12),
            ('Сосредоточься и спроси снова.', 0xF39C12),
            ('Не думаю.', 0xE74C3C),
            ('Нет.', 0xE74C3C),
            ('Определённо нет.', 0xE74C3C),
            ('Судя по всему, нет.', 0xE74C3C),
        ]
        answer, color = random.choice(responses)
        e = discord.Embed(title="🎱 Магический шар", color=color, timestamp=datetime.now(timezone.utc))
        e.description = f"```ansi\n\u001b[1;35m ОТВЕТ ПОЯВЛЯЕТСЯ...\u001b[0m\n```\n{_divider()}"
        e.add_field(name="Вопрос", value=f"*{вопрос}*", inline=False)
        e.add_field(name="Ответ", value=f"```{answer}```", inline=False)
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='random-member', description='Выбрать случайного участника сервера')
    async def random_member(self, interaction: discord.Interaction, роль: discord.Role = None):
        """Выбрать случайного участника (можно с фильтром по роли)"""
        members = [m for m in interaction.guild.members if not m.bot]
        if роль:
            members = [m for m in members if роль in m.roles]
        if not members:
            await interaction.response.send_message('Подходящих участников не найдено!', ephemeral=True)
            return
        выбранный = random.choice(members)
        e = discord.Embed(title="🎯 Случайный участник выбран!", color=0xDC143C, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;31m ВЫБОР СДЕЛАН\u001b[0m\n```\n{_divider()}\n\n"
            f"Жребий брошен и победитель определён! 🎉\n\n{_divider()}"
        )
        e.set_thumbnail(url=выбранный.display_avatar.url)
        e.add_field(name="Выбран", value=выбранный.mention, inline=True)
        if роль:
            e.add_field(name="Фильтр роли", value=роль.mention, inline=True)
        e.add_field(name="Кандидаты", value=f"```{len(members)} человек```", inline=True)
        e.set_footer(text=self._footer(interaction), icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(MiniGames(bot), guilds=Config.guild_objects())
