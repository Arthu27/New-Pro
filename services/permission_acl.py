"""
Ролевой контроль доступа к командам бота (Command ACL) + классические
разрешения на действия (Action ACL).

Хранит: guild_id -> { command_or_category: [role_ids...] }
Правило: пользователь может использовать команду, если ЛЮБАЯ его роль
находится в списке разрешённых для этой команды/категории.

Если для команды/категории не задано никаких ограничений — она доступна всем
(поведение по умолчанию, чтобы ничего не ломать).

Сабкоманды групп (slash): имя события передаётся как qualified name
("j2c lobby"); проверка идёт по цепочке кандидатов:
"j2c-lobby" -> "j2c". Это гарантирует, что правило, назначенное в панели
на группу ("j2c") или на конкретную сабкоманду ("j2c-lobby"), реально
срабатывает в рантайме. Кандидаты режутся ТОЛЬКО по пробелам:
имя "report-role-add" (одна команда) не ловит правило от "report".

Хранение — SQLite через db.GuildData (namespace "cmd_acl").

── Классические разрешения (Action ACL) ────────────────────────────────────
Действие не привязано к команде: правило «ban» блокирует ЛЮБУЮ команду,
которая банит (ban, tempban, unban, /moderate action=ban…). Это страховка
«на всякий случай»: сколько бы команд ни умели банить/мутить/таймаутить,
роль без разрешения на действие не выполнит его ни одной из них.

Хранение — SQLite через db.GuildData (namespace "action_acl").
"""
import json
import os
import re
from logger import get_logger

log = get_logger("cmd_acl")

# Категории команд для панели (label -> список команд).
# Значения — имена команд, которые бот определяет в рантайме.
# Набор урезан до ядра: модерация, тикеты, логи и AI — остальные модули
# (экономика, уровни, развлечения, музыка и т.д.) не управляются здесь.
COMMAND_CATEGORIES = {
    "Модерация": ["ban", "kick", "unban", "warn", "warnings", "unwarn", "clearwarns",
                   "mute", "unmute", "clear", "slowmode", "lock", "unlock",
                   "moderate", "modpanel", "temp-mute", "temp-unmute", "tempban",
                   "temp-unban", "tempkick", "vmute", "vunmute", "schedule", "unschedule",
                   "schedule-add", "schedule-list", "schedule-remove", "schedule-test",
                   "schedule-toggle", "pw", "history", "case", "cases", "note", "notes",
                   "watchlist", "banlist", "massrole", "modstats",
                   "mod-stats", "activemods", "modwhitelist", "tempmod", "voice-status",
                   "role", "utility", "report-panel",
                   "weekly-report", "report-setup", "report-role-add", "report-role-remove",
                   "meeting", "meeting-role-add", "meeting-role-remove", "staff-stats",
                   "filter", "filter-status", "filter-add", "filter-remove",
                   "filter-words", "filter-toggle", "filter-test", "filter-ignore",
                   "reactionrole", "removereactionrole",
                   "replay", "ladder", "ladder-add", "ladder-remove", "ladder-test"],
    "Тикеты": ["ticket-panel", "ticket-config", "ticket-add", "ticket-remove",
                "ticket-auto-close", "ticket-ai-toggle", "ticket-ai-stats",
                "ticket-force-escalate", "ticket-rate-limit-info", "ticket-reset-rate-limit",
                "ticket-feedback-stats", "sla-status", "sla-info", "sla-create", "sla-breaches"],
    "Логи": ["logs", "modlogs", "logmenu", "setup-logs", "logs-setup", "logs-center"],
    "AI-система": ["aimod", "aimod-escalate", "aimod-fp", "aimod-languages",
                    "aimod-logchannel", "aimod-sensitivity", "aimod-stats", "aimod-test",
                    "aimod-whitelist", "proactive-stats"],
}

