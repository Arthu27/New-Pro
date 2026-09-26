# Хранение данных модерации (14 дней)
# ==================================
#
# Владелец 2026-09-25: оставляем только последние 2 недели.
# Реализация: `services/data_retention.py` (DATA_RETENTION_DAYS, по умолчанию 14).
#
# Когда запускается
# -----------------
# * при старте бота (appeals.on_ready, через ~8 с) — dry-run в лог, затем apply;
# * раз в сутки — повторный apply.
#
# Что чистится
# ------------
# | Store | Что удаляется | Что сохраняется |
# |-------|---------------|-----------------|
# | `GuildData('appeals')` → `state.items` | accepted / rejected / closed старше 14 дней | все `pending` (открытые), свежие закрытые |
# | `data/reports.db` → `tickets` | закрытые (`closed > 0`) старше 14 дней | открытые тикеты |
# | `data/reports.db` → `violations` | `created` старше 14 дней | — |
# | `data/reports.db` → `archive` | `created` старше 14 дней | — |
# | `GuildData('warnings')` | варны с `timestamp` старше 14 дней | свежие варны |
# | `data/temp_history.json` | записи с `ts` старше 14 дней | свежая история (активные mute/ban файлы не трогаем) |
# | `data/audit_log.json` | события с `timestamp` старше 14 дней | свежие события |
#
# Не трогаем: `channel_routes`, `role_map`, `punish_roles`, активные
# `temp_mutes.json` / `temp_bans.json` / `temp_vmutes.json`, настройки панелей.
#
# Лог: `data_retention [APPLY] days=14 …` в journalctl / logs.
