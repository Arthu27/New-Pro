# -*- coding: utf-8 -*-
"""Роли по должности заявки — ветки набора.

Заявку одобряют в Discord (select на карточке).
Принимают ТОЛЬКО роли «× Отвечаю за …» своей ветки (жёсткие ID).

Чужая ветка / × Administrator / общий × Curator — отказ.
"""

import json
import os

from logger import get_logger

log = get_logger("staff_roles")

STAFF_ROLES_FILE = "data/staff_roles.json"
STAFF_SETTINGS_FILE = "data/staff_apply_settings.json"

# Должности набора (порядок в select меню)
POSITIONS = (
    "moderator", "helper", "event", "support",
    "closemod", "creative", "broadcaster",
)

STAFF_SETTING_KEYS = (
    "apply_channel",
    "helper_channel",
    "moderator_channel",
    "event_channel",
    "support_channel",
    "closemod_channel",
    "creative_channel",
    "broadcaster_channel",
    "helper_role",
    "moderator_role",
    "event_role",
    "support_role",
    "closemod_role",
    "creative_role",
    "broadcaster_role",
    "helper_curator_role",
    "moderator_curator_role",
    "event_curator_role",
    "support_curator_role",
    "closemod_curator_role",
    "creative_curator_role",
    "broadcaster_curator_role",
    "curator_role",  # legacy: один на всех (фолбек)
)

LEGACY_CURATOR_KEYS = ("helper_curator_role", "moderator_curator_role")

# Старый общий куратор (фолбек, если своей роли нет)
KNOWN_CURATOR_ROLE_ID = 807030012301541377

# «× Отвечаю за …» — ЕДИНСТВЕННЫЕ роли, кто принимает заявки своей ветки.
KNOWN_CURATOR_BY_KIND = {
    "moderator": 1551524708552278036,    # × Отвечаю за Moderator (silent ping)
    "helper": 1551525681207189504,       # × Отвечаю за Helper
    "event": 1551527644326002748,        # × Отвечаю за Eventsmod
    "broadcaster": 1552639452713848912,  # × Отвечаю за Broadcaster
    "support": 1553139245735219390,      # × Отвечаю за Support
    "closemod": 1553770122966073384,     # × Отвечаю за Close mod
    "creative": 1553854011449544825,     # × Отвечаю за Creative
}

# Каналы заявок по веткам (владелец 2026-09-29 — раздельные ветки)
KNOWN_CHANNEL_BY_KIND = {
    "moderator": 1554520410777976842,
    "helper": 1554520289046569120,
    "event": 1554520677615407115,
    "support": 1554520537609408563,
    "closemod": 1554520475483250831,
    "creative": 1554520793285787708,
    "broadcaster": 1554519758957846619,
}