# ─── Классические разрешения (действия) ────────────────────────────────────
# ключ — внутреннее имя действия, значение — русская подпись для панели.
ACTIONS = {
    "ban": "Бан (апелляция)",
    "kick": "Кик",
    "mute": "Мут",
    "timeout": "Таймаут",
    "warn": "Варн",
    "purge": "Очистка сообщений",
    "lockdown": "Локдаун",
    "roles": "Роли",
}

# команда -> действия, которые она выполняет (проверяется в рантайме).
# Команды вроде /moderate, где действие выбирается параметром, сюда не
# попадают — их ловит ACTION_VALUES в main.py (по значению опции action).
COMMAND_ACTIONS = {
    # бан
    "ban": ("ban",), "tempban": ("ban",), "unban": ("ban",), "temp-unban": ("ban",),
    "softban": ("ban",),
    # кик
    "kick": ("kick",), "tempkick": ("kick",),
    # мут (текстовый/голосовой)
    "mute": ("mute",), "unmute": ("mute",),
    "temp-mute": ("mute",), "temp-unmute": ("mute",),
    "vmute": ("mute",), "vunmute": ("mute",),
    # тихие муты (mod_plus) — то же действие «Мут», что и обычные муты
    "ghostmute": ("mute",), "ghostunmute": ("mute",),
    # таймаут
    "timeout": ("timeout",), "untimeout": ("timeout",),
    # варн
    "warn": ("warn",), "unwarn": ("warn",), "clearwarns": ("warn",), "pw": ("warn",),
    # очистка сообщений
    "clear": ("purge",), "purge": ("purge",),
    # пересоздание канала начисто = зачистка всех сообщений
    "nuke": ("purge",),
    # массовая зачистка рейда (кик или бан) — нужны оба разрешения,
    # чтобы один тумблер нельзя было обойти второй половиной действия
    "raidcleanup": ("kick", "ban"),
    # локдаун
    "lock": ("lockdown",), "unlock": ("lockdown",), "lockdown": ("lockdown",),
    # роли
    "role": ("roles",), "massrole": ("roles",),
    "reactionrole": ("roles",), "removereactionrole": ("roles",),
}

# значение опции action в slash-командах (/moderate, /utility) -> ключ действия.
ACTION_VALUES = {
    "ban": "ban", "unban": "ban", "softban": "ban",
    "kick": "kick",
    "mute": "mute", "unmute": "mute", "vmute": "mute", "vunmute": "mute",
    "timeout": "timeout", "untimeout": "timeout",
    "warn": "warn",
    "clear": "purge", "purge": "purge",
    "lock": "lockdown", "unlock": "lockdown",
}


def _acl_db():
    from db import GuildData
    return GuildData("cmd_acl")


def _action_acl_db():
    from db import GuildData
    return GuildData("action_acl")


def command_categories():
    """ЖИВОЙ список команд по разделам — из реального каталога бота.

    Каталог (services/command_registry) сканирует только включённые модули
    и только существующие команды: призраков удалённых команд здесь не
    бывает (заказ владельца 2026-08: «в Правах команд показываются старые»).
    """
    try:
        from services import command_registry as CR
        cats = {}
        for c in CR.catalog().get('commands', []):
            label = CR.CATEGORIES.get(c.get('cat'), {}).get('label',
                                                             c.get('cat', 'Прочее'))
            cats.setdefault(label, set()).add(c.get('name', ''))
        return {k: sorted(v) for k, v in cats.items() if k}
    except Exception as _ex:
        log.debug(f'command_categories(): каталог недоступен ({_ex}) — запасной список')
        return {k: list(v) for k, v in COMMAND_CATEGORIES.items()}


def all_categories():
    """Живые категории + legacy (правила на старые продолжают работать)."""
    merged = {k: list(v) for k, v in COMMAND_CATEGORIES.items()}
    for k, v in command_categories().items():
        bucket = merged.setdefault(k, [])
        for name in v:
            if name not in bucket:
                bucket.append(name)
    return merged


