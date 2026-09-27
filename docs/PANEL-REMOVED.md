# Веб-панель Hakumo — архив (удалена)

Дата снятия: 2026-09-27.  
Папка `web/`, скрипты запуска панели и тесты панели **полностью удалены** по запросу владельца.  
Discord-команды `/modpanel`, `/event-panel`, апелляции и бот **остались** — это не веб-панель.

---

## Зачем была панель

Flask-приложение «Hakumo Panel» (порт 5001 / gunicorn / Cloudflare Tunnel):
управление сервером из браузера — логи, наказания, роли, антирейд,
аналитика, доступы, тема, AI-чат панели, демки (proofs).

Запуск раньше: вместе с ботом (`main.py` → `_start_web_server`) или отдельно
(`start_panel.sh` / `start_panel.bat` / gunicorn `web.wsgi`).

---

## Что удалено

| Путь | Назначение |
| --- | --- |
| `web/` | Всё приложение панели (~294 файла) |
| `web/app.py` | Flask app, логин, API, инъекция меню |
| `web/wsgi.py` + `gunicorn_conf.py` | Прод-вход gunicorn |
| `web/websocket_server.py` | Live-обновления панели (WS :8765) |
| `web/routes/*.py` (~57) | Доменные маршруты (см. ниже) |
| `web/templates/*.html` (~89) | Страницы UI |
| `web/static/` | CSS/JS/иконки/шрифты панели |
| `web/ai_*.py`, `ai_helper.py`, … | AI-слой панели (DeepSeek и т.п.) |
| `start_panel.sh` / `.bat` | Отдельный запуск панели |
| `requirements-panel.txt` | Зависимости только панели |
| `scripts/demo_panel.py`, `seed_demo_panel.py` | Демо-данные панели |
| `scripts/setup_panel_tunnel.bat` | Cloudflare Tunnel → hakumods.xyz |
| `tests/test_*` (~120) | Тесты, которые импортировали `web.*` |

Данные в `data/` (mod_data, warnings, appeals, rules, mod_reasons…) **не трогали**.

---

## Страницы (templates) — что для чего было

### Вход и оболочка
- `login.html` / `register.html` / `change_password.html` — вход в панель
- `base.html` / `_sidebar_nav.html` / `panel_menu.html` — каркас и меню
- `dashboard.html` — главная: KPI «Модерация сегодня», графики, здоровье
- `spravka.html` — справка
- `theme_settings.html` / `theme_studio.html` — тема UI
- `notifications.html` — уведомления панели
- `status_public.html` — публичный статус

### Модерация
- `logs.html` — журнал наказаний/аудита
- `mod_center.html` / `mod_kiosk.html` / `mod_tools.html` / `mod_control.html` — центры модов
- `mod_insights.html` / `modhistory.html` / `mod_schedule.html` / `mod_settings.html` — инсайты, история, смены, настройки
- `warnings.html` / `temp_moderation.html` / `watchlist.html` — варны, временные меры, вотчлист
- `proofs.html` — демки/доказательства к наказаниям
- `appeals.html` — апелляции (веб-часть)
- `reports.html` / `reports_queue.html` — репорты
- `bulk_actions.html` — массовые меры
- `execute_command.html` / `send_command.html` / `konsol.html` — команды/консоль
- `rules_editor.html` — редактор правил
- `panel_access.html` / `panel_logs.html` — доступ к панели и её логи
- `ladder.html` — лестница наказаний
- `staff_apps.html` / `member_apply.html` / `public_apply.html` / `my_applications.html` — наборы стаффа

### Участники
- `users.html` / `user_profile.html` / `member_profile.html` / `member_search.html` / `member_notes.html` / `member_dashboard.html`
- `afk_list.html` / `voice_stats.html` / `birthday_register.html` / `invite_tracker.html` / `rejoin_roles.html` / `color_roles.html`

### Сервер / каналы / роли
- `guilds.html` / `channels.html` / `channel_settings.html` / `roles.html` / `role_settings.html` / `role_permissions.html`
- `log_settings.html` / `message_logs.html` / `welcome.html` / `welcome_editor.html` / `verification.html`
- `announcements.html` / `events.html` / `chat.html` / `commands.html` / `todo.html` / `team_board.html`

### Защита
- `security.html` / `antiraid.html` / `anticrash.html` / `antifake.html` / `guardian.html` / `autofilter.html` / `automod_settings.html` / `ai_moderation.html`