# Роли, выдаваемые после одобрения (владелец 2026-09-24)
KNOWN_HELPER_ROLE_ID = 948969471916249119
KNOWN_MODERATOR_ROLE_ID = 803553848396349510
# × Master — mid между Helper/Moderator и Curator (обе ветки)
KNOWN_MASTER_ROLE_ID = 1552637932907667466
# × Assistent — ВЫШЕ куратора (обе ветки); × Staff Assistent — старший
KNOWN_ASSISTENT_ROLE_ID = 1552815174115664013
KNOWN_STAFF_ASSISTENT_ROLE_ID = 1554932049528225842
KNOWN_ADMIN_ROLE_ID = 1189999426631122964  # × Administrator
# × Staff Administrator — эскалация жалоб на админов; тир admin, лимиты +2
KNOWN_STAFF_ADMIN_ROLE_ID = 1549118975110152263
# Общая роль на ВСЕ ветки (Helper/Mod/Creative/…) — если нет, выдаём при accept
KNOWN_COMMON_STAFF_ROLE_ID = 1553105240398631062
# Ассистенты (тир assistent > curator)
KNOWN_ASSISTENT_ROLE_IDS = (
    KNOWN_ASSISTENT_ROLE_ID,
    KNOWN_STAFF_ASSISTENT_ROLE_ID,
)
# backward-compat alias
KNOWN_HELPER_MASTER_ROLE_IDS = KNOWN_ASSISTENT_ROLE_IDS
KNOWN_GRANT_BY_KIND = {
    "helper": KNOWN_HELPER_ROLE_ID,
    "moderator": KNOWN_MODERATOR_ROLE_ID,
    "event": 852634463535759461,          # × Eventsmod
    "broadcaster": 1551180629687664670,   # × Broadcaster
    "support": 1553138713532563516,       # × Support
    "closemod": 1553769624603201546,      # × Close mod
    "creative": 1553853968969638058,      # × Creative
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
        "key": "support_role",
        "label": "Support",
        "icon": "fa-headset",
        "what": "Выдаётся после одобрения заявки Support.",
        "empty": "Не задана — ищем роль Support по имени.",
    },
    {
        "key": "closemod_role",
        "label": "Close mod",
        "icon": "fa-door-closed",
        "what": "Выдаётся после одобрения заявки Close mod.",
        "empty": "Не задана — ищем роль Close mod по имени.",
    },
    {
        "key": "creative_role",
        "label": "Creative",
        "icon": "fa-palette",
        "what": "Выдаётся после одобрения заявки Creative.",
        "empty": "Не задана — ищем роль Creative по имени.",
    },
    {
        "key": "helper_curator_role",
        "label": "Куратор Helper",
        "icon": "fa-user-check",
        "what": "«× Отвечаю за Helper» — только эта роль принимает заявки Helper.",
        "empty": "По умолчанию: 1551525681207189504.",
    },
    {
        "key": "moderator_curator_role",
        "label": "Куратор Moderator",
        "icon": "fa-user-shield",
        "what": "«× Отвечаю за Moderator» — silent ping; только эта роль принимает Moderator.",
        "empty": "По умолчанию: 1551524708552278036.",
    },
    {
        "key": "event_curator_role",
        "label": "Куратор Eventsmod",
        "icon": "fa-user-clock",
        "what": "«× Отвечаю за Eventsmod» — только эта роль принимает заявки Eventsmod.",
        "empty": "По умолчанию: 1551527644326002748.",
    },
    {
        "key": "broadcaster_curator_role",
        "label": "Куратор Broadcaster",
        "icon": "fa-podcast",
        "what": "«× Отвечаю за Broadcaster» — только эта роль принимает заявки Broadcaster.",
        "empty": "По умолчанию: 1552639452713848912.",
    },
    {
        "key": "support_curator_role",
        "label": "Куратор Support",
        "icon": "fa-user-nurse",
        "what": "«× Отвечаю за Support» — только эта роль принимает заявки Support.",
        "empty": "По умолчанию: 1553139245735219390.",
    },
    {
        "key": "closemod_curator_role",
        "label": "Куратор Close mod",
        "icon": "fa-user-lock",
        "what": "«× Отвечаю за Close mod» — только эта роль принимает заявки Close mod.",
        "empty": "По умолчанию: 1553770122966073384.",
    },
    {
        "key": "creative_curator_role",
        "label": "Куратор Creative",
        "icon": "fa-user-pen",
        "what": "«× Отвечаю за Creative» — только эта роль принимает заявки Creative.",
        "empty": "По умолчанию: 1553854011449544825.",
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
    """Куратор конкретной ветки: панель → .env → KNOWN_CURATOR_BY_KIND.

    Общий × Curator / STAFF_CURATOR_ROLE_ID для известных должностей
    НЕ используется — иначе куратор Helper принимает все ветки.
    """
    kind = normalize_position(kind) or str(kind or "").lower()
    key = f"{kind}_curator_role" if kind in POSITIONS else "curator_role"
    try:
        from config import Config
        env_map = {
            "helper": getattr(Config, "STAFF_HELPER_CURATOR_ROLE_ID", 0),
            "moderator": getattr(Config, "STAFF_MODERATOR_CURATOR_ROLE_ID", 0),
            "event": getattr(Config, "STAFF_EVENT_CURATOR_ROLE_ID", 0),
            "broadcaster": getattr(Config, "STAFF_BROADCASTER_CURATOR_ROLE_ID", 0),
            "support": getattr(Config, "STAFF_SUPPORT_CURATOR_ROLE_ID", 0),
            "closemod": getattr(Config, "STAFF_CLOSEMOD_CURATOR_ROLE_ID", 0),
            "creative": getattr(Config, "STAFF_CREATIVE_CURATOR_ROLE_ID", 0),
        }
        env_fallback = int(env_map.get(kind) or env_value or 0)
    except Exception:
        env_fallback = int(env_value or 0)

    rid = setting(guild_id, key, env_fallback)
    if rid:
        return int(rid)
    known = int(KNOWN_CURATOR_BY_KIND.get(kind) or 0)
    if known:
        return known
    # Неизвестная должность — без общего фолбека (изоляция веток)
    if kind in POSITIONS:
        return 0
    return int(KNOWN_CURATOR_ROLE_ID or 0)


def can_review_position(member, position) -> tuple:
    """Может ли участник принять/отклонить заявку этой должности.

    Да ТОЛЬКО при роли из KNOWN_CURATOR_BY_KIND для этой ветки.
    Плюс владелец сервера/бота. Панель/.env/× Administrator/чужой
    куратор — нет. Проверка по жёстким ID, без подмены из настроек.
    """
    if member is None:
        return False, "Участник не найден."

    role_ids = set()
    try:
        for r in list(getattr(member, "roles", None) or []):
            try:
                role_ids.add(int(getattr(r, "id", 0) or 0))
            except (TypeError, ValueError) as _ex:
                log.debug('staff_roles: except@246: %s', _ex)
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
    except Exception as _ex:
        log.debug('staff_roles: except@260: %s', _ex)

    kind = normalize_position(position)
    if not kind or kind not in KNOWN_CURATOR_BY_KIND:
        return False, "В заявке не указана должность."
    # Жёстко: только ID из таблицы владельца (не панель, не .env)
    rid = int(KNOWN_CURATOR_BY_KIND[kind])
    if rid in role_ids:
        return True, ""
    label = position_label(kind)
    return False, (
        f"Только <@&{rid}> принимает заявки на **{label}**."
    )


NAME_VARIANTS = {
    "helper": ["хелпер", "helper", "хелперы", "helpers", "хелпер команды"],
    "moderator": ["модератор", "moderator", "модераторы", "moderators",
                  "модератор команды", "мод"],
    "event": ["event", "events", "eventsmod", "ивент", "ивенты",
              "event mod", "eventmod", "event-mod"],
    "broadcaster": ["broadcaster", "broadcast", "бродкастер", "бродкаст",
                    "стример", "streamer"],
    "support": ["support", "саппорт", "поддержка", "supporter"],
    "closemod": ["closemod", "close mod", "close-mod", "клоузмод",
                 "клоуз мод", "close"],
    "creative": ["creative", "креатив", "креативщик"],
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
    "support": "support",
    "саппорт": "support",
    "поддержка": "support",
    "closemod": "closemod",
    "close mod": "closemod",
    "close-mod": "closemod",
    "клоузмод": "closemod",
    "клоуз мод": "closemod",
    "creative": "creative",
    "креатив": "creative",
}


def normalize_position(value):
    """Заявочная должность → ключ ветки или None."""
    if not value:
        return None
    key = " ".join(str(value).lower().replace("—", "-").split())
    if key in POSITION_ALIASES:
        return POSITION_ALIASES[key]
    if "бродк" in key or "broadcast" in key or "stream" in key:
        return "broadcaster"
    if "support" in key or "саппорт" in key or "поддерж" in key:
        return "support"
    if "close" in key or "клоуз" in key:
        return "closemod"
    if "creat" in key or "креатив" in key:
        return "creative"
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
        "support": "Support",
        "closemod": "Close mod",
        "creative": "Creative",
    }.get(kind, kind or "—")


