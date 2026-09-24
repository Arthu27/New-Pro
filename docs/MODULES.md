# Каталог модулей бота

Автогенерация из docstring-ов когов (`cogs/*.py`). Обновить:
`python3 scripts/gen_module_docs.py --write`.

## Системные — 5

| Модуль | Что делает |
| --- | --- |
| `cog_manager` | Управление модулями (cog) — из панели или слеш-командой /module (владелец). |
| `diagnostics` | Bot Diagnostic & Auto-Repair Cog |
| `help` | Help Cog — Luxury Dark-Gold Dashboard (Pillow) |
| `member_store_sync` | Состав участников — в файл (services/member_store.py). |
| `panel_live` | Живые обновления панели из Discord-событий (SSE-поток, services.live_bus). |

## Модерация (MOD_ONLY) — 19

| Модуль | Что делает |
| --- | --- |
| `age_verification` | Верификация участников с молодыми аккаунтами (+ анкета). |
| `ai_moderation` | AI Moderation Cog |
| `anti_alt` | Анти-альт (Anti-Alt Cog) |
| `antiraid` | Hakumo — Анти-рейд / Защита от рейдов |
| `appeals` | Апелляции на баны (Appeals Cog) |
| `auto_filter` | АВТОФИЛЬТР ЧАТА — настоящая автомодерация (PRO). |
| `guardian` | Hakumo «Щит» — анти-нюк защита сервера (PRO). |
| `impersonation` | AntiFake — защита от подделок (impersonation guard). |
| `log_menu` | Hakumo — Интерактивное графическое меню логов и аудит-хаб (Pillow + Discord UI). |
| `logs` | logs |
| `mod_plus` | Mod Plus — набор «быстрых» инструментов модератора: |
| `moderation` | moderation |
| `moderation_cog` | Moderation Cog |
| `proof_cog` | Proof — «демки» к наказаниям: доказательства в одном канале. |
| `reports` | Hakumo — Система репортов (ТЗ 2026-08-26) |
| `security` | Hakumo Security Cog |
| `staff_stats` | Staff Stats — таблица активности модераторов. |
| `temp_moderation` | Временная Модерация Cog |
| `warnings` | Warnings Cog |

## Комьюнити и развлечения — 14

| Модуль | Что делает |
| --- | --- |
| `_menu_bg` | Menu Background Generator — Custom Architectural Background Styles for Each Menu |
| `achievements` | Достижения (Achievements Cog) |
| `activity_stats` | Активность сервера → «Аналитика» в панели. |
| `afk` | AFK-система — /afk с причиной, уведомляет при упоминании |
| `ai_chat` | AI Chat Cog — DM + channel sohbet |
| `event_panel` | Панель событий Discord — бот сам постит embed + кнопки в канал. |
| `ladder` | Hakumo — /ladder: визуальная лестница авто-наказаний. |
| `mafia` | Бот Мафии — Discord UI по ТЗ. |
| `staff_apply` | Staff Apply — Набор в команду сервера |
| `staff_rating` | Рейтинг стаффа (Staff Rating Cog) |
| `voice_tracker` | Отслеживание голосовых каналов |
| `welcome_card` | Welcome Card — роскошная карточка приветствия (тёмно-синий + золото). |
| `welcome_cog` | Welcome Cog |
| `welcome_pro` | Приветствия PRO (Welcome PRO Cog) |

## Хелперы (импортируются) — 4

| Модуль | Что делает |
| --- | --- |
| `__init__` | __init__ |
| `_card_style` | Shared visual style kit — professional black/white/red dashboard aesthetic. |
| `embed_utils` | Hakumo — модуль Embed'ов и GIF |
| `icons` | Hakumo — фирменные иконки (assets/icons/) — помощник embed-миниатюр |

**Всего:** 42 файлов в `cogs/`.
