"""Panel menu visibility — which sidebar categories (groups) and rooms (pages)
are shown for each panel role (mod / curator / admin / owner).

- owner always sees everything.
- mod / curator / admin visibility is stored in data/panel_menu.json.
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
        # Сводный штаб раздела.
        {'path': '/mod-center', 'label': 'Центр модерации', 'icon': 'fa-shield-halved',
         'section': 'response', 'description': 'Сводный штаб: метрики, графики и все инструменты раздела',
         'access': 'Мод+', 'tone': 'security'},

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

        # Защита: вынесена в отдельную категорию сайдбара «Защита»
        # (заказ владельца 2026-08-25: разделить Модерация и Защита).

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
        {'path': '/staff-apps', 'label': 'Заявки в команду', 'icon': 'fa-file-signature',
         'section': 'management', 'description': 'Анкеты кандидатов: хелперы и модераторы',
         'access': 'Мод+', 'tone': 'analytics'},
    ]},
    # Защита — отдельная категория сайдбара (заказ владельца 2026-08-25).
    {'group': 'Защита', 'key': 'protection', 'icon': 'fa-shield-halved', 'pages': [
        {'path': '/security', 'label': 'Центр безопасности', 'icon': 'fa-shield-halved',
         'section': 'protection', 'description': 'Сводный риск, политики и готовность защиты',
         'access': 'Мод+', 'tone': 'security'},
        {'path': '/autofilter', 'label': 'Автофильтр', 'icon': 'fa-filter',
         'section': 'protection', 'description': 'Слова, ссылки, капс, флуд и исключения',
         'access': 'Мод+', 'tone': 'security'},
        {'path': '/antiraid', 'label': 'Анти-рейд', 'icon': 'fa-shield-virus',
         'section': 'protection', 'description': 'Защита от массовых входов и атак',
         'access': 'Админ', 'min_role': 'admin', 'tone': 'security'},
        {'path': '/guardian', 'label': 'Щит сервера', 'icon': 'fa-shield-heart',
         'section': 'protection', 'description': 'Анти-нюк + лимиты команды: каналы, роли, права, боты, периоды',
         'access': 'Админ', 'min_role': 'admin', 'tone': 'critical'},
        {'path': '/antifake', 'label': 'Антифейк', 'icon': 'fa-user-secret',
         'section': 'protection', 'description': 'Поиск подделок профилей и impersonation',
         'access': 'Мод+', 'tone': 'security'},
    ]},
    {'group': 'Участники', 'key': 'members', 'icon': 'fa-users', 'pages': [
        {'path': '/users', 'label': 'Пользователи', 'icon': 'fa-users'},
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
        {'path': '/panel-access', 'label': 'Панели и роли', 'icon': 'fa-user-shield'},
        {'path': '/panel-menu', 'label': 'Меню панели', 'icon': 'fa-bars'},
        {'path': '/role-permissions', 'label': 'Права команд', 'icon': 'fa-user-lock'},
    ]},
    {'group': 'Тикеты', 'key': 'tickets', 'icon': 'fa-ticket-alt', 'pages': [
        {'path': '/ai-tickets', 'label': 'AI-тикеты', 'icon': 'fa-ticket-alt'},
        {'path': '/tickets-ops', 'label': 'Операции', 'icon': 'fa-gauge-high'},
        {'path': '/ai_ticket_stats', 'label': 'Статистика', 'icon': 'fa-chart-pie'},
        {'path': '/ticket-search', 'label': 'Поиск тикетов', 'icon': 'fa-magnifying-glass'},
        {'path': '/transcripts', 'label': 'Транскрипты', 'icon': 'fa-file-lines'},
        {'path': '/sla', 'label': 'SLA-контроль', 'icon': 'fa-handshake'},
    ]},
    {'group': 'Бот', 'key': 'bot', 'icon': 'fa-robot', 'pages': [
        {'path': '/commands', 'label': 'Команды', 'icon': 'fa-terminal'},
        {'path': '/custom-commands', 'label': 'Свои команды', 'icon': 'fa-code'},
        {'path': '/send-command', 'label': 'Отправить', 'icon': 'fa-paper-plane'},
        {'path': '/schedule', 'label': 'Расписание', 'icon': 'fa-calendar-alt'},
        {'path': '/backups', 'label': 'Бэкапы', 'icon': 'fa-save'},
        {'path': '/templates', 'label': 'Шаблоны', 'icon': 'fa-clone'},
        {'path': '/konsol', 'label': 'Консоль', 'icon': 'fa-terminal'},
        {'path': '/cog-manager', 'label': 'Модули', 'icon': 'fa-cubes'},
    ]},
    # Отдельная категория «Настройки»: всё, что крутится и настраивается,
    # собрано в одном месте — сервер, модерация, каналы, бот, темы, защита.
    {'group': 'Настройки', 'key': 'settings', 'icon': 'fa-sliders', 'pages': [
        {'path': '/settings', 'label': 'Сервер', 'icon': 'fa-cog'},
        {'path': '/command-switches', 'label': 'Команды вкл/выкл', 'icon': 'fa-toggle-on'},
        {'path': '/mod-settings', 'label': 'Модерация', 'icon': 'fa-hammer'},
        {'path': '/channel-settings', 'label': 'Каналы и маршруты', 'icon': 'fa-route'},
        {'path': '/bot-settings', 'label': 'Бот', 'icon': 'fa-sliders-h'},
        {'path': '/ticket-settings', 'label': 'Тикеты', 'icon': 'fa-ticket-alt'},
        {'path': '/welcome-editor', 'label': 'Приветствие', 'icon': 'fa-handshake'},
        {'path': '/rules-editor', 'label': 'Правила', 'icon': 'fa-scroll'},
        {'path': '/warn-config', 'label': 'Варны', 'icon': 'fa-exclamation'},
        {'path': '/automation', 'label': 'Автоматика', 'icon': 'fa-wand-magic-sparkles'},
        {'path': '/notifications', 'label': 'Уведомления', 'icon': 'fa-bell'},
        {'path': '/theme-settings', 'label': 'Тема панели', 'icon': 'fa-palette'},
        {'path': '/theme-studio', 'label': 'Студия темы', 'icon': 'fa-swatchbook'},
        {'path': '/anticrash', 'label': 'Анти-краш', 'icon': 'fa-life-ring'},
        {'path': '/log-settings', 'label': 'Логи сервера', 'icon': 'fa-list-check'},
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
        # «Команда» (/execute-command) убрана из меню (заказ владельца:
        # дубль «Команд»). Сама страница жива — на неё ведёт профиль участника.
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
        {'path': '/team-board', 'label': 'Доска команды', 'icon': 'fa-table-columns'},
        {'path': '/todo', 'label': 'Задачи', 'icon': 'fa-check-square'},
        {'path': '/reminders', 'label': 'Напоминания', 'icon': 'fa-bell'},
        {'path': '/spravka', 'label': 'Справка', 'icon': 'fa-question-circle'},
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

_ROLE_LEVEL = {'uye': 0, 'mod': 1, 'curator': 2, 'admin': 3, 'owner': 4}

# Достижения «пока что не нужны» (заказ владельца 2026-08-25): страница
# «Ачивки» исчезает из меню, ког не грузится, команды не показываются.
# Вернуть — ACHIEVEMENTS_ENABLED = True в cogs/achievements.py.
HIDDEN_PATHS = []          # страницы, скрытые из меню выключенным модулем
try:
    from cogs.achievements import ACHIEVEMENTS_ENABLED as _ACHIEVEMENTS_ON
except Exception:
    _ACHIEVEMENTS_ON = True
if not _ACHIEVEMENTS_ON:
    HIDDEN_PATHS.append('/achievements')
    for _grp in MENU:
        _grp['pages'] = [p for p in _grp.get('pages', [])
                         if p.get('path') != '/achievements']


# Defaults applied if a role has no stored config yet.
# Куратор — старший модератор: всё модерское + тикеты и сообщество.
DEFAULT_GROUPS = {
    'mod': ['main', 'mod', 'protection', 'members', 'logs', 'ai'],
    'curator': ['main', 'mod', 'protection', 'members', 'tickets', 'community', 'logs', 'ai'],
    'admin': [g['key'] for g in MENU],
}

# Panels that can be configured (owner is always full and not stored).
# Куратор настраивается так же, как модератор и администратор.
CONFIGURABLE = ('mod', 'curator', 'admin')

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
    '/recap': ('recap',),
    '/appeals': ('appeals',),
    '/lockdown': ('lockdown',),
    '/staff-shifts': ('staff_shifts',),
    '/staff-stats': ('staff_stats',),
    '/security': ('security',),
    '/tagjail': ('tag_jail',),
    '/antifake': ('impersonation',),
    '/ladder': ('ladder', 'warnings'),
    '/replay': ('replay',),
    '/meetings': ('meeting',),
    '/leaderboards': ('leaderboard',),
    '/templates': ('server_template',),
    '/gamification': ('gamification_cog',),
}


def _off_cog_names():
    """Множество имён когов, выключенных сейчас.

    Бой: политика cogs_policy из окружения (MOD_ONLY/LEAN/...).
    Демо (DEMO_MODE=1): живого бота нет — всё включено по умолчанию,
    а выключенные через менеджер модулей (data/demo_cog_states.json)
    честно светятся чипом «выкл», пока их не включат обратно.
    """
    try:
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from services.demo_cogs import demo_mode, load_states
        if demo_mode():
            names = {f[:-3] for f in os.listdir(os.path.join(repo, 'cogs'))
                     if f.endswith('.py')}
            states = load_states()
            return frozenset(n for n in names if states.get(n, True) is False)
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


# ── Глобальный лэйаут меню: скрытые страницы + свой порядок ─────────────────
LAYOUT_KEY = '_layout'

# Эти страницы нельзя скрыть — иначе меню не вернуть обратно через панель.
_PROTECTED = ('/panel-menu',)


def _all_menu_paths():
    return {pg['path'] for g in MENU for pg in g['pages']}


def layout_view():
    """Лэйаут из data/panel_menu.json: {hidden_pages: [...], order: {group: [...]}}."""
    lay = _load().get(LAYOUT_KEY) or {}
    if not isinstance(lay, dict):
        lay = {}
    hp = lay.get('hidden_pages') or []
    od = lay.get('order') or {}
    return {
        'hidden_pages': [str(p) for p in hp if isinstance(p, (str, int))],
        'order': {str(k): [str(p) for p in (v or [])]
                  for k, v in od.items() if isinstance(v, list)},
    }


def save_layout(hidden_pages, order):
    """Сохранить скрытие/порядок (валидация по MENU). Возвращает чистый вид."""
    valid_paths = _all_menu_paths()
    valid_groups = {g['key'] for g in MENU}
    hp = []
    for p in hidden_pages or ():
        p = str(p)
        if p in _PROTECTED or p not in valid_paths or p in hp:
            continue
        hp.append(p)
    od = {}
    menu_order = {g['key']: [p['path'] for p in g['pages']] for g in MENU}
    for k, v in (order or {}).items():
        if k not in valid_groups or not isinstance(v, list):
            continue
        cleaned = [str(x) for x in v if str(x) in valid_paths]
        if cleaned == menu_order.get(str(k)):
            continue                    # порядок совпал с исходным — хранить нечего
        od[str(k)] = cleaned
    cfg = _load()
    cfg[LAYOUT_KEY] = {'hidden_pages': hp, 'order': od}
    _save(cfg)
    return layout_view()


def _apply_layout(pages, group_key):
    """Скрыть спрятанные страницы и выстроить свой порядок (стабильно)."""
    lay = layout_view()
    hidden = set(lay['hidden_pages']) - set(_PROTECTED)
    pages = [p for p in pages if p['path'] not in hidden]
    order = lay['order'].get(group_key) or []
    if order:
        rank = {p: i for i, p in enumerate(order)}
        indexed = list(enumerate(pages))
        indexed.sort(key=lambda t: (rank.get(t[1]['path'], len(order) + t[0])))
        pages = [p for _i, p in indexed]
    return pages


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
        # глобальный лэйаут: скрытые страницы и свой порядок (для всех ролей)
        pages = _apply_layout(pages, group['key'])
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
