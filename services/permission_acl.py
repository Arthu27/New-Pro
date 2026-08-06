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
                   "unschedule", "pw", "history", "case", "cases", "note", "notes", "watchlist",
                   "watchlist-show", "banlist", "massrole", "modstats", "mod-stats", "activemods",
                   "modwhitelist", "tempmod", "voice-status", "role", "jail", "jailed",
                   "unjail", "utility", "report-panel", "weekly-report", "report-setup",
                   "report-role-add", "report-role-remove", "meeting-start", "meeting-count",
                   "meeting", "meeting-role-add", "meeting-role-remove", "staff-stats"],
    "Экономика": ["economy", "shop", "buy", "inventory", "balance", "daily", "weekly",
                   "transfer", "top", "work", "job", "jobs", "bank", "bankup", "interest",
                   "vault", "stock", "trade", "slots", "casino-coinflip", "casino-dice",
                   "eco-history", "beg", "sell", "use", "pets", "gprofile"],
    "Уровни": ["profile", "xp-rank", "xp-leaderboard", "leaderboard", "level-role-add",
                "level-role-remove", "level-role", "badges", "streak"],
    "Тикеты": ["ticket", "ticket-panel", "ticket-config", "ticket-add", "ticket-remove",
                "ticket-auto-close", "ticket-ai-toggle", "ticket-ai-stats",
                "ticket-force-escalate", "ticket-rate-limit-info", "ticket-reset-rate-limit",
                "ticket-feedback-stats", "sla-status", "sla-info", "sla-create", "sla-breaches"],
    "Развлечения": ["poll", "poll-end", "activity", "activity-list", "game-find", "game-list",
                     "game-leaderboard", "coinflip", "rps", "8ball", "random-member", "dice",
                     "guess", "guess-start", "event-create", "events", "event-cancel",
                     "giveaway", "reroll", "pomodoro", "pomodoro-complete", "pomodoro-stats",
                     "anime", "anime-suggest", "anime-setup", "anime-off"],
    "Сервер": ["setup-logs", "antiraid", "antiraid-reload", "announce", "stats", "server",
                "botinfo", "uptime", "health", "avatar", "banner", "channelinfo", "roleinfo",
                "color", "say", "embed_builder", "embed_history", "duty-panel", "duty-add",
                "duty-stats", "backup", "backup-channel", "backup-list", "rejoin-toggle",
                "rejoin-status", "security", "security-toggle", "security-newaccount",
                "verify-toggle", "verify-status", "archive", "channel-stats", "scan-link",
                "changelog", "changelog-add", "changelog-latest", "summary", "welcome",
                "medialock", "j2c", "vc", "crown", "antifake", "emojis", "time", "account",
                "firstmessage", "invite"],
    "Приглашения/Участники": ["invites", "invite-ranking", "birthday",
                                "birthday-delete", "birthday-setup", "birthdays", "staff-panel",
                                "help", "userinfo", "report", "report-analytics", "report-custom",
                                "report-daily", "report-weekly"],
    "Служебные": ["leaveguild", "module", "load", "unload", "reload", "reload-all",
                   "execute-command", "ai-reset", "ai-info-list", "flag-create", "flag-enable",
                   "flag-disable", "flag-list", "flag-info", "flag-rollout", "ab-add-variant",
                   "ab-create", "ab-start", "ab-stats", "ab-stop", "ab-variants",
                   "time-report", "time-start", "time-stop", "report-no", "report-ok",
                   "play", "pause", "skip", "queue", "volume", "leave"],
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
