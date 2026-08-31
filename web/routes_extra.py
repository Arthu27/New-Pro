# -*- coding: utf-8 -*-
"""Extra panel routes — тонкий фасад (нарезка аудита).

Логика разложена по доменам в ``web/routes/*.py``; фасад сохраняет публичный
API: register_extra_routes(...) (сигнатура прежняя) и реэкспорт хелперов
``_common`` для старых импортов (web/app.py, тесты). Реестр _MODULES
собирается из имён выше автоматически — порядок перечисления каноничен
(backups раньше backup_restore — важно для дубля /api/backups GET).
"""
from logger import get_logger

_log = get_logger("routes_extra")

import types as _types

from web.routes._common import (  # noqa: F401  (реэкспорт для совместимости)
    Ctx, _REPO_ROOT, _run_async, _fetch_channel_msgs_async,
    _fetch_channel_msgs_sync, _load_ai_tickets, _notify_discord_sender,
    _fire_panel_notification, _process_action,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats,
)
from web.routes import (
    pages_core,
    anticrash,
    autofilter,
    todo,
    bot_settings,
    status,
    pages,
    modplus,
    backups,
    ai_chat,
    ai_mod,
    admin_api,
    members,
    guild_admin,
    security_api,
    ai_assist,
    chat,
    channels_admin,
    channel_settings,
    mod_settings,
    role_settings_panel,
    guardian,
    guild_features,
    member_ops,
    community,
    pages2,
    backup_restore,
    tasks_rules,
    roles_antiraid,
    guild_extra,
    permissions,
    dashboard,
    ticket_tags,
    user_profile,
    notifications,
    theme,
    adv_analytics,
    ux,
    music_panel,
    music_activity,
    flags_panel,
    analytics_plus,
    mod_control,
    mod_insights,
    panel_punish,
    appeals_panel,
    log_cards_panel,
    staff_limits_panel,
    welcome_panel,
    commands_panel,
    security_panel,
    ladder_panel,
    reports_panel,
    antifake_panel,
    verification_panel,
    pagerduty_hook,
    mod_schedule,
    reports_queue,
    live_sse,
)

_MODULES = tuple(
    _obj for _obj in globals().values()
    if isinstance(_obj, _types.ModuleType)
    and _obj.__name__.startswith('web.routes.')
)


def register_extra_routes(app, ROLES, login_required, role_required,
                          MAIN_GUILD_ID='1384282749317152878'):
    """Регистрирует все extra-роуты панели (порядок доменов = исходный)."""
    ctx = Ctx(app, ROLES, login_required, role_required, MAIN_GUILD_ID)
    for module in _MODULES:
        module.register(ctx)
