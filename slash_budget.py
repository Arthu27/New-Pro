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

# Что видит обычный участник и модератор в слеш-меню. Кураторский набор:
# ежедневное (справка, профили, топы), быстрые игры, самая ходовая модерация
# и аварийные кнопки. Настройки/рареджи (сетапы, выключатели, отчёты админам)
# живут на префиксе и в веб-панели.
KEEP_SLASH = frozenset({
    # справка и профиль
    'help', 'profile', 'leaderboard', 'stats', 'badges', 'streak',
    'afk', 'invites', 'birthday', 'changelog',
    # социалка и быстрые игры
    'спасибо', 'карма', 'дуэль', 'coinflip', 'rps', '8ball', 'dice',
    'poll', 'events', 'ачивки', 'счёт', 'crown', 'recap', 'оценить', 'квиз',
    # быт участника
    'напомни', 'report', 'my-application',
    # модерация — ежедневное
    'warn', 'warnings', 'moderate', 'role', 'case', 'userinfo',
    'snipe', 'jail', 'unjail', 'logs', 'ticket-panel',
    # аварийные кнопки
    'panic', 'lockdown', 'unlockdown', 'nuke', 'raidcleanup',
    'antiraid', 'scan-link',
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