def load_acl(guild_id: int) -> dict:
    """Вернуть ограничения: {command_or_category: [role_ids]}"""
    try:
        acl = _acl_db().get(int(guild_id), "acl", {})
        return acl if isinstance(acl, dict) else {}
    except Exception as e:
        log.warning(f"[cmd_acl] load error: {e}")
        return {}


def effective_acl(guild_id: int) -> dict:
    """ACL для отображения: правила категории развёрнуты в её команды.

    Категория и команда — два уровня правил, при правке из панели это
    путало («выдал категорию, а команды показывают "для всех"»). Здесь
    каждое правило категории материализуется на все её команды, если у
    команды нет своего личного правила."""
    acl = dict(load_acl(guild_id))
    for cat, cmds in all_categories().items():
        rule = acl.get(cat)
        if not rule:
            continue
        for cmd in cmds:
            if cmd not in acl:
                acl[cmd] = list(rule)
    return acl


def materialize_category(acl: dict, cat: str) -> dict:
    """Правило категории → явные правила на каждую её команду (in-place).

    После этого категорийный ключ убирается: остаётся один уровень
    правил, который и панель показывает, и бот проверяет — без
    пересечений и сюрпризов."""
    rule = acl.get(cat)
    cmds = all_categories().get(cat, [])
    if rule:
        for cmd in cmds:
            if cmd not in acl:
                acl[cmd] = list(rule)
    elif cmds:
        for cmd in cmds:
            acl.setdefault(cmd, [])  # категория была «всем» — команды тоже
    acl.pop(cat, None)
    return acl


def save_acl(guild_id: int, acl: dict):
    try:
        _acl_db().set(int(guild_id), "acl", acl or {})
    except Exception as e:
        log.warning(f"[cmd_acl] save error: {e}")


def set_rule(guild_id: int, command: str, role_ids: list):
    """Установить разрешённые роли для команды/категории."""
    acl = load_acl(guild_id)
    acl[str(command)] = [str(r) for r in role_ids]
    save_acl(guild_id, acl)


def clear_rule(guild_id: int, command: str):
    """Снять ограничение (команда доступна всем)."""
    acl = load_acl(guild_id)
    acl.pop(str(command), None)
    save_acl(guild_id, acl)


# ─── Классические разрешения (Action ACL) ──────────────────────────────────
def load_action_acl(guild_id: int) -> dict:
    """Вернуть ограничения действий: {action: [role_ids]}"""
    try:
        acl = _action_acl_db().get(int(guild_id), "acl", {})
        return acl if isinstance(acl, dict) else {}
    except Exception as e:
        log.warning(f"[action_acl] load error: {e}")
        return {}


def save_action_acl(guild_id: int, acl: dict):
    try:
        _action_acl_db().set(int(guild_id), "acl", acl or {})
    except Exception as e:
        log.warning(f"[action_acl] save error: {e}")


def set_action_rule(guild_id: int, action: str, role_ids: list):
    """Разрешить действие только перечисленным ролям (пусто — снять правило)."""
    acl = load_action_acl(guild_id)
    if role_ids:
        acl[str(action)] = [str(r) for r in role_ids]
    else:
        acl.pop(str(action), None)
    save_action_acl(guild_id, acl)


def clear_action_rules(guild_id: int):
    """Снять все ограничения действий (всё можно всем)."""
    save_action_acl(guild_id, {})


def allowed_roles_for_action(guild_id: int, action: str) -> list:
    """Какие роли разрешены для действия (пусто = все)."""
    acl = load_action_acl(guild_id)
    return acl.get(str(action), []) or []


