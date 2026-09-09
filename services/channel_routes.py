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

# Каналы боевого сервера (владелец 2026-09-06). Бот сам их не создаёт:
# если на сервере есть такой канал — используем, иначе молчим.
# Карточки апелляций / репорты — канал модеров.
# Комната после бана — отдельный канал, туда карточки НЕ идут.
MODS_CHANNEL_ID = 1312434963941167134
BAN_APPEAL_ROOM_ID = 1544483947705008188
# Оценка рассмотрения апелляции (владелец 2026-09-06). Не выдуман.
APPEAL_RATING_CHANNEL_ID = 1518751543329951904
KNOWN_CHANNELS = {
    'appeals_channel': MODS_CHANNEL_ID,
    'report_channel': MODS_CHANNEL_ID,
    'ban_appeal_channel': BAN_APPEAL_ROOM_ID,
    'meeting_channel': 0,
    'meeting_helper_channel': 0,
    'meeting_mod_channel': 0,
}

# Имя-подсказка для комнаты апелляций в стиле сервера («эмодзи・слово»).
# Маршрут работает по ID — имя нужно только в текстах-подсказках панели.
APPEALS_ROOM_HINT = '⚖・апелляции'

# Спецификация маршрутов (панель строит из неё страницу настроек).
# kind: 'native' — канал живёт в этом файле; остальные — адаптеры к конфигам
# других систем (их редактирует панель через их же хранилища).
# Порядок настройки для владельца (три уровня):
#   required=True, step=1 — ЕДИНСТВЕННОЕ, что надо задать, чтобы не было
#     ошибок: канал апелляции после бана (без него «бан» из /modpanel не
#     работает и прямо об этом просит).
#   step = 2..N, required=False — «по желанию, можно потом»: у каждого есть
#     разумный фоллбэк по умолчанию (бот создаст канал сам / пишет в логи /
#     системный канал), ничего не сломается, если не настраивать.
#   step = None — дополнительное (меню апелляций, PagerDuty, отдельные ветки
#     заявок, анти-рейд/анти-краш) — трогать не нужно, работает по умолчанию.
# create_hint — нужно ли заводить отдельный канал: почти везде можно выбрать
#   уже существующий (🛡・модерация, один #⚖・апелляции и т.п.).
ROUTE_SPECS = [
    {
        'key': 'ban_appeal_channel',
        'label': 'Комната апелляции (для забаненного)',
        'icon': 'fa-user-lock',
        'kind': 'native',
        'access': 'Админ',
        'step': 1,
        'required': True,
        'create_hint': 'Отдельная комната для человека после бана — сюда же идут заявки в команду.',
        'what': 'Единая комната «всё сюда, кроме логов» (владелец '
                '2026-09-06): карточки апелляций с кнопками, заявки в '
                'команду с тегом куратора. Забаненный видит её ПОСЛЕ '
                'подачи апелляции — в момент бана она закрыта.',
        'empty': 'Не задан — при «бане» из /modpanel бот попросит выбрать канал. На боевом сервере комната уже есть.',
    },
    {
        'key': 'report_channel',
        'label': 'Канал вызовов модератора (/report)',
        'icon': 'fa-bullhorn',
        'kind': 'native',
        'access': 'Админ',
        'step': 2,
        'required': False,
        'create_hint': 'Уже работает: по умолчанию вызовы идут в канал репортов (1312434963941167134). Здесь можно указать другой.',
        'what': 'Сюда падают вызовы модератора (/report): кто кого вызвал, за что, голосовой канал вызывавшего — разбирает модерация.',
        'empty': 'Не задан — вызовы идут в канал репортов по умолчанию (1312434963941167134), затем в #🛡・модерация.',
    },
    {
        'key': 'proof_channel',
        'label': 'Канал доказательств',
        'icon': 'fa-folder-open',
        'kind': 'native',
        'access': 'Админ',
        'step': 3,
        'required': False,
        'create_hint': 'Можно не настраивать: не выберешь — бот сам создаст #📸・доказательства в категории «Логи».',
        'what': 'Сюда падают «демки» к наказаниям (/report, /warn, /moderate и панель): кто, кого, за что — '
                'и само фото/видео прямо в сообщении.',
        'empty': 'Не задан — бот сам создаст #📸・доказательства в категории «Логи».',
    },
    {
        'key': 'appeals_channel',
        'label': 'Карточки апелляций (запасной канал)',
        'icon': 'fa-scale-balanced',
        'kind': 'native',
        'access': 'Админ',
        'step': 4,
        'required': False,
        'create_hint': 'Запасной канал карточек: используется, только если комната апелляции не задана.',
        'what': 'Карточки апелляций живут в самой комнате апелляции — «всё сюда, '
                'кроме логов» (владелец 2026-09-06). Этот канал — запасной: если '
                'комнаты нет, заявки падают сюда, каждая в своей ветке.',
        'empty': 'Не задан — карточки идут в комнату апелляции.',
    },
    {
        'key': 'guardian_channel',
        'hidden_from_hub': True,  # дублирует категорию логов в «Логи сервера» (/log-settings) — в хабе не показываем
        'label': 'Тревоги Щита сервера (анти-нюк)',
        'icon': 'fa-shield-heart',
        'kind': 'native',
        'access': 'Админ',
        'step': 5,
        'required': False,
        'create_hint': 'Настраивать не обязательно: тревоги и так уходят в лог-канал 🛡・модерация (бот создаёт сам). Можно указать тот же лог-канал.',
        'what': 'Анти-нюк (страница «Щит сервера»): кто что снёс, кому что выдал, '
                'какая мера применена — каждая остановленная атака прилетает сюда.',
        'empty': 'Не задан — тревоги уходят в 🛡・модерация (авто).',
    },
    {
        'key': 'security_channel',
        'hidden_from_hub': True,  # дублирует категорию логов в «Логи сервера» (/log-settings) — в хабе не показываем
        'label': 'Лог авто-защиты (ссылки/спам/фейки)',
        'icon': 'fa-user-secret',
        'kind': 'security',
        'access': 'Админ',
        'step': 6,
        'required': False,
        'create_hint': 'Настраивать не обязательно: авто-защита пишет в лог-канал 🛡・модерация сама.',
        'what': 'Центр безопасности: вредоносные ссылки, спам-сигналы, '
                'фейковые аккаунты (та же настройка, что на странице «Центр безопасности»).',
        'empty': 'Не задан — авто-защита пишет в 🛡・модерация (авто).',
    },
    {
        'key': 'welcome_channel',
        'label': 'Канал приветствий',
        'icon': 'fa-hand-sparkles',
        'kind': 'welcome',
        'access': 'Админ',
        'step': 7,
        'required': False,
        'create_hint': 'Не обязательно: не укажешь — приветствия уходят в системный канал. Обычно это общий чат новичков.',
        'what': 'Приветственные карточки новых участников (welcome PRO).',
        'empty': 'Не задан — приветствия уходят в системный канал.',
    },
    {
        'key': 'staff_apply_channel',
        'label': 'Канал заявок в команду',
        'icon': 'fa-file-signature',
        'kind': 'staff_apply',
        'access': 'Админ',
        'step': 8,
        'required': False,
        'create_hint': 'Нужен, только если открываешь набор в команду. Один канал на все заявки (хелперы и модераторы).',
        'what': 'Сюда падают заявки в команду (заменяет APPLY_CHANNEL_ID из .env). '
                'Если ниже не заданы отдельные ветки — и хелперы, и модераторы идут сюда.',
        'empty': 'Не задан — уведомления о заявках не отправляются (понадобится, только когда открываешь набор).',
    },
    # ── Дополнительное (трогать не нужно — работает по умолчанию) ──
    {
        'key': 'appeal_menu_channel',
        'label': 'Канал меню апелляций',
        'icon': 'fa-scale-balanced',
        'kind': 'native',
        'access': 'Админ',
        'step': None,
        'required': False,
        'create_hint': 'Дополнительно: постоянная кнопка-меню «Подать апелляцию». Можно оставить как есть.',
        'what': 'Постоянное меню «Подать апелляцию» (select + окно). Участник '
                'выбирает в канале — апелляция создаётся тредом, без личных '
                'сообщений боту.',
        'empty': 'Не задан — меню можно опубликовать из «Настроек модерации».',
    },
    {
        'key': 'antiraid_channel',
        'hidden_from_hub': True,  # дублирует категорию логов в «Логи сервера» (/log-settings) — в хабе не показываем
        'label': 'Алерты анти-рейда',
        'icon': 'fa-shield-virus',
        'kind': 'antiraid',
        'access': 'Админ',
        'step': None,
        'required': False,
        'create_hint': 'Дополнительно: алерты и так уходят в стандартный лог-канал.',
        'what': 'Волны заходов, подозрительные новички, рейд-флаги '
                '(та же настройка, что на странице «Анти-рейд»).',
        'empty': 'Не задан — алерты уходят в стандартный лог-канал.',
    },
    {
        'key': 'anticrash_channel',
        'hidden_from_hub': True,  # дублирует категорию логов в «Логи сервера» (/log-settings) — в хабе не показываем
        'label': 'Сводки анти-краша',
        'icon': 'fa-life-ring',
        'kind': 'anticrash',
        'access': 'Админ',
        'step': None,
        'required': False,
        'create_hint': 'Дополнительно: для продвинутых, сводки видно на странице «Анти-краш».',
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
        'required': False,
        'create_hint': 'Дополнительно: только если подключён PagerDuty.',
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
        'required': False,
        'create_hint': 'Запасная ветка: используется, только если комнаты заявок нет на сервере.',
        'what': 'Заявки в команду идут в единую комнату заявок и апелляций '
                '(владелец 2026-09-06). Эта ветка — запасная: комнату '
                'убрали — заявки хелперов падают сюда.',
        'empty': 'Не задан — заявки идут в комнату заявок.',
    },
    {
        'key': 'staff_moderator_channel',
        'label': 'Ветка заявок модераторов (отдельно)',
        'icon': 'fa-shield-halved',
        'kind': 'staff_apply',
        'access': 'Админ',
        'step': None,
        'required': False,
        'create_hint': 'Запасная ветка: используется, только если комнаты заявок нет на сервере.',
        'what': 'Заявки в команду идут в единую комнату заявок и апелляций '
                '(владелец 2026-09-06). Эта ветка — запасная: комнату '
                'убрали — заявки модераторов падают сюда.',
        'empty': 'Не задан — заявки идут в комнату заявок.',
    },
    # ── Собрания стаффа (2026-09-09) ──
    {
        'key': 'meeting_channel',
        'label': 'Канал собраний (общий)',
        'icon': 'fa-users',
        'kind': 'native',
        'access': 'Админ',
        'step': 9,
        'required': False,
        'create_hint': 'Общий канал для всех собраний стаффа — сюда падают карточки собраний. Скинь ID канала сюда.',
        'what': 'Собрания стаффа: общие, модерские и хелперские. Карточка собрания с кнопками «Буду / Не буду» и таблицей явки. Бот сам шлёт таблицу без команды.',
        'empty': 'Не задан — собрания некуда постить, бот попросит выбрать канал.',
    },
    {
        'key': 'meeting_helper_channel',
        'label': 'Канал собраний хелперов',
        'icon': 'fa-hands-helping',
        'kind': 'native',
        'access': 'Админ',
        'step': 10,
        'required': False,
        'create_hint': 'Отдельный канал для хелперских собраний. Если не задан — используется общий канал собраний.',
        'what': 'Собрания только для хелперов (роль 948969471916249119). Пинг роли хелперов + ЛС всем хелперам.',
        'empty': 'Не задан — хелперские собрания идут в общий канал собраний.',
    },
    {
        'key': 'meeting_mod_channel',
        'label': 'Канал собраний модеров',
        'icon': 'fa-shield-halved',
        'kind': 'native',
        'access': 'Админ',
        'step': 11,
        'required': False,
        'create_hint': 'Отдельный канал для модерских собраний. Если не задан — используется общий канал.',
        'what': 'Собрания только для модераторов. Пинг роли модеров + ЛС всем модерам.',
        'empty': 'Не задан — модерские собрания идут в общий канал собраний.',
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


def channel_on_guild(guild, cid):
    """Канал/ветка по ID, если он реально есть на этом сервере."""
    if not cid or guild is None:
        return None
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    fn = getattr(guild, 'get_channel_or_thread', None)
    if callable(fn):
        ch = fn(cid)
        if ch is not None:
            return ch
    ch = guild.get_channel(cid) if hasattr(guild, 'get_channel') else None
    if ch is not None:
        return ch
    getter = getattr(guild, 'get_thread', None)
    return getter(cid) if callable(getter) else None


def resolve_route(gid, key, guild=None):
    """ID маршрута: сохранённый в панели, иначе известный канал если он есть.

    Известные ID (канал модеров / комната апелляции) подставляются ТОЛЬКО
    когда такой канал реально есть на guild. На тестовых гильдиях без этих
    комнат остаётся 0 — бан по-прежнему требует явной настройки.
    """
    stored = get_route(gid, key)
    if stored:
        return stored
    guess = int(KNOWN_CHANNELS.get(key) or 0)
    if not guess:
        return 0
    if guild is not None and channel_on_guild(guild, guess) is not None:
        return guess
    return 0


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