### Аналитика и ops
- `analytics.html` / `bot_stats.html` / `bot_diagnostics.html` / `server_health.html` / `ops_center.html` / `pagerduty.html` / `backups.html` / `feature_flags.html` / `cog_manager.html` / `bot_settings.html` / `settings.html`

### AI панели
- `ai_chat_panel.html` — чат с AI внутри панели (не Discord `/ai`)

---

## Routes (`web/routes/`) — что для чего было

| Модуль | Для чего |
| --- | --- |
| `_common.py` | Общий контекст Flask, имена, ACL, демо-участники |
| `pages.py` / `pages2.py` / `pages_core.py` | Раздача HTML-страниц |
| `dashboard.py` | SSR-цифры «Модерация сегодня» |
| `guild_admin.py` / `guild_extra.py` / `guild_features.py` | Сервер: каналы, роли, фичи |
| `channels_admin.py` / `channel_settings.py` | Каналы |
| `mod_control.py` / `mod_settings.py` / `mod_schedule.py` / `mod_insights.py` / `panel_punish.py` / `modplus.py` | Мод-API и наказания из панели |
| `appeals_panel.py` | Веб-апелляции |
| `reports_panel.py` / `reports_queue.py` | Репорты |
| `security_panel.py` / `security_api.py` / `guardian.py` / `anticrash.py` / `antifake_panel.py` / `autofilter.py` / `roles_antiraid.py` | Защита |
| `analytics_plus.py` | Аналитика + чтение аудита (`_read_audit`) |
| `permissions.py` / `staff_limits_panel.py` / `role_settings_panel.py` | Права и лимиты стаффа |
| `members.py` / `member_ops.py` / `user_profile.py` / `community.py` | Участники |
| `welcome_panel.py` / `verification_panel.py` / `ladder_panel.py` | Приветствие, верификация, лестница |
| `ai_assist.py` / `ai_chat.py` / `ai_mod.py` | AI в панели |
| `backup_restore.py` / `backups.py` / `flags_panel.py` / `bot_settings.py` | Бэкапы, флаги, настройки бота |
| `commands_panel.py` / `chat.py` / `todo.py` / `theme.py` / `ux.py` / `status.py` / `notifications.py` / `pagerduty_hook.py` / `live_sse.py` / `log_cards_panel.py` / `tasks_rules.py` / `admin_api.py` | Прочее UI/API |

---

## Что бот брал из `web/` (и тоже убрано)

Раньше бот импортировал куски панели. После удаления — импорты сняты / мягкий fallback:

| Кто | Что брал | Зачем | После удаления |
| --- | --- | --- | --- |
| `main.py` | `web.app`, `_start_web_server`, websocket | Поднять панель рядом с ботом | Панель не стартует |
| `cogs/ai_chat.py` | `web.ai_helper.ai_assistant` | Ответы AI в Discord | Локальный fallback / «AI недоступен» |
| `services/mod_leaderboard.py` | `analytics_plus._read_audit`, `mod_control.names_from_audit` | Рейтинг модов | Без аудита панели — пустая активность |
| `services/health_index.py` | `_read_audit`, `_parse_ts` | Индекс здоровья | Половина баллов / нет данных |
| `services/freshness.py` | `_parse_ts`, `load_warns_map`, `_read_audit` | «Остывание» нарушителя | Без аудита панели |
| `services/ai_server_snapshot.py` | `_read_audit`, `_parse_ts` | Снимок для AI | Пустая неделя модов |

**Не путать с Discord `/modpanel`** — это `cogs/moderation.py` + `services/menu_banners.py` + `services/v2_layouts.py`. Они **не удалялись**.

Оставшиеся сервисы с именем panel (не веб-UI):
- `services/panel_notify.py` — Discord-уведомления о мерах (использует мод-ког)
- `services/panel_menu.py` / `panel_todo.py` — **тоже удалены** (только веб-меню/todo)

---

## Как снова поднять панель (если понадобится)

Нужен git-restore ветки/коммита до удаления `web/`, плюс `requirements-panel.txt`,
`start_panel.*`, правки `main.py` на `_start_web_server` и мост `set_bot_instance`.
Документация домена: раньше `docs/PANEL-DOMAIN.md` (Cloudflare Tunnel → hakumods.xyz).

---

## Итог для оператора

- Бот Discord работает **без** старой браузерной панели.
- **Новая компактная панель (v2):** см. [`PANEL-PAGES.md`](PANEL-PAGES.md) — только модерация + страницы бота для владельца.
- Управление мерами: Discord `/modpanel` + журнал в панели v2.
- Старый URL/`hakumods.xyz` туннель больше не обязателен.
