"""
Help Cog — Select Menu
Тёмная тема, без эмодзи, только select menu
"""

MENU_GIF = "https://media.tenor.com/x8v1oNUOmg4AAAAC/rain-dark.gif"

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime


CATEGORIES = [
    {
        "id": "moderation",
        "title": "Модерация",
        "commands": [
            ("!ban @user [причина]", "Бан", "Админ"),
            ("!kick @user [причина]", "Кик", "Админ"),
            ("!mute @user [время]", "Мьют", "Мод"),
            ("!unmute @user", "Размьют", "Мод"),
            ("!timeout @user [время]", "Таймаут", "Мод"),
            ("!clear [кол-во]", "Очистить сообщения", "Мод"),
            ("!lock [#канал]", "Заблокировать канал", "Мод"),
            ("!unlock [#канал]", "Разблокировать канал", "Мод"),
            ("!slowmode [сек]", "Медленный режим", "Мод"),
        ]
    },
    {
        "id": "warnings",
        "title": "Предупреждения",
        "commands": [
            ("/warn @user [причина]", "Выдать предупреждение", "Мод"),
            ("/warnings @user", "Список предупреждений", "Мод"),
            ("/clearwarns @user", "Очистить предупреждения", "Админ"),
        ]
    },
    {
        "id": "tickets",
        "title": "Тикеты",
        "commands": [
            ("/ticket-panel", "Создать панель тикетов", "Админ"),
            ("/tickets [статус]", "Список тикетов", "Все"),
            ("/ticket-info [ID]", "Информация о тикете", "Все"),
            ("/ticket-close [ID]", "Закрыть тикет", "Все"),
            ("/ticket-assign [ID] @user", "Назначить тикет", "Мод"),
        ]
    },
    {
        "id": "economy",
        "title": "Экономика",
        "commands": [
            ("!balance [@user]", "Баланс", "Все"),
            ("!daily", "Ежедневная награда", "Все"),
            ("!work", "Работать", "Все"),
            ("!beg", "Попросить деньги", "Все"),
            ("!rob @user", "Ограбить", "Все"),
            ("!deposit [сумма]", "Положить в банк", "Все"),
            ("!withdraw [сумма]", "Снять из банка", "Все"),
            ("!transfer @user [сумма]", "Перевести", "Все"),
            ("!shop", "Магазин", "Все"),
            ("!buy [предмет]", "Купить", "Все"),
            ("!inventory [@user]", "Инвентарь", "Все"),
        ]
    },
    {
        "id": "music",
        "title": "Музыка",
        "commands": [
            ("!play [запрос]", "Воспроизвести", "Все"),
            ("!pause", "Пауза", "Все"),
            ("!resume", "Продолжить", "Все"),
            ("!skip", "Пропустить", "Все"),
            ("!queue", "Очередь", "Все"),
            ("!stop", "Остановить", "Все"),
            ("!volume [0-100]", "Громкость", "Все"),
            ("!loop", "Зациклить", "Все"),
            ("!shuffle", "Перемешать", "Все"),
            ("!leave", "Покинуть канал", "Все"),
        ]
    },
    {
        "id": "levels",
        "title": "Уровни",
        "commands": [
            ("!rank [@user]", "Ранг", "Все"),
            ("!leaderboard", "Таблица лидеров", "Все"),
            ("!rewards", "Награды за уровни", "Все"),
            ("!setlevel @user [уровень]", "Установить уровень", "Админ"),
        ]
    },
    {
        "id": "utility",
        "title": "Утилиты",
        "commands": [
            ("!ping", "Задержка бота", "Все"),
            ("!botinfo", "О боте", "Все"),
            ("!serverinfo", "О сервере", "Все"),
            ("!userinfo [@user]", "О пользователе", "Все"),
            ("!avatar [@user]", "Аватар", "Все"),
            ("!color [hex]", "Показать цвет", "Все"),
            ("!base64 [en/de] [текст]", "Base64", "Все"),
            ("!hesap [выражение]", "Калькулятор", "Все"),
        ]
    },
    {
        "id": "voice",
        "title": "Голосовые",
        "commands": [
            ("!voicetime [@user]", "Время в голосовых", "Все"),
            ("!voiceleaderboard", "Топ по голосовым", "Все"),
            ("!voiceonline", "Кто в голосовых", "Все"),
        ]
    },
    {
        "id": "fun",
        "title": "Развлечения",
        "commands": [
            ("!8ball [вопрос]", "Магический шар", "Все"),
            ("!coinflip", "Монетка", "Все"),
            ("!dice [грани]", "Кубик", "Все"),
            ("!meme", "Мем", "Все"),
            ("!joke", "Шутка", "Все"),
            ("!cat", "Кот", "Все"),
            ("!dog", "Пёс", "Все"),
        ]
    },
    {
        "id": "giveaway",
        "title": "Розыгрыши",
        "commands": [
            ("!giveaway [время] [победителей] [приз]", "Создать розыгрыш", "Админ"),
            ("!reroll [ID]", "Перевыбрать победителя", "Админ"),
        ]
    },
    {
        "id": "profile",
        "title": "Профиль",
        "commands": [
            ("!profile [@user]", "Карточка профиля", "Все"),
            ("/profile [@user]", "Карточка профиля (slash)", "Все"),
        ]
    },
]

TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)


def build_embed(category_id: str = None) -> discord.Embed:
    if category_id is None:
        embed = discord.Embed(
            title="Aether Bot",
            description=(
                f"Добро пожаловать! Здесь вы найдёте все доступные команды.\n\n"
                f"Выберите категорию из списка ниже, чтобы увидеть список команд.\n\n"
                f"Всего команд: **{TOTAL_CMDS}** | Префикс: **!**"
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.set_image(url=MENU_GIF)

        return embed

    cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
    if not cat:
        return build_embed()

    embed = discord.Embed(
        title=cat["title"],
        color=discord.Color.dark_grey(),
        timestamp=datetime.now()
    )

    lines = []
    for cmd, desc, perm in cat["commands"]:
        lines.append(f"`{cmd}` — {desc} *[{perm}]*")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(cat['commands'])} команд")
    embed.set_image(url=MENU_GIF)

    return embed


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=c["title"],
                value=c["id"],
                description=f"{len(c['commands'])} команд",
            )
            for c in CATEGORIES
        ]
        super().__init__(
            placeholder="Выберите категорию",
            options=options,
            custom_id="help_select_v4"
        )

    async def callback(self, interaction: discord.Interaction):
        cat_id = self.values[0]
        view = HelpView()
        await interaction.response.edit_message(embed=build_embed(cat_id), view=view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(HelpSelect())


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "команды", "menu"])
    async def help_prefix(self, ctx):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(embed=build_embed(), view=HelpView())

    @app_commands.command(name="help", description="Справка по командам")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_embed(), view=HelpView(), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Help(bot))
