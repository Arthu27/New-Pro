# -*- coding: utf-8 -*-
"""Каналы и маршруты: единое место, куда бот что пишет.

Хранилище data/channel_routes.json:
    { "<guild_id>": {"proof_channel": 123, ...}, ... }

Читают и бот (cogs/proof_cog.py), и панель (web/routes/channel_settings.py) —
одна правда, без рассинхрона. Другие системы (апелляции, приветствия,
tag jail) хранят каналы в своих конфигах — панель редактирует их через
свои адаптеры, а этот модуль — для новых маршрутов Hakumo.
"""
import json
import os

from logger import get_logger

log = get_logger('channel_routes')

ROUTES_FILE = 'data/channel_routes.json'

# Спецификация маршрутов (панель строит из неё страницу настроек).
# kind: 'native' — канал живёт в этом файле; остальные — адаптеры к конфигам
# других систем (их редактирует панель через их же хранилища).
# Порядок настройки для владельца:
#   step = 1..N  — «со старта» (нужно для боевой работы), настраивать по порядку;
#   step = None  — необязательное (можно оставить «Авто» и вернуться потом).
# create_hint — нужно ли заводить отдельный канал: False = можно выбрать
#   уже существующий (лог-модерация, заявки и т.п.), отдельный не обязателен.
ROUTE_SPECS = [
    {
        'key': 'proof_channel',
        'label': 'Канал доказательств',
        'icon': 'fa-folder-open',
        'kind': 'native',
        'access': 'Админ',
        'step': 1,
        'create_hint': 'Можно выбрать существующий канал для демок; отдельный не обязателен — не выберешь, бот создаст #-доказательства сам.',
        'what': 'Сюда падают «демки» к наказаниям (/proof): кто, кого, за что — '
                'и само фото/видео прямо в сообщении. Без этого канала наказания '
                'с доказательством не выдаются.',
        'empty': 'Не задан — бот сам создаст #-доказательства в категории «Логи».',
    },
    {
        'key': 'guardian_channel',
        'label': 'Тревоги Щита сервера (анти-нюк)',
        'icon': 'fa-shield-heart',
        'kind': 'native',
        'access': 'Админ',
        'step': 2,
        'create_hint': 'Отдельный канал не нужен — выбери существующий лог-канал модерации, тревоги защиты летят туда же.',
        'what': 'Анти-нюк (страница «Щит сервера»): кто что снёс, кому что выдал, '
                'какая мера применена — каждая остановленная атака прилетает сюда.',
        'empty': 'Не задан — тревоги уходят в -модерация (авто).',
    },
    {
        'key': 'security_channel',
        'label': 'Лог авто-защиты (ссылки/спам/фейки)',
        'icon': 'fa-user-secret',
        'kind': 'security',
        'access': 'Админ',
        'step': 3,
        'create_hint': 'Отдельный канал не нужен — тот же лог-канал модерации.',
        'what': 'Центр безопасности: вредоносные ссылки, спам-сигналы, '
                'фейковые аккаунты (та же настройка, что на странице «Центр безопасности»).',
        'empty': 'Не задан — авто-защита пишет в -модерация (авто).',
    },
    {
        'key': 'ban_appeal_channel',
        'label': 'Канал апелляции после бана',
        'icon': 'fa-user-lock',
        'kind': 'native',
        'access': 'Админ',
        'step': 4,
        'create_hint': 'Заведи ОДИН канал для разбора наказаний (например #апелляции) — и «бан», и апелляции ведут сюда, плодить отдельные не надо.',
        'what': 'Куда попадает участник после «бана» из /modpanel: с сервера '
                'его не выкидывает — все каналы закрываются, открыт только '
                'этот. Разговор с модераторами идёт здесь.',
        'empty': 'Не задан — «бан» из панели не работает, пока канал не выбран.',
    },
    {
        'key': 'appeals_channel',
        'label': 'Канал апелляций (карточки на разбан)',
        'icon': 'fa-scale-balanced',
        'kind': 'appeals',
        'access': 'Админ',
        'step': 5,
        'create_hint': 'Можно выбрать тот же канал апелляций, что и выше, — отдельный не нужен.',
        'what': 'Карточки апелляций на разбан с кнопками «Принять / Отклонить». '
                'Обычно это тот же канал, что и «апелляция после бана».',
        'empty': 'Не задан — карточки идут в системный канал сервера.',
    },
    {
        'key': 'staff_apply_channel',
        'label': 'Канал заявок в команду',
        'icon': 'fa-file-signature',
        'kind': 'staff_apply',
        'access': 'Админ',
        'step': 6,
        'create_hint': 'Один канал на все заявки (хелперы и модераторы) — отдельные ветки ниже не обязательны.',
        'what': 'Сюда падают заявки в команду (заменяет APPLY_CHANNEL_ID из .env). '
                'Если ниже не заданы отдельные ветки — и хелперы, и модераторы идут сюда.',
        'empty': 'Не задан — уведомления о заявках не отправляются.',
    },
    {
        'key': 'welcome_channel',
        'label': 'Канал приветствий',
        'icon': 'fa-hand-sparkles',
        'kind': 'welcome',
        'access': 'Админ',
        'step': 7,
        'create_hint': 'Обычно это общий канал чата/новичков — отдельный не нужен.',
        'what': 'Приветственные карточки новых участников (welcome PRO).',
        'empty': 'Не задан — приветствия уходят в системный канал.',
    },
    # ── Необязательное (можно оставить «Авто» и настроить потом) ──
    {
        'key': 'appeal_menu_channel',
        'label': 'Канал меню апелляций',
        'icon': 'fa-scale-balanced',
        'kind': 'native',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: это постоянная кнопка-меню «Подать апелляцию». Можно оставить как есть.',
        'what': 'Постоянное меню «Подать апелляцию» (select + окно). Участник '
                'выбирает в канале — апелляция создаётся тредом, без личных '
                'сообщений боту.',
        'empty': 'Не задан — меню можно опубликовать из «Настроек модерации».',
    },
    {
        'key': 'antiraid_channel',
        'label': 'Алерты анти-рейда',
        'icon': 'fa-shield-virus',
        'kind': 'antiraid',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: алерты и так уходят в лог-канал.',
        'what': 'Волны заходов, подозрительные новички, рейд-флаги '
                '(та же настройка, что на странице «Анти-рейд»).',
        'empty': 'Не задан — алерты уходят в стандартный лог-канал.',
    },
    {
        'key': 'anticrash_channel',
        'label': 'Сводки анти-краша',
        'icon': 'fa-life-ring',
        'kind': 'anticrash',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: для продвинутых, сводки видно на странице «Анти-краш».',
        'what': 'Критические сводки об ошибках и зависаниях самого бота '
                '(та же настройка, что на странице «Анти-краш» — ID канала там).',
        'empty': 'Не задан — сводки остаются на странице «Анти-краш».',
    },
    {
        'key': 'pagerduty_channel',
        'label': 'Канал тревог PagerDuty',
        'icon': 'fa-tower-broadcast',
        'kind': 'native',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: только если подключён PagerDuty.',
        'what': 'Карточки инцидентов PagerDuty (тревога / принято / решено) '
                'с цветом и ссылкой на инцидент. Сам мост включается на '
                'странице «PagerDuty» в настройках панели.',
        'empty': 'Не задан — тревоги PagerDuty некуда постить (мост молчит).',
    },
    {
        'key': 'staff_helper_channel',
        'label': 'Ветка заявок хелперов (отдельно)',
        'icon': 'fa-hands-helping',
        'kind': 'staff_apply',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: если не задать — заявки хелперов идут в общий канал заявок.',
        'what': 'Заявки на должность хелпера уходят в этот канал — их смотрят '
                'кураторы хелперов (роль-пинг настраивается в «Настройки → Бот»).',
        'empty': 'Не задан — заявки хелперов идут в общий канал заявок.',
    },
    {
        'key': 'staff_moderator_channel',
        'label': 'Ветка заявок модераторов (отдельно)',
        'icon': 'fa-shield-halved',
        'kind': 'staff_apply',
        'access': 'Админ',
        'step': None,
        'create_hint': 'Необязательно: если не задать — заявки модераторов идут в общий канал заявок.',
        'what': 'Заявки на модератора — в этот канал, смотрят кураторы модераторов.',
        'empty': 'Не задан — заявки модераторов идут в общий канал заявок.',
    },
]


def _load():
    try:
        with open(ROUTES_FILE, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(ROUTES_FILE), exist_ok=True)
    tmp = ROUTES_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, ROUTES_FILE)


def spec_for(key):
    for spec in ROUTE_SPECS:
        if spec['key'] == key:
            return spec
    return None


def native_keys():
    return [s['key'] for s in ROUTE_SPECS if s.get('kind') == 'native']


def get_route(gid, key):
    """ID канала маршрута (0 — не задан). Только native-маршруты."""
    if key not in native_keys():
        return 0
    try:
        return int((_load().get(str(gid)) or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def set_route(gid, key, channel_id):
    """Записать маршрут (0 = очистить). Возвращает True при успехе."""
    if key not in native_keys():
        return False
    data = _load()
    row = data.setdefault(str(gid), {})
    try:
        row[key] = int(channel_id or 0)
    except (TypeError, ValueError):
        return False
    _save(data)
    return True


def all_routes(gid):
    """Все native-маршруты сервера одним словарём {key: channel_id}."""
    row = _load().get(str(gid)) or {}
    out = {}
    for key in native_keys():
        try:
            out[key] = int(row.get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out
