"""
Ролевой контроль доступа к командам бота (Command ACL).

Хранит: guild_id -> { command_or_category: [role_ids...] }
Правило: пользователь может использовать команду, если ЛЮБАЯ его роль
находится в списке разрешённых для этой команды/категории.

Если для команды/категории не задано никаких ограничений — она доступна всем
(поведение по умолчанию, чтобы ничего не ломать).

Хранение — SQLite через db.GuildData (namespace "cmd_acl").
"""
import json
import os
from logger import get_logger

log = get_logger("cmd_acl")

# Категории команд для панели (label -> список команд)
# Значения — это имена команд, которые бот определяет в рантайме.
COMMAND_CATEGORIES = {
    "Модерация": ["ban", "kick", "timeout", "untimeout", "unban", "warn", "warnings",
                   "unwarn", "clearwarns", "moderate", "modpanel", "temp-mute", "temp-unmute",
                   "tempban", "temp-unban", "tempkick", "vmute", "vunmute", "schedule",
                   "unschedule", "pw", "history", "case", "note", "notes", "watchlist",
                   "watchlist-show", "banlist", "massrole", "modstats", "activemods",
                   "modwhitelist", "tempmod", "voice-status", "role"],
    "Экономика": ["economy", "shop", "buy", "games", "leaderboard"],
    "Уровни": ["profil-kartы", "profile", "rank", "top-level", "leveling"],
    "Тикеты": ["ticket", "ticket-panel", "mytickets", "viewticket", "ticket-help",
                "ticket-config", "ticket-add", "ticket-cikar", "ticket-auto-close",
                "ticket-ai-toggle", "ticket-ai-stats"],
    "Развлечения": ["fun", "games", "anket", "anket-bitir", "rastgele-участник",
                     "geri-число", "hatыrlatыcы", "etkinlik", "oyun-ara", "oyun-liste",
                     "coinflip", "rps", "8ball", "poll"],
    "Сервер": ["setup-logs", "antiraid", "announce", "stats", "server", "botinfo",
                "uptime", "health", "avatar", "banner", "channelinfo", "roleinfo",
                "rolemembers", "color", "say", "embed_builder", "embed_history",
                "duty-panel", "duty-add", "duty-stats", "backup", "rejoin-toggle",
                "security", "security-toggle", "verify-toggle", "archive", "channel-stats"],
    "Приглашения/Участники": ["davet", "invites", "invite-ranking", "afk", "birthday",
                                "birthdays", "staff-panel", "faq-learn", "faq-list", "help"],
    "Служебные": ["leaveguild", "cog-manager", "execute-command", "vc_leave"],
}


def _acl_db():
    from db import GuildData
    return GuildData("cmd_acl")


def load_acl(guild_id: int) -> dict:
    """Вернуть ограничения: {command_or_category: [role_ids]}"""
    try:
        acl = _acl_db().get(int(guild_id), "acl", {})
        return acl if isinstance(acl, dict) else {}
    except Exception as e:
        log.warning(f"[cmd_acl] load error: {e}")
        return {}


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


def has_access(guild_id: int, command: str, member) -> bool:
    """Может ли member использовать команду command.

    Правило: если для команды (или её категории) заданы разрешённые роли,
    пользователь должен иметь хотя бы одну из них. Иначе — доступно всем.
    """
    if member is None or getattr(member, "bot", False):
        return True
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True

    acl = load_acl(guild_id)
    user_roles = {str(r.id) for r in getattr(member, "roles", [])}

    # Проверка точного имени команды
    allowed = acl.get(str(command))
    if allowed:
        if not user_roles.intersection(set(allowed)):
            return False

    # Проверка категорий (если команда в категории с ограничением)
    for cat, cmds in COMMAND_CATEGORIES.items():
        if command in cmds:
            cat_allowed = acl.get(cat)
            if cat_allowed:
                if not user_roles.intersection(set(cat_allowed)):
                    return False
    return True


def roles_for_command(guild_id: int, command: str) -> list:
    """Какие роли разрешены для команды (пусто = все)."""
    acl = load_acl(guild_id)
    allowed = acl.get(str(command))
    if allowed:
        return allowed
    for cat, cmds in COMMAND_CATEGORIES.items():
        if command in cmds:
            ca = acl.get(cat)
            if ca:
                return ca
    return []


def available_commands() -> list:
    """Список всех команд (для панели)."""
    cmds = set()
    for cmds_list in COMMAND_CATEGORIES.values():
        cmds.update(cmds_list)
    return sorted(cmds)
