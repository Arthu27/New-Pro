# -*- coding: utf-8 -*-
"""Кастомные предметы магазина экономики (задаются из панели, действуют на сервере).

Хранилище — GuildData('economy_shop'), ключ 'items': {название: карточка}.
Ког economy_cog читает каталог только через effective_items(): базовый
ITEM_DETAILS + кастомные предметы сервера. Панель и ког зовут одни и те же
функции, поэтому тексты ошибок и карточки совпадают по построению.

Модуль ничего не импортирует из economy_cog (никаких циклических импортов):
редкости и категории передаются параметрами.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from db import GuildData
from logger import get_logger

log = get_logger("economy_shop")

MAX_CUSTOM_ITEMS = 50
NAME_MAX = 40
DESC_MAX = 100
PRICE_MAX = 1_000_000
DEFAULT_CATEGORY = "другое"
_NAME_RE = re.compile(r"^[0-9a-zA-Zа-яА-ЯёЁ \-]+$")
_CARD_FIELDS = ("price", "rarity", "desc", "sell", "category", "pet_bonus")
_META_FIELDS = ("by", "created_at", "updated_at")


def _db() -> GuildData:
    return GuildData("economy_shop")


def load_custom(guild_id) -> Dict[str, Dict[str, Any]]:
    """Кастомные предметы сервера: {название: карточка}. Битые записи отбрасываем — команды не должны падать."""
    if guild_id in (None, "", 0):
        return {}
    try:
        raw = _db().get(int(guild_id), "items", {}) or {}
    except Exception as exc:  # хранилище недоступно — отдаём пусто, команды не должны падать
        log.debug("load_custom(%s): %s", guild_id, exc)
        return {}
    items: Dict[str, Dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return items
    for name, card in raw.items():
        if not isinstance(name, str) or not isinstance(card, dict):
            continue
        clean = {k: card[k] for k in _CARD_FIELDS if k in card}
        if not isinstance(clean.get("price"), int) or not clean.get("rarity"):
            continue
        clean.setdefault("sell", clean["price"] // 2)
        clean.setdefault("desc", "")
        clean.setdefault("category", DEFAULT_CATEGORY)
        for meta_key in _META_FIELDS:
            if card.get(meta_key):
                clean[meta_key] = card[meta_key]
        items[name] = clean
    return items


def _save_custom(guild_id, items: Mapping[str, Dict[str, Any]]) -> None:
    _db().set(int(guild_id), "items", dict(items))


def effective_items(guild_id, base: Mapping[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Базовый каталог + кастомные предметы сервера.

    Базовые карточки копируются, чтобы читатель случайно не замутировал
    глобальный ITEM_DETAILS. Кастом не может перекрыть базовый предмет —
    validate_item это запрещает, поэтому простой update безопасен.
    """
    merged: Dict[str, Dict[str, Any]] = {
        str(k): dict(v) for k, v in base.items() if isinstance(v, dict)
    }
    merged.update(load_custom(guild_id))
    return merged


def validate_item(
    name,
    card: Mapping[str, Any],
    *,
    base: Mapping[str, Any],
    existing: Mapping[str, Any],
    rarities=(),
    categories=(),
    max_items: int = MAX_CUSTOM_ITEMS,
) -> Tuple[bool, str]:
    """Проверка карточки предмета. Возвращает (ok, текст ошибки или '')."""
    name = (name or "").strip().lower()
    if not name:
        return False, "Введите название предмета."
    if len(name) > NAME_MAX:
        return False, f"Название слишком длинное (максимум {NAME_MAX} символов)."
    if not _NAME_RE.match(name):
        return False, "В названии можно использовать только буквы, цифры, пробелы и дефис."
    if name in base:
        return False, "Предмет с таким названием уже есть в базовом магазине."
    if name not in existing and len(existing) >= max_items:
        return False, f"Достигнут лимит кастомных предметов ({max_items})."
    try:
        price = int(card.get("price"))
    except (TypeError, ValueError):
        return False, "Цена должна быть целым числом."
    if not 1 <= price <= PRICE_MAX:
        return False, f"Цена должна быть от 1 до {PRICE_MAX:,}."
    sell_raw = card.get("sell")
    if sell_raw in (None, ""):
        sell = price // 2
    else:
        try:
            sell = int(sell_raw)
        except (TypeError, ValueError):
            return False, "Цена продажи должна быть целым числом."
        if not 0 <= sell <= price:
            return False, "Цена продажи не может быть больше цены покупки."
    rarity = str(card.get("rarity") or "").strip().lower()
    if rarities and rarity not in rarities:
        return False, "Неизвестная редкость."
    category = str(card.get("category") or "").strip().lower() or DEFAULT_CATEGORY
    if categories and category not in categories:
        return False, "Неизвестная категория."
    desc = str(card.get("desc") or "").strip()
    if len(desc) > DESC_MAX:
        return False, f"Описание слишком длинное (максимум {DESC_MAX} символов)."
    if category == "питомцы":
        bonus_raw = card.get("pet_bonus")
        try:
            bonus = int(bonus_raw)
        except (TypeError, ValueError):
            return False, "Укажите бонус питомца (от 1 до 100%)."
        if not 1 <= bonus <= 100:
            return False, "Бонус питомца должен быть от 1 до 100%."
    return True, ""


def upsert_item(
    guild_id,
    name,
    card: Mapping[str, Any],
    *,
    base: Mapping[str, Any],
    rarities=(),
    categories=(),
    by: str = "",
) -> Tuple[bool, str]:
    """Создать или обновить кастомный предмет. Возвращает (ok, текст ошибки или '')."""
    existing = load_custom(guild_id)
    ok, err = validate_item(
        name, card, base=base, existing=existing,
        rarities=rarities, categories=categories,
    )
    if not ok:
        return False, err
    key = (name or "").strip().lower()
    price = int(card["price"])
    sell_raw = card.get("sell")
    sell = int(sell_raw) if sell_raw not in (None, "") else price // 2
    category = str(card.get("category") or "").strip().lower() or DEFAULT_CATEGORY
    new_card: Dict[str, Any] = {
        "price": price,
        "rarity": str(card.get("rarity") or "").strip().lower(),
        "desc": str(card.get("desc") or "").strip(),
        "sell": sell,
        "category": category,
    }
    if category == "питомцы":
        new_card["pet_bonus"] = int(card.get("pet_bonus"))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev = existing.get(key) or {}
    new_card["created_at"] = prev.get("created_at") or now
    new_card["updated_at"] = now
    new_card["by"] = by or prev.get("by", "")
    existing[key] = new_card
    _save_custom(guild_id, existing)
    return True, ""


def remove_item(guild_id, name) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Удалить кастомный предмет. Возвращает (ok, ошибка, удалённая карточка для undo)."""
    existing = load_custom(guild_id)
    key = (name or "").strip().lower()
    if key not in existing:
        return False, "Такого кастомного предмета нет.", None
    removed = existing.pop(key)
    _save_custom(guild_id, existing)
    return True, "", removed


async def setup(bot):
    """Модуль-помощник (не ког): команды не регистрируются, загружается
    как пустое расширение — чтобы авто-загрузчик не писал ошибки,
    а импортирующие функции (`icon_attach` / `effective_items`) работали."""
    return None
