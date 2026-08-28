# -*- coding: utf-8 -*-
"""Роли по должности заявки: Хелпер или Модератор.

Заявку в команду одобряют в двух местах — кнопками в Discord и в панели
(«Доступ → Заявки в команду»). Раньше панель брала «первую попавшуюся»
роль из role_map.json, а кнопки вообще не выдавали ничего. Теперь обе
точки спрашивают этот сервис: должность заявки → конкретная роль.

Откуда берётся роль (по порядку):
  1. .env: STAFF_HELPER_ROLE_ID / STAFF_MODERATOR_ROLE_ID
  2. data/staff_roles.json  {"helper": "id", "moderator": "id"}
  3. Роль на сервере по имени: «Хелпер»/«Helper», «Модератор»/«Moderator»

Должность «Чат-контроль» упразднена (заказ владельца 2026-08-27):
старые заявки с ней проводим как модераторские.
"""

import json
import os

from logger import get_logger

log = get_logger("staff_roles")

STAFF_ROLES_FILE = "data/staff_roles.json"
# Настройки заявок из панели: data/staff_apply_settings.json
# { "<guild_id>": {"helper_channel": 0, "moderator_channel": 0, ...} }
STAFF_SETTINGS_FILE = "data/staff_apply_settings.json"

STAFF_SETTING_KEYS = (
    "apply_channel",          # общий канал заявок (запасной)
    "helper_channel",         # ветка заявок хелперов
    "moderator_channel",      # ветка заявок модераторов
    "helper_role",            # роль, выдаваемая хелперу
    "moderator_role",         # роль, выдаваемая модератору
    "curator_role",           # куратор заявок — ОДИН на обе ветки
)

# Кураторская роль раньше была раздельной (хелперы/модераторы) — читаем
# старые ключи как запасное значение, чтобы настройки не потерялись.
LEGACY_CURATOR_KEYS = ("helper_curator_role", "moderator_curator_role")

