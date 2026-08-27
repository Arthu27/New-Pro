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
ROUTE_SPECS = [
    {
        'key': 'ban_appeal_channel',
        'label': 'Канал апелляции (бан)',
        'icon': 'fa-user-lock',
        'kind': 'native',
        'access': 'Админ',
        'what': 'Куда попадает участник после «бана» из /modpanel: с сервера '
                'его не выкидывает — все каналы закрываются, открыт только '
                'этот. Разговор с модераторами идёт здесь.',
        'empty': 'Не задан — «бан» из панели не работает, пока канал не выбран '
                 '(создай канал сам и выбери его здесь).',
    },
    {
        'key': 'proof_channel',
        'label': 'Канал доказательств',
        'icon': 'fa-folder-open',
        'kind': 'native',
        'access': 'Админ',
        'what': 'Сюда падают «демки» к наказаниям (/proof): кто, кого, за что — '
                'и само фото/видео прямо в сообщении.',
        'empty': 'Не задан — бот сам создаст #-доказательства в категории «Логи».',
    },
    {
        'key': 'appeals_channel',
        'label': 'Канал апелляций',
        'icon': 'fa-scale-balanced',
        'kind': 'appeals',
        'access': 'Админ',
        'what': 'Карточки апелляций на разбан с кнопками «Принять / Отклонить».',
        'empty': 'Не задан — карточки идут в системный канал сервера.',
    },
    {
        'key': 'welcome_channel',
        'label': 'Канал приветствий',
        'icon': 'fa-hand-sparkles',
        'kind': 'welcome',
        'access': 'Админ',
        'what': 'Приветственные карточки новых участников (welcome PRO).',
        'empty': 'Не задан — приветствия уходят в системный канал.',
    },
    {
        'key': 'tagjail_channel',
        'label': 'Лог Tag Jail',
        'icon': 'fa-lock',
        'kind': 'tagjail',
        'access': 'Админ',
        'what': 'Кто и за какой тег улетел в джейл, авто-освобождения, обходы.',
        'empty': 'Не задан — логи джейла не пишутся (остальное работает).',
    },
    {
        'key': 'guardian_channel',
        'label': 'Тревоги Щита сервера',
        'icon': 'fa-shield-heart',
        'kind': 'native',
        'access': 'Админ',
        'what': 'Анти-нюк (страница «Щит сервера»): кто что снёс, кому что выдал, '
                'какая мера применена — каждая остановленная атака прилетает сюда.',
        'empty': 'Не задан — тревоги уходят в -модерация (авто).',
    },
    {
        'key': 'antiraid_channel',
        'label': 'Алерты анти-рейда',
        'icon': 'fa-shield-virus',
        'kind': 'antiraid',
        'access': 'Админ',
        'what': 'Волны заходов, подозрительные новички, рейд-флаги '
                '(та же настройка, что на странице «Анти-рейд»).',
        'empty': 'Не задан — алерты уходят в стандартный лог-канал.',
    },
    {
        'key': 'security_channel',
        'label': 'Лог авто-защиты',
        'icon': 'fa-user-secret',
        'kind': 'security',
        'access': 'Админ',
        'what': 'Центр безопасности: вредоносные ссылки, спам-сигналы, '
                'фейковые аккаунты (та же настройка, что на странице «Центр безопасности»).',
        'empty': 'Не задан — авто-защита пишет в -модерация (авто).',
    },
    {
        'key': 'anticrash_channel',
        'label': 'Сводки анти-краша',
        'icon': 'fa-life-ring',
        'kind': 'anticrash',
        'access': 'Админ',
        'what': 'Критические сводки об ошибках и зависаниях самого бота '
                '(та же настройка, что на странице «Анти-краш» — ID канала там).',
        'empty': 'Не задан — сводки остаются на странице «Анти-краш».',
    },
    {
        'key': 'counting_channel',
        'label': 'Канал считалки',
        'icon': 'fa-list-ol',
        'kind': 'counting',
        'access': 'Админ',
        'what': 'Игра «Счёт»: участники по очереди пишут числа '
                '(дублирует кнопку канала на странице «Счёт»).',
        'empty': 'Не задан — считалка выключена, задаётся командой в нужном канале.',
    },
    {
        'key': 'starboard_channel',
        'label': 'Канал Starboard',
        'icon': 'fa-star',
        'kind': 'starboard',
        'access': 'Админ',
        'what': 'Доска славы: сообщения, набравшие нужные реакции '
                '(та же настройка, что на странице «Starboard»).',
        'empty': 'Не задан — дублирование лучших сообщений выключено.',
    },
    {
        'key': 'night_report_channel',
        'label': 'Ночная сводка',
        'icon': 'fa-moon',
        'kind': 'night_summary',
        'access': 'Админ',
        'what': 'Ежедневный дайджест активности ночной смены '
                '(страница «Автоматика» дублирует эту настройку).',
        'empty': 'Не задан — сводка не шлётся.',
    },
    {
        'key': 'mod_digest_channel',
        'label': 'Сводка модерации',
        'icon': 'fa-chart-simple',
        'kind': 'mod_digest',
        'access': 'Админ',
        'what': 'Ежедневная сводка по наказаниям, варнам и тикетам команды '
                '(дублируется на странице «Автоматика»).',
        'empty': 'Не задан — сводка модерации выключена.',
    },
    {
        'key': 'shifts_channel',
        'label': 'Дежурства персонала',
        'icon': 'fa-user-clock',
        'kind': 'staff_shifts',
        'access': 'Админ',
        'what': 'Напоминания о начале смен дежурных '
                '(та же настройка, что на странице «Смены персонала»).',
        'empty': 'Не задан — напоминания о сменах не уходят.',
    },
    {
        'key': 'staff_helper_channel',
        'label': 'Ветка заявок хелперов',
        'icon': 'fa-hands-helping',
        'kind': 'staff_apply',
        'access': 'Админ',
        'what': 'Заявки на должность хелпера уходят в этот канал — их смотрят '
                'кураторы хелперов (роль-пинг настраивается ниже, в «Ролях»).',
        'empty': 'Не задан — заявки хелперов идут в общий канал заявок.',
    },
    {
        'key': 'staff_moderator_channel',
        'label': 'Ветка заявок модераторов',
        'icon': 'fa-shield-halved',
        'kind': 'staff_apply',
        'access': 'Админ',
        'what': 'Заявки на модератора — в этот канал, смотрят кураторы '
                'модераторов.',
        'empty': 'Не задан — заявки модераторов идут в общий канал заявок.',
    },
    {
        'key': 'staff_apply_channel',
        'label': 'Общий канал заявок',
        'icon': 'fa-file-signature',
        'kind': 'staff_apply',
        'access': 'Админ',
        'what': 'Запасной канал: сюда падают заявки, для которых своя ветка '
                'не задана (заменяет APPLY_CHANNEL_ID из .env).',
        'empty': 'Не задан — уведомления о заявках не отправляются.',
    },
    {
        'key': 'ticket_notify_channel',
        'label': 'Призыв модераторов',
        'icon': 'fa-ticket-alt',
        'kind': 'ticket_notify',
        'access': 'Админ',
        'what': 'Куда летит призыв команды при новом тикете '
                '(дублируется в настройках тикетов).',
        'empty': 'Не задан — призывы не рассылаются.',
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
