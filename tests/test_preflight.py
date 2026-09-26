# -*- coding: utf-8 -*-
"""Тест предстартовой проверки настроек (services/preflight.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.preflight import run_checks, format_report, count_errors, count_warns

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS: {msg}")
    else:
        FAIL += 1
        print(f"  FAIL: {msg}")


print("== 1. Пустой конфиг — критичные ошибки названы ==")
res = run_checks(env={}, facts={})
levels = {r["key"]: r["level"] for r in res}
check(levels.get("TOKEN") == "error", "нет TOKEN -> error")
check(levels.get("OWNER_ID") == "error", "нет OWNER_ID -> error")
check(levels.get("MAIN_GUILD_ID") == "warn", "нет MAIN_GUILD_ID -> warn")
check(levels.get("AI") == "warn", "нет AI-ключей -> warn")
check(count_errors(res) >= 2, f"критичных замечаний >= 2 (получено {count_errors(res)})")

print("== 2. Токен-заглушка ==")
res = run_checks(env={"TOKEN": "YOUR_TOKEN_HERE", "OWNER_ID": "123"}, facts={})
levels = {r["key"]: r["level"] for r in res}
check(levels.get("TOKEN") == "error", "TOKEN-заглушка -> error")

print("== 3. Полный валидный конфиг — ошибок нет ==")
env = {
    "TOKEN": "MTIzOkFB.QWJyYWRhY2FicmE.abc",  # похож на реальный
    "OWNER_ID": "999000111",
    "MAIN_GUILD_ID": "555666",
    "MISTRAL_API_KEY": "sk-xxx",
}
facts = {"db_ok": True, "db_path": "data/bot.db", "dirs_ok": True,
         "panel_port": 5001, "ws_port": 8765,
         "hardcoded_ids": {"APPLY_CHANNEL_ID": 0}, "reachable": ["discord.com"]}
res = run_checks(env=env, facts=facts)
levels = {r["key"]: r["level"] for r in res}
check(levels.get("TOKEN") == "ok", "нормальный токен -> ok")
check(levels.get("OWNER_ID") == "ok", "OWNER_ID -> ok")
check(levels.get("MAIN_GUILD_ID") == "ok", "MAIN_GUILD_ID -> ok")
check(levels.get("DB") == "ok", "БД доступна -> ok")
check(levels.get("PANEL") == "ok", "панель -> ok")
check(levels.get("NETWORK") == "ok", "сеть есть -> ok")
check(count_errors(res) == 0, f"критичных ошибок 0 (получено {count_errors(res)})")
check("AI" not in levels, "AI-ключ задан -> предупреждения об AI нет")

print("== 4. БД недоступна и сеть закрыта ==")
facts_bad = {"db_ok": False, "reachable": [], "dirs_ok": False}
res = run_checks(env={"TOKEN": "x.y.z", "OWNER_ID": "1", "MISTRAL_API_KEY": "k"},
                 facts=facts_bad)
levels = {r["key"]: r["level"] for r in res}
check(levels.get("DB") == "error", "БД не открылась -> error")
check(levels.get("NETWORK") == "error", "сети нет -> error")
check(levels.get("DIRS") == "warn", "папки не создались -> warn")

print("== 5. Хардкод-ID предупреждают только при пустом MAIN_GUILD_ID ==")
facts_hc = {"hardcoded_ids": {"LOG_CHANNEL_ID": 111, "APPLY_CHANNEL_ID": 222}}
res_hc = run_checks(env={"TOKEN": "a.b.c"}, facts=facts_hc)
check(any(r["key"] == "HARDCODED_IDS" and r["level"] == "warn" for r in res_hc),
      "чужеродные ID без MAIN_GUILD_ID -> warn")
res_hc2 = run_checks(env={"TOKEN": "a.b.c", "MAIN_GUILD_ID": "999"}, facts=facts_hc)
check(not any(r["key"] == "HARDCODED_IDS" for r in res_hc2),
      "с заданным MAIN_GUILD_ID предупреждения о хардкоде нет")

print("== 6. format_report читается и иконки на месте ==")
txt = format_report(res)
check("[ОШИБКА]" in txt and "[OK]" in txt, "сводка содержит иконки уровней")

print(f"\n=== PASS {PASS} / FAIL {FAIL} ===")
sys.exit(1 if FAIL else 0)