def position_select_value(kind: str) -> str:
    return {
        "helper": "Helper",
        "moderator": "Moderator",
        "event": "Eventsmod",
        "broadcaster": "Broadcaster",
        "support": "Support",
        "closemod": "Close mod",
        "creative": "Creative",
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
    """Имя роли → ключ сравнения (без × / ・ / декора)."""
    s = str(name or "").lower().replace("—", "-").replace("–", "-")
    for ch in ("×", "・", "•", "●", "✦", "★", "☆", "❖", "◆", "▪", "▫"):
        s = s.replace(ch, " ")
    return " ".join(s.split())


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
            "support": getattr(Config, "STAFF_SUPPORT_ROLE_ID", 0),
            "closemod": getattr(Config, "STAFF_CLOSEMOD_ROLE_ID", 0),
            "creative": getattr(Config, "STAFF_CREATIVE_ROLE_ID", 0),
        }.get(kind) or 0)
    except Exception:
        return 0


def resolve_staff_role(guild, kind: str):
    """Найти роль сервера для должности. Вернуть (role, искали_имена).

    Порядок: жёсткий KNOWN_GRANT → панель/.env → staff_roles.json → имя.
    KNOWN первым: ошибочный support_role в панели больше не подменит × Support.
    """
    if not guild or kind not in NAME_VARIANTS:
        return None, []
    variants = NAME_VARIANTS[kind]

    # 1) Известные grant-ID (владелец) — главный источник правды
    try:
        known = int(KNOWN_GRANT_BY_KIND.get(kind) or 0)
    except (TypeError, ValueError):
        known = 0
    if known:
        role = guild.get_role(known)
        if role:
            return role, []

    # 2) Панель / .env (только если known нет на сервере)
    try:
        panel_id = setting(getattr(guild, "id", 0),
                           _panel_role_key(kind), _env_role_id(kind))
        if panel_id:
            role = guild.get_role(int(panel_id))
            if role:
                return role, []
    except Exception as _ex:
        log.debug("staff_roles resolve panel: %s", _ex)

    # 3) data/staff_roles.json
    mapped = str(load_role_map().get(kind, "") or "")
    if mapped.isdigit():
        role = guild.get_role(int(mapped))
        if role:
            return role, []

    # 4) По имени на сервере (× Support / ・Support → support)
    for role in getattr(guild, "roles", []):
        if _norm_name(role.name) in variants:
            return role, variants
    return None, variants


