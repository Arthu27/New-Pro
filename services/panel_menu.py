"""Panel menu visibility — which sidebar categories (groups) and rooms (pages)
are shown for each panel role (mod / admin / owner).

- owner always sees everything.
- mod / admin visibility is stored in data/panel_menu.json.
- member (uye) panel is managed separately by the user later.
"""

import os
import json

_PATH = 'data/panel_menu.json'

# The full sidebar menu: groups -> items (pages). Order matters (top -> bottom).
MENU = [
    {'group': 'Основное', 'key': 'main', 'icon': 'fa-house', 'pages': [
        {'path': '/', 'label': 'Обзор сервера', 'icon': 'fa-home'},
        {'path': '/guilds', 'label': 'Серверы', 'icon': 'fa-server'},
        {'path': '/analytics', 'label': 'Аналитика', 'icon': 'fa-chart-line'},
        {'path': '/bot-stats', 'label': 'Статистика бота', 'icon': 'fa-robot'},
        {'path': '/server-health', 'label': 'Состояние', 'icon': 'fa-heartbeat'},
    ]},
    {'group': 'Модерация', 'key': 'mod', 'icon': 'fa-shield-halved', 'pages': [
        {'path': '/logs', 'label': 'Логи модерации', 'icon': 'fa-clipboard-list'},
        {'path': '/temp-moderation', 'label': 'Временная модерация', 'icon': 'fa-clock'},
        {'path': '/warnings', 'label': 'Предупреждения', 'icon': 'fa-exclamation-triangle'},
        {'path': '/mod-history', 'label': 'История', 'icon': 'fa-history'},
        {'path': '/automod-settings', 'label': 'Автомодерация', 'icon': 'fa-shield-alt'},
        {'path': '/antiraid', 'label': 'Анти-рейд', 'icon': 'fa-shield-virus'},
        {'path': '/tagjail', 'label': 'Tag Jail', 'icon': 'fa-lock'},
        {'path': '/bulk-actions', 'label': 'Массовые действия', 'icon': 'fa-layer-group'},
    ]},
    {'group': 'Участники', 'key': 'members', 'icon': 'fa-users', 'pages': [
        {'path': '/users', 'label': 'Пользователи', 'icon': 'fa-users'},
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
        {'path': '/ai_ticket_stats', 'label': 'Статистика', 'icon': 'fa-chart-pie'},
        {'path': '/ticket-settings', 'label': 'Настройки', 'icon': 'fa-cogs'},
        {'path': '/staff-apps', 'label': 'Заявки', 'icon': 'fa-file-signature'},
    ]},
    {'group': 'Бот', 'key': 'bot', 'icon': 'fa-robot', 'pages': [
        {'path': '/commands', 'label': 'Команды', 'icon': 'fa-terminal'},
        {'path': '/custom-commands', 'label': 'Свои команды', 'icon': 'fa-code'},
        {'path': '/send-command', 'label': 'Отправить', 'icon': 'fa-paper-plane'},
        {'path': '/bot-settings', 'label': 'Настройки', 'icon': 'fa-sliders-h'},
        {'path': '/anticrash', 'label': 'Анти-краш', 'icon': 'fa-life-ring'},
        {'path': '/konsol', 'label': 'Консоль', 'icon': 'fa-terminal'},
        {'path': '/cog-manager', 'label': 'Модули', 'icon': 'fa-cubes'},
        {'path': '/settings', 'label': 'Сервер', 'icon': 'fa-cog'},
        {'path': '/rules-editor', 'label': 'Правила', 'icon': 'fa-gavel'},
        {'path': '/welcome-editor', 'label': 'Приветствие', 'icon': 'fa-handshake'},
        {'path': '/warn-config', 'label': 'Варны', 'icon': 'fa-exclamation'},
    ]},
    {'group': 'Сообщество', 'key': 'community', 'icon': 'fa-gamepad', 'pages': [
        {'path': '/economy', 'label': 'Экономика', 'icon': 'fa-coins'},
        {'path': '/leveling', 'label': 'Уровни', 'icon': 'fa-star'},
        {'path': '/giveaway', 'label': 'Розыгрыши', 'icon': 'fa-gift'},
        {'path': '/polls', 'label': 'Опросы', 'icon': 'fa-poll-h'},
        {'path': '/suggestions', 'label': 'Предложения', 'icon': 'fa-lightbulb'},
        {'path': '/starboard', 'label': 'Starboard', 'icon': 'fa-star'},
        {'path': '/voice-stats', 'label': 'Голосовая', 'icon': 'fa-microphone'},
        {'path': '/duty-panel-web', 'label': 'Дежурства', 'icon': 'fa-user-clock'},
        {'path': '/scheduled-messages', 'label': 'Расписание', 'icon': 'fa-clock'},
    ]},
    {'group': 'Логи', 'key': 'logs', 'icon': 'fa-file-lines', 'pages': [
        {'path': '/chat', 'label': 'Чат', 'icon': 'fa-comments'},
        {'path': '/message-logs', 'label': 'Сообщения', 'icon': 'fa-comment-alt'},
        {'path': '/panel-logs', 'label': 'Панель', 'icon': 'fa-list'},
        {'path': '/backup', 'label': 'Бэкапы', 'icon': 'fa-database'},
    ]},
    {'group': 'Контент', 'key': 'content', 'icon': 'fa-palette', 'pages': [
        {'path': '/custom-embeds', 'label': 'Embed-ы', 'icon': 'fa-palette'},
        {'path': '/channels', 'label': 'Каналы', 'icon': 'fa-hashtag'},
        {'path': '/execute-command', 'label': 'Команда', 'icon': 'fa-bolt'},
    ]},
    {'group': 'AI', 'key': 'ai', 'icon': 'fa-brain', 'pages': [
        {'path': '/ai-chat', 'label': 'AI Чат', 'icon': 'fa-comments'},
        {'path': '/ai-moderation', 'label': 'AI Модерация', 'icon': 'fa-robot'},
    ]},
    {'group': 'Система', 'key': 'ops', 'icon': 'fa-server', 'pages': [
        {'path': '/bot-diagnostics', 'label': 'Диагностика', 'icon': 'fa-heartbeat'},
        {'path': '/leveling-admin', 'label': 'Leveling', 'icon': 'fa-trophy'},
    ]},
    {'group': 'Утилиты', 'key': 'utility', 'icon': 'fa-toolbox', 'pages': [
        {'path': '/todo', 'label': 'Задачи', 'icon': 'fa-check-square'},
        {'path': '/yardim', 'label': 'Справка', 'icon': 'fa-question-circle'},
    ]},
]

