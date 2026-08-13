# Каталог модулей бота

Автогенерация из docstring-ов когов (`cogs/*.py`). Обновить:
`python3 scripts/gen_module_docs.py --write`.

## Системные — 5

| Модуль | Что делает |
| --- | --- |
| `cog_manager` | Управление модулями (cog) — загрузка/выгрузка/перезагрузка из панели или командой |
| `diagnostics` | Bot Diagnostic & Auto-Repair Cog |
| `feature_flag_cog` | Feature Flags Cog |
| `health` | Сервер состояние skoru + channel основанный на статистика |
| `help` | Help Cog — Luxury Dark-Gold Dashboard (Pillow) |

## Модерация (MOD_ONLY) — 32

| Модуль | Что делает |
| --- | --- |
| `advanced_mod` | advanced_mod |
| `ai_moderation` | AI Moderation Cog |
| `anti_alt` | Анти-альт (Anti-Alt Cog) |
| `antiraid` | Aether — Анти-рейд / Защита от рейдов |
| `appeals` | Апелляции на баны (Appeals Cog) |
| `auto_filter` | АВТОФИЛЬТР ЧАТА — настоящая автомодерация (PRO). |
| `dm_report` | Zhaloba — линия жалоб на DM-рекламу / скаутинг. |
| `impersonation` | AntiFake — защита от подделок (impersonation guard). |
| `invite_tracker` | invite_tracker |
| `lockdown` | Локдаун (Lockdown Cog) |
| `log_menu` | Aether — Интерактивное графическое меню логов и аудит-хаб (Pillow + Discord UI). |
| `logs` | logs |
| `media_only` | Medialock — режим каналов (медиа-только / текст-только / ссылки-только). |
| `mod_case` | MOD CASE — /case: полная карточка нарушителя одной картинкой. |
| `mod_digest` | Мод-дайджест (Mod Digest Cog) |
| `mod_kit` | MOD KIT — быстрые инструменты модератора (PRO). |
| `mod_plus` | Mod Plus — набор «быстрых» инструментов модератора: |
| `mod_report` | Система отчётов модераторов — еженедельный отчёт к собранию |
| `mod_tools` | Инструменты модераторов (Pro-панель в один клик): |
| `moderation` | moderation |
| `moderation_cog` | Moderation Cog |
| `night_mode` | Ночной режим (Night Mode Cog) |
| `proactive_mod` | proactive_mod |
| `proof_cog` | Proof — «демки» к наказаниям: доказательства в одном канале. |
| `rejoin_roles` | Aether — Re-Join Roles (автоматическое восстановление ролей при повторном входе) |
| `report_cog` | Report Cog |
| `security` | Aether Security Cog |
| `tag_jail` | Tag Jail — система «запрещённый тег». |
| `temp_moderation` | Временная Модерация Cog |
| `ticket` | ticket |
| `verification` | Aether — Верификация — режим наблюдателя / opt-in |
| `warnings` | Warnings Cog |

## Комьюнити и развлечения — 57

| Модуль | Что делает |
| --- | --- |
| `_ai_card` | AI Visual Novel Dialogue Card Generator — ИИ пишет текст прямо на картинке |
| `_menu_bg` | Menu Background Generator — Custom Architectural Background Styles for Each Menu |
| `ab_cog` | A/B Testing Cog |
| `achievements` | Достижения (Achievements Cog) |
| `afk` | AFK-система — /afk с причиной, уведомляет при упоминании |
| `ai_chat` | AI Chat Cog — DM + channel sohbet |
| `anime_daily` | Ежедневное аниме-предложение — Jikan API + кнопка русского перевода |
| `archive` | archive |
| `autorole_join` | AutoRole Join — применяет автоматические роли из настроек панели. |
| `autorole_level` | autorole_level |
| `backup_cog` | Backup — автоматическое резервное копирование данных бота. |
| `birthday` | birthday |
| `changelog_cog` | Changelog Cog |
| `companion` | Companion Cog — Bot, belirli bir userya ara очередь kendi желание DM atar. |
| `custom_commands` | Custom Commands — исполнитель своих команд из панели. |
| `custom_embeds` | Custom Embed Builder - Allows сервер admins to create custom embeds |
| `dm_logger` | DM Logger — надёжно записывает ВСЕ входящие личные сообщения (DM) в data/dm_log.json. |
| `duty` | duty |
| `economy_cog` | Economy Cog |
| `events` | Система событий — назначить дату, отправить напоминание |
| `fun_cog` | Fun Cog |
| `gamification_cog` | Gamification Cog |
| `giveaway` | Giveaway Cog |
| `info_tools` | Информация и инструменты — префиксные команды (!uptime, !botinfo, !avatar, и т.д.) |
| `join_to_create` | Join-to-Create — личные голосовые комнаты. |
| `ladder` | Aether — /ladder: визуальная лестница авто-наказаний. |
| `leaderboard` | Leaderboard Cog — Luxury Dark-Gold Dashboard & Leaderboard Table via Pillow |
| `level_cog` | Level Cog |
| `meeting` | Система собраний — собирает реальные данные, сканируя историю сообщений Discord |
| `menu_bg` | Menu Background Generator — Custom Architectural Background Styles for Each Menu |
| `minigames` | Мини-игры |
| `music_cog` | Music Cog |
| `night_summary` | Night Summary — автоматическая ежедневная сводка. |
| `proactive_ai` | Проактивный AI — бот сам размышляет и пишет Артуру в ЛС |
| `profile` | Profile Cog — Professional dashboard/ID-card style generation via Pillow |
| `reaction_roles_cog` | Reaction / Select Roles Cog |
| `recap` | Рекап канала (Recap Cog) |
| `reminders` | Напоминания (Reminders Cog) |
| `replay` | Aether — /replay: визуальная лента событий сервера (реплеер инцидентов). |
| `scheduler` | Scheduler — запланированные анонсы. |
| `search_cog` | Search Cog |
| `server_info` | Server Info — обученные ответы о сервере (FAQ-система) |
| `server_template` | Шаблон сервера (Server Template Cog) |
| `sla_cog` | SLA Cog |
| `social` | Aether Social Cog |
| `staff_apply` | Staff Apply — Набор в команду сервера |
| `staff_stats` | Staff Stats — таблица активности модераторов. |
| `starboard` | Starboard — зал славы (звёздная доска). |
| `stats` | stats |
| `time_tracking_cog` | Time Tracking Cog |
| `voice_commands` | Голосовые команды |
| `voice_tracker` | Отслеживание голосовых каналов |
| `webhooks` | Webhook controli |
| `weekly_crown` | Weekly Crown — еженедельная коронация. |
| `welcome_card` | Welcome Card — роскошная карточка приветствия (тёмно-синий + золото). |
| `welcome_cog` | Welcome Cog |
| `welcome_pro` | Приветствия PRO (Welcome PRO Cog) |

## Хелперы (импортируются) — 5

| Модуль | Что делает |
| --- | --- |
| `__init__` | __init__ |
| `_card_style` | Shared visual style kit — professional black/white/red dashboard aesthetic. |
| `embed_utils` | Aether — модуль Embed'ов и GIF |
| `icons` | Aether — фирменные иконки (assets/icons/) — помощник embed-миниатюр |
| `leveling_engagement` | Leveling & Engagement System |

**Всего:** 99 файлов в `cogs/`.