# Спецификации для панели («Настройки» → «Бот» → «Заявки в команду»)
ROLE_SPECS = [
    {
        "key": "helper_role",
        "label": "Роль хелпера",
        "icon": "fa-hands-helping",
        "what": "Эту роль бот выдаёт после одобрения заявки хелпера. "
                "Не задана — бот ищет роль по имени «Хелпер»/«Helper».",
        "empty": "Авто: поиск по имени на сервере.",
    },
    {
        "key": "moderator_role",
        "label": "Роль модератора",
        "icon": "fa-shield-halved",
        "what": "Выдаётся после одобрения заявки модератора. "
                "Не задана — бот ищет роль по имени «Модератор»/«Moderator».",
        "empty": "Авто: поиск по имени на сервере.",
    },
    {
        "key": "curator_role",
        "label": "Куратор заявок",
        "icon": "fa-user-graduate",
        "what": "Эту роль бот пингует в обеих ветках заявок (хелперы и "
                "модераторы) — куратор один на весь набор.",
        "empty": "Не задана — пинга нет, заявка просто приходит в ветку.",
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
        out = {k: row.get(k, 0) for k in STAFF_SETTING_KEYS}
        for lk in LEGACY_CURATOR_KEYS:
            if row.get(lk):
                out["curator_role"] = out["curator_role"] or row.get(lk)
        return out
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
    """Роль куратора: панель (curator_role → старые раздельные ключи) → .env."""
    stored = load_settings(guild_id)
    for key in ("curator_role",) + LEGACY_CURATOR_KEYS:
        try:
            val = int(stored.get(key) or 0)
        except (TypeError, ValueError):
            val = 0
        if val:
            return val
    return int(env_value or 0)

# Варианты имён ролей на сервере (регистр не важен)
NAME_VARIANTS = {
    "helper": ["хелпер", "helper", "хелперы", "helpers", "хелпер команды"],
    "moderator": ["модератор", "moderator", "модераторы", "moderators",
                  "модератор команды", "мод"],
}

POSITION_ALIASES = {
    "helper": "helper",
    "хелпер": "helper",
    "помощник": "helper",
    "moderator": "moderator",
    "модератор": "moderator",
    "мод": "moderator",
    "chat control": "moderator",      # должность упразднена — ведём как модератор
    "chat-control": "moderator",
    "чат-контроль": "moderator",
    "чат контроль": "moderator",
    "чат контрольный": "moderator",
}


def normalize_position(value) -> str or None:
    """Заявочная должность → 'helper' | 'moderator' | None."""
    if not value:
        return None
    key = " ".join(str(value).lower().replace("—", "-").split())
    if key in POSITION_ALIASES:
        return POSITION_ALIASES[key]
    if "хелп" in key or "help" in key:
        return "helper"
    if "модер" in key or "mod" in key or "чат" in key:
        return "moderator"
    return None


def position_label(kind: str) -> str:
    return {None: "—", "helper": "Хелпер", "moderator": "Модератор"}.get(kind, kind)


def load_role_map() -> dict:
    """{"helper": "role_id", "moderator": "role_id"} — ручная привязка."""
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


def resolve_staff_role(guild, kind: str):
    """Найти роль сервера для должности. Вернуть (role, искали_имена).

    Порядок: .env → data/staff_roles.json → имя роли на сервере."""
    if not guild or kind not in NAME_VARIANTS:
        return None, []
    variants = NAME_VARIANTS[kind]

    # 1) Настройка из ПАНЕЛИ (Каналы и маршруты) — главнее всего
    try:
        from config import Config
        env_id = (Config.STAFF_HELPER_ROLE_ID if kind == "helper"
                  else Config.STAFF_MODERATOR_ROLE_ID)
        panel_id = setting(getattr(guild, "id", 0),
                           "helper_role" if kind == "helper" else "moderator_role",
                           env_id)
        if panel_id:
            role = guild.get_role(int(panel_id))
            if role:
                return role, []
    except Exception as _ex:
        log.debug("staff_roles: подавлено: {_ex}", _ex)
        pass

    # 2) Ручная привязка из data/staff_roles.json
    mapped = str(load_role_map().get(kind, "") or "")
    if mapped.isdigit():
        role = guild.get_role(int(mapped))
        if role:
            return role, []

    # 3) По имени на сервере
    for role in getattr(guild, "roles", []):
        if _norm_name(role.name) in variants:
            return role, variants
    return None, variants


async def grant_staff_role(guild, user_id, position, *, client=None):
    """Выдать участнику роль по должности заявки.

    Возвращает:
      {"kind", "role_name", "reason", "searched"}
      role_name = None, reason ∈ {no_guild, no_position, not_found,
                                  member_left, no_member, forbidden}"""
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
            except Exception:
                member = None
    if member is None:
        return {"kind": kind, "role_name": None, "reason": "member_left",
                "searched": []}

    role, searched = resolve_staff_role(guild, kind or "moderator")
    if role is None:
        return {"kind": kind, "role_name": None, "reason": "not_found",
                "searched": searched}

    try:
        await member.add_roles(role, reason="Заявка в команду одобрена (Hakumo)")
    except Exception as e:
        log.warning(f"[staff_roles] add_roles({role.name}): {e}")
        return {"kind": kind, "role_name": None, "reason": "forbidden",
                "searched": searched}
    return {"kind": kind, "role_name": role.name, "reason": None,
            "searched": searched}


def role_hint(result: dict) -> str:
    """Человекочитаемая подсказка, почему роль не выдана."""
    reason = (result or {}).get("reason")
    kind = (result or {}).get("kind") or "moderator"
    label = position_label("helper" if kind == "helper" else "moderator")
    searched = ", ".join(f"«{n}»" for n in (result or {}).get("searched") or [])
    if reason == "no_guild":
        return "сервер не найден ботом"
    if reason == "no_position":
        return "в заявке не указана должность"
    if reason == "member_left":
        return "участник покинул сервер"
    if reason == "no_member":
        return "участник не найден"
    if reason == "forbidden":
        return f"у бота нет прав выдать роль «{label}» (поставьте роль выше роли бота)"
    if reason == "not_found":
        env = "STAFF_HELPER_ROLE_ID" if kind == "helper" else "STAFF_MODERATOR_ROLE_ID"
        return (f"на сервере нет роли {searched} — создайте её "
                f"или задайте {env} в .env")
    return "неизвестная причина"
