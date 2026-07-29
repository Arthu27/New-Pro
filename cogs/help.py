import discord
from discord import app_commands
from discord.ext import commands

PERM_ICON = {"all": "🟢", "mod": "🟡", "admin": "🔴", "owner": "⚙️"}
PERM_LABEL = {"all": "Все", "mod": "Модератор", "admin": "Админ", "owner": "Владелец"}

CATEGORIES = [
    {"id": "home", "emoji": "🏠", "title": "Главное меню", "color": 0x7B68EE, "commands": []},
    {"id": "mod", "emoji": "🛡️", "title": "Модерация", "color": 0xFF4757, "commands": [
        ("/moderate ban", "Перманентный бан", "/moderate ban @user причина", "admin"),
        ("/moderate kick", "Исключить с serverа", "/moderate kick @user причина", "admin"),
        ("/moderate timeout", "Временный мут", "/moderate timeout @user 10m", "admin"),
        ("/moderate untimeout", "Снять мут", "/moderate untimeout @user", "admin"),
        ("/moderate unban", "Снять бан", "/moderate unban user_id", "admin"),
        ("/utility clear", "Массовое удаление сообщений", "/utility clear 50", "admin"),
        ("/utility lock", "Заблокировать channel", "/utility lock", "mod"),
        ("/utility unlock", "Разблокировать channel", "/utility unlock", "mod"),
        ("/utility userinfo", "Информация о пользователе", "/utility userinfo @user", "mod"),
        ("/role", "Выдать / снять role", "/role @user @role", "admin"),
        ("/history", "История модерации", "/history @user", "mod"),
        ("/case", "Детали дела", "/case 42", "mod"),
        ("/note", "Добавить заметку", "/note @user текст", "mod"),
        ("/notes", "Показать заметки", "/notes @user", "mod"),
        ("/watchlist", "Список наблюдения", "/watchlist @user причина", "mod"),
        ("/watchlist-show", "Показать список наблюдения", "/watchlist-show", "mod"),
        ("/banlist", "Забаненные пользователи", "/banlist", "admin"),
        ("/massrole", "Массовая выдача ролей", "/massrole @role выдать", "admin"),
        ("/massban", "Массовый бан", "/massban id1 id2 id3", "admin"),
    ]},
    {"id": "warn", "emoji": "⚠️", "title": "Предупреждения", "color": 0xFFA502, "commands": [
        ("/warn", "Выдать предупреждение", "/warn @user причина", "mod"),
        ("/warnings", "Список предупреждений", "/warnings @user", "mod"),
        ("/clearwarns", "Очистить все предупреждения", "/clearwarns @user", "admin"),
    ]},
    {"id": "music", "emoji": "🎵", "title": "Музыка", "color": 0x2ED573, "commands": [
        ("/play", "Воспроизвести музыку", "/play lofi hip hop", "all"),
        ("/pause", "Пауза / продолжить", "/pause", "all"),
        ("/skip", "Пропустить трек", "/skip", "all"),
        ("/queue", "Показать очередь", "/queue", "all"),
        ("/volume", "Громкость 0-100", "/volume 80", "all"),
        ("/clear-queue", "Очистить очередь", "/clear-queue", "all"),
        ("/leave", "Покинуть голосовой channel", "/leave", "all"),
        ("/join", "Присоединиться к channelу", "/join", "all"),
    ]},
    {"id": "fun", "emoji": "🎮", "title": "Развлечения и игры", "color": 0xFF6B81, "commands": [
        ("/coinflip", "Подбросить монету", "/coinflip", "all"),
        ("/rolel", "Бросить кубик 1-5", "/rolel 2", "all"),
        ("/rps", "Камень ножницы бумага", "/rps", "all"),
        ("/guess-start", "Игра угадай число", "/guess-start", "all"),
        ("/guess", "Угадать число", "/guess 42", "all"),
        ("/8ball", "Магический шар 8", "/8ball вопрос", "all"),
        ("/random-member", "Случайный участник", "/random-member", "all"),
        ("/fun", "Развлекательные команды", "/fun dice", "all"),
        ("/poll", "Быстрый опрос", "/poll вопрос", "all"),
    ]},
    {"id": "eco", "emoji": "💰", "title": "Экономика и функции", "color": 0xFFD700, "commands": [
        ("/economy", "Баланс, ежедневное, перевод", "/economy balance", "all"),
        ("/games", "Азартные игры, слоты", "/games gamble 100", "all"),
        ("/shop", "Просмотр магазина", "/shop", "all"),
        ("/buy", "Купить товар", "/buy предмет", "all"),
        ("/birthday", "Сохранить день рождения", "/birthday 15 3", "all"),
        ("/birthdays", "Ближайшие дни рождения", "/birthdays", "all"),
        ("/afk", "Режим AFK", "/afk причина", "all"),
        ("/duty-panel", "Панель заданий", "/duty-panel", "admin"),
        ("/duty-add", "Ручной прогресс", "/duty-add @user 10", "mod"),
        ("/duty-stats", "Таблица очков заданий", "/duty-stats", "mod"),
        ("/ticket_panel", "Панель ticketов", "/ticket_panel", "admin"),
        ("/staff-apply", "Заявка модератора", "/staff-apply", "all"),
    ]},
    {"id": "leaderboard", "emoji": "🏆", "title": "Рейтинг и отчёты", "color": 0xF1C40F, "commands": [
        ("!ranking", "Общий рейтинг", "!ranking", "all"),
        ("!ranking messages", "Рейтинг сообщений", "!ranking messages", "all"),
        ("!ranking voice", "Рейтинг голосового времени", "!ranking voice", "all"),
        ("!ranking invites", "Рейтинг приглашений", "!ranking invites", "all"),
        ("/profile", "Ваша статистика", "/profile", "all"),
        ("/invites", "Статистика приглашений", "/invites", "all"),
        ("/invite-ranking", "Топ приглашающих", "/invite-ranking", "all"),
        ("!weekly-report", "Еженедельный отчёт", "!weekly-report", "mod"),
        ("!meeting-start", "Начать собрание", "!meeting-start", "admin"),
        ("!meeting-counter", "Дней с последнего собрания", "!meeting-counter", "all"),
        ("!report-setup", "Настроить авто-отчёт", "!report-setup #channel 0 9", "admin"),
        ("!report-role-add", "Добавить role в отчёт", "!report-role-add @Роль", "admin"),
        ("!mod-stats", "Статистика модераторов", "!mod-stats @user", "mod"),
    ]},
    {"id": "events", "emoji": "📅", "title": "Система мероприятий", "color": 0x5865F2, "commands": [
        ("/event-create", "Создать мероприятие", "/event-create название", "admin"),
        ("/events", "Список активных мероприятий", "/events", "all"),
        ("/event-cancel", "Отменить мероприятие", "/event-cancel id", "admin"),
    ]},
    {"id": "util", "emoji": "🔧", "title": "Инструменты", "color": 0x5352ED, "commands": [
        ("/modstats", "Статистика модераторов", "/modstats", "mod"),
        ("/activemods", "Самые активные модераторы", "/activemods", "mod"),
        ("/health", "Оценка здоровья serverа", "/health", "all"),
        ("/channel-stats", "Статистика сообщений channelа", "/channel-stats", "all"),
        ("/verify-setup", "Настроить верификацию", "/verify-setup", "admin"),
        ("/botinfo", "Информация о боте", "/botinfo", "all"),
        ("/uptime", "Время работы бота", "/uptime", "all"),
        ("/avatar", "Показать аватар", "/avatar @user", "all"),
        ("/serverinfo", "Информация о serverе", "/serverinfo", "all"),
        ("/archive", "Архивировать сообщения", "/archive 100", "admin"),
        ("/ai-reset", "Сбросить историю AI", "/ai-reset", "all"),
        ("/ai-learn", "Обучить AI", "/ai-learn тема info", "admin"),
    ]},
]

