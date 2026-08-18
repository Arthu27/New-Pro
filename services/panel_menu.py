"""Panel menu visibility — which sidebar categories (groups) and rooms (pages)
are shown for each panel role (mod / admin / owner).

- owner always sees everything.
- mod / admin visibility is stored in data/panel_menu.json.
- member (uye) panel is managed separately by the user later.

Moderation section metadata (section / tone / access) is used by the sidebar
sub-groups and by the moderation pages themselves (badges, colors).
"""

from logger import get_logger

_log = get_logger("panel_menu")

import os
import json

_PATH = 'data/panel_menu.json'

# The full sidebar menu: groups -> items (pages). Order matters (top -> bottom).
MENU = [
    {'group': 'Основное', 'key': 'main', 'icon': 'fa-house', 'pages': [
        {'path': '/', 'label': 'Обзор сервера', 'icon': 'fa-home'},
        {'path': '/guilds', 'label': 'Серверы', 'icon': 'fa-server'},
        {'path': '/analytics', 'label': 'Аналитика', 'icon': 'fa-chart-line'},
        {'path': '/advanced-analytics', 'label': 'Про-аналитика', 'icon': 'fa-chart-pie'},
        {'path': '/bot-stats', 'label': 'Статистика бота', 'icon': 'fa-robot'},
        {'path': '/server-health', 'label': 'Состояние', 'icon': 'fa-heartbeat'},
        {'path': '/ops-center', 'label': 'Оперативный центр', 'icon': 'fa-gauge-high'},
        {'path': '/recap', 'label': 'Рекап канала', 'icon': 'fa-clock-rotate-left'},
    ]},
    {'group': 'Модерация', 'key': 'mod', 'icon': 'fa-shield-halved', 'pages': [
        # Реагирование: от мягкой меры к аварийному сценарию.
        {'path': '/warnings', 'label': 'Варны', 'icon': 'fa-triangle-exclamation',
         'section': 'response', 'description': 'Предупреждения, причины и история участника',
         'access': 'Мод+', 'tone': 'warning'},
        {'path': '/temp-moderation', 'label': 'Временные меры', 'icon': 'fa-clock',
         'section': 'response', 'description': 'Мьюты и баны с автоматическим снятием',
         'access': 'Мод+', 'tone': 'warning'},
        {'path': '/mod-tools', 'label': 'Инструменты', 'icon': 'fa-thumbtack',
         'section': 'response', 'description': 'Sticky-сообщения, panic и быстрые действия',
         'access': 'Мод+', 'tone': 'warning'},
        {'path': '/bulk-actions', 'label': 'Массовые операции', 'icon': 'fa-layer-group',
         'section': 'response', 'description': 'Пакетные роли, сообщения и действия с участниками',
         'access': 'Админ', 'min_role': 'admin', 'tone': 'critical'},
        {'path': '/lockdown', 'label': 'Локдаун', 'icon': 'fa-house-lock',
         'section': 'response', 'description': 'Экстренное закрытие каналов и контролируемый откат',
         'access': 'Мод+', 'tone': 'critical'},
        {'path': '/tagjail', 'label': 'Tag Jail', 'icon': 'fa-lock',
         'section': 'response', 'description': 'Изоляция опасных тегов и возврат ролей',
         'access': 'Админ', 'min_role': 'admin', 'tone': 'critical'},

        # Расследование: факты, доказательства и пересмотр решений.
        {'path': '/logs', 'label': 'Журнал модерации', 'icon': 'fa-clipboard-list',
         'section': 'investigation', 'description': 'Лента действий с фильтрами и экспортом',
         'access': 'Мод+', 'tone': 'info'},
        {'path': '/mod-history', 'label': 'История решений', 'icon': 'fa-clock-rotate-left',
         'section': 'investigation', 'description': 'Хронология наказаний и решений команды',
         'access': 'Мод+', 'tone': 'info'},
        {'path': '/proofs', 'label': 'Доказательства', 'icon': 'fa-folder-open',
         'section': 'investigation', 'description': 'Скриншоты, видео и привязка к наказаниям',
         'access': 'Мод+', 'tone': 'info'},
        {'path': '/appeals', 'label': 'Апелляции', 'icon': 'fa-scale-balanced',
         'section': 'investigation', 'description': 'Очередь пересмотра наказаний и вердикты',
         'access': 'Мод+', 'tone': 'info'},

        # Защита: превентивные политики безопасности.
        {'path': '/security', 'label': 'Центр безопасности', 'icon': 'fa-shield-halved',
         'section': 'protection', 'description': 'Сводный риск, политики и готовность защиты',
         'access': 'Мод+', 'tone': 'security'},
        {'path': '/autofilter', 'label': 'Автофильтр', 'icon': 'fa-filter',
         'section': 'protection', 'description': 'Слова, ссылки, капс, флуд и исключения',
         'access': 'Мод+', 'tone': 'security'},
        {'path': '/antiraid', 'label': 'Анти-рейд', 'icon': 'fa-shield-virus',
         'section': 'protection', 'description': 'Защита от массовых входов и атак',
         'access': 'Админ', 'min_role': 'admin', 'tone': 'security'},
        {'path': '/antifake', 'label': 'Антифейк', 'icon': 'fa-user-secret',
         'section': 'protection', 'description': 'Поиск подделок профилей и impersonation',
         'access': 'Мод+', 'tone': 'security'},

        # Команда и аналитика: качество, нагрузка и эскалация.
        {'path': '/mod-control', 'label': 'Контроль команды', 'icon': 'fa-clipboard-check',
         'section': 'management', 'description': 'Очереди, заметки и контроль исполнения',
         'access': 'Мод+', 'tone': 'analytics'},
        {'path': '/mod-report', 'label': 'Отчёты', 'icon': 'fa-chart-simple',
         'section': 'management', 'description': 'Нагрузка, рецидивисты и выгрузка результатов',
         'access': 'Мод+', 'tone': 'analytics'},
        {'path': '/mod-insights', 'label': 'Аналитика рисков', 'icon': 'fa-user-shield',
         'section': 'management', 'description': 'Причины нарушений, тренды и рекомендации',
         'access': 'Мод+', 'tone': 'analytics'},
        {'path': '/ladder', 'label': 'Лестница наказаний', 'icon': 'fa-stairs',
         'section': 'management', 'description': 'Ступени эскалации и контроль сроков',
         'access': 'Мод+', 'tone': 'analytics'},
    ]},
    {'group': 'Участники', 'key': 'members', 'icon': 'fa-users', 'pages': [
        {'path': '/users', 'label': 'Пользователи', 'icon': 'fa-users'},
        {'path': '/member-card', 'label': 'Карточка 360°', 'icon': 'fa-id-card-clip'},
        {'path': '/member-search', 'label': 'Поиск', 'icon': 'fa-search'},
        {'path': '/member-notes', 'label': 'Заметки', 'icon': 'fa-sticky-note'},
        {'path': '/watchlist-panel', 'label': 'Наблюдение', 'icon': 'fa-eye'},
        {'path': '/invite-tracker', 'label': 'Приглашения', 'icon': 'fa-user-plus'},
        {'path': '/afk-list', 'label': 'AFK список', 'icon': 'fa-moon'},
        {'path': '/rejoin-roles', 'label': 'Re-Join роли', 'icon': 'fa-undo'},
    ]},
    {'group': 'Роли', 'key': 'roles', 'icon': 'fa-user-tag', 'pages': [
        {'path': '/roles', 'label': 'Управление ролями', 'icon': 'fa-user-tag'},
        {'path': '/autorole', 'label': 'Автороли', 'icon': 'fa-id-badge'},
        {'path': '/color-roles', 'label': 'Цветовые роли', 'icon': 'fa-palette'},
        {'path': '/reaction-roles', 'label': 'Роли по реакциям', 'icon': 'fa-smile'},
    ]},
    {'group': 'Доступ', 'key': 'access', 'icon': 'fa-shield-alt', 'pages': [
        {'path': '/panel-access', 'label': 'Доступ к панелям', 'icon': 'fa-user-shield'},
        {'path': '/panel-menu', 'label': 'Доступ к меню', 'icon': 'fa-bars'},
        {'path': '/role-permissions', 'label': 'Доступ к командам', 'icon': 'fa-user-lock'},
    ]},
    {'group': 'Тикеты', 'key': 'tickets', 'icon': 'fa-ticket-alt', 'pages': [
        {'path': '/ai-tickets', 'label': 'AI Тикеты', 'icon': 'fa-ticket-alt'},
        {'path': '/tickets-ops', 'label': 'OPS-центр', 'icon': 'fa-gauge-high'},
        {'path': '/ai_ticket_stats', 'label': 'Статистика', 'icon': 'fa-chart-pie'},
        {'path': '/ticket-search', 'label': 'Поиск тикетов', 'icon': 'fa-magnifying-glass'},
        {'path': '/transcripts', 'label': 'Транскрипты', 'icon': 'fa-file-lines'},
        {'path': '/sla', 'label': 'SLA-контроль', 'icon': 'fa-handshake'},
        {'path': '/ticket-settings', 'label': 'Настройки', 'icon': 'fa-cogs'},
        {'path': '/staff-apps', 'label': 'Заявки', 'icon': 'fa-file-signature'},
    ]},
    {'group': 'Бот', 'key': 'bot', 'icon': 'fa-robot', 'pages': [
        {'path': '/commands', 'label': 'Команды', 'icon': 'fa-terminal'},
        {'path': '/custom-commands', 'label': 'Свои команды', 'icon': 'fa-code'},
        {'path': '/send-command', 'label': 'Отправить', 'icon': 'fa-paper-plane'},
        {'path': '/schedule', 'label': 'Расписание', 'icon': 'fa-calendar-alt'},
        {'path': '/bot-settings', 'label': 'Настройки', 'icon': 'fa-sliders-h'},
        {'path': '/theme-settings', 'label': 'Тема панели', 'icon': 'fa-palette'},
        {'path': '/anticrash', 'label': 'Анти-краш', 'icon': 'fa-life-ring'},
        {'path': '/backups', 'label': 'Бэкапы', 'icon': 'fa-save'},
        {'path': '/templates', 'label': 'Шаблоны', 'icon': 'fa-clone'},
        {'path': '/konsol', 'label': 'Консоль', 'icon': 'fa-terminal'},
        {'path': '/cog-manager', 'label': 'Модули', 'icon': 'fa-cubes'},
        {'path': '/automation', 'label': 'Автоматика', 'icon': 'fa-wand-magic-sparkles'},
        {'path': '/settings', 'label': 'Сервер', 'icon': 'fa-cog'},
        {'path': '/notifications', 'label': 'Уведомления', 'icon': 'fa-bell'},
        {'path': '/rules-editor', 'label': 'Правила', 'icon': 'fa-gavel'},
        {'path': '/welcome-editor', 'label': 'Приветствие', 'icon': 'fa-handshake'},
        {'path': '/warn-config', 'label': 'Варны', 'icon': 'fa-exclamation'},
    ]},
    {'group': 'Сообщество', 'key': 'community', 'icon': 'fa-gamepad', 'pages': [
        {'path': '/economy', 'label': 'Экономика', 'icon': 'fa-coins'},
        {'path': '/shop', 'label': 'Магазин', 'icon': 'fa-store'},
        {'path': '/music', 'label': 'Музыка', 'icon': 'fa-music'},
        {'path': '/achievements', 'label': 'Ачивки', 'icon': 'fa-trophy'},
        {'path': '/duels', 'label': 'Дуэли', 'icon': 'fa-shield-halved'},
        {'path': '/fun', 'label': 'Развлечения', 'icon': 'fa-dice'},
        {'path': '/leveling', 'label': 'Уровни', 'icon': 'fa-star'},
        {'path': '/giveaway', 'label': 'Розыгрыши', 'icon': 'fa-gift'},
        {'path': '/polls', 'label': 'Опросы', 'icon': 'fa-poll-h'},
        {'path': '/suggestions', 'label': 'Предложения', 'icon': 'fa-lightbulb'},
        {'path': '/starboard', 'label': 'Starboard', 'icon': 'fa-star'},
        {'path': '/voice-stats', 'label': 'Голосовая', 'icon': 'fa-microphone'},
        {'path': '/duty-panel-web', 'label': 'Дежурства', 'icon': 'fa-user-clock'},
        {'path': '/quiz', 'label': 'Квиз', 'icon': 'fa-brain'},
        {'path': '/counting', 'label': 'Счёт', 'icon': 'fa-list-ol'},
        {'path': '/crown', 'label': 'Зал корон', 'icon': 'fa-crown'},
        {'path': '/karma', 'label': 'Карма', 'icon': 'fa-hand-holding-heart'},
        {'path': '/birthdays', 'label': 'Дни рождения', 'icon': 'fa-cake-candles'},
        {'path': '/social', 'label': 'События', 'icon': 'fa-calendar-days'},
        {'path': '/anime-daily', 'label': 'Аниме дня', 'icon': 'fa-tv'},
        {'path': '/tops', 'label': 'Топ сервера', 'icon': 'fa-ranking-star'},
        {'path': '/join-to-create', 'label': 'Комнаты J2C', 'icon': 'fa-door-open'},
        {'path': '/staff-rating', 'label': 'Оценки персонала', 'icon': 'fa-star-half-stroke'},
        {'path': '/staff-shifts', 'label': 'Смены персонала', 'icon': 'fa-calendar-week'},
        {'path': '/staff-stats', 'label': 'Активность персонала', 'icon': 'fa-chart-column'},
        {'path': '/meetings', 'label': 'Собрания', 'icon': 'fa-people-group'},
        {'path': '/leaderboards', 'label': 'Рейтинги', 'icon': 'fa-medal'},
        {'path': '/gamification', 'label': 'Геймификация', 'icon': 'fa-trophy'},
        {'path': '/scheduled-messages', 'label': 'Расписание', 'icon': 'fa-clock'},
    ]},
    {'group': 'Логи', 'key': 'logs', 'icon': 'fa-file-lines', 'pages': [
        {'path': '/chat', 'label': 'Чат', 'icon': 'fa-comments'},
        {'path': '/message-logs', 'label': 'Сообщения', 'icon': 'fa-comment-alt'},
        {'path': '/panel-logs', 'label': 'Панель', 'icon': 'fa-list'},
        {'path': '/replay', 'label': 'Инцидент-лента', 'icon': 'fa-film'},
        {'path': '/reports', 'label': 'Отчёты поддержки', 'icon': 'fa-chart-pie'},
        {'path': '/archive', 'label': 'Архиватор', 'icon': 'fa-box-archive'},
        {'path': '/backup', 'label': 'Бэкапы', 'icon': 'fa-database'},
    ]},
    {'group': 'Контент', 'key': 'content', 'icon': 'fa-palette', 'pages': [
        {'path': '/custom-embeds', 'label': 'Embed-ы', 'icon': 'fa-palette'},
        {'path': '/webhooks', 'label': 'Вебхуки', 'icon': 'fa-link'},
        {'path': '/channels', 'label': 'Каналы', 'icon': 'fa-hashtag'},
        {'path': '/announcements', 'label': 'Объявления', 'icon': 'fa-bullhorn'},
        {'path': '/execute-command', 'label': 'Команда', 'icon': 'fa-bolt'},
    ]},
    {'group': 'AI', 'key': 'ai', 'icon': 'fa-brain', 'pages': [
        {'path': '/ai-chat', 'label': 'AI Чат', 'icon': 'fa-comments'},
        {'path': '/ai-moderation', 'label': 'AI Модерация', 'icon': 'fa-robot'},
        {'path': '/server-info', 'label': 'Инфо-база', 'icon': 'fa-circle-info'},
    ]},
    {'group': 'Система', 'key': 'ops', 'icon': 'fa-server', 'pages': [
        {'path': '/bot-diagnostics', 'label': 'Диагностика', 'icon': 'fa-heartbeat'},
        {'path': '/leveling-admin', 'label': 'Leveling', 'icon': 'fa-trophy'},
        {'path': '/feature-flags', 'label': 'Флаги', 'icon': 'fa-flag'},
    ]},
    {'group': 'Утилиты', 'key': 'utility', 'icon': 'fa-toolbox', 'pages': [
        {'path': '/todo', 'label': 'Задачи', 'icon': 'fa-check-square'},
        {'path': '/reminders', 'label': 'Напоминания', 'icon': 'fa-bell'},
        {'path': '/yardim', 'label': 'Справка', 'icon': 'fa-question-circle'},
        {'path': '/search', 'label': 'Поиск по серверу', 'icon': 'fa-magnifying-glass'},
    ]},
]

