# -*- coding: utf-8 -*-
"""Политика загрузки модулей (когов) бота.

Один модуль — три ручки управления через .env, без правки кода:

    MOD_ONLY=1            — «только модерация»: грузятся модераторские и
                            системные модули, вся «веселуха» (экономика, игры,
                            музыка, AI-чат, ивенты, левелинг…) выключена.
    DISABLED_COGS=a,b,c   — добить конкретные модули в любом режиме.
    EXTRA_COGS=a,b        — вернуть конкретные модули поверх MOD_ONLY.

    BOT_SLIM=1            — «модерация + тикеты + музыка»: грузятся ядро,
                            модераторские, тикетные и музыкальные модули;
                            вся остальная «веселуха» (экономика, игры,
                            AI-чат, ивенты, левелинг…) выключена. Данные
                            на диске остаются — вернёшь флаг, всё вернётся.

Имена модулей в DISABLED_COGS / EXTRA_COGS — с «.py» или без, регистр не
важен (music_cog == Music_Cog.py). Режим подхватывается при старте бота —
поменял .env, перезапустил, готово. Никаких правок кода и миграций данных:
дата-файлы (экономика, уровни…) на диске остаются, модуль просто спит.

Чистые функции (select_cog_files / select_from_environment) покрыты тестом
tests/test_cogs_policy.py — классификация протестирована отдельно от бота.
"""
import os

# ─── вспомогательные модули (НЕ коги — грузятся импортом из других файлов) ──
HELPER_COGS = frozenset({
    '__init__.py',
    '_card_style.py',
    'embed_utils.py',
    'icons.py',
    'leveling_engagement.py',
    # CRUD-хранилище магазина: импортируют economy_cog и shop_panel,
    # само по себе когом не является (setup нет и не нужен).
    'economy_shop.py',
})

# ─── системные модули — живут всегда, даже в MOD_ONLY ─────────────────────
CORE_COGS = frozenset({
    'help.py',             # /help индексирует только загруженные команды — полезен всегда
    'cog_manager.py',      # !module load/unload — чтобы вернуть модуль без рестарта
    'feature_flag_cog.py', # фиче-флаги (инфраструктура)
    'health.py',           # health-check / мониторинг
    'diagnostics.py',      # самодиагностика бота
})

# ─── модерация — ядро, которое остаётся в MOD_ONLY ────────────────────────
MODERATION_COGS = frozenset({
    # наказания / кейсы / демки
    'moderation.py', 'moderation_cog.py', 'advanced_mod.py',
    'mod_case.py', 'mod_kit.py', 'mod_plus.py', 'mod_tools.py',
    'warnings.py', 'temp_moderation.py', 'proof_cog.py',
    # автомод
    'ai_moderation.py', 'auto_filter.py', 'proactive_mod.py',
    # анти-рейд / безопасность / верификация
    'antiraid.py', 'security.py', 'verification.py', 'tag_jail.py',
    'impersonation.py',
    # анти-альт / локдаун / ночной режим — аварийный арсенал
    'anti_alt.py', 'lockdown.py', 'night_mode.py',
    # модераторская разведка
    'invite_tracker.py',
    # контент-ограничения и анти-эвейд
    'media_only.py', 'rejoin_roles.py',
    # репорты от пользователей
    'report_cog.py', 'dm_report.py',
    # журнал аудита (на него завязана веб-панель)
    'logs.py', 'log_menu.py',
    # обращения к модерам + отчёт по модерации
    'ticket.py', 'mod_report.py',
    # апелляции на баны + еженедельный мод-дайджест
    'appeals.py', 'mod_digest.py',
    # расписание дежурств стаффа с автонапоминаниями
    'staff_shifts.py',
})

# итоговый список MOD_ONLY
MOD_ONLY_COGS = CORE_COGS | MODERATION_COGS

