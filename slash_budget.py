# -*- coding: utf-8 -*-
"""Бюджет слеш-команд: Discord даёт максимум 100 глобальных app-команд.

С сотней модулей в cogs/ правило «каждый гибрид попадает в слеш-меню» не
масштабируется: дерево переполняется (CommandLimitReached) и коги начинают
падать каскадом по алфавиту — включая боевую модерацию (warnings, ticket...).

Решение — централизованный white-list. После загрузки каждого модуля дерево
чистится: в слеш-меню остаются только имена из KEEP_SLASH, всё остальное
выносится ИЗ ДЕРЕВА, но НЕ из бота: префиксные версии гибридных команд
продолжают работать (!варн, !тикет-конфиг, !отчёт-неделя...). То есть
функциональность не теряется — меню просто остаётся компактным и осмысленным.

ВАЖНО (баг 2026-08-28): часть когов регистрирует команды ЛОКАЛЬНО —
add_cog(..., guilds=Config.guild_objects()) — и раньше бюджет чистил только
глобальное дерево. Guild-scoped команды (/security, /backup, /ticket-*…)
обходили whitelist и возвращались в меню сервера (вместо 6 команд было 13).
Теперь бюджет чистит и все guild-скоупы (MAIN_GUILD_ID + EXTRA_GUILD_IDS).

Как вернуть команду в слеш-меню: добавь её ИМЯ КАК В DISCORD (name= из
декоратора, это не всегда имя функции) в KEEP_SLASH. Страж-бюджета —
tests/test_slash_budget.py: следит, чтобы меню не переполнилось и чтобы
имена из KEEP_SLASH реально существовали (ловит переименования).
"""
from discord import AppCommandType, app_commands

LIMIT = 100          # жёсткий лимит Discord на глобальные chat-input команды
WARN_AT = 90         # мягкий порог — пора пересмотреть меню

# Что видит участник и модератор в слеш-меню. Кураторский набор ЛЁГКОГО
# состава (cogs_policy LEAN — он по умолчанию): модерация-ядро, защита,
# jail, апелляции, логи, тикеты + заявки, приветствие, AI и служебное.
# Игровых/экономических имён здесь больше нет — эти модули спят, и
# держать их в меню бессмысленно (команды просто не существуют в боте).
# Редкие настройки живут в веб-панели и на префиксе.
KEEP_SLASH = frozenset({
    # Боевой минимум (заказ владельца 2026-08-28, «как можно меньше»):
    # мод-панель (внутри варн/мут/бан/клир — выпадающим меню), музыка
    # (управление кнопками на пульте ответа), апелляция (ЛС боту,
    # keep_global) и /update (только владелец, виден только в ЛС).
    'modpanel',
    'play',
    'апелляция',
    'update',
    # Вернуло владельца (2026-08-28 «/afk ведь есть?»): статус AFK —
    # вход/выход обеими командами.
    'afk',
    'afk-remove',
    # Тикеты (2026-08-29 «куда пропали тикеты»): вернул в меню.
    # ticket-panel — панель выбора категории в канал (админ);
    # ticket-add / ticket-remove — добавить/убрать участника в тикете
    # (мод, manage_channels). Внутри тикета меню кнопок (➕/➖/📣/🗑)
    # приходит автоматически — TicketManageView.
    'ticket-panel',
    'ticket-add',
    'ticket-remove',
})


def _chat_input_commands(tree, guild=None):
    """Chat-input команды дерева (контекстные меню — отдельный лимит).

    guild=None — глобальный scope; guild=discord.Object — локальный
    (guild-scoped) scope команд, зарегистрированных через
    add_cog(..., guilds=Config.guild_objects()).
    """
    try:
        cmds = tree.get_commands(guild=guild)
    except TypeError:
        cmds = tree.get_commands()
    return [c for c in cmds if not isinstance(c, app_commands.ContextMenu)]


def _guild_scopes():
    """Скоупы из .env (MAIN_GUILD_ID + EXTRA_GUILD_IDS) — discord.Object.

    ВАЖНО: часть когов регистрирует свои слеш-команды как ЛОКАЛЬНЫЕ
    (guild-scoped) — add_cog(..., guilds=Config.guild_objects()). Белый
    список обязателен и для них: без этого бюджет чистил только глобальное
    дерево, а локальные команды (security, backup, ticket-panel…) на
    сервере МИНОВАЛИ whitelist и возвращались в меню после рестарта.
    """
    try:
        from config import Config
        return list(Config.guild_objects())
    except Exception:
        return []


def apply_slash_budget(tree, keep=None, guilds=None):
    """Оставить в дереве только имена из keep. Идемпотентно.

    Чистит и глобальный scope, и все guild-скоупы (.env: MAIN_GUILD_ID /
    EXTRA_GUILD_IDS) — иначе локальные команды миновали бы бюджет.
    guilds — переопределить скоупы (None — из Config).

    Возвращает (kept, pruned) — отсортированные списки имён оставленных и
    удалённых из дерева команд (удалённые остаются доступны через префикс).
    """
    keep = KEEP_SLASH if keep is None else keep
    kept, pruned = [], []
    scopes = _guild_scopes() if guilds is None else list(guilds)
    for scope in [None] + scopes:
        for cmd in _chat_input_commands(tree, guild=scope):
            if cmd.name in keep:
                kept.append(cmd.name)
                continue
            try:
                tree.remove_command(cmd.name, type=AppCommandType.chat_input,
                                    guild=scope)
                pruned.append(cmd.name)
            except Exception as _ex:
                if scope is None:
                    raise
    return sorted(set(kept)), sorted(set(pruned))
