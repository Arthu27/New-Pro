# -*- coding: utf-8 -*-
"""Все пользовательские тексты Staff Manager.

Запрещено: «ранг», «выше/ниже», цифры рангов, ключи (master…),
protected, hierarchy, ID, технические англ. слова в UI.
"""
from __future__ import annotations

# ── действия ──────────────────────────────────────────────────────────
ACTION_LABELS = {
    'assign': 'Назначить',
    'promote': 'Повысить',
    'demote': 'Понизить',
    'remove': 'Снять с должности',
    'transfer': 'Перевести',
    'probation': 'Испытательный',
    'vacation': 'Отпуск',
    'history': 'История',
    'request': 'Заявка',
    'self_leave': 'Уйти по собственному',
    'propose_transfer': 'Предложить перевод',
}

ACTION_DESC = {
    'assign': 'Первое назначение в команду',
    'promote': 'Следующая ступень',
    'demote': 'Предыдущая ступень',
    'remove': 'Убрать все стафф-роли',
    'transfer': 'В другую ветку · нужно согласие',
    'probation': 'Отметить испытательный срок',
    'vacation': 'Поставить в отпуск',
    'history': 'Последние действия',
    'self_leave': 'Добровольный уход',
    'propose_transfer': 'Запрос в другую ветку',
    'request': 'Заявка ответственному',
}

# Описание роли в select — без «ранг N / выше / ниже»
ROLE_DESC = {
    'master': 'Стартовая ступень',
    'curator': 'Куратор ветки',
    'assistant': 'Помощник администратора',
    'admin': 'Администратор ветки',
}

BRANCH_DESC = {
    'moderators': 'Ветка модерации',
    'helpers': 'Ветка хелперов',
    'event': 'Ветка ивентов',
    'broadcaster': 'Ветка эфиров',
    'support': 'Ветка поддержки',
    'closemod': 'Ветка CloseMod',
    'creative': 'Ветка Creative',
}

REMOVAL_KINDS = {
    'own': 'По собственному желанию',
    'inactive': 'Неактивность',
    'violation': 'Нарушение',
    'probation': 'По итогам испытательного',
    'other': 'Другое',
}

# ── панель ────────────────────────────────────────────────────────────
PANEL_TITLE = '# Staff Manager\n-# HAKUMO'
PANEL_MEMBER = '**Участник** · {mention}'
PANEL_ROLE_BRANCH = '{role_emoji} **{role}** · {branch_emoji} {branch}'
PANEL_VACATION = '-# в отпуске'
PANEL_MULTI = '-# роли нескольких веток — только Стафф админ'
PANEL_DOUBLE = '-# лишние стафф-роли · сначала снимите'
PANEL_QUEUE = '-# Очередь · шаг {step}/{total}{tail}'
PANEL_ACTION = '**Действие**'
PANEL_ROLE = '**Роль**'
PANEL_BRANCH = '**Ветка**'
PANEL_REMOVAL_KIND = '**Тип снятия**'
PANEL_CONFIRM = '**Подтверждение**'
BTN_OK = 'Подтвердить'
BTN_CANCEL = 'Отмена'
BTN_REVOKE = 'Отозвать запрос'
BTN_REQUEST = 'Заявка'
PLACEHOLDER_ACTION = 'Действие'
PLACEHOLDER_ROLE = 'Роль'
PLACEHOLDER_BRANCH = 'Ветка'
PLACEHOLDER_REMOVAL = 'Тип снятия'

