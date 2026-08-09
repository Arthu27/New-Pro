"""
Ролевой контроль доступа к командам бота (Command ACL).

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
"""
import json
import os
import re
from logger import get_logger

log = get_logger("cmd_acl")

# Категории команд для панели (label -> список команд)
# Значения — это имена команд, которые бот определяет в рантайме.
COMMAND_CATEGORIES = {
    "Модерация": ["ban", "kick", "unban", "warn", "warnings", "unwarn", "clearwarns",
                   "mute", "unmute", "clear", "slowmode", "lock", "unlock",
                   "moderate", "modpanel", "temp-mute", "temp-unmute", "tempban",
                   "temp-unban", "tempkick", "vmute", "vunmute", "schedule", "unschedule",
                   "schedule-add", "schedule-list", "schedule-remove", "schedule-test",
                   "schedule-toggle", "pw", "history", "case", "cases", "note", "notes",
                   "watchlist", "watchlist-show", "banlist", "massrole", "modstats",
                   "mod-stats", "activemods", "modwhitelist", "tempmod", "voice-status",
                   "role", "jail", "jailed", "unjail", "utility", "report-panel",
                   "weekly-report", "report-setup", "report-role-add", "report-role-remove",
                   "meeting", "meeting-role-add", "meeting-role-remove", "staff-stats",
                   "tagjail", "tagjail-on", "tagjail-off", "tagjail-status", "tagjail-scan",
                   "tagjail-style", "tagjail-auto-release", "tagjail-log-channel",
                   "tagjail-jail-role", "tagjail-exempt-role", "tagjail-exempt-user",
                   "tagjail-age-limit", "tagjail-age-action", "tagjail-add-tag",
                   "tagjail-del-tag", "tagjail-tags",
                   "aimod", "aimod-escalate", "aimod-fp", "aimod-languages",
                   "aimod-logchannel", "aimod-sensitivity", "aimod-stats", "aimod-test",
                   "aimod-whitelist", "automod", "addword", "removeword", "wordlist",
                   "proactive-stats", "reactionrole", "removereactionrole",
                   "replay", "ladder", "ladder-add", "ladder-remove", "ladder-test"],
    "Экономика": ["shop", "buy", "inventory", "balance", "daily", "weekly",
                   "transfer", "top", "work", "job", "jobs", "bank", "bankup", "interest",
                   "vault", "stock", "trade", "slots", "casino-coinflip", "casino-dice",
                   "eco-history", "beg", "sell", "use", "pets", "gprofile",
                   "deposit", "withdraw", "rob"],
    "Уровни": ["profile", "xp-rank", "xp-leaderboard", "leaderboard", "level-role-add",
                "level-role-remove", "level-role", "badges", "streak",
                "level-lb", "level-rank", "rewards", "setlevel", "toggle-leveling",
                "levelset", "achievements", "voiceleaderboard", "voiceonline", "voicetime"],
    "Тикеты": ["ticket-panel", "ticket-config", "ticket-add", "ticket-remove",
                "ticket-auto-close", "ticket-ai-toggle", "ticket-ai-stats",
                "ticket-force-escalate", "ticket-rate-limit-info", "ticket-reset-rate-limit",
                "ticket-feedback-stats", "sla-status", "sla-info", "sla-create", "sla-breaches"],
    "Развлечения": ["poll", "poll-end", "activity", "activity-list", "game-find", "game-list",
                     "game-leaderboard", "coinflip", "rps", "8ball", "random-member", "dice",
                     "guess", "guess-start", "event-create", "events", "event-cancel",
                     "giveaway", "reroll", "pomodoro", "pomodoro-complete", "pomodoro-stats",
                     "anime", "anime-suggest", "anime-setup", "anime-off",
                     "cat", "dog", "meme", "joke", "quote", "base64"],
    "Сервер": ["setup-logs", "logs-setup", "logs-center", "antiraid", "antiraid-reload", "announce", "stats",
                "server-info", "botinfo", "uptime", "health", "avatar", "banner", "channelinfo",
                "roleinfo", "rolemembers", "color", "say", "embed_builder", "embed_history",
                "duty-panel", "duty-add", "duty-stats", "backup", "backup-channel", "backup-list",
                "rejoin-toggle", "rejoin-status", "security", "security-toggle",
                "security-newaccount", "verify-toggle", "verify-status", "archive",
                "channel-stats", "scan-link", "changelog", "changelog-add", "changelog-latest",
                "summary", "summary-channel", "summary-now", "summary-off", "summary-on",
                "summary-timezone", "welcome", "welcome-channel", "welcome-status",
                "welcome-test", "welcome-toggle", "setwelcome", "setwelcomechannel",
                "testwelcome", "medialock", "medialock-set", "medialock-list",
                "medialock-remove", "j2c", "j2c-lobby", "j2c-category", "j2c-limit",
                "j2c-template", "j2c-on", "j2c-off", "j2c-status",
                "vc", "vc-lock", "vc-unlock", "vc-limit", "vc-rename", "vc-transfer",
                "crown", "crown-channel", "crown-now", "crown-role", "crown-status",
                "crown-toggle", "antifake", "antifake-on", "antifake-off", "antifake-status",
                "antifake-protect", "antifake-unprotect", "antifake-threshold",
                "antifake-action", "antifake-log-channel", "antifake-test", "upload-emoji",
                "emojis", "time", "account", "firstmessage", "invite"],
    "Приглашения/Участники": ["invites", "invite-ranking", "afk", "afk-remove", "birthday",
                                "birthday-delete", "birthday-setup", "birthdays", "birthday-set",
                                "staff-panel", "help", "userinfo", "report", "reports",
                                "report-analytics", "report-custom", "report-daily",
                                "report-weekly", "my-application", "search", "searchuser",
                                "searchchannel", "searchrole", "searchticket"],
    "Служебные": ["leaveguild", "module", "cog", "hotreload", "gc", "diagnose", "webhook",
                   "ai-reset", "ai-info-list", "ai-info-clear", "flag-create", "flag-enable",
                   "flag-disable", "flag-list", "flag-info", "flag-rollout", "ab-add-variant",
                   "ab-create", "ab-start", "ab-stats", "ab-stop", "ab-variants",
                   "time-report", "time-start", "time-stop", "report-no", "report-ok",
                   "play", "pause", "skip", "queue", "volume", "leave",
                   "nowplaying", "resume", "shuffle", "loop", "clearqueue"],
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

    Правило: если для команды (или её категории, или родительской группы)
    заданы разрешённые роли, пользователь должен иметь хотя бы одну из них.
    Иначе — доступно всем. Каждое подходящее правило является ограничением:
    нарушение любого из них запрещает доступ.
    """
    if member is None or getattr(member, "bot", False):
        return True
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True

    acl = load_acl(guild_id)
    if not acl:
        return True
    user_roles = {str(r.id) for r in getattr(member, "roles", [])}

    for name in _candidates(command):
        # Проверка точного имени (команда/группа)
        allowed = acl.get(name)
        if allowed:
            if not user_roles.intersection(set(allowed)):
                return False

        # Проверка категорий (если имя входит в категорию с ограничением)
        for cat, cmds in COMMAND_CATEGORIES.items():
            if name in cmds:
                cat_allowed = acl.get(cat)
                if cat_allowed:
                    if not user_roles.intersection(set(cat_allowed)):
                        return False
    return True


def roles_for_command(guild_id: int, command: str) -> list:
    """Какие роли разрешены для команды (пусто = все)."""
    acl = load_acl(guild_id)
    for name in _candidates(command):
        allowed = acl.get(name)
        if allowed:
            return allowed
        for cat, cmds in COMMAND_CATEGORIES.items():
            if name in cmds:
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
