"""Панель логов — интерактивное меню с фильтрацией по категориям"""
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime

AUDIT_FILE = "data/audit_log.json"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
EVENTS_PER_PAGE = 5

# Категории логов
LOG_CATEGORIES = [
    {"id": "all",     "title": "Все события",    "color": 0xC8922A},
    {"id": "mod",     "title": "Модерация",      "color": 0xE74C3C},
    {"id": "member",  "title": "Участники",      "color": 0x2ECC71},
    {"id": "message", "title": "Сообщения",      "color": 0x3498DB},
    {"id": "voice",   "title": "Голос",          "color": 0x1ABC9C},
    {"id": "server",  "title": "Сервер",         "color": 0x9B59B6},
]


def _load_logs(guild_id: int) -> list:
    """Загрузить логи для сервера"""
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(str(guild_id), [])
    except:
        return []


def _filter_logs(logs: list, category: str) -> list:
    """Фильтровать логи по категории"""
    if category == "all":
        return logs
    return [l for l in logs if l.get('category') == category]


def _format_time(timestamp: str) -> str:
    """Форматировать время"""
    try:
        dt = datetime.datetime.fromisoformat(timestamp)
        return dt.strftime("%H:%M")
    except:
        return "??:??"


def _format_date(timestamp: str) -> str:
    """Форматировать дату"""
    try:
        dt = datetime.datetime.fromisoformat(timestamp)
        return dt.strftime("%d.%m.%Y")
    except:
        return "??"


def _count_today(logs: list) -> dict:
    """Подсчитать события за сегодня по категориям"""
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    counts = {}
    for log in logs:
        ts = log.get('timestamp', '')
        if ts.startswith(today):
            cat = log.get('category', 'other')
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def _get_action_emoji(action: str) -> str:
    """Получить текстовый индикатор для действия (без эмодзи)"""
    action_lower = action.lower()
    if 'бан' in action_lower and 'снят' not in action_lower:
        return '**[БАН]**'
    if 'бан снят' in action_lower:
        return '**[РАЗБАН]**'
    if 'кик' in action_lower:
        return '**[КИК]**'
    if 'мут' in action_lower and 'снят' not in action_lower:
        return '**[МУТ]**'
    if 'мут снят' in action_lower:
        return '**[РАЗМУТ]**'
    if 'предупреждение' in action_lower:
        return '**[ПРЕДУПРЕЖДЕНИЕ]**'
    if 'вошёл' in action_lower or 'присоединился' in action_lower:
        return '**[ВХОД]**'
    if 'вышел' in action_lower or 'покинул' in action_lower:
        return '**[ВЫХОД]**'
    if 'ник' in action_lower:
        return '**[НИК]**'
    if 'удалено' in action_lower:
        return '**[УДАЛЕНО]**'
    if 'изменено' in action_lower:
        return '**[ИЗМЕНЕНО]**'
    if 'голос' in action_lower and 'вошёл' in action_lower:
        return '**[ГОЛОС+]**'
    if 'голос' in action_lower and 'вышел' in action_lower:
        return '**[ГОЛОС-]**'
    if 'роль' in action_lower and 'создана' in action_lower:
        return '**[РОЛЬ+]**'
    if 'роль' in action_lower and 'удалена' in action_lower:
        return '**[РОЛЬ-]**'
    if 'роль' in action_lower:
        return '**[РОЛЬ]**'
    if 'канал' in action_lower and 'создан' in action_lower:
        return '**[КАНАЛ+]**'
    if 'канал' in action_lower and 'удалён' in action_lower:
        return '**[КАНАЛ-]**'
    if 'канал' in action_lower:
        return '**[КАНАЛ]**'
    if 'приглашение' in action_lower:
        return '**[ИНВАЙТ]**'
    return f'**[{action.upper()}]**'


def _format_log_entry(log: dict) -> str:
    """Форматировать одну запись лога"""
    time = _format_time(log.get('timestamp', ''))
    action = log.get('action', '?')
    indicator = _get_action_emoji(action)

    user_name = log.get('user_name', log.get('target_name', '?'))
    user_id = log.get('user_id', log.get('target_id', ''))

    lines = [f"`{time}` {indicator} **{user_name}**"]

    # Детали
    details = []
    if log.get('reason'):
        details.append(f"Причина: {log['reason']}")
    if log.get('mod_name'):
        details.append(f"Модератор: {log['mod_name']}")
    if log.get('channel'):
        details.append(f"Канал: {log['channel']}")
    if log.get('content'):
        content = log['content'][:100]
        details.append(f'"{content}"')
    if log.get('added_roles'):
        details.append(f"+ {', '.join(log['added_roles'])}")
    if log.get('removed_roles'):
        details.append(f"- {', '.join(log['removed_roles'])}")
    if log.get('old_nick'):
        details.append(f"{log['old_nick']} → {log.get('new_nick', '?')}")
    if log.get('account_age_days') is not None:
        details.append(f"Аккаунт: {log['account_age_days']} дн.")

    if details:
        lines.append(f"> {' · '.join(details)}")

    return '\n'.join(lines)


# ── Embed Builders ────────────────────────────────────────────────────────────