# ── ошибки (коротко + что делать) ─────────────────────────────────────
ERR_NO_CONFIG = 'Staff Manager не настроен. Проверьте конфиг и перезапустите бота.'
ERR_SERVER_ONLY = 'Команда только на сервере.'
ERR_NO_ACCESS = 'Нет доступа.'
ERR_STALE = 'Данные обновились. Откройте /staff заново.'
ERR_NOT_FOUND = 'Участник не найден на сервере.'
ERR_SELF = 'Нельзя изменить самого себя.'
ERR_OTHER_BRANCH = 'Это другая ветка.'
ERR_ADMIN_ONLY = 'Эту роль выдаёт только Стафф админ.'
ERR_NO_RIGHTS = 'Нет прав управлять ролями.'
ERR_ALREADY_PENDING = 'У человека уже есть ожидающий запрос.'
ERR_DM_CLOSED = 'Личка закрыта. Укажите запасной канал согласий в конфиге.'
ERR_CONSENT_ONLY_TARGET = 'Кнопку может нажать только тот, кому предложен перевод.'
ERR_BOT_BELOW = (
    'Роль бота ниже выдаваемой. Поднимите роль бота выше в настройках сервера.'
)
ERR_DOUBLE_STAFF = 'Нельзя оставить две стафф-роли. Откат выполнен.'
ERR_ROLE_NOT_APPLIED = 'Роль не применилась. Проверьте права бота (/staff_diagnose).'
ERR_NO_STAFF = 'У человека нет стафф-роли.'
ERR_PICK_REMOVAL = 'Выберите тип снятия.'

OK_DONE = '✅ {action} · {mention}{extra}'
OK_CONSENT_SENT = '⏳ Запрос согласия отправлен {mention}.'

# ── наборы / повышение / отпуск ───────────────────────────────────────
PROMO_MISSING = 'Нельзя повысить:\n{items}'
PROMO_BYPASS = 'Повысить вне правил'
PROMO_CEREMONY_TITLE = 'Церемония'
DEMOTE_TITLE = 'Понижение'
VACATION_CARD_TITLE = 'Открытка: отпуск'
VACATION_WELCOME_BACK = 'С возвращением!'
VACATION_PENDING = 'Заявка на отпуск отправлена на одобрение.'
VACATION_IN_BLOCK = 'В отпуске'
ACCEPTED_BY = 'Принял: {actor}'
DECLINED_BY = 'Отклонил: {actor}'
BUNDLE_BLOCK = 'Набор роли'
NEXT_STEP = 'Следующая ступень'
HISTORY_TITLE = 'История'
ROSTER_TITLE = 'Состав стаффа'
ROSTER_ON_VACATION = 'В отпуске'

# ── согласия / DM ─────────────────────────────────────────────────────
CONSENT_TITLE = '## Предложение: {action}'
CONSENT_BODY = (
    'От: {actor}\n'
    'Из: **{from_role}** / {from_branch}\n'
    'В: **{to_role}** / {to_branch}\n'
    'Причина: {reason}\n'
    'Срок: **{hours}ч** · {expires}'
)
CONSENT_ACCEPT = 'Принять'
CONSENT_DECLINE = 'Отказаться'
CONSENT_ACCEPTED = '✅ Принято. Роли обновлены.'
CONSENT_DECLINED_OK = 'Отказ зафиксирован.'
CONSENT_EXPIRED_DM = '⏱ Срок согласия на перевод истёк (цель {mention}).'
REMOVE_DM_TITLE = '## Снятие с должности'
REMOVE_DM_BODY = (
    'Вы сняты с **{role}** в ветке **{branch}**.\n'
    'Тип: {kind}\n'
    'Кем: {actor}\n'
    'Причина: {reason}'
)

# стоп-слова для тестов (в UI-текстах быть не должно)
STOP_WORDS = (
    'ранг', 'выше', 'ниже', 'равно', 'protected', 'hierarchy',
    'дабл-стафф', 'дабл стафф', 'branch_key', 'role_key',
    'master', 'curator', 'assistant', 'admin',  # как сырые ключи в UI
)
# исключения: слова в названиях ролей из конфига (Master/Curator…) — ок в label
STOP_IN_DESC = (
    'ранг', 'выше', 'ниже', 'равно', 'protected', 'hierarchy',
    'дабл-стафф', 'дабл стафф', 'branch_key', 'role_key',
)


def t(key: str, **kwargs) -> str:
    val = globals().get(key)
    if val is None:
        return key
    if kwargs and isinstance(val, str):
        try:
            return val.format(**kwargs)
        except Exception:
            return val
    return val if isinstance(val, str) else str(val)
