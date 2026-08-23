# -*- coding: utf-8 -*-
"""Бюджет слеш-команд: Discord даёт максимум 100 глобальных app-команд.

С сотней модулей в cogs/ правило «каждый гибрид попадает в слеш-меню» не
масштабируется: дерево переполняется (CommandLimitReached) и коги начинают
падать каскадом по алфавиту — включая боевую модерацию (warnings, ticket...).

Решение — централизованный white-list. После загрузки каждого модуля дерево
чистится: в глобальном слеш-меню остаются только имена из KEEP_SLASH, всё
остальное выносится ИЗ ДЕРЕРА, но НЕ из бота: префиксные версии гибридных
команд продолжают работать (!варн, !тикет-конфиг, !отчёт-неделя...). То есть
функциональность не теряется — меню просто остаётся компактным и осмысленным.

Как вернуть команду в слеш-меню: добавь её ИМЯ КАК В DISCORD (name= из
декоратора, это не всегда имя функции) в KEEP_SLASH. Страж-бюджета —
tests/test_slash_budget.py: следит, чтобы меню не переполнилось и чтобы
имена из KEEP_SLASH реально существовали (ловит переименования).
"""
from discord import AppCommandType, app_commands

LIMIT = 100          # жёсткий лимит Discord на глобальные chat-input команды
WARN_AT = 90         # мягкий порог — пора пересмотреть меню

# Что видит участник и модератор в слеш-меню. Кураторский набор ЛЁГКОГО
# состава (cogs_policy LEAN — он по умолчанию): модерация-ядро, защита,
# jail, апелляции, логи, тикеты + заявки, приветствие, AI и служебное.
# Игровых/экономических имён здесь больше нет — эти модули спят, и
# держать их в меню бессмысленно (команды просто не существуют в боте).
# Редкие настройки живут в веб-панели и на префиксе.
KEEP_SLASH = frozenset({
    # справка и профиль участника
    'help',
    # модерация — ежедневное (всё в одном select-меню /modpanel)
    'modpanel', 'warnings', 'unwarn', 'clearwarns', 'role', 'utility',
    'jail', 'unjail', 'jailed', 'tagjail',
    # доказательства
    'proof', 'proofs', 'proofdel',
    # автомод и защита
    'filter', 'antiraid', 'antiraid-reload', 'scan-link',
    'security', 'security-toggle', 'security-newaccount', 'backup', 'backup-list',
    'verify-status', 'verify-toggle',
    # апелляции
    'апелляция', 'апелляции',
    # логи
    'logs', 'logs-center', 'logs-setup', 'setup-logs', 'modlogs', 'logmenu',
    'логи-экспорт',
    # тикеты и заявки
    'ticket-panel', 'ticket-config', 'ticket-add', 'ticket-remove',
    'ticket-auto-close', 'ticket-ai-toggle', 'ticket-ai-stats',
    'ticket-feedback-stats', 'ticket-force-escalate',
    'ticket-rate-limit-info', 'ticket-reset-rate-limit',
    'sla-status', 'sla-info', 'sla-create', 'sla-breaches',
    'my-application', 'staff-panel',
    # приветствие
    'welcome', 'приветствие',
    # AI
    'ai-info-list', 'ai-info-clear', 'ai-reset',
    # служебное (здоровье и фиче-флаги)
    'server-health', 'channel-stats', 'leaveguild',
    'flag-list', 'flag-info', 'flag-create', 'flag-enable', 'flag-disable',
    'flag-rollout',
})


def _chat_input_commands(tree):
    """Глобальные chat-input команды дерева (контекстные меню — отдельный лимит)."""
    return [c for c in tree.get_commands() if not isinstance(c, app_commands.ContextMenu)]


def apply_slash_budget(tree, keep=None):
    """Оставить в глобальном дереве только имена из keep. Идемпотентно.

    Возвращает (kept, pruned) — отсортированные списки имён оставленных и
    удалённых из дерева команд (удалённые остаются доступны через префикс).
    """
    keep = KEEP_SLASH if keep is None else keep
    kept, pruned = [], []
    for cmd in _chat_input_commands(tree):
        if cmd.name in keep:
            kept.append(cmd.name)
        else:
            tree.remove_command(cmd.name, type=AppCommandType.chat_input)
            pruned.append(cmd.name)
    return sorted(kept), sorted(pruned)