# Рабочие подразделы модерации. Порядок задаёт сценарий работы команды:
# реагирование -> расследование -> защита -> команда и аналитика.
MODERATION_SECTIONS = (
    {'key': 'response', 'label': 'Реагирование', 'short': 'Реагирование',
     'icon': 'fa-bolt', 'description': 'Наказания и экстренные действия'},
    {'key': 'investigation', 'label': 'Расследование', 'short': 'Расследование',
     'icon': 'fa-magnifying-glass', 'description': 'Факты, доказательства и пересмотр решений'},
    {'key': 'protection', 'label': 'Защита', 'short': 'Защита',
     'icon': 'fa-shield-halved', 'description': 'Превентивные политики безопасности'},
    {'key': 'management', 'label': 'Команда и аналитика', 'short': 'Команда',
     'icon': 'fa-chart-line', 'description': 'Нагрузка, качество и эскалация'},
)

_ROLE_LEVEL = {'uye': 0, 'mod': 1, 'admin': 2, 'owner': 3}


# Defaults applied if a role has no stored config yet.
DEFAULT_GROUPS = {
    'mod': ['main', 'mod', 'members', 'logs', 'ai'],
    'admin': [g['key'] for g in MENU],
}

# Panels that can be configured (owner is always full and not stored).
CONFIGURABLE = ('mod', 'admin')

