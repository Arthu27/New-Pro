import discord
from discord import app_commands
from discord.ext import commands

# ── Права доступа ─────────────────────────────────────────────────────────────
PERM = {
    "all":   {"icon": "🟢", "label": "Все",       "color": 0x2ECC71},
    "mod":   {"icon": "🟡", "label": "Модератор",  "color": 0xF39C12},
    "admin": {"icon": "🔴", "label": "Админ",      "color": 0xE74C3C},
    "owner": {"icon": "⚙️", "label": "Владелец",   "color": 0x9B59B6},
}

# ── Категории команд ──────────────────────────────────────────────────────────
CATEGORIES = [
    {"id": "home", "emoji": "🏠", "title": "Главное меню", "color": 0xC8922A, "commands": []},

    {"id": "mod", "emoji": "🛡️", "title": "Модерация", "color": 0xE74C3C, "commands": [
        ("/moderate ban",     "Перманентный бан",               "@user причина",         "admin"),
        ("/moderate kick",    "Исключить с сервера",            "@user причина",         "admin"),
        ("/moderate timeout", "Временный мут",                  "@user 10m причина",     "admin"),
        ("/moderate untimeout","Снять мут",                     "@user",                 "admin"),
        ("/moderate unban",   "Снять бан",                      "user_id",               "admin"),
        ("/utility clear",    "Массовое удаление сообщений",    "50",                    "admin"),
        ("/utility lock",     "Заблокировать канал",            "",                      "mod"),
        ("/utility unlock",   "Разблокировать канал",           "",                      "mod"),
        ("/utility userinfo", "Информация о пользователе",      "@user",                 "mod"),
        ("/role",             "Выдать / снять роль",            "@user @роль",           "admin"),
        ("/history",          "История модерации",              "@user",                 "mod"),
        ("/case",             "Детали дела",                    "42",                    "mod"),
        ("/note",             "Добавить заметку",               "@user текст",           "mod"),
        ("/notes",            "Показать заметки",               "@user",                 "mod"),
        ("/watchlist",        "Список наблюдения",              "@user причина",         "mod"),
        ("/watchlist-show",   "Показать список наблюдения",     "",                      "mod"),
        ("/banlist",          "Забаненные пользователи",        "",                      "admin"),
        ("/massrole",         "Массовая выдача ролей",          "@роль выдать",          "admin"),
        ("/massban",          "Массовый бан",                   "id1 id2 id3",           "admin"),
    ]},

    {"id": "warn", "emoji": "⚠️", "title": "Предупреждения", "color": 0xF39C12, "commands": [
        ("/warn",       "Выдать предупреждение",     "@user причина",  "mod"),
        ("/warnings",   "Список предупреждений",     "@user",          "mod"),
        ("/clearwarns", "Очистить предупреждения",   "@user",          "admin"),
    ]},

    {"id": "music", "emoji": "🎵", "title": "Музыка", "color": 0x1DB954, "commands": [
        ("/play",        "Воспроизвести",             "название/ссылка",  "all"),
        ("/pause",       "Пауза / продолжить",        "",                 "all"),
        ("/skip",        "Пропустить трек",           "",                 "all"),
        ("/queue",       "Очередь",                   "",                 "all"),
        ("/volume",      "Громкость 0-100",           "80",               "all"),
        ("/clear-queue", "Очистить очередь",          "",                 "all"),
        ("/leave",       "Покинуть голосовой канал",  "",                 "all"),
        ("/join",        "Присоединиться к каналу",   "",                 "all"),
    ]},

    {"id": "fun", "emoji": "🎮", "title": "Развлечения", "color": 0xFF6B81, "commands": [
        ("/coinflip",      "Монетка",                "",             "all"),
        ("/roll",          "Бросить кубик 1-5",      "2",            "all"),
        ("/rps",           "Камень-ножницы-бумага",  "",             "all"),
        ("/guess-start",   "Угадай число",           "",             "all"),
        ("/guess",         "Ввести число",           "42",           "all"),
        ("/8ball",         "Магический шар",         "вопрос",       "all"),
        ("/random-member", "Случайный участник",     "",             "all"),
        ("/fun",           "Развлекательные",        "dice",         "all"),
        ("/poll",          "Быстрый опрос",          "вопрос",       "all"),
    ]},

    {"id": "eco", "emoji": "💰", "title": "Экономика", "color": 0xFFD700, "commands": [
        ("/economy balance",  "Баланс",                "",           "all"),
        ("/economy daily",    "Ежедневная награда",    "",           "all"),
        ("/economy transfer", "Перевести coins",       "@user 100",  "all"),
        ("/economy ranking",  "Топ богачей",           "",           "all"),
        ("/games gamble",     "Азартная игра",         "100",        "all"),
        ("/games slot",       "Слот-машина",           "50",         "all"),
        ("/games heist",      "Ограбление",            "@user",      "all"),
        ("/shop",             "Магазин",               "",           "all"),
        ("/buy",              "Купить товар",          "предмет",    "all"),
    ]},

    {"id": "social", "emoji": "👥", "title": "Социальное", "color": 0x3498DB, "commands": [
        ("/birthday",       "Сохранить день рождения", "15 3",       "all"),
        ("/birthdays",      "Ближайшие дни рождения",  "",           "all"),
        ("/afk",            "Режим AFK",               "причина",    "all"),
        ("/staff-apply",    "Заявка модератора",       "",           "all"),
        ("/profile",        "Ваш профиль",             "",           "all"),
        ("/invites",        "Статистика приглашений",  "",           "all"),
        ("/invite-ranking", "Топ приглашающих",        "",           "all"),
    ]},

    {"id": "rank", "emoji": "🏆", "title": "Рейтинги", "color": 0xF1C40F, "commands": [
        ("/rank",               "Ваш уровень и XP",           "",           "all"),
        ("/top-level",          "Топ-10 по уровню",           "",           "all"),
        ("!ranking",            "Общий рейтинг",              "",           "all"),
        ("!ranking messages",   "Рейтинг сообщений",          "",           "all"),
        ("!ranking voice",      "Рейтинг голосового времени", "",           "all"),
        ("!ranking invites",    "Рейтинг приглашений",        "",           "all"),
        ("/mod-stats",          "Статистика модераторов",     "@user",      "mod"),
        ("/activemods",         "Активные модераторы",        "",           "mod"),
    ]},

    {"id": "events", "emoji": "📅", "title": "Мероприятия и розыгрыши", "color": 0x5865F2, "commands": [
        ("/event-create",  "Создать мероприятие",     "название",    "admin"),
        ("/events",        "Активные мероприятия",    "",            "all"),
        ("/event-cancel",  "Отменить мероприятие",    "id",          "admin"),
        ("/giveaway",      "Создать розыгрыш",        "",            "admin"),
    ]},

    {"id": "server", "emoji": "⚙️", "title": "Управление сервером", "color": 0x9B59B6, "commands": [
        ("/setup-logs",    "Создать лог-каналы",       "",            "admin"),
        ("/verify-setup",  "Настроить верификацию",    "",            "admin"),
        ("/ticket_panel",  "Панель тикетов",           "",            "admin"),
        ("/duty-panel",    "Панель заданий",           "",            "admin"),
        ("/duty-add",      "Добавить прогресс",        "@user 10",    "mod"),
        ("/duty-stats",    "Таблица очков",            "",            "mod"),
        ("/automod",       "Настройки автомодерации",  "",            "admin"),
        ("/level-role-add","Роль за уровень",          "5 @роль",     "admin"),
        ("/level-roles",   "Список ролей за уровни",   "",            "all"),
    ]},

    {"id": "util", "emoji": "🔧", "title": "Инструменты", "color": 0x1ABC9C, "commands": [
        ("/botinfo",       "Информация о боте",        "",            "all"),
        ("/serverinfo",    "Информация о сервере",     "",            "all"),
        ("/uptime",        "Время работы бота",        "",            "all"),
        ("/health",        "Здоровье сервера",         "",            "all"),
        ("/avatar",        "Аватар пользователя",      "@user",       "all"),
        ("/channel-stats", "Статистика канала",        "",            "all"),
        ("/archive",       "Архив сообщений",          "100",         "admin"),
        ("/ai-reset",      "Сбросить историю AI",      "",            "all"),
        ("/ai-learn",      "Обучить AI",               "тема текст",  "admin"),
        ("/color",         "Информация о цвете",       "#FF5733",     "all"),
        ("/announce",      "Создать объявление",       "#канал текст","admin"),
    ]},

    {"id": "ai", "emoji": "🤖", "title": "AI Ассистент", "color": 0xC8922A, "commands": [
        ("AI Чат",        "Просто напишите в канал с AI",     "",  "all"),
        ("/ai-reset",     "Сбросить историю разговора",       "",  "all"),
        ("/ai-learn",     "Научить AI новому факту",          "",  "admin"),
        ("Тикеты",        "AI помогает в тикетах автоматически", "", "all"),
    ]},
]

