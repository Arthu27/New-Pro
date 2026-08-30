# -*- coding: utf-8 -*-
"""Настройки бота (presence, sync) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    # ── BOT SETTINGS: презенс + синк команд (страница /bot-settings) ──
    BOT_CFG_PATH = 'data/bot_config.json'   # тот же файл читает main.py on_ready


    def _bot_cfg_load() -> dict:
        if os.path.exists(BOT_CFG_PATH):
            try:
                with open(BOT_CFG_PATH, encoding='utf-8') as f:
                    d = json.load(f)
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}


    @app.route('/api/bot-settings')
    @login_required
    @role_required('owner')
    def api_bot_settings_get():
        import web.app as _app
        import discord as _discord
        from config import Config
        bot = _app.bot_instance
        cfg = _bot_cfg_load()
        online = False
        if bot is not None:
            try:
                online = not bot.is_closed()
            except Exception:
                online = False
        return jsonify({'ok': True, 'bot_online': online,
                        'guilds': len(getattr(bot, 'guilds', []) or []),
                        'discord_version': _discord.__version__,
                        'prefix': Config.COMMAND_PREFIX,
                        'presence': {'status': cfg.get('status', 'idle'),
                                     'activity_type': cfg.get('activity_type', 'listening'),
                                     'activity_text': cfg.get('activity_text', '.gg/Hakumo')}})


    @app.route('/api/bot-settings/presence', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_bot_settings_presence():
        import web.app as _app
        import discord as _discord
        data = request.get_json(silent=True) or {}
        status = str(data.get('status', ''))
        activity_type = str(data.get('activity_type', ''))
        activity_text = ' '.join(str(data.get('activity_text', '') or '').split())[:80]
        errors = []
        status_map = {'online': _discord.Status.online, 'idle': _discord.Status.idle,
                      'dnd': _discord.Status.dnd, 'invisible': _discord.Status.invisible}
        type_map = {'listening': _discord.ActivityType.listening,
                    'playing': _discord.ActivityType.playing,
                    'watching': _discord.ActivityType.watching,
                    'competing': _discord.ActivityType.competing}
        if status not in status_map:
            errors.append(f'status: допустимо {"/".join(status_map)}')
        if activity_type not in type_map:
            errors.append(f'activity_type: допустимо {"/".join(type_map)}')
        if not activity_text:
            errors.append('activity_text: пустой текст')
        if errors:
            return jsonify({'ok': False, 'errors': errors}), 400
        cfg = _bot_cfg_load()
        cfg.update({'status': status, 'activity_type': activity_type,
                    'activity_text': activity_text})
        os.makedirs('data', exist_ok=True)
        with open(BOT_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        applied = False
        bot = _app.bot_instance
        if bot is not None and hasattr(bot, 'change_presence'):
            try:
                _run_async(bot.change_presence(
                    activity=_discord.Activity(type=type_map[activity_type], name=activity_text),
                    status=status_map[status]))
                applied = True
            except Exception:
                applied = False
        return jsonify({'ok': True, 'applied_live': applied,
                        'presence': {'status': status, 'activity_type': activity_type,
                                     'activity_text': activity_text}})


    @app.route('/api/bot-settings/sync', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_bot_settings_sync():
        import web.app as _app
        import asyncio
        bot = _app.bot_instance
        tree = getattr(bot, 'tree', None) if bot is not None else None
        if tree is None:
            return jsonify({'ok': False, 'error': 'Бот офлайн — синхронизировать некому'}), 503
        try:
            # Синк уходит ФОНОМ и без ожидания ответа: full_sync ходит в
            # Discord (глобальная очистка + синк каждой гильдии) и легко
            # идёт дольше 10 секунд. Прежний «wait с таймаутом» показывал
            # «Синк упал», хотя синк продолжался, — и повторные клики
            # плодили вызовы до rate limit (дубли в меню). Лок внутри
            # full_sync не пускает второй прогон параллельно.
            from services.sync_filtered import full_sync as _full_sync
            asyncio.run_coroutine_threadsafe(_full_sync(bot), bot.loop)
            return jsonify({'ok': True, 'started': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Синк не запустился: {e}'}), 500