# ─── тикеты и музыка — профиль BOT_SLIM (модерация + тикеты + музыка) ──────
# Тикеты уже сидят в MODERATION_COGS (ticket.py, mod_report.py) — здесь
# дополнение: SLA, набор команды и приём заявок.
TICKET_COGS = frozenset({
    'sla_cog.py',        # SLA тикетов
    'staff_apply.py',    # заявки в команду (веб-панель читает данные)
})

# Музыка: плеер + голосовые команды + трекер времени в голосе
# (на трекер завязана веб-панель — голосовая статистика).
MUSIC_COGS = frozenset({
    'music_cog.py',
    'voice_commands.py',
    'voice_tracker.py',
})

# AI-чат — по желанию владельца включается в профиль SLIM
AI_CHAT_COGS = frozenset({
    'ai_chat.py',        # AI-чат (Mistral/OpenRouter/DeepSeek/Ollama)
})

# Профиль «модерация + тикеты + музыка + AI-чат»
SLIM_COGS = CORE_COGS | MODERATION_COGS | TICKET_COGS | MUSIC_COGS | AI_CHAT_COGS

# env-переменные
ENV_MOD_ONLY = 'MOD_ONLY'
ENV_SLIM = 'BOT_SLIM'
ENV_DISABLED = 'DISABLED_COGS'
ENV_EXTRA = 'EXTRA_COGS'

_TRUTHY = {'1', 'true', 'yes', 'on', 'да', 'вкл'}


def env_flag(name, default=False, environ=None):
    """Булев флаг из окружения: 1/true/yes/on/да/вкл — правда."""
    env = os.environ if environ is None else environ
    raw = str(env.get(name, '') or '').strip().lower()
    if not raw:
        return bool(default)
    return raw in _TRUTHY


def _norm_name(name):
    """Имя модуля к единому виду: 'Cogs/Music_Cog.py ' -> 'music_cog'."""
    n = str(name or '').strip().lower().replace('\\', '/').split('/')[-1]
    if n.endswith('.py'):
        n = n[:-3]
    if n.startswith('cogs.'):
        n = n[5:]
    return n.strip()


def _parse_list(text):
    """'a, b.py ,C' -> {'a', 'b', 'c'} (пустое -> пустое множество)."""
    if not text:
        return frozenset()
    if isinstance(text, (list, tuple, set, frozenset)):
        parts = [str(x) for x in text]
    else:
        parts = str(text).replace(';', ',').split(',')
    return frozenset(n for n in (_norm_name(p) for p in parts) if n)


def is_helper(filename):
    """Вспомогательный модуль (не загружается как extension)."""
    return filename in HELPER_COGS


def select_cog_files(files, mod_only=False, slim=False, disabled=None, extra=None):
    """Разделить файлы ./cogs на (загрузить, отключить).

    files — имена файлов с расширением '.py' (как из os.listdir).
    disabled / extra — списки или строки через запятую; имена в любом виде.
    Возвращает кортеж (enabled, disabled) — оба отсортированы, без хелперов.
    """
    disabled_names = _parse_list(disabled)
    extra_names = _parse_list(extra)

    enabled, gone = [], []
    for f in files:
        if not f.endswith('.py') or is_helper(f):
            continue
        mod = _norm_name(f)
        if mod in disabled_names:
            gone.append(f)
            continue
        if mod_only and f not in MOD_ONLY_COGS and mod not in extra_names:
            gone.append(f)
            continue
        if slim and f not in SLIM_COGS and mod not in extra_names:
            gone.append(f)
            continue
        enabled.append(f)
    return sorted(enabled), sorted(gone)


def select_from_environment(files, environ=None):
    """Обёртка: прочитать MOD_ONLY / DISABLED_COGS / EXTRA_COGS из окружения."""
    env = os.environ if environ is None else environ
    return select_cog_files(
        files,
        mod_only=env_flag(ENV_MOD_ONLY, environ=env),
        slim=env_flag(ENV_SLIM, environ=env),
        disabled=env.get(ENV_DISABLED, ''),
        extra=env.get(ENV_EXTRA, ''),
    )
