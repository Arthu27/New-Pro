# -*- coding: utf-8 -*-
"""Нарезка routes_extra: фасад худой, модули на месте, карта роутов 1:1.

Запуск: python3 tests/test_routes_layout.py
"""
import ast
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_routes_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══ 1. Фасад худой, модули существуют и регистрируют ══════════════════
print('== верстка пакета web/routes ==')
facade = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
fl = facade.count(chr(10))
check(fl < 200, f'routes_extra.py — тонкий фасад ({fl} строк < 200, было 8701)')
check('def register_extra_routes' in facade, 'фасад хранит register_extra_routes (API не изменён)')

MODS = ['pages_core', 'anticrash', 'autofilter', 'todo', 'economy', 'bot_settings',
        'status', 'tagjail', 'schedule', 'pages', 'modplus', 'backups', 'ai_chat',
        'leveling', 'ai_mod', 'admin_api', 'members', 'giveaways', 'guild_admin',
        'security_api', 'ai_assist', 'chat', 'channels_admin', 'guild_features',
        'member_ops', 'community', 'reaction_roles', 'pages2', 'tickets_admin',
        'backup_restore', 'tasks_rules', 'roles_antiraid', 'guild_extra',
        'permissions', 'dashboard', 'ticket_search', 'ticket_tags', 'user_profile',
        'notifications', 'transcripts', 'ticket_templates', 'theme',
        'adv_analytics', 'knowledge_base', 'customer_portal']
missing = [m for m in MODS
           if not os.path.exists(os.path.join(ROOT, 'web', 'routes', m + '.py'))]
check(not missing, f'все 45 доменных модулей на месте ({missing or "да"})')