TOTAL_PAGES = len(CATEGORIES)
TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Построение Embed ──────────────────────────────────────────────────────────

def build_home(guild=None):
    """Главная страница — красивый обзор всех категорий"""
    g_name = guild.name if guild else "Aether"
    g_icon = guild.icon.url if guild and guild.icon else None
    g_banner = guild.banner.url if guild and guild.banner else None

    e = discord.Embed(color=0xC8922A)
    e.set_author(name=f"{g_name}  ·  Справочник команд", icon_url=g_icon)

    e.description = (
        f"### 📦 {TOTAL_CMDS} команд  ·  {TOTAL_PAGES - 1} категорий\n\n"
        f"🟢 **Все**  ·  🟡 **Мод**  ·  🔴 **Админ**\n\n"
        f"{DIVIDER}\n"
    )

    for c in CATEGORIES[1:]:
        count = len(c['commands'])
        # Краткое описание из первых 3 команд
        preview = " · ".join(cmd[0].split()[-1] for cmd in c['commands'][:3])
        if len(c['commands']) > 3:
            preview += f" · +{len(c['commands'])-3}"
        e.description += f"\n{c['emoji']}  **{c['title']}** — `{count} команд`\n-# {preview}\n"

    e.description += f"\n{DIVIDER}\n-# Выберите категорию в меню ниже ↓"

    if g_banner:
        e.set_image(url=g_banner)

    e.set_footer(text=f"{g_name}  ·  !help  ·  1/{TOTAL_PAGES}", icon_url=g_icon)
    return e


