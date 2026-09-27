# -*- coding: utf-8 -*-
"""Каталог причин наказаний для /modpanel и /report (правила 1.1–1.9).

В селекте: ярлык «1.1 · Реклама», описание = наказание + срок + текст запрета.
В деле/логе: «1.1 — <текст запрета>» (без строки «Бан/Варн»).

Селект фильтруется по действию: бан → только правила с баном,
мут → с мутом, варн → с варном/предом.
"""
from __future__ import annotations

from typing import Iterable

# Действия панели → ключ допуска в правиле
_ACTION_PUNISH = {
    'warn': 'warn',
    'ban': 'ban',
    'timeout': 'mute',
    'mute_chat': 'mute',
    'vmute': 'mute',
}

# (код, ярлык, текст запрета, допустимые меры, подпись наказания, длительность)
# меры: 'warn' | 'mute' | 'ban'
MODPANEL_REASONS: tuple[tuple[str, str, str, tuple[str, ...], str, str], ...] = (
    (
        '1.1',
        'Реклама',
        'Запрещена реклама любых сторонних серверов, продуктов, а также '
        'прямые запросы денег, товаров или услуг.',
        ('ban', 'warn'),
        'Бан/Варн',
        'На усмотрение администрации',
    ),
    (
        '1.2',
        '18+ / хейт / вред',
        'Запрещается публикация, распространение и трансляция шокирующих, '
        'порнографических и иных материалов сексуального характера, а также '
        'контента, разжигающего ненависть или содержащего пропаганду, призывы, '
        'инструкции, советы либо нормализацию причинения вреда себе или другим '
        'людям. Строго запрещены любые действия, направленные на сексуальное '
        'совращение или эксплуатацию несовершеннолетних, а также '
        'распространение сексуального контента с их участием.',
        ('mute', 'warn', 'ban'),
        'Мут/Варн/Бан',
        'На усмотрение администрации',
    ),
    (
        '1.3',
        'Обход / твинк',
        'Запрещено использование другой учетной записи для обхода наложенных '
        'на вас наказаний или с целью фарма серверной валюты. Варн/выдается '
        'на основной аккаунт, твинк получает блокировку.',
        ('warn', 'ban'),
        'Варн/Бан',
        'от 30 дней',
    ),
    (
        '1.4',
        'Личка / докс',
        'Запрещено распространение любой личной информации или фото человека '
        'без его согласия, угрозы сватом/доксом и их совершение, а также '
        'демонстрация способов деанонимизации пользователей.',
        ('warn', 'ban'),
        'Пред/Бан',
        'от 30 дней',
    ),
    (
        '1.5',
        'Аватар / баннер',
        'Запрещено использование изображений профиля (аватарка, баннер), '
        'содержащего оскорбительный, шокирующий, сексуальный, тошнотворный '
        'или изображающий кровопролитие контент. Также запрещены изображения '
        'профиля, содержащие в себе разжигающую ненависть и иную запрещенную '
        'символику.',
        ('warn', 'ban'),
        'Пред/Бан',
        'от 30 дней',
    ),
    (
        '1.6',
        'Помеха серверу',
        'Запрещены деструктивные действия по отношению к серверу, способные '
        'привести к помехам в процессе его развития, т.е. любое '
        'препятствование работе стаффа, неконструктивная критика в сторону '
        'персонала сервера, призывы покинуть проект, намеренный багоюз бота '
        'или ролей, злоупотребление подачей жалоб.',
        ('warn', 'mute'),
        'Предупреждение/Мут',
        'До 2 часов',
    ),
    (
        '1.7',
        'SoundPad / голос',
        'Запрещен SoundPad и его аналоги, громкие мешающие звуки, увеличение '
        'громкости микрофона, использование программ для изменения голоса.',
        ('warn', 'mute'),
        'Предупреждение/Мут',
        'До 2 часов',
    ),
    (
        '1.8',
        'Капс / спам / флуд',
        'Запрещен капс, спам, флуд в любых его проявлениях, беспричинное '
        'многократное упоминание участников и ролей, а также несоблюдение '
        'тематики чата.',
        ('warn', 'mute'),
        'Предупреждение/Мут',
        'До 2 часов',
    ),
    (
        '1.9',
        'Провокации / травля',
        'Запрещено неадекватное поведение в любых его проявлениях, '
        'грубые/косвенные/ завуалированные провокации, а так же травля в '
        'любой форме.',
        ('warn', 'mute'),
        'Предупреждение/Мут',
        'До 2 часов',
    ),
)

