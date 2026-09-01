# -*- coding: utf-8 -*-
"""Предстартовая проверка соединений и настроек (preflight).

Запускается при старте бота ДО входа в Discord (main.py вызывает
preflight_report()) и печатает короткую наглядную сводку: что настроено,
что критично сломано, что просто не задано (опционально).

Уровни:
  ERROR   — бот не сможет работать корректно (нет токена / владелец не
            задан / не грузится БД / нет связи с Discord);
  WARN    — работать будет, но часть функций выключена или настройки
            подозрительны (хардкод-ID чужого сервера, AI-ключи, порт…);
  OK      — всё на месте.

Функция чистая и тестируемая (tests/test_preflight.py): принимает
словарь окружения и набор «фактов», не лезет в сеть и диск сама.
"""
from __future__ import annotations

import os


def _is_set(env, name):
    return bool(str(env.get(name, "") or "").strip())


def run_checks(env=None, facts=None):
    """Вернуть список результатов проверок.

    env   — словарь переменных окружения (по умолчанию os.environ);
    facts — словарь с фактами окружения (для теста/боя), ключи:
              db_ok(bool), db_path(str),
              panel_port(int), ws_port(int),
              dirs_ok(bool), dirs(list[str]),
              hardcoded_ids(dict имя->id),
              reachable(list[str]) — хосты, до которых есть доступ.
    Каждый результат: dict(level='ok'|'warn'|'error', key, msg).
    """
    env = os.environ if env is None else env
    facts = dict(facts or {})
    out = []

    # ── 1. Токен ────────────────────────────────────────────────
    token = (str(env.get("TOKEN", "") or "")
             or str(env.get("TОКEN", "") or "")).strip()
    if not token:
        out.append(dict(level="error", key="TOKEN",
                        msg="TOKEN не задан в .env — бот не войдёт в Discord. "
                            "Возьми токен на discord.com/developers/applications"))
    elif "YOUR" in token.upper() or token.lower() in ("token", "ххх", "xxx"):
        out.append(dict(level="error", key="TOKEN",
                        msg="TOKEN в .env — заглушка, впиши настоящий токен бота"))
    else:
        out.append(dict(level="ok", key="TOKEN", msg="токен бота задан"))

    # ── 2. Владелец ─────────────────────────────────────────────
    owner = str(env.get("OWNER_ID", "") or "").strip()
    if not owner:
        out.append(dict(level="error", key="OWNER_ID",
                        msg="OWNER_ID не задан — команды владельца (/update, "
                            "/hotreload, /diagnose) и панель не будут знать хозяина"))
    else:
        out.append(dict(level="ok", key="OWNER_ID",
                        msg=f"владелец бота: {owner}"))

    # ── 3. Серверы для слэш-команд ──────────────────────────────
    main_g = str(env.get("MAIN_GUILD_ID", "") or "").strip()
    extra = [p.strip() for p in str(env.get("EXTRA_GUILD_IDS", "") or "").split(",") if p.strip()]
    if main_g:
        out.append(dict(level="ok", key="MAIN_GUILD_ID",
                        msg=f"слэш-команды публикуются на сервер {main_g}"
                            + (f" + ещё {len(extra)} из EXTRA_GUILD_IDS" if extra else "")))
    else:
        out.append(dict(level="warn", key="MAIN_GUILD_ID",
                        msg="MAIN_GUILD_ID не задан — команды публикуются ГЛОБАЛЬНО "
                            "(на всех серверах, обновление до часа). Для мгновенной "
                            "работы укажи ID основного сервера"))

    # ── 4. База данных ──────────────────────────────────────────
    if facts.get("db_ok"):
        out.append(dict(level="ok", key="DB",
                        msg=f"база данных доступна ({facts.get('db_path', 'data/bot.db')})"))
    elif "db_ok" in facts:
        out.append(dict(level="error", key="DB",
                        msg=f"не удалось открыть базу {facts.get('db_path', 'data/bot.db')} "
                            "— проверь права на папку data/ и диск"))

    # ── 5. Директории ───────────────────────────────────────────
    if facts.get("dirs_ok") is False:
        out.append(dict(level="warn", key="DIRS",
                        msg=f"не создались папки {facts.get('dirs')} — данные/логи "
                            "могут не сохраняться (права на запись?)"))

    # ── 6. Захардкоженные ID с «чужого» сервера ─────────────────
    hc = facts.get("hardcoded_ids") or {}
    defaults = {k: v for k, v in hc.items() if v}
    if defaults and not main_g:
        # MAIN_GUILD_ID пуст → хардкод-дефолты почти наверняка чужеродные
        out.append(dict(level="warn", key="HARDCODED_IDS",
                        msg="в config.py зашиты ID каналов/ролей по умолчанию "
                            f"({', '.join(sorted(defaults))}) — это ID с сервера "
                            "разработки. На твоём сервере они не существуют; задай "
                            "свои в .env или настрой через веб-панель"))

    # ── 7. Панель / порты ───────────────────────────────────────
    pport = facts.get("panel_port")
    if pport:
        out.append(dict(level="ok", key="PANEL",
                        msg=f"веб-панель на порту {pport}"))
    wsport = facts.get("ws_port")
    if wsport:
        out.append(dict(level="ok", key="WS",
                        msg=f"WebSocket панели на порту {wsport}"))

    # ── 8. Сеть (факт из main.py — TCP-проверка) ────────────────
    reachable = facts.get("reachable")
    if reachable is not None:
        if reachable:
            out.append(dict(level="ok", key="NETWORK",
                            msg="доступ к Discord есть (" + ", ".join(reachable) + ":443)"))
        else:
            out.append(dict(level="error", key="NETWORK",
                            msg="НЕТ доступа к Discord (discord.com/gateway:443) — "
                                "закрыт исходящий порт 443, фаервол или блокировка "
                                "провайдера; нужен VPN/прокси на сервере"))

    # ── 8.5 ffmpeg (нужен музыке) ───────────────────────────────
    if facts.get("ffmpeg") is False:
        out.append(dict(level="warn", key="FFMPEG",
                        msg="ffmpeg не найден — музыка (/play) играть не будет. "
                            "Установи ffmpeg и добавь в PATH, либо укажи путь в .env: "
                            "FFMPEG_BINARY=путь/к/ffmpeg(.exe)"))
    elif facts.get("ffmpeg"):
        out.append(dict(level="ok", key="FFMPEG",
                        msg=f"ffmpeg найден ({facts.get('ffmpeg')}) — музыка готова"))

    # ── 9. Опциональные функции ─────────────────────────────────
    ai_providers = {"MISTRAL_API_KEY": "Mistral", "OPENROUTER_API_KEY": "OpenRouter",
                    "OPENAI_API_KEY": "OpenAI", "DEEPSEEK_API_KEY": "DeepSeek"}
    has_cloud_ai = any(_is_set(env, name) for name in ai_providers)
    # OLLAMA_URL в config.py имеет дефолт (http://127.0.0.1:11434). Локальный
    # Ollama считаем источником AI, только если он задан в .env явно и не
    # равен пустому/дефолтному значению (иначе это просто заглушка).
    _ollama_default = "http://127.0.0.1:11434"
    ollama_set = str(env.get("OLLAMA_URL", "") or "").strip() not in ("", _ollama_default)
    if not has_cloud_ai and not ollama_set:
        out.append(dict(level="warn", key="AI",
                        msg="ни одного AI-ключа не задано — AI-чат недоступен "
                            "(провайдеры: " + ", ".join(ai_providers.values())
                            + "). Не критично для модерации/тикетов/музыки"))

    return out


def format_report(results):
    """Человекочитаемая сводка для консоли."""
    icons = {"ok": "[OK]   ", "warn": "[!]    ", "error": "[ОШИБКА]"}
    lines = []
    for r in results:
        lines.append(f"{icons.get(r['level'], '?')} {r['msg']}")
    return "\n".join(lines)


def count_errors(results):
    return sum(1 for r in results if r["level"] == "error")


def count_warns(results):
    return sum(1 for r in results if r["level"] == "warn")