def build_category(page, guild=None):
    """Страница конкретной категории"""
    cat = CATEGORIES[page]
    cmds = cat["commands"]
    g_name = guild.name if guild else "Aether"
    g_icon = guild.icon.url if guild and guild.icon else None

    e = discord.Embed(color=cat["color"])
    e.set_author(
        name=f"{cat['emoji']}  {cat['title']}  ·  {len(cmds)} команд",
        icon_url=g_icon
    )

    # Формируем список команд
    lines = []
    for name, desc, usage, perm in cmds:
        icon = PERM[perm]["icon"]
        usage_str = f" `{usage}`" if usage else ""
        lines.append(f"{icon} **`{name}`**{usage_str}\n╰ {desc}")

    # Разбиваем на 2 колонки если много команд
    if len(lines) > 8:
        mid = (len(lines) + 1) // 2
        col1 = "\n".join(lines[:mid])
        col2 = "\n".join(lines[mid:])
        e.add_field(name="", value=col1, inline=True)
        e.add_field(name="", value=col2, inline=True)
    else:
        e.description = "\n".join(lines)

    # Подсчёт по правам
    perm_counts = {}
    for _, _, _, p in cmds:
        perm_counts[p] = perm_counts.get(p, 0) + 1
    parts = []
    for k in ("all", "mod", "admin", "owner"):
        if k in perm_counts:
            parts.append(f"{PERM[k]['icon']} {PERM[k]['label']}: **{perm_counts[k]}**")
    if parts:
        e.add_field(name="", value="  ·  ".join(parts), inline=False)

    e.set_footer(
        text=f"{g_name}  ·  {page + 1}/{TOTAL_PAGES}  ·  !help",
        icon_url=g_icon
    )
    if g_icon:
        e.set_thumbnail(url=g_icon)
    return e


def build_embed(page, guild=None):
    if page == 0:
        return build_home(guild)
    return build_category(page, guild)


# ── UI компоненты ─────────────────────────────────────────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self, current_page):
        options = []
        for i, c in enumerate(CATEGORIES):
            count = len(c['commands'])
            desc = f"{count} команд" if count else "Обзор всех категорий"

            options.append(discord.SelectOption(
                label=c['title'],
                value=str(i),
                description=desc[:100],
                default=(i == current_page),
            ))

        super().__init__(
            placeholder="Выберите категорию...",
            options=options,
            custom_id="help_cat_select",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction):
        page = int(self.values[0])
        view = HelpView(page=page)
        await interaction.response.edit_message(
            embed=build_embed(page, interaction.guild), view=view
        )


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
        await interaction.response.edit_message(
            embed=build_embed(self.page, interaction.guild), view=self
        )

    @discord.ui.button(
        label="  1 / 12  ", style=discord.ButtonStyle.primary,
        disabled=True, row=1, custom_id="help_page"
    )
    async def page_label(self, interaction, button):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1, custom_id="help_next")
    async def next_btn(self, interaction, button):
        self.page = min(TOTAL_PAGES - 1, self.page + 1)
        self._sync()
        await interaction.response.edit_message(
            embed=build_embed(self.page, interaction.guild), view=self
        )

    @discord.ui.button(
        label="🏠 Меню", style=discord.ButtonStyle.success,
        row=1, custom_id="help_home"
    )
    async def home_btn(self, interaction, button):
        self.page = 0
        self._sync()
        await interaction.response.edit_message(
            embed=build_embed(0, interaction.guild), view=self
        )

    @discord.ui.button(
        label="✖", style=discord.ButtonStyle.danger,
        row=1, custom_id="help_close"
    )
    async def close_btn(self, interaction, button):
        await interaction.response.defer()
        await interaction.delete_original_response()


# ── Cog ───────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["yardim", "h", "?", "команды", "помощь"])
    async def help_prefix(self, ctx):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(embed=build_embed(0, ctx.guild), view=HelpView(page=0))

    @app_commands.command(name="help", description="Показать все команды бота")
    async def help_slash(self, interaction):
        await interaction.response.send_message(
            embed=build_embed(0, interaction.guild),
            view=HelpView(page=0),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Help(bot))
    bot.add_view(HelpView())
