"""
Help Cog — Select Menu
Профессиональная карточка-меню (чёрно-белый + красный дизайн) вместо тёмного embed.
Каждая категория рисуется как изображение через help_card.py.
"""

import io
import discord
from discord import app_commands
from discord.ext import commands

from cogs.help_card import generate_help_overview, generate_help_category


CATEGORIES = [
    {
        "id": "moderation",
        "title": "Модерация",
        "emoji": "🛡️",
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
        "emoji": "⚠️",
        "commands": [
            ("/warn @user [причина]", "Выдать предупреждение", "Мод"),
            ("/warnings @user", "Список предупреждений", "Мод"),
            ("/clearwarns @user", "Очистить предупреждения", "Админ"),
        ]
    },
    {
        "id": "tickets",
        "title": "Тикеты",
        "emoji": "🎫",
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
        "emoji": "💰",
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
        "emoji": "🎵",
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
        "emoji": "⭐",
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
        "emoji": "⚙️",
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
        "emoji": "🎧",
        "commands": [
            ("!voicetime [@user]", "Время в голосовых", "Все"),
            ("!voiceleaderboard", "Топ по голосовым", "Все"),
            ("!voiceonline", "Кто в голосовых", "Все"),
        ]
    },
    {
        "id": "fun",
        "title": "Развлечения",
        "emoji": "🎲",
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
        "emoji": "🎁",
        "commands": [
            ("!giveaway [время] [победителей] [приз]", "Создать розыгрыш", "Админ"),
            ("!reroll [ID]", "Перевыбрать победителя", "Админ"),
        ]
    },
    {
        "id": "profile",
        "title": "Профиль",
        "emoji": "🪪",
        "commands": [
            ("!profile [@user]", "Карточка профиля", "Все"),
            ("/profile [@user]", "Карточка профиля (slash)", "Все"),
        ]
    },
]

TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)


def _find_category(category_id):
    return next((c for c in CATEGORIES if c["id"] == category_id), None)


def _card_file(image, filename="help.png"):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename=filename)


def build_overview_file():
    image = generate_help_overview(CATEGORIES, TOTAL_CMDS)
    return _card_file(image, "help_overview.png")


def build_category_file(category_id):
    cat = _find_category(category_id)
    if not cat:
        return build_overview_file()
    index = CATEGORIES.index(cat)
    image = generate_help_category(cat, index, len(CATEGORIES))
    return _card_file(image, f"help_{category_id}.png")


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=c["title"],
                value=c["id"],
                description=f"{len(c['commands'])} команд",
                emoji=c["emoji"],
            )
            for c in CATEGORIES
        ]
        super().__init__(
            placeholder="Выберите категорию команд",
            options=options,
            custom_id="help_select_v5",
        )

    async def callback(self, interaction: discord.Interaction):
        cat_id = self.values[0]
        view = HelpView()
        file = build_category_file(cat_id)
        await interaction.response.edit_message(attachments=[file], view=view)


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
        await ctx.send(file=build_overview_file(), view=HelpView())

    @app_commands.command(name="help", description="Справка по командам")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            file=build_overview_file(), view=HelpView(), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Help(bot))
