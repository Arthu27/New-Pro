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
import os

from discord import AppCommandType, app_commands

LIMIT = 100          # жёсткий лимит Discord на chat-input команды В СКОУПЕ
WARN_AT = 90         # мягкий порог — пора пересмотреть меню

# Полный состав (BOT_FULL=1): сколько команд держать в меню. Меньше LIMIT:
# 1) самый тяжёлый ког добавляет до 9 команд за раз — нужен запас, иначе
#    discord.py валит модуль CommandLimitReached прямо при загрузке;
# 2) full_sync копирует глобальное дерево в гильдию ПОВЕРХ локальных —
#    сумма в гильдии обязана остаться <= LIMIT, иначе guild-синк падает
#    и «команды не грузятся» целиком.
SAFE_FULL = 80
MAX_COG_BURST = 12   # измеренный максимум от одного кога (9) + запас

_TRUE = ('1', 'true', 'yes', 'on')

_budget_log = None


def _logger():
    global _budget_log
    if _budget_log is None:
        import logging
        _budget_log = logging.getLogger('slash_budget')
        _budget_log.addHandler(logging.NullHandler())
    return _budget_log


def full_menu_mode(environ=None):
    """BOT_FULL=1 — слеш-меню держит ВСЕ команды (до жёсткого лимита).

    Жалоба владельца 30.08 «команды не грузятся»: в полном составе модулей
    пользователь ожидает видеть в Discord ВСЕ команды, а не кураторские 7.
    Лёгкий состав (LEAN, по умолчанию) — по-прежнему кураторский KEEP_SLASH.

    Приоритет: тумблер на странице «Команды» (data/menu_mode.json — заказ
    30.08 «оставим только 7») → BOT_FULL из .env. Так режим переключается
    из панели без правки .env на сервере.
    """
    try:
        from services.menu_mode import is_full
        return bool(is_full(environ))
    except Exception as ex:      # сервис недоступен — .env, как раньше
        _logger().warning('full_menu_mode: menu_mode недоступен (%s) — '
                          'читаю BOT_FULL из .env', ex)
        env = os.environ if environ is None else environ
        return str(env.get('BOT_FULL', '') or '').strip().lower() in _TRUE

# Что видит участник и модератор в слеш-меню. Кураторский набор ЛЁГКОГО
# состава (cogs_policy LEAN — он по умолчанию): модерация-ядро, защита,
# jail, апелляции, логи, тикеты + заявки, приветствие, AI и служебное.
# Игровых/экономических имён здесь больше нет — эти модули спят, и
# держать их в меню бессмысленно (команды просто не существуют в боте).
# Редкие настройки живут в веб-панели и на префиксе.
KEEP_SLASH = frozenset({
    # Боевой минимум (заказ владельца 2026-08-28, «как можно меньше»):
    # мод-панель (внутри варн/мут/бан/клир — выпадающим меню), апелляция
    # (ЛС боту, keep_global) и /update (только владелец, виден только в ЛС).
    # Музыка (/play) снята с эксплуатации 2026-09-01 — бот модерационный;
    # коги music_cog/voice_commands в RETIRED_COGS, команды не публикуются.
    'modpanel',
    'апелляция',
    'update',
    # Вернуло владельца (2026-08-28 «/afk ведь есть?»): статус AFK —
    # вход/выход обеими командами.
    'afk',
    'afk-remove',
    # Тикет-система снята с эксплуатации (2026-08-31) — её роль выполняет
    # система репортов /report (жалоба карточкой в канал модерации). Команды
    # ticket-* в меню больше не держим; ког ticket.py в RETIRED_COGS.
    'report',              # подать жалобу (фото/видео-доказательство) — всем
    'my-violations',       # мои нарушения (обжалование — /апелляция в ЛС)
    # Верификация молодых аккаунтов (заказ владельца 2026-08-31): разовая
    # админ-настройка — создаёт канал верификации и публикует кнопку анкеты.
    # Дальнейшее управление — из веб-панели (страница «Верификация»).
    'verify-setup',
})

# Контекстные меню (ПКМ по сообщению/участнику: «Предупредить», «Изолировать»,
# «Варн за сообщение», войс-мут/размут/кик). Это ОТДЕЛЬНЫЙ лимит Discord (5
# user + 5 message на скоуп), но жалоба владельца «грузятся 13 лишних команд»
# была именно про них: бюджет раньше чистил только chat-input и 6 ПКМ-меню из
# mod_tools уезжали на сервер даже в кураторском наборе. В LEAN их в меню не
# держим (всё это есть в /modpanel выпадающим списком) — пустой белый список.
# В BOT_FULL они остаются (full_menu_mode → все меню разрешены).
KEEP_CTX = frozenset()


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


def _context_menus(tree, guild=None):
    """Контекстные меню (ПКМ) дерева в скоупе (глобально или guild-scoped)."""
    try:
        cmds = tree.get_commands(guild=guild)
    except TypeError:
        cmds = tree.get_commands()
    return [c for c in cmds if isinstance(c, app_commands.ContextMenu)]


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
    # Режим меню: полный (BOT_FULL) держит всё, что влезает; кураторский
    # (LEAN по умолчанию) — только KEEP_SLASH слэш-команды и KEEP_CTX меню.
    _full = full_menu_mode()
    if keep is None:
        if _full:
            # Полный состав: единый keep-сет на ВСЕ скоупы (глобальный и
            # гильдовые) — иначе копия глобального в гильдию переполнит её
            # поверх локальных команд и guild-синк упадёт целиком.
            _names = set()
            scopes_pre = _guild_scopes() if guilds is None else list(guilds)
            for scope in [None] + scopes_pre:
                for cmd in _chat_input_commands(tree, guild=scope):
                    _names.add(cmd.name)
            if len(_names) <= LIMIT - MAX_COG_BURST:
                keep = _names            # всё влезает с запасом — не режем
            else:
                # перебор: кураторские всегда в меню + первые по алфавиту
                _rest = sorted(_names - KEEP_SLASH)[:max(0, SAFE_FULL - len(KEEP_SLASH))]
                keep = set(KEEP_SLASH) | set(_rest)
        else:
            keep = KEEP_SLASH
    # Контекстные ПКМ-меню: в полном составе оставляем все (отдельный лимит
    # Discord, в бюджет 100 не входят), в кураторском — только KEEP_CTX.
    # Баг «13 лишних команд на старте»: 6 ПКМ-меню mod_tools регистрируются
    # глобально и раньше НЕ вырезались бюджетом, уезжая на сервер.
    keep_ctx = None if _full else set(KEEP_CTX)
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
        # Контекстные меню того же скоупа
        for cmd in _context_menus(tree, guild=scope):
            if keep_ctx is None or cmd.name in keep_ctx:
                kept.append(cmd.name)
                continue
            try:
                tree.remove_command(cmd.name,
                                    type=getattr(cmd, 'type', None) or AppCommandType.user,
                                    guild=scope)
                pruned.append(cmd.name)
            except Exception as _ex:
                if scope is None:
                    raise
    return sorted(set(kept)), sorted(set(pruned))
