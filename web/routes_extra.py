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
    economy,
    bot_settings,
    status,
    tagjail,
    schedule,
    pages,
    modplus,
    backups,
    ai_chat,
    leveling,
    ai_mod,
    admin_api,
    members,
    giveaways,
    guild_admin,
    security_api,
    ai_assist,
    chat,
    channels_admin,
    guild_features,
    member_ops,
    community,
    reaction_roles,
    pages2,
    tickets_admin,
    backup_restore,
    tasks_rules,
    roles_antiraid,
    guild_extra,
    permissions,
    dashboard,
    ticket_search,
    ticket_tags,
    user_profile,
    notifications,
    transcripts,
    ticket_templates,
    theme,
    adv_analytics,
    knowledge_base,
    customer_portal,
    automation,
    ux,
    quiz_panel,
    shop_panel,
    music_panel,
    music_activity,
    achievements_panel,
    duels_panel,
    flags_panel,
    analytics_plus,
    tickets_ops,
    mod_report,
    mod_control,
    mod_insights,
    karma_panel,
    gamif_panel,
    tops_panel,
    birthdays_panel,
    social_panel,
    anime_panel,
    j2c_panel,
    staff_rating_panel,
    member_card_panel,
    recap_panel,
    appeals_panel,
    log_cards_panel,
    welcome_panel,
    commands_panel,
    lockdown_panel,
    shifts_panel,
    security_panel,
    replay_panel,
    meetings_panel,
    leaderboards_panel,
    templates_panel,
    ladder_panel,
    reminders_panel,
    counting_panel,
    crown_panel,
    webhooks_panel,
    sla_panel,
    reports_panel,
    archive_panel,
    server_info_panel,
    search_panel,
    fun_panel,
    antifake_panel,
    staff_stats_panel,
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
