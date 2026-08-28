# -*- coding: utf-8 -*-
"""Русские метки действий журнала аудита Discord.

Единый словарь для бота (cogs/logs.py пишет события) и панели
(/api/logs, поиск, лента активности, экспорт): сырые коды вида
bot_add / integration_delete / overwrite_create больше нигде не должны
всплывать «как есть» — ни в новых записях, ни в уже накопленных
(переводим и при показе, старые файлы мигрировать не нужно).

Ключи — имена AuditLogAction (строками, чтобы панель не тянула discord).
Значения: (категория из CATEGORIES cogs/logs.py, русская метка).
Плюс легаси-глаголы бота (warn/mute/timeout...) — они попадают в журнал
из mod_data и Discord-команд.
"""

# ── Все действия AuditLogAction (discord.py 2.x, полный набор) ─────────────
AUDIT_LABELS = {
    # сервер
    'guild_update': ('сервер', 'Сервер обновлён'),
    'bot_add': ('сервер', 'Бот добавлен'),
    'integration_create': ('сервер', 'Интеграция добавлена'),
    'integration_update': ('сервер', 'Интеграция обновлена'),
    'integration_delete': ('сервер', 'Интеграция удалена'),
    'webhook_create': ('сервер', 'Вебхук создан'),
    'webhook_update': ('сервер', 'Вебхук обновлён'),
    'webhook_delete': ('сервер', 'Вебхук удалён'),
    'emoji_create': ('сервер', 'Эмодзи создан'),
    'emoji_update': ('сервер', 'Эмодзи обновлён'),
    'emoji_delete': ('сервер', 'Эмодзи удалён'),
    'sticker_create': ('сервер', 'Стикер создан'),
    'sticker_update': ('сервер', 'Стикер обновлён'),
    'sticker_delete': ('сервер', 'Стикер удалён'),
    'scheduled_event_create': ('сервер', 'Событие создано'),
    'scheduled_event_update': ('сервер', 'Событие обновлено'),
    'scheduled_event_delete': ('сервер', 'Событие отменено'),
    'stage_instance_create': ('сервер', 'Трибуна открыта'),
    'stage_instance_update': ('сервер', 'Трибуна обновлена'),
    'stage_instance_delete': ('сервер', 'Трибуна завершена'),
    'app_command_permission_update': ('сервер', 'Доступ к командам обновлён'),
    'soundboard_sound_create': ('сервер', 'Звук добавлен'),
    'soundboard_sound_update': ('сервер', 'Звук обновлён'),
    'soundboard_sound_delete': ('сервер', 'Звук удалён'),
    'creator_monetization_request_created': ('сервер', 'Запрос монетизации'),
    'creator_monetization_terms_accepted': ('сервер', 'Условия монетизации приняты'),
    'onboarding_prompt_create': ('сервер', 'Экран приветствия создан'),
    'onboarding_prompt_update': ('сервер', 'Экран приветствия обновлён'),
    'onboarding_prompt_delete': ('сервер', 'Экран приветствия удалён'),
    'onboarding_create': ('сервер', 'Онбординг создан'),
    'onboarding_update': ('сервер', 'Онбординг обновлён'),
    'home_settings_create': ('сервер', 'Главная страница настроена'),
    'home_settings_update': ('сервер', 'Главная страница обновлена'),
    # каналы
    'channel_create': ('channel', 'Канал создан'),
    'channel_update': ('channel', 'Канал обновлён'),
    'channel_delete': ('channel', 'Канал удалён'),
    'overwrite_create': ('channel', 'Права на канал выданы'),
    'overwrite_update': ('channel', 'Права на канал изменены'),
    'overwrite_delete': ('channel', 'Права на канал сброшены'),
    'thread_create': ('channel', 'Ветка создана'),
    'thread_update': ('channel', 'Ветка обновлена'),
    'thread_delete': ('channel', 'Ветка удалена'),
    # модерация
    'ban': ('mod', 'Бан'),
    'unban': ('mod', 'Бан снят'),
    'kick': ('mod', 'Кик'),
    'member_prune': ('mod', 'Чистка неактивных'),
    'member_update': ('mod', 'Участник обновлён'),
    'automod_block_message': ('automod', 'AutoMod: сообщение заблокировано'),
    'automod_flag_message': ('automod', 'AutoMod: сообщение помечено'),
    'automod_timeout_member': ('automod', 'AutoMod: таймаут'),
    'automod_quarantine_user': ('automod', 'AutoMod: карантин'),
    'automod_rule_create': ('automod', 'Правило AutoMod создано'),
    'automod_rule_update': ('automod', 'Правило AutoMod обновлено'),
    'automod_rule_delete': ('automod', 'Правило AutoMod удалено'),
    # роли
    'role_create': ('role', 'Роль создана'),
    'role_update': ('role', 'Роль обновлена'),
    'role_delete': ('role', 'Роль удалена'),
    'member_role_update': ('role', 'Изменение ролей'),
    # голос
    'member_move': ('voice', 'Перемещён в голосовом'),
    'member_disconnect': ('voice', 'Отключён от голосового'),
    # сообщения
    'message_delete': ('message', 'Сообщение удалено'),
    'message_bulk_delete': ('message', 'Массовое удаление'),
    'message_pin': ('message', 'Сообщение закреплено'),
    'message_unpin': ('message', 'Сообщение откреплено'),
    # приглашения
    'invite_create': ('invite', 'Приглашение создано'),
    'invite_update': ('invite', 'Приглашение обновлено'),
    'invite_delete': ('invite', 'Приглашение удалено'),
}

# ── Легаси-глаголы бота (mod_data, Discord-команды): туда же в русское ─────
LEGACY_ACTION_LABELS = {
    'warn': 'Предупреждение',
    'mute': 'Мут',
    'unmute': 'Мут снят',
    'timeout': 'Таймаут',
    'untimeout': 'Таймаут снят',
    'jail': 'Тюрьма',
    'unjail': 'Освобождён',
    'vmute': 'Войс-мут',
    'note': 'Заметка',
}


def audit_label(name):
    """(категория, метка) для имени AuditLogAction; None, если неизвестно."""
    return AUDIT_LABELS.get(str(name or ''))


def human_action(raw):
    """Человеческая метка для показа: сырой код → русский, остальное не трогаем.

    Переведено → возвращаем как есть; сырой код (bot_add, 'AuditLogAction.ban',
    легаси 'warn'/'Mute') → русская метка; неизвестное → исходная строка.
    """
    s = str(raw or '').strip()
    if not s:
        return 'Действие'
    key = s.split('.')[-1]            # 'AuditLogAction.ban' → 'ban'
    lbl = AUDIT_LABELS.get(key)
    if lbl:
        return lbl[1]
    low = key.lower()                 # 'Ban' (capitalize в api_logs), 'WARN'
    if low in AUDIT_LABELS:
        return AUDIT_LABELS[low][1]
    if low in LEGACY_ACTION_LABELS:
        return LEGACY_ACTION_LABELS[low]
    return s