def check_action(guild_id: int, member, action: str) -> bool:
    """Может ли member выполнять действие action (бан/кик/мут/таймаут…).

    Действие не привязано к команде: правило «ban» блокирует ЛЮБУЮ команду,
    которая банит (ban, tempban, unban, /moderate action=ban…). По умолчанию
    (правила нет) — можно. Админ/бот — всегда можно, панель (is_panel) —
    отдельная авторизация, ролевые правила её не касаются.
    """
    if member is None or getattr(member, "bot", False) \
            or getattr(member, "is_panel", False):
        return True
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True
    try:  # владелец бота — действия не проверяем
        from config import Config
        if int(getattr(member, "id", 0) or 0) in Config.all_owner_ids():
            return True
    except Exception as _ex:
        log.debug(f'владелец-скип ACL: {_ex}')
    allowed = allowed_roles_for_action(guild_id, action)
    if not allowed:
        return True
    user_roles = {str(r.id) for r in getattr(member, "roles", [])}
    return bool(user_roles.intersection(set(allowed)))


def _candidates(command: str) -> list:
    """Цепочка имён для проверки, от более специфичного к родительскому.

    Разрезаем ТОЛЬКО по пробелам (qualified name сабкоманд):
      "j2c lobby"        -> ["j2c-lobby", "j2c"]
      "ticket ssla show" -> ["ticket-ssla-show", "ticket-ssla", "ticket"]
    Одиночное имя (даже с дефисами) даёт ровно одного кандидата:
      "report-role-add"  -> ["report-role-add"]  (правило "report" не сработает)
    """
    raw = str(command or "").strip()
    if not raw:
        return []
    parts = raw.split()
    if len(parts) == 1:
        return [parts[0]]
    out = []
    seen = set()
    for i in range(len(parts), 0, -1):
        cand = "-".join(parts[:i])
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def has_access(guild_id: int, command: str, member) -> bool:
    """Может ли member использовать команду command.

    Два уровня:
    1. Command ACL — правила на команду/категорию (как раньше).
    2. Action ACL — команда выполняет действие (бан/мут/таймаут…), и для
       этого действия заданы разрешённые роли: у member должна быть одна из них.
    Правило: каждое подходящее правило является ограничением — нарушение
    любого из них запрещает доступ. Если ограничений нет — доступно всем.
    """
    if member is None or getattr(member, "bot", False):
        return True
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True
    # Владелец бота (OWNER_ID/OWNER_IDS) — команды не проверяем вовсе:
    # бот принадлежит ему, ограничения ролей его не касаются
    try:
        from config import Config
        if int(getattr(member, "id", 0) or 0) in Config.all_owner_ids():
            return True
    except Exception as _ex:
        log.debug(f'владелец-скип ACL (вторая ветка): {_ex}')

    acl = load_acl(guild_id)
    user_roles = {str(r.id) for r in getattr(member, "roles", [])}

    for name in _candidates(command):
        # 1. Проверка точного имени (команда/группа)
        allowed = acl.get(name)
        if allowed and not user_roles.intersection(set(allowed)):
            return False

        # 1.1 Проверка категорий (если имя входит в категорию с ограничением)
        for cat, cmds in all_categories().items():
            if name in cmds:
                cat_allowed = acl.get(cat)
                if cat_allowed and not user_roles.intersection(set(cat_allowed)):
                    return False

        # 2. Классические разрешения: команда выполняет действие
        actions = COMMAND_ACTIONS.get(name)
        if actions:
            for action in actions:
                if not check_action(guild_id, member, action):
                    return False
    return True


def roles_for_command(guild_id: int, command: str) -> list:
    """Какие роли разрешены для команды (пусто = все)."""
    acl = load_acl(guild_id)
    for name in _candidates(command):
        allowed = acl.get(name)
        if allowed:
            return allowed
        for cat, cmds in all_categories().items():
            if name in cmds:
                ca = acl.get(cat)
                if ca:
                    return ca
    return []


def available_commands() -> list:
    """Список всех команд (для панели)."""
    cmds = set()
    for cmds_list in all_categories().values():
        cmds.update(cmds_list)
    return sorted(cmds)