def _bot_can_assign(guild, role) -> tuple:
    """Может ли бот выдать роль (иерархия + manage_roles)."""
    if guild is None or role is None:
        return False, "no_guild"
    me = getattr(guild, "me", None)
    if me is None:
        return True, ""  # нет кэша — пусть API решит
    try:
        perms = getattr(me, "guild_permissions", None)
        if perms is not None and not getattr(perms, "manage_roles", True):
            return False, "no_perms"
    except Exception:
        pass
    try:
        top = getattr(me, "top_role", None)
        if top is not None and hasattr(role, "position"):
            if int(getattr(role, "position", 0) or 0) >= int(
                    getattr(top, "position", 0) or 0):
                return False, "hierarchy"
    except Exception as _ex:
        log.debug("staff_roles hierarchy check: %s", _ex)
    try:
        if getattr(role, "managed", False):
            return False, "managed"
    except Exception:
        pass
    return True, ""

def _member_has_role(member, role_id: int) -> bool:
    try:
        rid = int(role_id)
    except (TypeError, ValueError):
        return False
    for r in (getattr(member, "roles", None) or []):
        try:
            if int(getattr(r, "id", 0) or 0) == rid:
                return True
        except (TypeError, ValueError):
            continue
    # тестовые фейки
    added = list(getattr(member, "added", None) or [])
    if rid in {int(x) for x in added if str(x).isdigit()}:
        return True
    return False


