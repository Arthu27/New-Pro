# -*- coding: utf-8 -*-
"""Роли по должности заявки: Хелпер / Модератор / Event / Broadcaster.

Заявку одобряют в Discord (select на карточке) и в панели
(«Доступ → Заявки в команду»). Обе точки спрашивают этот сервис.

Кураторы раздельные (владелец 2026-09-24): ветка Helper не принимает
Event/Broadcaster/Moderator и наоборот — у каждой должности своя роль
«× Отвечаю за …».
"""

import json
import os

from logger import get_logger

log = get_logger("staff_roles")

STAFF_ROLES_FILE = "data/staff_roles.json"
STAFF_SETTINGS_FILE = "data/staff_apply_settings.json"

# Должности набора (порядок в select меню)
POSITIONS = ("helper", "moderator", "event", "broadcaster")

STAFF_SETTING_KEYS = (
    "apply_channel",
    "helper_channel",
    "moderator_channel",
    "event_channel",
    "broadcaster_channel",
    "helper_role",
    "moderator_role",
    "event_role",
    "broadcaster_role",
    "helper_curator_role",
    "moderator_curator_role",
    "event_curator_role",
    "broadcaster_curator_role",
    "curator_role",  # legacy: один на всех (фолбек)
)

LEGACY_CURATOR_KEYS = ("helper_curator_role", "moderator_curator_role")

# Старый общий куратор (фолбек, если своей роли нет)
KNOWN_CURATOR_ROLE_ID = 807030012301541377

# «× Отвечаю за …» — кто принимает заявки своей ветки (Hakumo 2026-09-24)
KNOWN_CURATOR_BY_KIND = {
    "helper": 1551525681207189504,       # × Отвечаю за Helper
    "moderator": 1551524708552278036,    # × Отвечаю за Moderator
    "event": 1551527644326002748,        # × Отвечаю за Eventsmod
    "broadcaster": 1552640159051157576,  # × Отвечаю за Broadcaster
}

# Роли, выдаваемые после одобрения (владелец 2026-09-24)
KNOWN_HELPER_ROLE_ID = 948969471916249119
KNOWN_MODERATOR_ROLE_ID = 803553848396349510
KNOWN_ADMIN_ROLE_ID = 1189999426631122964  # × Administrator
KNOWN_GRANT_BY_KIND = {
    "helper": KNOWN_HELPER_ROLE_ID,
    "moderator": KNOWN_MODERATOR_ROLE_ID,
    "event": 852634463535759461,          # × Eventsmod
    "broadcaster": 1551180629687664670,   # × Broadcaster
}

ROLE_SPECS = [
    {
        "key": "helper_role",
        "label": "Helper",
        "icon": "fa-hands-helping",
        "what": "Выдаётся после одобрения заявки Helper.",
        "empty": "По умолчанию: известная роль Helper.",
    },
    {
        "key": "moderator_role",
        "label": "Moderator",
        "icon": "fa-shield-halved",
        "what": "Выдаётся после одобрения заявки Moderator.",
        "empty": "По умолчанию: известная роль Moderator.",
    },
    {
        "key": "event_role",
        "label": "Eventsmod",
        "icon": "fa-calendar-star",
        "what": "Выдаётся после одобрения заявки Eventsmod.",
        "empty": "По умолчанию: известная роль Eventsmod.",
    },
    {
        "key": "broadcaster_role",
        "label": "Broadcaster",
        "icon": "fa-tower-broadcast",
        "what": "Выдаётся после одобрения заявки Broadcaster.",
        "empty": "По умолчанию: известная роль Broadcaster.",
    },
    {
        "key": "helper_curator_role",
        "label": "Куратор Helper",
        "icon": "fa-user-check",
        "what": "«× Отвечаю за Helper» — куратор ветки (+ админы) принимает заявки Helper.",
        "empty": "По умолчанию: известная роль × Отвечаю за Helper.",
    },
    {
        "key": "moderator_curator_role",
        "label": "Куратор Moderator",
        "icon": "fa-user-shield",
        "what": "«× Отвечаю за Moderator» — куратор ветки (+ админы) принимает заявки Moderator.",
        "empty": "По умолчанию: известная роль × Отвечаю за Moderator.",
    },
    {
        "key": "event_curator_role",
        "label": "Куратор Eventsmod",
        "icon": "fa-user-clock",
        "what": "«× Отвечаю за Eventsmod» — куратор ветки (+ админы) принимает заявки Eventsmod.",
        "empty": "По умолчанию: известная роль × Отвечаю за Eventsmod.",
    },
    {
        "key": "broadcaster_curator_role",
        "label": "Куратор Broadcaster",
        "icon": "fa-podcast",
        "what": "«× Отвечаю за Broadcaster» — куратор ветки (+ админы) принимает заявки Broadcaster.",
        "empty": "По умолчанию: известная роль × Отвечаю за Broadcaster.",
    },
]