# Defaults applied if a role has no stored config yet.
DEFAULT_GROUPS = {
    'mod': ['main', 'mod', 'members', 'logs', 'ai'],
    'admin': [g['key'] for g in MENU],
}

# Panels that can be configured (owner is always full and not stored).
CONFIGURABLE = ('mod', 'admin')


def _load():
    try:
        if os.path.exists(_PATH):
            with open(_PATH, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _save(cfg):
    try:
        os.makedirs('data', exist_ok=True)
        with open(_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_config():
    return _load()


def save_config(cfg):
    _save(cfg)


def panel_groups_for(role):
    """Return the list of visible groups (with visible items) for a panel role.

    owner -> everything. mod/admin -> from config (with defaults).
    """
    if role == 'owner':
        return MENU
    cfg = _load().get(role, {})
    allowed_groups = cfg.get('groups') or DEFAULT_GROUPS.get(role, [])
    allowed_items = cfg.get('items') or []
    if not isinstance(allowed_groups, list):
        allowed_groups = []
    if not isinstance(allowed_items, list):
        allowed_items = []
    out = []
    has_items_filter = bool(allowed_items)
    for g in MENU:
        if g['key'] not in allowed_groups:
            continue
        if has_items_filter:
            items = [it for it in g['pages'] if it['path'] in allowed_items]
        else:
            # No explicit page filter -> show all pages of an allowed group.
            items = list(g['pages'])
        if not items:
            continue
        out.append({'group': g['group'], 'key': g['key'], 'icon': g['icon'], 'pages': items})
    return out