TOTAL_PAGES = len(CATEGORIES)
TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)


def build_embed(page, guild=None):
    cat = CATEGORIES[page]
    PT = {"all": "🟢", "mod": "🟡", "admin": "🔴", "owner": "⚙️"}

    guild_name   = guild.name   if guild else "Aether"
    guild_banner = guild.banner if guild else None
    guild_icon   = guild.icon   if guild else None

    if cat["id"] == "home":
        embed = discord.Embed(color=0x5865F2)
        embed.set_author(
            name=f"{guild_name}  ·  Справочник команд",
            icon_url=guild_icon.url if guild_icon else None
        )
        embed.description = (
            f"> 📦 **{TOTAL_CMDS}** команд  ·  **{TOTAL_PAGES - 1}** категорий\n"
            f"> 🔑 `🟢 Все`  `🟡 Мод`  `🔴 Админ`  `⚙️ Владелец`\n\n"
            f"**Выберите категорию ниже ↓**"
        )

        if guild_banner:
            embed.set_image(url=guild_banner.url)
        elif guild_icon:
            embed.set_thumbnail(url=guild_icon.url)

        CAT_DESC = {
            "mod":         "Бан · Кик · Мут · История",
            "warn":        "Предупреждения · Список · Очистка",
            "music":       "Музыка · Очередь · Громкость",
            "fun":         "Игры · Опросы · Развлечения",
            "eco":         "Экономика · Задания · Ticketы · AFK",
            "leaderboard": "Рейтинг · Отчёты · Собрания",
            "events":      "Создать · Список мероприятий",
            "util":        "Статистика · Инструменты · AI",
        }

        for c in CATEGORIES[1:]:
            count = len(c['commands'])
            embed.add_field(
                name=f"{c['emoji']}  **{c['title']}**",
                value=f"```{CAT_DESC.get(c['id'], '')}```\n-# {count} команд",
                inline=True
            )

        embed.set_footer(
            text=f"{guild_name}  ·  !help  ·  Страница 1/{TOTAL_PAGES}",
            icon_url=guild_icon.url if guild_icon else None
        )
        return embed

    cmds = cat["commands"]
    embed = discord.Embed(color=cat["color"])
    embed.set_author(
        name=f"{cat['emoji']}  {cat['title']}  ·  {len(cmds)} команд",
        icon_url=guild_icon.url if guild_icon else None
    )

    mid = (len(cmds) + 1) // 2
    left_cmds  = cmds[:mid]
    right_cmds = cmds[mid:]

    def fmt(name, desc, usage, perm):
        return (
            f"{PT[perm]} **`{name}`**\n"
            f"╰ {desc}\n"
            f"╰ -# `{usage}`"
        )

    embed.add_field(name="", value="\n\n".join(fmt(*c) for c in left_cmds), inline=True)
    if right_cmds:
        embed.add_field(name="", value="\n\n".join(fmt(*c) for c in right_cmds), inline=True)

    perm_counts = {}
    for _, _, _, p in cmds:
        perm_counts[p] = perm_counts.get(p, 0) + 1
    summary_parts = []
    for k in ("all", "mod", "admin", "owner"):
        if k in perm_counts:
            summary_parts.append(f"{PT[k]} {PERM_LABEL[k]}: **{perm_counts[k]}**")
    embed.add_field(name="", value="  ·  ".join(summary_parts), inline=False)

    embed.set_footer(
        text=f"{guild_name}  ·  Страница {page + 1}/{TOTAL_PAGES}  ·  !help",
        icon_url=guild_icon.url if guild_icon else None
    )
    if guild_icon:
        embed.set_thumbnail(url=guild_icon.url)
    return embed