def load_settings(guild_id) -> dict:
    """Настройки заявок сервера (из панели)."""
    if not os.path.exists(STAFF_SETTINGS_FILE):
        return {k: 0 for k in STAFF_SETTING_KEYS}
    try:
        with open(STAFF_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        row = (data.get(str(guild_id)) or {}) if isinstance(data, dict) else {}
        return {k: row.get(k, 0) for k in STAFF_SETTING_KEYS}
    except Exception as e:
        log.warning(f"[staff_roles] load_settings: {e}")
        return {k: 0 for k in STAFF_SETTING_KEYS}


def save_setting(guild_id, key, value) -> bool:
    """Записать одну настройку (0 = сбросить в авто/.env)."""
    if key not in STAFF_SETTING_KEYS:
        return False
    data = {}
    try:
        os.makedirs(os.path.dirname(STAFF_SETTINGS_FILE) or "data", exist_ok=True)
        if os.path.exists(STAFF_SETTINGS_FILE):
            with open(STAFF_SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
    except Exception as e:
        log.warning(f"[staff_roles] save_setting(read): {e}")
        data = {}
    try:
        row = data.setdefault(str(guild_id), {})
        row[key] = int(value or 0)
        with open(STAFF_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.warning(f"[staff_roles] save_setting: {e}")
        return False


def setting(guild_id, key, env_value=0) -> int:
    """Значение настройки: панель главнее .env, 0 — не задано."""
    try:
        stored = int(load_settings(guild_id).get(key) or 0)
    except (TypeError, ValueError):
        stored = 0
    return stored or int(env_value or 0)


def curator_role_id(guild_id, env_value=0) -> int:
    """Legacy: один общий куратор (фолбек). Предпочитай curator_role_id_for."""
    stored = load_settings(guild_id)
    for key in ("curator_role",) + LEGACY_CURATOR_KEYS:
        try:
            val = int(stored.get(key) or 0)
        except (TypeError, ValueError):
            val = 0
        if val:
            return val
    if int(env_value or 0):
        return int(env_value)
    return int(KNOWN_CURATOR_ROLE_ID)


def curator_role_id_for(guild_id, kind: str, env_value=0) -> int:
    """Куратор конкретной ветки: панель → .env → KNOWN_CURATOR_BY_KIND."""
    kind = normalize_position(kind) or str(kind or "").lower()
    key = f"{kind}_curator_role" if kind in POSITIONS else "curator_role"
    try:
        from config import Config
        env_map = {
            "helper": getattr(Config, "STAFF_HELPER_CURATOR_ROLE_ID", 0),
            "moderator": getattr(Config, "STAFF_MODERATOR_CURATOR_ROLE_ID", 0),
            "event": getattr(Config, "STAFF_EVENT_CURATOR_ROLE_ID", 0),
            "broadcaster": getattr(Config, "STAFF_BROADCASTER_CURATOR_ROLE_ID", 0),
        }
        env_fallback = int(env_map.get(kind) or env_value or 0)
        # общий STAFF_CURATOR_ROLE_ID — только если своей нет
        common = int(getattr(Config, "STAFF_CURATOR_ROLE_ID", 0) or 0)
    except Exception:
        env_fallback = int(env_value or 0)
        common = 0

    rid = setting(guild_id, key, env_fallback)
    if rid:
        return int(rid)
    known = int(KNOWN_CURATOR_BY_KIND.get(kind) or 0)
    if known:
        return known
    if common:
        return common
    return int(KNOWN_CURATOR_ROLE_ID or 0)


def can_review_position(member, position) -> tuple:
    """Может ли участник принять/отклонить заявку этой должности.

    Да: × Administrator / admin|owner в role_map, владелец сервера/бота,
    либо куратор ЭТОЙ ветки («× Отвечаю за …»).

    Discord-бит administrator НЕ даёт доступ: на сервере декоративные роли
    иногда имеют этот бит (куратор Helper иначе лезет в Events).
    """
    if member is None:
        return False, "Участник не найден."

    role_ids = set()
    try:
        for r in list(getattr(member, "roles", None) or []):
            try:
                role_ids.add(int(getattr(r, "id", 0) or 0))
            except (TypeError, ValueError):
                pass
    except Exception:
        role_ids = set()

    # владелец сервера / бота
    try:
        guild = getattr(member, "guild", None)
        mid = int(getattr(member, "id", 0) or 0)
        if guild is not None and mid and int(getattr(guild, "owner_id", 0) or 0) == mid:
            return True, ""
        from config import Config
        if mid and mid in Config.all_owner_ids():
            return True, ""
    except Exception:
        pass

    # × Administrator и выше по карте ролей (не Discord admin-бит)
    try:
        from services.staff_hierarchy import RANK, best_mapped_tier
        tier = best_mapped_tier(member)
        if tier and RANK.get(tier, -1) >= RANK.get("admin", 4):
            return True, ""
    except Exception:
        pass
    if int(KNOWN_ADMIN_ROLE_ID or 0) and int(KNOWN_ADMIN_ROLE_ID) in role_ids:
        return True, ""

    kind = normalize_position(position)
    if not kind:
        return False, "В заявке не указана должность."
    guild = getattr(member, "guild", None)
    gid = getattr(guild, "id", 0) if guild else 0
    rid = curator_role_id_for(gid, kind)
    if not rid:
        return False, "Куратор этой ветки не настроен."
    if int(rid) in role_ids:
        return True, ""
    label = position_label(kind)
    return False, (
        f"Только <@&{int(rid)}> или администратор "
        f"принимает заявки на **{label}**."
    )


NAME_VARIANTS = {
    "helper": ["хелпер", "helper", "хелперы", "helpers", "хелпер команды"],
    "moderator": ["модератор", "moderator", "модераторы", "moderators",
                  "модератор команды", "мод"],
    "event": ["event", "events", "eventsmod", "ивент", "ивенты",
              "event mod", "eventmod", "event-mod"],
    "broadcaster": ["broadcaster", "broadcast", "бродкастер", "бродкаст",
                    "стример", "streamer"],
}

POSITION_ALIASES = {
    "helper": "helper",
    "хелпер": "helper",
    "помощник": "helper",
    "moderator": "moderator",
    "модератор": "moderator",
    "мод": "moderator",
    "chat control": "moderator",
    "chat-control": "moderator",
    "чат-контроль": "moderator",
    "чат контроль": "moderator",
    "чат контрольный": "moderator",
    "event": "event",
    "events": "event",
    "eventsmod": "event",
    "event mod": "event",
    "event-mod": "event",
    "ивент": "event",
    "ивенты": "event",
    "broadcaster": "broadcaster",
    "broadcast": "broadcaster",
    "бродкастер": "broadcaster",
    "бродкаст": "broadcaster",
}


def normalize_position(value):
    """Заявочная должность → helper|moderator|event|broadcaster|None."""
    if not value:
        return None
    key = " ".join(str(value).lower().replace("—", "-").split())
    if key in POSITION_ALIASES:
        return POSITION_ALIASES[key]
    if "бродк" in key or "broadcast" in key or "stream" in key:
        return "broadcaster"
    if "ивент" in key or "event" in key:
        return "event"
    if "хелп" in key or key == "help" or key.startswith("help"):
        return "helper"
    if "модер" in key or key in ("mod",) or "чат" in key:
        return "moderator"
    return None


def position_label(kind: str) -> str:
    """English labels — как роли на сервере."""
    return {
        None: "—",
        "helper": "Helper",
        "moderator": "Moderator",
        "event": "Eventsmod",
        "broadcaster": "Broadcaster",
    }.get(kind, kind or "—")


def position_select_value(kind: str) -> str:
    return {
        "helper": "Helper",
        "moderator": "Moderator",
        "event": "Eventsmod",
        "broadcaster": "Broadcaster",
    }.get(kind, kind or "Moderator")


def load_role_map() -> dict:
    try:
        if os.path.exists(STAFF_ROLES_FILE):
            with open(STAFF_ROLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        log.warning(f"[staff_roles] load_role_map: {e}")
    return {}


def save_role_map(mapping: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STAFF_ROLES_FILE) or "data", exist_ok=True)
        with open(STAFF_ROLES_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"[staff_roles] save_role_map: {e}")


def _norm_name(name: str) -> str:
    return " ".join(str(name or "").lower().replace("—", "-").split())


def _panel_role_key(kind: str) -> str:
    return f"{kind}_role"


def _env_role_id(kind: str) -> int:
    try:
        from config import Config
        return int({
            "helper": getattr(Config, "STAFF_HELPER_ROLE_ID", 0),
            "moderator": getattr(Config, "STAFF_MODERATOR_ROLE_ID", 0),
            "event": getattr(Config, "STAFF_EVENT_ROLE_ID", 0),
            "broadcaster": getattr(Config, "STAFF_BROADCASTER_ROLE_ID", 0),
        }.get(kind) or 0)
    except Exception:
        return 0


def resolve_staff_role(guild, kind: str):
    """Найти роль сервера для должности. Вернуть (role, искали_имена)."""
    if not guild or kind not in NAME_VARIANTS:
        return None, []
    variants = NAME_VARIANTS[kind]

    # 1) Панель / .env
    try:
        panel_id = setting(getattr(guild, "id", 0),
                           _panel_role_key(kind), _env_role_id(kind))
        if panel_id:
            role = guild.get_role(int(panel_id))
            if role:
                return role, []
    except Exception as _ex:
        log.debug("staff_roles resolve panel: %s", _ex)

    # 2) data/staff_roles.json
    mapped = str(load_role_map().get(kind, "") or "")
    if mapped.isdigit():
        role = guild.get_role(int(mapped))
        if role:
            return role, []

    # 3) Известные grant-ID (Eventsmod / Broadcaster / Helper)
    try:
        known = int(KNOWN_GRANT_BY_KIND.get(kind) or 0)
    except (TypeError, ValueError):
        known = 0
    if known:
        role = guild.get_role(known)
        if role:
            return role, []

    # 4) По имени на сервере
    for role in getattr(guild, "roles", []):
        if _norm_name(role.name) in variants:
            return role, variants
    return None, variants


async def grant_staff_role(guild, user_id, position, *, client=None):
    """Выдать участнику роль по должности заявки.

    После add_roles проверяем, что роль реально на участнике
    (иначе в базе «выдано», а в Discord пусто).
    """
    kind = normalize_position(position)
    if not guild:
        return {"kind": kind, "role_name": None, "reason": "no_guild",
                "searched": []}

    member = None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = 0
    if uid:
        member = guild.get_member(uid)
        if member is None and hasattr(guild, "fetch_member"):
            try:
                member = await guild.fetch_member(uid)
            except Exception as _fe:
                log.warning("[staff_roles] fetch_member(%s): %s", uid, _fe)
                member = None
    if member is None:
        return {"kind": kind, "role_name": None, "reason": "member_left",
                "searched": []}

    if not kind:
        return {"kind": None, "role_name": None, "reason": "no_position",
                "searched": []}

    role, searched = resolve_staff_role(guild, kind)
    if role is None:
        return {"kind": kind, "role_name": None, "reason": "not_found",
                "searched": searched}

    # уже есть — считаем успехом
    try:
        if any(int(getattr(r, "id", 0) or 0) == int(role.id)
               for r in (getattr(member, "roles", None) or [])):
            return {"kind": kind, "role_name": role.name, "reason": None,
                    "searched": searched, "already": True}
    except Exception:
        pass

    try:
        await member.add_roles(role, reason="Заявка в команду одобрена (Hakumo)")
    except Exception as e:
        log.warning(f"[staff_roles] add_roles({role.name}): {e}")
        return {"kind": kind, "role_name": None, "reason": "forbidden",
                "searched": searched, "error": str(e)}

    # проверка: роль реально повисла (только если fetch_member доступен)
    has = False
    verified = False
    try:
        fresh = None
        if hasattr(guild, "fetch_member"):
            try:
                fresh = await guild.fetch_member(uid)
                verified = fresh is not None
            except Exception:
                fresh = None
        check_m = fresh or member
        has = any(int(getattr(r, "id", 0) or 0) == int(role.id)
                  for r in (getattr(check_m, "roles", None) or []))
        # тестовые фейки пишут в .added, не обновляя .roles
        if not has:
            added = list(getattr(check_m, "added", None)
                         or getattr(member, "added", None)
                         or [])
            if role.name in added or int(role.id) in {
                    int(x) for x in added if str(x).isdigit()}:
                has = True
    except Exception as _ve:
        log.debug("staff_roles verify: %s", _ve)

    if verified and not has:
        log.warning(
            "[staff_roles] add_roles(%s) ок, но роли нет у %s — иерархия/права?",
            role.name, uid)
        return {"kind": kind, "role_name": None, "reason": "not_applied",
                "searched": searched}

    log.info("[staff_roles] выдана «%s» → %s (kind=%s)", role.name, uid, kind)
    return {"kind": kind, "role_name": role.name, "reason": None,
            "searched": searched}


def role_hint(result: dict) -> str:
    """Почему роль не выдана."""
    reason = (result or {}).get("reason")
    kind = (result or {}).get("kind") or "moderator"
    label = position_label(kind)
    searched = ", ".join(f"«{n}»" for n in (result or {}).get("searched") or [])
    if reason == "no_guild":
        return "сервер не найден"
    if reason == "no_position":
        return "должность не указана"
    if reason == "member_left":
        return "участник покинул сервер"
    if reason == "no_member":
        return "участник не найден"
    if reason == "forbidden":
        return f"нет прав выдать **{label}** (роль бота ниже)"
    if reason == "not_applied":
        return (f"роль **{label}** не повисла после выдачи "
                "(проверьте иерархию ролей бота)")
    if reason == "not_found":
        env = {
            "helper": "STAFF_HELPER_ROLE_ID",
            "moderator": "STAFF_MODERATOR_ROLE_ID",
            "event": "STAFF_EVENT_ROLE_ID",
            "broadcaster": "STAFF_BROADCASTER_ROLE_ID",
        }.get(kind, "STAFF_MODERATOR_ROLE_ID")
        return (f"роль {searched or f'«{label}»'} не найдена — задайте {env}")
    return reason or "неизвестно"