no_register = []
for m in MODS:
    src = open(os.path.join(ROOT, 'web', 'routes', m + '.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'register'
               for n in tree.body):
        no_register.append(m)
check(not no_register, f'в каждом модуле есть register(ctx) ({no_register or "да"})')

# порядок в фасаде = канонический (важно для дубля /api/backups GET)
i_back = facade.find('    backups,')
i_rest = facade.find('    backup_restore,')
check(-1 < i_back < i_rest, 'порядок регистрации: backups раньше backup_restore (дубль /api/backups)')

# ═══ 2. Публичные реэкспорты фасада ════════════════════════════════════
print('== обратная совместимость ==')
from web.routes_extra import (  # noqa: E402
    register_extra_routes, _notify_discord_sender, _run_async,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats,
)
check(callable(register_extra_routes), 'register_extra_routes импортируется')
check(callable(_notify_discord_sender), '_notify_discord_sender (нужен web/app.py)')
check(ms_normalize_query(' HéLLo ') == 'héllo' and ms_normalize_query('<@123>') == '123',
      'ms_* хелперы работают из фасада (trim/lower + <@id>)')

from web.routes._common import Ctx  # noqa: E402
check(hasattr(Ctx, 'active_guild_id') and hasattr(Ctx, '_resolve_member_async'),
      'Ctx несёт бывшие замыкания active_guild_id/_resolve_member_async')

# ═══ 3. Карта роутов 1:1 (эндпоинт -> путь) ════════════════════════════
print('== карта роутов ==')
from web.app import app  # noqa: E402

actual = {}
for r in app.url_map.iter_rules():
    actual.setdefault(r.endpoint, str(r.rule))

EXPECTED = {
    'advanced_analytics_page': '/advanced-analytics',
    'afk_list_page': '/afk-list',
    'ai_chat_page': '/ai-chat',
    'ai_moderation_page': '/ai-moderation',
    'ai_ticket_stats': '/ai_ticket_stats',
    'ai_tickets_page': '/ai-tickets',
    'analytics_page': '/analytics',
    'announcements': '/announcements',
    'anticrash_page': '/anticrash',
    'antiraid_page': '/antiraid',
    'api_activity_feed': '/api/activity-feed',
    'api_add_member': '/api/add-member',
    'api_add_member_note': '/api/member-notes/<member_id>/add',
    'api_afk_list': '/api/afk/<guild_id>',
    'api_ai_announcement': '/api/ai/announcement',
    'api_ai_assistant': '/api/ai/assistant',
    'api_ai_chat': '/api/ai-chat',
    'api_ai_chat_clear': '/api/ai-chat/clear',
    'api_ai_clear': '/api/ai/clear',
    'api_ai_embed': '/api/ai/embed',
    'api_ai_mod_config': '/api/ai-mod/config',
    'api_ai_mod_report': '/api/ai/mod-report',
    'api_ai_mod_stats': '/api/ai-mod/stats',
    'api_ai_mod_test': '/api/ai-mod/test',
    'api_ai_stream': '/api/ai/stream',
    'api_all_member_notes': '/api/member-notes',
    'api_analytics_advanced': '/api/analytics/advanced',
    'api_analytics_export': '/api/analytics/export',
    'api_announcements': '/api/announcements',
    'api_anticrash_config': '/api/anticrash/config',
    'api_anticrash_overview': '/api/anticrash/overview',
    'api_anticrash_reset': '/api/anticrash/reset',
    'api_antiraid_settings': '/api/guild/<guild_id>/antiraid',
    'api_autofilter_get': '/api/autofilter',
    'api_autofilter_save': '/api/autofilter/save',
    'api_autofilter_test': '/api/autofilter/test',
    'api_automod_settings': '/api/guild/<guild_id>/automod',
    'api_autorole': '/api/guild/<guild_id>/autorole',
    'api_backups_create': '/api/backups',
    'api_backups_delete': '/api/backups/<name>',
    'api_backups_download': '/api/backups/download/<name>',
    'api_backups_list': '/api/backups',
    'api_ban': '/api/command/ban',
    'api_birthdays': '/api/guild/<guild_id>/birthdays',
    'api_birthdays_list': '/api/birthdays/<guild_id>',
    'api_bot_diagnose': '/api/bot/diagnose',
    'api_bot_errors': '/api/bot/errors',
    'api_bot_gc': '/api/bot/gc',
    'api_bot_health': '/api/bot/health',
    'api_bot_hot_reload': '/api/bot/hot-reload',
    'api_bot_prefix': '/api/bot/prefix',
    'api_bot_restart': '/api/bot/restart',
    'api_bot_settings_get': '/api/bot-settings',
    'api_bot_settings_presence': '/api/bot-settings/presence',
    'api_bot_settings_sync': '/api/bot-settings/sync',
    'api_bot_stats': '/api/bot-stats',
    'api_bot_status': '/api/bot/status',
    'api_bot_sync': '/api/bot/sync',
    'api_bulk_ban': '/api/guild/<guild_id>/bulk-ban',
    'api_bulk_dm': '/api/guild/<guild_id>/bulk-dm',
    'api_bulk_kick': '/api/guild/<guild_id>/bulk-kick',
    'api_bulk_mute': '/api/guild/<guild_id>/bulk-mute',
    'api_bulk_role': '/api/guild/<guild_id>/bulk-roles',
    'api_change_password': '/api/change-password',
    'api_channels_default': '/api/channels',
    'api_chat_delete': '/api/chat/<guild_id>/<channel_id>/delete/<message_id>',
    'api_chat_members': '/api/chat/<guild_id>/members',
    'api_chat_messages': '/api/chat/<guild_id>/<channel_id>/messages',
    'api_chat_send': '/api/chat/<guild_id>/<channel_id>/send',
    'api_check_member': '/api/public/check-member',
    'api_clear_panel_logs': '/api/panel-logs/clear',
    'api_close_ticket': '/api/guild/<guild_id>/tickets/<ticket_id>/close',
    'api_cog_load': '/api/cogs/load',
    'api_cog_reload': '/api/cogs/reload',
    'api_cog_reload_all': '/api/cogs/reload-all',
    'api_cog_unload': '/api/cogs/unload',
    'api_cogs': '/api/cogs',
    'api_color_roles': '/api/guild/<guild_id>/color-roles',
    'api_create_backup': '/api/guild/<guild_id>/backup',
    'api_create_channel': '/api/guild/<guild_id>/channels/create',
    'api_create_custom_command': '/api/guild/<guild_id>/custom-commands/create',
    'api_create_giveaway': '/api/guild/<guild_id>/giveaways/create',
    'api_create_poll': '/api/guild/<guild_id>/polls/create',
    'api_create_reaction_role': '/api/guild/<guild_id>/reaction-roles/create',
    'api_create_role': '/api/guild/<guild_id>/roles/create',
    'api_create_scheduled_message': '/api/guild/<guild_id>/scheduled-messages/create',
    'api_create_task': '/api/tasks',
    'api_custom_commands': '/api/guild/<guild_id>/custom-commands',
    'api_customer_portal_create_ticket': '/api/customer-portal/tickets',
    'api_customer_portal_get': '/api/customer-portal',
    'api_customer_portal_get_tickets': '/api/customer-portal/tickets',
    'api_customer_portal_update_profile': '/api/customer-portal/profile',
    'api_dashboard_stats': '/api/dashboard/stats',
    'api_delete_backup': '/api/backups/<backup_id>/delete',
    'api_delete_channel': '/api/guild/<guild_id>/channels/<channel_id>/delete',
    'api_delete_custom_command': '/api/guild/<guild_id>/custom-commands/<cmd_id>/delete',
    'api_delete_event': '/api/guild/<guild_id>/events/<event_id>/delete',
    'api_delete_member_note': '/api/member-notes/<member_id>/<note_id>/delete',
    'api_delete_reaction_role': '/api/guild/<guild_id>/reaction-roles/<rr_id>/delete',
    'api_delete_role': '/api/guild/<guild_id>/roles/<role_id>/delete',
    'api_delete_role_map': '/api/role-map/<role_id>',
    'api_delete_scheduled_message': '/api/guild/<guild_id>/scheduled-messages/<msg_id>/delete',
    'api_delete_task': '/api/tasks/<task_id>/delete',
    'api_discord_check': '/api/discord-check',
    'api_discord_login': '/api/discord-login',
    'api_dm_messages': '/api/dm/<guild_id>/<user_id>/messages',
    'api_dm_recent': '/api/dm/<guild_id>/recent',
    'api_dm_send': '/api/dm/<guild_id>/<user_id>/send',
    'api_download_backup': '/api/backups/<backup_id>/download',
    'api_duty_data': '/api/duty/<guild_id>',
    'api_economy': '/api/guild/<guild_id>/economy',
    'api_economy_overview': '/api/economy/overview',
    'api_economy_rich': '/api/guild/<guild_id>/economy/rich',
    'api_economy_shop': '/api/guild/<guild_id>/economy/shop',
    'api_economy_shop_add': '/api/guild/<guild_id>/economy/shop/add',
    'api_economy_shop_remove': '/api/guild/<guild_id>/economy/shop/<item_id>/remove',
    'api_end_giveaway': '/api/guild/<guild_id>/giveaways/<gw_id>/end',
    'api_execute_command': '/api/execute-command',
    'api_forgot_password': '/api/forgot-password',
    'api_get_role_map': '/api/role-map',
    'api_get_tasks': '/api/tasks',
    'api_ghost_add': '/api/ghost',
    'api_ghost_list': '/api/ghost',
    'api_ghost_remove': '/api/ghost',
    'api_giveaway_create': '/api/giveaway/<guild_id>/create',
    'api_giveaway_delete': '/api/giveaway/<guild_id>/<gw_id>/delete',
    'api_giveaway_end': '/api/giveaway/<guild_id>/<gw_id>/end',
    'api_giveaway_list': '/api/giveaway/<guild_id>',
    'api_giveaways': '/api/guild/<guild_id>/giveaways',
    'api_global_search': '/api/search',
    'api_guild_analytics': '/api/guild/<guild_id>/analytics',
    'api_guild_badges': '/api/guild/<guild_id>/badges',
    'api_guild_channels': '/api/guild/<guild_id>/channels',
    'api_guild_events': '/api/guild/<guild_id>/events',
    'api_guild_health': '/api/guild/<guild_id>/health',
    'api_guild_info': '/api/guild/<guild_id>/info',
    'api_guild_info2': '/api/guild/<guild_id>/info2',
    'api_guild_members': '/api/guild/<guild_id>/members',
    'api_guild_roles': '/api/guild/<guild_id>/roles',
    'api_guild_webhooks': '/api/guild/<guild_id>/webhooks',
    'api_guilds': '/api/guilds',
    'api_invite_tracker': '/api/guild/<guild_id>/invite-tracker',
    'api_invite_tracker_full': '/api/guild/<guild_id>/invite-tracker-full',
    'api_join_giveaway': '/api/guild/<guild_id>/giveaways/<gw_id>/join',
    'api_kick': '/api/command/kick',
    'api_knowledge_base_articles_create': '/api/knowledge-base/articles',
    'api_knowledge_base_categories_create': '/api/knowledge-base/categories',
    'api_knowledge_base_categories_get': '/api/knowledge-base/categories',
    'api_knowledge_base_get': '/api/knowledge-base',
    'api_knowledge_base_search': '/api/knowledge-base/search',
    'api_leaderboard': '/api/guild/<guild_id>/leaderboard',
    'api_leave_guild': '/api/leave-guild',
    'api_leveling': '/api/guild/<guild_id>/leveling',
    'api_leveling_achievements': '/api/leveling/achievements',
    'api_leveling_config': '/api/leveling/config',
    'api_leveling_rewards': '/api/leveling/rewards',
    'api_leveling_stats': '/api/leveling/stats',
    'api_list_backups': '/api/backups',
    'api_live_logs': '/api/live-logs',
    'api_login_log': '/api/login-log',
    'api_login_suggest': '/api/login/suggest',
    'api_logs': '/api/logs',
    'api_member_notes': '/api/member-notes/<member_id>',
    'api_member_profile': '/api/member-profile/<guild_id>/<user_id>',
    'api_member_roles': '/api/guild/<guild_id>/member/<member_id>/роли',
    'api_member_search': '/api/member-search/<guild_id>',
    'api_members_default': '/api/members',
    'api_message_logs': '/api/guild/<guild_id>/message-logs',
    'api_mod_history': '/api/mod-history',
    'api_modstats': '/api/modstats',
    'api_my_applications': '/api/my-applications',
    'api_my_birthday_get': '/api/my-birthday/<guild_id>',
    'api_my_birthday_save': '/api/my-birthday/<guild_id>',
    'api_my_notifications': '/api/my-notifications',
    'api_my_profile': '/api/my-profile',
    'api_my_token': '/api/my-token',
    'api_notifications_history': '/api/notifications/history',
    'api_notifications_poll': '/api/notifications/poll',
    'api_notifications_settings_get': '/api/notifications/settings',
    'api_notifications_settings_post': '/api/notifications/settings',
    'api_notifications_test': '/api/notifications/test',
    'api_panel_logs': '/api/panel-logs',
    'api_panel_menu_get': '/api/panel-menu',
    'api_panel_menu_set': '/api/panel-menu',
    'api_panic_status_panel': '/api/panic',
    'api_panic_toggle': '/api/panic',
    'api_polls': '/api/guild/<guild_id>/polls',
    'api_proofs_delete': '/api/proofs/<int:pid>',
    'api_proofs_list': '/api/proofs',
    'api_public_apply': '/api/public/apply',
    'api_public_guilds': '/api/public/guilds',
    'api_publish_color_roles': '/api/guild/<guild_id>/color-roles/publish',
    'api_publish_rules': '/api/guild/<guild_id>/rules/publish',
    'api_purge': '/api/guild/<guild_id>/purge',
    'api_reaction_roles': '/api/guild/<guild_id>/reaction-roles',
    'api_rejoin_roles': '/api/guild/<guild_id>/rejoin-roles',
    'api_reload_cog': '/api/cogs/<cog_name>/reload',
    'api_reset_password': '/api/reset-password',
    'api_restore_backup': '/api/guild/<guild_id>/restore',
    'api_restore_upload': '/api/restore-upload',
    'api_review_staff_app': '/api/staff-apps/<app_id>/review',
    'api_review_suggestion': '/api/guild/<guild_id>/suggestions/<sug_id>/review',
    'api_role_permissions_category_assign': '/api/role-permissions/<guild_id>/category/assign',
    'api_role_permissions_category_everyone': '/api/role-permissions/<guild_id>/category/everyone',
    'api_role_permissions_clear': '/api/role-permissions/<guild_id>/clear',
    'api_role_permissions_get': '/api/role-permissions/<guild_id>',
    'api_role_permissions_preset': '/api/role-permissions/<guild_id>/preset',
    'api_role_permissions_set': '/api/role-permissions/<guild_id>/set',
    'api_roles_default': '/api/roles',
    'api_rules': '/api/guild/<guild_id>/rules',
    'api_schedule_delete': '/api/schedule/delete',
    'api_schedule_save': '/api/schedule/save',
    'api_schedule_state': '/api/schedule/state',
    'api_schedule_test': '/api/schedule/test',
    'api_schedule_toggle': '/api/schedule/toggle',
    'api_scheduled_messages': '/api/guild/<guild_id>/scheduled-messages',
    'api_send_announcement': '/api/send-announcement',
    'api_send_embed': '/api/send-embed',
    'api_send_message': '/api/send-message',
    'api_send_notification': '/api/send-notification',
    'api_send_webhook_v2': '/api/guild/<guild_id>/webhooks/send',
    'api_set_nick': '/api/guild/<guild_id>/member/<member_id>/nick',
    'api_set_role_map': '/api/role-map',
    'api_staff_apps': '/api/staff-apps',
    'api_starboard': '/api/guild/<guild_id>/starboard',
    'api_starboard_settings': '/api/guild/<guild_id>/starboard/settings',
    'api_stats': '/api/stats',
    'api_status_public': '/api/status-public',
    'api_sticky_create': '/api/sticky',
    'api_sticky_delete': '/api/sticky',
    'api_sticky_list': '/api/sticky',
    'api_suggestions': '/api/guild/<guild_id>/suggestions',
    'api_suggestions_channel': '/api/guild/<guild_id>/suggestions/channel',
    'api_tagjail_config': '/api/tagjail/config',
    'api_tagjail_scan': '/api/tagjail/scan',
    'api_tagjail_state': '/api/tagjail/state',
    'api_tagjail_tag': '/api/tagjail/tag',
    'api_tagjail_unjail': '/api/tagjail/unjail',
    'api_temp_mod_active': '/api/temp-mod/active',
    'api_temp_mod_ban': '/api/temp-mod/ban',
    'api_temp_mod_kick': '/api/temp-mod/kick',
    'api_temp_mod_mute': '/api/temp-mod/mute',
    'api_temp_mod_unban': '/api/temp-mod/unban',
    'api_temp_mod_unmute': '/api/temp-mod/unmute',
    'api_temp_mod_unschedule': '/api/temp-mod/unschedule',
    'api_theme_settings_get': '/api/theme/settings',
    'api_theme_settings_post': '/api/theme/settings',
    'api_threat_index': '/api/security/threat-index',
    'api_ticket_notify_channel': '/api/guild/<guild_id>/ticket-notify-channel',
    'api_ticket_notify_diagnose': '/api/guild/<guild_id>/ticket-notify-diagnose',
    'api_ticket_permissions_get': '/api/guild/<int:guild_id>/ticket-permissions',
    'api_ticket_permissions_set': '/api/guild/<int:guild_id>/ticket-permissions',
    'api_ticket_search': '/api/tickets/search',
    'api_ticket_settings': '/api/guild/<guild_id>/ticket-settings',
    'api_ticket_tags_create': '/api/ticket-tags',
    'api_ticket_tags_delete': '/api/ticket-tags/<tag_id>',
    'api_ticket_tags_get': '/api/ticket-tags',
    'api_ticket_template_delete': '/api/ticket-templates/<template_id>',
    'api_ticket_template_get': '/api/ticket-templates/<template_id>',
    'api_ticket_templates_create': '/api/ticket-templates',
    'api_ticket_templates_get': '/api/ticket-templates',
    'api_tickets': '/api/guild/<guild_id>/tickets',
    'api_todo_add': '/api/todo/add',
    'api_todo_delete': '/api/todo/delete',
    'api_todo_list': '/api/todo',
    'api_todo_toggle': '/api/todo/toggle',
    'api_toggle_lockdown': '/api/security/toggle-lockdown',
    'api_toggle_scheduled_message': '/api/guild/<guild_id>/scheduled-messages/<msg_id>/toggle',
    'api_totp_begin': '/api/2fa/totp/begin',
    'api_totp_disable': '/api/2fa/totp/disable',
    'api_totp_enable': '/api/2fa/totp/enable',
    'api_totp_status': '/api/2fa/totp/status',
    'api_transcript_export': '/api/transcripts/<transcript_id>/export',
    'api_transcript_get': '/api/transcripts/<transcript_id>',
    'api_transcripts_search': '/api/transcripts/search',
    'api_tunnel_url': '/api/tunnel-url',
    'api_unload_cog': '/api/cogs/<cog_name>/unload',
    'api_update_channel': '/api/guild/<guild_id>/channels/<channel_id>/update',
    'api_update_task': '/api/tasks/<task_id>',
    'api_user_change_password': '/api/user/change-password',
    'api_user_info': '/api/user/<user_id>',
    'api_user_messages': '/api/guild/<guild_id>/user-messages',
    'api_user_profile': '/api/user-profile',
    'api_voice_command': '/api/voice-command',
    'api_voice_stats': '/api/guild/<guild_id>/voice-stats',
    'api_vote_poll': '/api/guild/<guild_id>/polls/<poll_id>/vote',
    'api_warn': '/api/command/warn',
    'api_warn_config': '/api/guild/<guild_id>/warn-config',
    'api_warn_config_get': '/api/warn-config/<guild_id>',
    'api_warn_config_save': '/api/warn-config/<guild_id>',
    'api_warn_dm': '/api/guild/<guild_id>/warn-dm',
    'api_warnings': '/api/warnings',
    'api_watchlist': '/api/watchlist/<guild_id>',
    'api_welcome_settings': '/api/guild/<guild_id>/welcome-settings',
    'autofilter_page': '/autofilter',
    'automod_settings_page': '/automod-settings',
    'autorole_page': '/autorole',
    'backup_page': '/backup',
    'backups_page': '/backups',
    'birthday_register_page': '/birthday-register',
    'bot_diagnostics_page': '/bot-diagnostics',
    'bot_settings_page': '/bot-settings',
    'bot_stats_page': '/bot-stats',
    'bulk_actions_page': '/bulk-actions',
    'change_password_page': '/change-password',
    'channels_page': '/channels',
    'chat_page': '/chat',
    'cog_manager_page': '/cog-manager',
    'color_roles_page': '/color-roles',
    'commands_page': '/commands',
    'custom_commands_page': '/custom-commands',
    'custom_embeds_page': '/custom-embeds',
    'customer_portal_page': '/customer-portal',
    'dashboard_page': '/dashboard',
    'duty_panel_web_page': '/duty-panel-web',
    'economy_page': '/economy',
    'execute_command_page': '/execute-command',
    'favicon': '/favicon.ico',
    'giveaway_page': '/giveaway',
    'guilds_page': '/guilds',
    'health_check': '/health',
    'index': '/',
    'invite_tracker_page': '/invite-tracker',
    'knowledge_base_page': '/knowledge-base',
    'konsol_page': '/konsol',
    'leveling_admin_page': '/leveling-admin',
    'leveling_page': '/leveling',
    'login': '/login',
    'logout': '/logout',
    'logs_page': '/logs',
    'member_apply_page': '/member-apply',
    'member_notes_page': '/member-notes',
    'member_search_page': '/member-search',
    'message_logs_page': '/message-logs',
    'mod_tools_page': '/mod-tools',
    'modhistory_page': '/mod-history',
    'my_applications': '/my-applications',
    'my_profile_page': '/my-profile',
    'notifications': '/notifications',
    'notifications_page': '/notifications',
    'panel_access_page': '/panel-access',
    'panel_logs_page': '/panel-logs',
    'panel_menu_page': '/panel-menu',
    'polls_page': '/polls',
    'proofs_page': '/proofs',
    'public_apply': '/apply',
    'reaction_roles_page': '/reaction-roles',
    'register': '/register',
    'rejoin_roles_page': '/rejoin-roles',
    'role_permissions_page': '/role-permissions',
    'roles_page': '/roles',
    'rules_editor_page': '/rules-editor',
    'schedule_page': '/schedule',
    'scheduled_messages_page': '/scheduled-messages',
    'send_command_page': '/send-command',
    'settings_page': '/settings',
    'staff_apps_page': '/staff-apps',
    'starboard_page': '/starboard',
    'static': '/static/<path:filename>',
    'status_public_page': '/status',
    'suggestions_page': '/suggestions',
    'sunucu_health_page': '/server-health',
    'tagjail_page': '/tagjail',
    'temp_moderation_page': '/temp-moderation',
    'theme_settings_page': '/theme-settings',
    'ticket_search_page': '/ticket-search',
    'ticket_settings_page': '/ticket-settings',
    'ticket_tags_page': '/ticket-tags',
    'ticket_templates_page': '/ticket-templates',
    'todo_page': '/todo',
    'transcripts_page': '/transcripts',
    'two_factor': '/2fa',
    'user_profile_page': '/user-profile',
    'users_page': '/users',
    'voice_stats_page': '/voice-stats',
    'warn_config_page': '/warn-config',
    'warnings_page': '/warnings',
    'watchlist_panel_page': '/watchlist-panel',
    'welcome_editor_page': '/welcome-editor',
    'yardim_page': '/yardim',
}

bad = []
for ep, rule in EXPECTED.items():
    if actual.get(ep) != rule:
        bad.append((ep, rule, actual.get(ep)))
check(not bad, f'все {len(EXPECTED)} эндпоинтов панели зарегистрированы на тех же путях'
               f'{"" if not bad else " — РАСХОЖДЕНИЯ: " + str(bad[:3])}')
check(len(actual) >= len(EXPECTED), f'всего роутов {len(actual)} (ожидали >= {len(EXPECTED)})')

# ═══ 4. Смоук поведения через test_client ══════════════════════════════
print('== смоук поведения ==')
c = app.test_client()
r = c.get('/autofilter')
check(r.status_code in (302, 308), 'гость: /autofilter → редирект на логин (302)')
r = c.get('/api/todo')
check(r.status_code in (302, 401, 403, 308), 'гость: /api/todo закрыт (не 200/500)')
r = c.get('/no-such-page-zzz')
check(r.status_code == 404, '404 на несуществующем пути')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