# ── Режим модулей: какие страницы обслуживаются какими когами ─────────────
# Если все коги страницы выключены (MOD_ONLY / DISABLED_COGS), пункт меню
# приглушается и получает чип «выкл» — видно, что модуль спит, а не сломан.
# Страницы, работающие через Discord API напрямую (роли, каналы, бэкапы...),
# в карту НЕ входят: они живы и без когов.
PAGE_COGS = {
    '/tickets-ops': ('ticket',),
    '/reports': ('report_cog',),
    '/archive': ('archive',),
    '/server-info': ('server_info',),
    '/search': ('search_cog',),
    '/sla': ('sla_cog',),
    '/economy': ('economy_cog',),
    '/shop': ('economy_cog',),
    '/music': ('music_cog',),
    '/achievements': ('achievements',),
    '/duels': ('duels',),
    '/fun': ('minigames', 'fun_cog'),
    '/leveling': ('level_cog',),
    '/leveling-admin': ('level_cog',),
    '/giveaway': ('giveaway',),
    '/polls': ('social',),
    '/suggestions': ('social',),
    '/starboard': ('starboard',),
    '/voice-stats': ('voice_tracker',),
    '/duty-panel-web': ('duty',),
    '/quiz': ('quiz',),
    '/reminders': ('reminders',),
    '/counting': ('counting',),
    '/crown': ('weekly_crown',),
    '/webhooks': ('webhooks',),
    '/scheduled-messages': ('scheduler',),
    '/schedule': ('scheduler',),
    '/afk-list': ('afk',),
    '/reaction-roles': ('reaction_roles_cog',),
    '/autorole': ('autorole_join', 'autorole_level'),
    '/ai-chat': ('ai_chat',),
    '/custom-commands': ('custom_commands',),
    '/custom-embeds': ('custom_embeds',),
    '/welcome-editor': ('welcome_cog',),
    '/staff-apps': ('staff_apply',),
    # Автоматика живёт, пока жив хотя бы один её модуль (анти-альт/ночной
    # режим в MOD_ONLY, приветствия и дайджест — в полном режиме).
    '/automation': ('anti_alt', 'night_mode', 'welcome_pro', 'mod_digest',
                    'server_stats', 'media_only', 'night_summary'),
    '/karma': ('karma',),
    '/birthdays': ('birthday',),
    '/social': ('social',),
    '/anime-daily': ('anime_daily',),
    '/tops': ('leaderboard',),
    '/join-to-create': ('join_to_create',),
    '/staff-rating': ('staff_rating',),
    '/member-card': ('profile', 'karma', 'birthday'),
    '/recap': ('recap',),
    '/appeals': ('appeals',),
    '/lockdown': ('lockdown',),
    '/staff-shifts': ('staff_shifts',),
    '/staff-stats': ('staff_stats',),
    '/security': ('security',),
    '/antifake': ('impersonation',),
    '/ladder': ('ladder', 'warnings'),
    '/replay': ('replay',),
    '/meetings': ('meeting',),
    '/leaderboards': ('leaderboard',),
    '/templates': ('server_template',),
    '/gamification': ('gamification_cog',),
}