def build_log_home(guild, logs: list) -> discord.Embed:
    """Главная страница — обзор всех категорий"""
    counts = _count_today(logs)
    total = len(logs)

    e = discord.Embed(color=0xC8922A)
    e.description = (
        f"## Журнал событий\n"
        f"**{guild.name}** · всего **{total}** записей\n\n"
        f"{DIVIDER}"
    )

    for cat in LOG_CATEGORIES[1:]:  # пропускаем "all"
        cat_count = counts.get(cat['id'], 0)
        cat_logs = _filter_logs(logs, cat['id'])
        # Последние 2 события для превью
        preview_lines = []
        for log in cat_logs[-2:]:
            time = _format_time(log.get('timestamp', ''))
            action = log.get('action', '?')
            user = log.get('user_name', log.get('target_name', '?'))
            preview_lines.append(f"`{time}` {action} — {user}")

        preview = '\n'.join(preview_lines) if preview_lines else "Нет событий"

        e.description += (
            f"\n**{cat['title']}** — {cat_count} за сегодня\n"
            f"-# {preview}\n"
        )

    e.description += f"{DIVIDER}\n-# Выберите категорию в меню ниже"
    e.set_footer(text=f"!logs · {guild.name}")
    return e


def build_log_category(guild, logs: list, category_id: str, page: int = 0) -> discord.Embed:
    """Страница конкретной категории"""
    cat = next((c for c in LOG_CATEGORIES if c['id'] == category_id), LOG_CATEGORIES[0])
    filtered = _filter_logs(logs, category_id)
    # Сортируем по времени (новые первые)
    filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    total = len(filtered)
    total_pages = max(1, (total + EVENTS_PER_PAGE - 1) // EVENTS_PER_PAGE)
    page = min(page, total_pages - 1)

    # Логи для текущей страницы
    start = page * EVENTS_PER_PAGE
    end = start + EVENTS_PER_PAGE
    page_logs = filtered[start:end]

    e = discord.Embed(color=cat['color'])

    if category_id == "all":
        counts = _count_today(logs)
        stats_parts = []
        for c in LOG_CATEGORIES[1:]:
            cnt = counts.get(c['id'], 0)
            if cnt > 0:
                stats_parts.append(f"**{c['title']}**: {cnt}")
        stats_line = ' · '.join(stats_parts) if stats_parts else "Нет событий за сегодня"

        e.description = (
            f"## Все события\n"
            f"**{total}** записей · страница {page + 1}/{total_pages}\n"
            f"{DIVIDER}\n"
            f"{stats_line}\n"
            f"{DIVIDER}\n"
        )
    else:
        e.description = (
            f"## {cat['title']}\n"
            f"**{total}** записей · страница {page + 1}/{total_pages}\n"
            f"{DIVIDER}\n"
        )

    if not page_logs:
        e.description += "\nНет событий в этой категории."
    else:
        for log in page_logs:
            entry = _format_log_entry(log)
            e.description += f"\n{entry}\n"

    e.description += f"\n{DIVIDER}"

    date_str = _format_date(datetime.datetime.utcnow().isoformat())
    e.set_footer(text=f"{guild.name} · {date_str} · {page + 1}/{total_pages}")
    return e


def build_log_embed(guild, category_id: str, page: int = 0) -> discord.Embed:
    """Построить embed для категории"""
    logs = _load_logs(guild.id)
    if category_id == "home":
        return build_log_home(guild, logs)
    return build_log_category(guild, logs, category_id, page)


# ── Select Menu ───────────────────────────────────────────────────────────────

class LogCategorySelect(discord.ui.Select):
    def __init__(self, current_category: str):
        logs_all = []
        options = []
        for cat in LOG_CATEGORIES:
            options.append(discord.SelectOption(
                label=cat['title'],
                value=cat['id'],
                description=f"Показать {cat['title'].lower()}",
                default=(cat['id'] == current_category),
            ))

        super().__init__(
            placeholder="Выберите категорию...",
            options=options,
            custom_id="log_cat_select",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction):
        category = self.values[0]
        view = LogView(category=category, page=0)
        embed = build_log_embed(interaction.guild, category, 0)
        await interaction.response.edit_message(embed=embed, view=view)


# ── View ──────────────────────────────────────────────────────────────────────

class LogView(discord.ui.View):
    def __init__(self, category: str = "all", page: int = 0):
        super().__init__(timeout=None)
        self.category = category
        self.page = page
        self.add_item(LogCategorySelect(category))


# ── Cog ───────────────────────────────────────────────────────────────────────

class LogPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="logs", aliases=["log", "журнал", "логи"])
    async def logs_prefix(self, ctx):
        try:
            await ctx.message.delete()
        except:
            pass
        embed = build_log_embed(ctx.guild, "all", 0)
        await ctx.send(embed=embed, view=LogView(category="all", page=0))

    @app_commands.command(name="logs", description="Открыть журнал событий")
    async def logs_slash(self, interaction):
        embed = build_log_embed(interaction.guild, "all", 0)
        await interaction.response.send_message(
            embed=embed,
            view=LogView(category="all", page=0),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(LogPanel(bot))
    bot.add_view(LogView())