class CategorySelect(discord.ui.Select):
    def __init__(self, current_page):
        options = [
            discord.SelectOption(
                label=f"{c['emoji']} {c['title']}",
                value=str(i),
                description=f"{len(c['commands'])} команд" if c["commands"] else "Главное меню",
                default=(i == current_page),
            )
            for i, c in enumerate(CATEGORIES)
        ]
        super().__init__(placeholder="📂  Выбрать категорию...", options=options, custom_id="help_cat_select", row=0)

    async def callback(self, interaction):
        page = int(self.values[0])
        view = HelpView(page=page)
        await interaction.response.edit_message(embed=build_embed(page, interaction.guild), view=view)


class HelpView(discord.ui.View):
    def __init__(self, page=0):
        super().__init__(timeout=None)
        self.page = page
        self.add_item(CategorySelect(page))
        self._sync()

    def _sync(self):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page == TOTAL_PAGES - 1)
        self.page_label.label = f"  {self.page + 1} / {TOTAL_PAGES}  "

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1, custom_id="help_prev")
    async def prev_btn(self, interaction, button):
        self.page = max(0, self.page - 1)
        self._sync()
        await interaction.response.edit_message(embed=build_embed(self.page, interaction.guild), view=self)

    @discord.ui.button(label="  1 / 9  ", style=discord.ButtonStyle.primary, disabled=True, row=1, custom_id="help_page")
    async def page_label(self, interaction, button):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1, custom_id="help_next")
    async def next_btn(self, interaction, button):
        self.page = min(TOTAL_PAGES - 1, self.page + 1)
        self._sync()
        await interaction.response.edit_message(embed=build_embed(self.page, interaction.guild), view=self)

    @discord.ui.button(label="🏠 Главное меню", style=discord.ButtonStyle.success, row=1, custom_id="help_home")
    async def home_btn(self, interaction, button):
        self.page = 0
        self._sync()
        await interaction.response.edit_message(embed=build_embed(0, interaction.guild), view=self)

    @discord.ui.button(label="✖ Закрыть", style=discord.ButtonStyle.danger, row=1, custom_id="help_close")
    async def close_btn(self, interaction, button):
        await interaction.response.defer()
        await interaction.delete_original_response()


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliaголос=["yardim", "h", "?", "команды"])
    async def help_prefix(self, ctx):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(embed=build_embed(0, ctx.guild), view=HelpView(page=0))

    @app_commands.command(name="help", description="Показать все команды бота")
    async def help_slash(self, interaction):
        await interaction.response.send_message(embed=build_embed(0, interaction.guild), view=HelpView(page=0), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
    bot.add_view(HelpView())