RULES_NOTES: tuple[str, ...] = (
    'Доп.: многочисленные нарушения влекут наказание. '
    '3 мута за 48 часов — Варн; 3 варна — Бан.',
    'Примечания: администрация может изменить правила, отступать от норм '
    'и блокировать проблемных пользователей. Подключаясь к серверу, '
    'вы принимаете правила.',
    'Жалобы: /report — нужны доказательства (скрин/видео).',
)

STAFF_HINTS: dict[str, str] = {
    code: f'{punish} · {duration}'
    for code, _t, _x, _a, punish, duration in MODPANEL_REASONS
}

_BY_CODE = {code: text for code, _title, text, *_rest in MODPANEL_REASONS}
_TITLE_BY_CODE = {code: title for code, title, *_rest in MODPANEL_REASONS}
_ROW_BY_CODE = {row[0]: row for row in MODPANEL_REASONS}


def codes() -> list[str]:
    return [c for c, *_ in MODPANEL_REASONS]


def title_for(code: str) -> str:
    return _TITLE_BY_CODE.get(str(code or '').strip(), '')


def text_for(code: str) -> str:
    return _BY_CODE.get(str(code or '').strip(), '')


def is_known(code: str) -> bool:
    return str(code or '').strip() in _BY_CODE


def punish_key_for_action(action: str) -> str:
    """warn|mute|ban или '' если действие без селекта правил."""
    return _ACTION_PUNISH.get(str(action or '').strip(), '')


def allows(code: str, action: str) -> bool:
    """Можно ли выдать action по правилу code."""
    key = punish_key_for_action(action)
    if not key:
        return False
    row = _ROW_BY_CODE.get(str(code or '').strip())
    if not row:
        return False
    return key in row[3]


def codes_for_action(action: str) -> list[str]:
    key = punish_key_for_action(action)
    if not key:
        return []
    return [c for c, _t, _x, actions, *_ in MODPANEL_REASONS if key in actions]


def format_reason(code: str) -> str:
    """Строка для дела/лога: «1.9 — <текст запрета>»."""
    code = str(code or '').strip()
    text = text_for(code)
    if not text:
        return code or 'Не указана'
    return f'{code} — {text}'


def select_label(code: str, limit: int = 100) -> str:
    code = str(code or '').strip()
    title = title_for(code)
    label = f'{code} · {title}' if title else code
    if len(label) <= limit:
        return label
    return label[: max(0, limit - 1)].rstrip() + '…'


def _clip(text: str, limit: int = 100) -> str:
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + '…'


def select_description(code: str, limit: int = 100) -> str:
    """Описание option: наказание · срок · текст запрета (≤100)."""
    row = _ROW_BY_CODE.get(str(code or '').strip())
    if not row:
        return ''
    _c, _title, text, _acts, punish, duration = row
    head = f'{punish} · {duration}'
    return _clip(f'{head}. {text}', limit)


def _option_dict(code: str, title: str, text: str, actions: Iterable[str],
                 punish: str, duration: str) -> dict:
    return {
        'value': code,
        'label': select_label(code),
        'description': select_description(code),
        'title': title,
        'text': text,
        'actions': list(actions),
        'punish': punish,
        'duration': duration,
    }


def select_options_data(action: str | None = None) -> list[dict]:
    """Опции селекта. action=warn|ban|timeout|… — только подходящие правила."""
    key = punish_key_for_action(action) if action else ''
    out = []
    for code, title, text, actions, punish, duration in MODPANEL_REASONS:
        if key and key not in actions:
            continue
        out.append(_option_dict(code, title, text, actions, punish, duration))
    return out


def rules_for_channel() -> list[dict]:
    """Правила + примечания для публикации в канал правил (panel)."""
    items = []
    for c, title, text, actions, punish, duration in MODPANEL_REASONS:
        items.append({
            'code': c,
            'title': title,
            't': text,
            'punish': punish,
            'duration': duration,
            'actions': list(actions),
        })
    for note in RULES_NOTES:
        items.append({'code': '', 'title': '', 't': note})
    return items


def resolve_stored_reason(raw: str) -> str:
    """Из кода или уже готовой строки — каноничный текст дела."""
    raw = (raw or '').strip()
    if not raw:
        return 'Не указана'
    head = raw.split('—', 1)[0].strip()
    if is_known(head):
        return format_reason(head)
    if is_known(raw):
        return format_reason(raw)
    return raw
