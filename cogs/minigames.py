"""Мини-игры"""
import discord
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
import random
from cogs.embed_utils import _divider
from config import Config

_DICE = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

COIN_SIDES = ('Орёл', 'Решка')

RPS_CHOICES = ['камень', 'бумага', 'ножницы']
RPS_EMOJIS = {'камень': '🪨', 'бумага': '📄', 'ножницы': '✂️'}
RPS_NAMES = {'камень': 'Камень', 'бумага': 'Бумага', 'ножницы': 'Ножницы'}
RPS_WINS = {'камень': 'ножницы', 'бумага': 'камень', 'ножницы': 'бумага'}
RPS_RESULTS = {
    'draw': ('Ничья!', 0xF39C12),
    'win': ('Победа!', 0x2ECC71),
    'lose': ('Поражение!', 0xE74C3C),
}

EIGHT_BALL = [
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
EIGHT_BALL_TONES = {0x2ECC71: 'yes', 0xF39C12: 'maybe', 0xE74C3C: 'no'}


def norm_coin_pick(pick):
    """Нормализация прогноза 1:1 команде /coinflip."""
    if not pick:
        return None
    norm = str(pick).lower().strip()
    if norm in ('орёл', 'orel', 'орел'):
        return 'Орёл'
    if norm in ('решка', 'reshka'):
        return 'Решка'
    return None


def flip_coin(pick=None, chooser=None):
    """Подброс монетки 1:1 /coinflip (chooser — только для тестов)."""
    choose = chooser or random.choice
    result = choose(list(COIN_SIDES))
    user_pick = norm_coin_pick(pick)
    return {
        'result': result,
        'pick': user_pick,
        'guessed': bool(pick),
        'correct': user_pick is not None and user_pick == result,
    }


def roll_dice(count=1, randint=None):
    """Бросок костей 1:1 /dice: кламп 1..5, сумма — только при n>1."""
    rnd = randint or random.randint
    n = max(1, min(5, int(count)))
    results = [rnd(1, 6) for _ in range(n)]
    return {
        'count': n,
        'results': results,
        'faces': ' '.join(_DICE[r] for r in results),
        'total': sum(results) if n > 1 else None,
    }


def play_rps(choice, chooser=None):
    """Партия 1:1 /rps; choice обязан быть из RPS_CHOICES (как Discord choices)."""
    if choice not in RPS_CHOICES:
        raise ValueError(f'unknown rps choice: {choice!r}')
    choose = chooser or random.choice
    bot_choice = choose(RPS_CHOICES)
    if choice == bot_choice:
        outcome = 'draw'
    elif RPS_WINS[choice] == bot_choice:
        outcome = 'win'
    else:
        outcome = 'lose'
    result, color = RPS_RESULTS[outcome]
    return {
        'choice': choice,
        'bot_choice': bot_choice,
        'outcome': outcome,
        'result': result,
        'color': color,
        'choice_name': RPS_NAMES[choice],
        'bot_name': RPS_NAMES[bot_choice],
        'choice_emoji': RPS_EMOJIS[choice],
        'bot_emoji': RPS_EMOJIS[bot_choice],
    }


def ask_8ball(question, chooser=None):
    """Ответ магического шара 1:1 /8ball — те же 12 ответов и цвета."""
    choose = chooser or random.choice
    answer, color = choose(EIGHT_BALL)
    return {
        'question': str(question or '').strip(),
        'answer': answer,
        'color': color,
        'tone': EIGHT_BALL_TONES[color],
    }


def member_candidates(guild, role=None):
    """Отбор кандидатов 1:1 /random-member: без ботов, опционально по роли."""
    members = [m for m in guild.members if not m.bot]
    if role is not None:
        members = [m for m in members if role in m.roles]
    return members


def pick_random_member(guild, role=None, chooser=None):
    """(кандидаты, выбранный); выбранный None, если кандидатов нет."""
    candidates = member_candidates(guild, role)
    if not candidates:
        return candidates, None
    choose = chooser or random.choice
    return candidates, choose(candidates)


class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_guesses = {}

    def _footer(self, interaction):
        return f"Hakumo • {interaction.guild.name}"

    @app_commands.command(name='coinflip', description='Подбросить монету')
    async def coin_flip(self, interaction: discord.Interaction, выбор: str = None):
        """Подбросить монету — угадаешь, победишь"""
        game = flip_coin(выбор)
        result = game['result']
        e = discord.Embed(title="🪙 Монетка", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;33m МОНЕТА ПОДБРОШЕНА\u001b[0m\n```\n{_divider()}\n\n"
            f"# {'🟡 Орёл' if result == 'Орёл' else '🟠 Решка'}\n\n{_divider()}"
        )
        e.add_field(name="Результат", value=f"```{result}```", inline=True)
        if выбор:
            e.add_field(name="Твой выбор", value=f"```{выбор.capitalize()}```", inline=True)
            e.add_field(name="Статус", value=f"```{'✅ Верно!' if game['correct'] else '❌ Неверно!'}```", inline=True)
            e.color = 0x2ECC71 if game['correct'] else 0xE74C3C
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='dice', description='Бросить кость')
    @app_commands.describe(количество='Сколько костей (1-5)')
    async def roll_dice(self, interaction: discord.Interaction, количество: int = 1):
        """Бросить кость — от 1 до 5 костей"""
        game = roll_dice(количество)
        results = game['results']
        e = discord.Embed(title="🎲 Бросок кости!", color=0x9B59B6, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"```ansi\n\u001b[1;35m РЕЗУЛЬТАТ КОСТИ\u001b[0m\n```\n{_divider()}\n\n"
            f"# {game['faces']}\n\n{_divider()}"
        )
        e.add_field(name="Результат", value=f"```{' | '.join(str(r) for r in results)}```", inline=True)
        if game['count'] > 1:
            e.add_field(name="Сумма", value=f"```{game['total']}```", inline=True)
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
        game = play_rps(выбор)
        badge = {'draw': 'НИЧЬЯ', 'win': 'ПОБЕДА', 'lose': 'ПОРАЖЕНИЕ'}[game['outcome']]
        ansi = {'draw': '\u001b[1;33m', 'win': '\u001b[1;32m', 'lose': '\u001b[1;31m'}[game['outcome']]
        e = discord.Embed(title="🪨📄✂️ Камень-ножницы-бумага", color=game['color'], timestamp=datetime.now(timezone.utc))
        e.description = f"```ansi\n{ansi}{badge}\u001b[0m\n```\n{_divider()}"
        e.add_field(name="Твой выбор", value=f"# {game['choice_emoji']} {game['choice_name']}", inline=True)
        e.add_field(name="Выбор бота", value=f"# {game['bot_emoji']} {game['bot_name']}", inline=True)
        e.add_field(name="Результат", value=f"```{game['result']}```", inline=False)
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
        game = ask_8ball(вопрос)
        e = discord.Embed(title="🎱 Магический шар", color=game['color'], timestamp=datetime.now(timezone.utc))
        e.description = f"```ansi\n\u001b[1;35m ОТВЕТ ПОЯВЛЯЕТСЯ...\u001b[0m\n```\n{_divider()}"
        e.add_field(name="Вопрос", value=f"*{вопрос}*", inline=False)
        e.add_field(name="Ответ", value=f"```{game['answer']}```", inline=False)
        e.set_footer(text=f"Просил: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='random-member', description='Выбрать случайного участника сервера')
    async def random_member(self, interaction: discord.Interaction, роль: discord.Role = None):
        """Выбрать случайного участника (можно с фильтром по роли)"""
        members, выбранный = pick_random_member(interaction.guild, роль)
        if выбранный is None:
            await interaction.response.send_message('Подходящих участников не найдено!', ephemeral=True)
            return
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