def staff_role_ids_to_strip() -> list:
    """ID ролей «стафф-идентичности», снимаемых при 3 варнах у стаффа."""
    ids = set()
    for rid in (KNOWN_GRANT_BY_KIND or {}).values():
        try:
            ids.add(int(rid))
        except (TypeError, ValueError):
            continue
    for rid in (KNOWN_CURATOR_BY_KIND or {}).values():
        try:
            ids.add(int(rid))
        except (TypeError, ValueError):
            continue
    for rid in (
            KNOWN_COMMON_STAFF_ROLE_ID,
            KNOWN_MASTER_ROLE_ID,
            KNOWN_ASSISTENT_ROLE_ID,
            KNOWN_STAFF_ASSISTENT_ROLE_ID,
            KNOWN_HELPER_ROLE_ID,
            KNOWN_MODERATOR_ROLE_ID,
    ):
        try:
            if int(rid or 0):
                ids.add(int(rid))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


async def strip_staff_roles(guild, member, *, reason: str = '') -> dict:
    """Снять роли стаффа (ветки / кураторы / common / master / assistent).

    Admin-роли не трогаем. Возвращает {removed: [ids], failed: [...], ...}.
    """
    out = {"removed": [], "failed": [], "skipped": 0}
    if guild is None or member is None:
        out["reason"] = "no_member"
        return out
    want = set(staff_role_ids_to_strip())
    have = []
    for r in list(getattr(member, "roles", None) or []):
        try:
            rid = int(getattr(r, "id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if rid in want:
            have.append(r)
    if not have:
        out["skipped"] = 1
        return out
    why = reason or "3 варна — снятие со стаффа (Hakumo)"
    try:
        await member.remove_roles(*have, reason=why)
        out["removed"] = [int(r.id) for r in have]
        # тестовые фейки без Discord-кэша
        try:
            if hasattr(member, "roles"):
                keep = [r for r in list(member.roles or [])
                        if int(getattr(r, "id", 0) or 0) not in want]
                member.roles = keep
        except Exception:
            pass
        log.info(
            "[staff_roles] снято со стаффа %s → %s ролей (%s)",
            getattr(member, "id", "?"), len(have), why)
    except Exception as e:
        # по одной — чтобы часть всё же слетела
        for r in have:
            try:
                await member.remove_roles(r, reason=why)
                out["removed"].append(int(r.id))
            except Exception as e2:
                out["failed"].append({"id": int(r.id), "error": str(e2)})
        if not out["removed"]:
            out["error"] = str(e)
            log.warning("[staff_roles] strip_staff_roles: %s", e)
    return out


async def ensure_common_staff_role(guild, member) -> dict:
    """Общая роль на все ветки — выдать, если ещё нет."""
    out = {"role_id": KNOWN_COMMON_STAFF_ROLE_ID, "granted": False,
           "already": False, "reason": None, "role_name": None}
    if guild is None or member is None:
        out["reason"] = "no_member"
        return out
    role = guild.get_role(int(KNOWN_COMMON_STAFF_ROLE_ID))
    if role is None:
        out["reason"] = "not_found"
        return out
    out["role_name"] = getattr(role, "name", None) or str(role.id)
    if _member_has_role(member, KNOWN_COMMON_STAFF_ROLE_ID):
        out["already"] = True
        return out
    try:
        await member.add_roles(
            role, reason="Общая staff-роль (все ветки набора, Hakumo)")
        out["granted"] = True
        log.info("[staff_roles] общая роль «%s» → %s",
                 out["role_name"], getattr(member, "id", "?"))
    except Exception as e:
        out["reason"] = "forbidden"
        out["error"] = str(e)
        log.warning("[staff_roles] common role %s: %s", role.id, e)
    return out


async def _verify_member_role(guild, member, role_id: int, uid: int):
    """Проверить, что роль реально на участнике (fetch + кэш + тестовый added)."""
    check_m = member
    fetched = False
    if guild is not None and hasattr(guild, "fetch_member") and uid:
        try:
            fresh = await guild.fetch_member(uid)
            if fresh is not None:
                check_m = fresh
                fetched = True
        except Exception as _fe:
            log.debug("staff_roles verify fetch: %s", _fe)
    has = _member_has_role(check_m, role_id)
    if not has:
        added = list(getattr(check_m, "added", None)
                     or getattr(member, "added", None)
                     or [])
        try:
            if int(role_id) in {int(x) for x in added if str(x).isdigit()}:
                has = True
        except (TypeError, ValueError):
            pass
    return has, fetched, check_m


async def grant_staff_role(guild, user_id, position, *, client=None):
    """Выдать участнику роль по должности заявки + общую staff-роль.

    Успех ТОЛЬКО если роль реально на участнике после add_roles
    (иначе раньше логировали «выдана», а в Discord пусто — Support-баг).
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

    # общая роль — всегда при accept любой ветки (если нет)
    common = await ensure_common_staff_role(guild, member)

    role, searched = resolve_staff_role(guild, kind)
    if role is None:
        return {"kind": kind, "role_name": None, "reason": "not_found",
                "searched": searched, "common": common}

    # уже есть — считаем успехом (общую всё равно уже попробовали)
    try:
        if _member_has_role(member, role.id):
            return {"kind": kind, "role_name": role.name, "reason": None,
                    "searched": searched, "already": True, "common": common,
                    "role_id": int(role.id)}
    except Exception as _ex:
        log.debug('staff_roles: except@476: %s', _ex)

    ok_assign, why = _bot_can_assign(guild, role)
    if not ok_assign:
        log.warning(
            "[staff_roles] нельзя выдать «%s» (%s) → %s: %s",
            getattr(role, "name", "?"), getattr(role, "id", "?"), uid, why)
        return {"kind": kind, "role_name": None, "reason": why or "forbidden",
                "searched": searched, "common": common,
                "role_id": int(role.id)}

    last_err = None
    for attempt in (1, 2):
        try:
            await member.add_roles(
                role, reason="Заявка в команду одобрена (Hakumo)")
            last_err = None
        except Exception as e:
            last_err = e
            log.warning(
                "[staff_roles] add_roles(%s) try=%s: %s",
                role.name, attempt, e)
            if attempt == 1:
                try:
                    import asyncio
                    await asyncio.sleep(0.6)
                except Exception:
                    pass
                continue
            return {"kind": kind, "role_name": None, "reason": "forbidden",
                    "searched": searched, "error": str(e), "common": common,
                    "role_id": int(role.id)}

        has, fetched, check_m = await _verify_member_role(
            guild, member, role.id, uid)
        if has:
            # обновить кэш ссылки на member для последующих шагов
            member = check_m or member
            log.info(
                "[staff_roles] выдана «%s» → %s (kind=%s, id=%s, try=%s)",
                role.name, uid, kind, role.id, attempt)
            return {"kind": kind, "role_name": role.name, "reason": None,
                    "searched": searched, "common": common,
                    "role_id": int(role.id), "verified": bool(fetched or has)}

        # роли нет — повтор или fail (НИКОГДА не успех без роли)
        log.warning(
            "[staff_roles] add_roles(%s) ok, но роли нет у %s "
            "(try=%s, fetched=%s) — иерархия/права/лаг Discord?",
            role.name, uid, attempt, fetched)
        if attempt == 1:
            try:
                import asyncio
                await asyncio.sleep(0.8)
            except Exception:
                pass
            # обновить member перед ретраем
            if fetched and check_m is not None:
                member = check_m
            continue

    if last_err is not None:
        return {"kind": kind, "role_name": None, "reason": "forbidden",
                "searched": searched, "error": str(last_err), "common": common,
                "role_id": int(role.id)}
    return {"kind": kind, "role_name": None, "reason": "not_applied",
            "searched": searched, "common": common, "role_id": int(role.id)}

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
    if reason == "hierarchy":
        return (f"роль **{label}** выше роли бота — "
                "поднимите бота выше × Support/ветки в списке ролей")
    if reason == "no_perms":
        return f"у бота нет Manage Roles — нельзя выдать **{label}**"
    if reason == "managed":
        return f"роль **{label}** управляемая (бот/интеграция) — выдать нельзя"
    if reason == "not_applied":
        return (f"роль **{label}** не повисла после выдачи "
                "(проверьте иерархию ролей бота)")
    if reason == "not_found":
        env = {
            "helper": "STAFF_HELPER_ROLE_ID",
            "moderator": "STAFF_MODERATOR_ROLE_ID",
            "event": "STAFF_EVENT_ROLE_ID",
            "broadcaster": "STAFF_BROADCASTER_ROLE_ID",
            "support": "STAFF_SUPPORT_ROLE_ID",
            "closemod": "STAFF_CLOSEMOD_ROLE_ID",
            "creative": "STAFF_CREATIVE_ROLE_ID",
        }.get(kind, "STAFF_MODERATOR_ROLE_ID")
        return (f"роль {searched or f'«{label}»'} не найдена — задайте {env}")
    return reason or "неизвестно"


async def heal_missing_grants(bot, *, limit: int = 40) -> dict:
    """Повторно выдать роли по approved-заявкам, где роль не повисла.

    Чинит кейсы вроде Support-accept: в логе «выдана», в Discord пусто.
    """
    from datetime import datetime, timezone

    out = {"checked": 0, "healed": 0, "failed": 0, "skipped": 0, "errors": []}
    path = "data/staff_apps.json"
    try:
        if not os.path.exists(path):
            return out
        with open(path, "r", encoding="utf-8") as f:
            apps = json.load(f)
        if not isinstance(apps, list):
            return out
    except Exception as e:
        out["errors"].append(str(e))
        return out

    # свежие approved сначала
    candidates = [
        a for a in apps
        if isinstance(a, dict) and a.get("status") == "approved"
        and a.get("user_id") and a.get("role")
    ]
    candidates.sort(
        key=lambda a: str(a.get("reviewed_at") or a.get("submitted_at") or ""),
        reverse=True)

    dirty = False
    for app in candidates[: max(1, int(limit or 40))]:
        out["checked"] += 1
        try:
            gid = int(app.get("guild_id") or 0)
        except (TypeError, ValueError):
            gid = 0
        guild = bot.get_guild(gid) if gid else None
        if guild is None and hasattr(bot, "guilds"):
            # фолбек: единственный/основной гильд
            try:
                from config import Config
                mg = int(getattr(Config, "MAIN_GUILD_ID", 0) or 0)
            except Exception:
                mg = 0
            guild = bot.get_guild(mg) if mg else None
            if guild is None and bot.guilds:
                guild = bot.guilds[0]
        if guild is None:
            out["skipped"] += 1
            continue

        kind = normalize_position(app.get("role"))
        role, _ = resolve_staff_role(guild, kind) if kind else (None, [])
        if role is None:
            out["skipped"] += 1
            continue

        try:
            uid = int(app.get("user_id"))
        except (TypeError, ValueError):
            out["skipped"] += 1
            continue

        member = guild.get_member(uid)
        if member is None and hasattr(guild, "fetch_member"):
            try:
                member = await guild.fetch_member(uid)
            except Exception:
                member = None
        if member is None:
            out["skipped"] += 1
            continue

        if _member_has_role(member, role.id):
            # уже есть — подчистить grant_error если был
            if app.get("grant_error") or not app.get("granted_role"):
                app["granted_role"] = role.name
                app.pop("grant_error", None)
                dirty = True
            out["skipped"] += 1
            continue

        # роли нет — пробуем выдать снова
        res = await grant_staff_role(
            guild, uid, app.get("role"), client=bot)
        if res.get("role_name"):
            app["granted_role"] = res["role_name"]
            app.pop("grant_error", None)
            app["grant_healed_at"] = datetime.now(timezone.utc).isoformat()
            dirty = True
            out["healed"] += 1
            log.info(
                "[staff_roles] heal «%s» → %s (kind=%s)",
                res["role_name"], uid, kind)
        else:
            hint = role_hint(res)
            app["grant_error"] = hint
            dirty = True
            out["failed"] += 1
            out["errors"].append(f"{uid}:{kind}:{res.get('reason')}")

    if dirty:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(apps, f, indent=2, ensure_ascii=False)
        except Exception as e:
            out["errors"].append(f"save:{e}")
    return out