def _off_cog_names():
    """Множество имён когов, отключённых политикой cogs_policy из окружения."""
    try:
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo not in sys.path:
            sys.path.insert(0, repo)
        import cogs_policy
        files = [f for f in os.listdir(os.path.join(repo, 'cogs')) if f.endswith('.py')]
        _on, off = cogs_policy.select_from_environment(files)
        return frozenset(cogs_policy._norm_name(f) for f in off)
    except Exception as _ex:
        _log.debug("_off_cog_names(): подавлено: %s", _ex)
        return frozenset()


def module_mode_active():
    """True, если включён режим «только модерация» (MOD_ONLY из окружения)."""
    try:
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo not in sys.path:
            sys.path.insert(0, repo)
        import cogs_policy
        return cogs_policy.env_flag(cogs_policy.ENV_MOD_ONLY)
    except Exception:
        return str(os.environ.get('MOD_ONLY', '')).strip().lower() in ('1', 'true', 'yes', 'on')


def module_off_paths():
    """Пути страниц, чьи коги полностью выключены режимом модулей."""
    off = _off_cog_names()
    if not off:
        return frozenset()
    return frozenset(p for p, cogs in PAGE_COGS.items() if all(c in off for c in cogs))


def _load():
    try:
        if os.path.exists(_PATH):
            with open(_PATH, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception as _ex:
        _log.debug("_load(): подавлено: %s", _ex)
    return {}


def _save(cfg):
    try:
        os.makedirs('data', exist_ok=True)
        with open(_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as _ex:
        _log.debug("_save(): подавлено: %s", _ex)


def get_config():
    return _load()


def save_config(cfg):
    _save(cfg)


def _role_can_open(role, page):
    """Не показывать ссылку, которая гарантированно закончится HTTP 403."""
    required = page.get('min_role', 'uye')
    return _ROLE_LEVEL.get(role, -1) >= _ROLE_LEVEL.get(required, 99)


def _moderation_sections(items):
    """Сгруппировать видимые мод-инструменты без изменения их URL/настроек."""
    sections = []
    for meta in MODERATION_SECTIONS:
        pages = [page for page in items if page.get('section') == meta['key']]
        if pages:
            sections.append({**meta, 'pages': pages})
    return sections


def moderation_pages():
    """Плоский список всех инструментов раздела модерации (для тестов и API)."""
    return list(next(group['pages'] for group in MENU if group['key'] == 'mod'))


def panel_groups_for(role):
    """Return visible sidebar groups with role-safe, workflow-aware pages.

    Owner sees everything. Mod/admin visibility still follows panel_menu.json,
    while `min_role` removes dead links that would inevitably return HTTP 403.
    The moderation group additionally receives `sections` for grouped nav.
    """
    cfg = _load().get(role, {}) if role != 'owner' else {}
    if not isinstance(cfg, dict):
        cfg = {}
    allowed_groups = (cfg.get('groups') or DEFAULT_GROUPS.get(role, []))
    if role == 'owner':
        allowed_groups = [g['key'] for g in MENU]
    allowed_items = cfg.get('items') or []
    if not isinstance(allowed_groups, list):
        allowed_groups = []
    if not isinstance(allowed_items, list):
        allowed_items = []

    out = []
    has_items_filter = bool(allowed_items)
    for group in MENU:
        if group['key'] not in allowed_groups:
            continue
        pages = [page for page in group['pages'] if _role_can_open(role, page)]
        if has_items_filter:
            pages = [page for page in pages if page['path'] in allowed_items]
        if not pages:
            continue
        payload = {
            'group': group['group'],
            'key': group['key'],
            'icon': group['icon'],
            'pages': pages,
        }
        if group['key'] == 'mod':
            payload['sections'] = _moderation_sections(pages)
        out.append(payload)
    return out
