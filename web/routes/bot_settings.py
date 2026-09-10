# -*- coding: utf-8 -*-
"""Настройки бота (presence, sync) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _safe_json_obj,
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone)

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
        guilds_n = 0
        # Имя бота (жалоба: «настройки бота — имя не видно»). Порядок:
        # живой процесс → пульс data/bot_state.json (панель отдельным
        # процессом) → демо-заглушка для превью.
        ident = {}
        if bot is not None:
            try:
                online = not bot.is_closed()
            except Exception:
                online = False
            guilds_n = len(getattr(bot, 'guilds', []) or [])
            _bu = getattr(bot, 'user', None)
            if _bu is not None:
                try:
                    ident = {
                        'id': str(_bu.id),
                        'name': str(getattr(_bu, 'name', '') or ''),
                        'display_name': str(getattr(_bu, 'display_name', '')
                                            or getattr(_bu, 'name', '') or ''),
                        'avatar': str(getattr(getattr(_bu, 'display_avatar', None),
                                              'url', '') or ''),
                    }
                except Exception:
                    ident = {}
        else:
            # Панель отдельным процессом от бота — правда по пульсу
            # (data/bot_state.json), иначе страница вечно показывает «офлайн».
            try:
                from services import bot_bridge as _bb
                _st = _bb.read_state()
                if _bb.state_status(_st) == 'online':
                    online = True
                    guilds_n = len(_bb.guild_ids(_st))
                # имя — последнее известное, даже если бот сейчас офлайн
                ident = _bb.state_identity(_st)
            except Exception:
                online = False
        if not ident.get('name') and getattr(_app, '_demo_mode', lambda: False)():
            ident = {'id': '987654321098765432', 'name': 'Hakumo',
                     'display_name': 'Hakumo (демо)', 'avatar': ''}
            online = True
            guilds_n = guilds_n or 1
        return jsonify({'ok': True, 'bot_online': online,
                        'guilds': guilds_n,
                        'discord_version': _discord.__version__,
                        'prefix': Config.COMMAND_PREFIX,
                        'bot_name': ident.get('display_name') or ident.get('name') or '',
                        'bot_username': ident.get('name') or '',
                        'bot_id': ident.get('id') or '',
                        'bot_avatar': ident.get('avatar') or '',
                        'presence': {'status': cfg.get('status', 'online'),
                                     'activity_type': cfg.get('activity_type', 'watching'),
                                     'activity_text': cfg.get('activity_text', 'Hakumo') or 'Hakumo'}})


    @app.route('/api/bot-settings/presence', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_bot_settings_presence():
        import web.app as _app
        import discord as _discord
        data = _safe_json_obj()
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


    @app.route('/api/bot-settings/update-source', methods=['GET', 'POST'])
    @login_required
    @role_required('owner')
    def api_bot_settings_update_source():
        """Источник обновлений: ОТКУДА бот качает версии (заказ 30.08
        «дай, я поставлю, откуда он будет скачивать»).

        Репозиторий и ветку владелец задаёт прямо в панели — без правки
        .env. Значения читают и /update, и демон автообновления. GET ещё
        показывает локальную и свежую версии — сразу видно, отстаёт ли
        бот и откуда он качает.
        """
        import web.app as _app
        from services import update_source as US
        if request.method == 'GET':
            payload = {'ok': True, 'repo': US.get_repo(), 'branch': US.get_branch(),
                       'kind': US.source_kind(), 'local_sha': None, 'remote_sha': None}
            if getattr(_app, '_demo_mode', lambda: False)():
                payload['demo'] = True
                return jsonify(payload)
            try:
                from services import self_update as SU
                payload['local_sha'] = SU.local_sha(str(_REPO_ROOT))
                payload['remote_sha'] = SU.remote_sha()
            except Exception as _ex:
                _log.debug('update-source GET: %s', _ex)
            return jsonify(payload)

        data = _safe_json_obj()
        repo = str(data.get('repo') or '').strip()
        branch = str(data.get('branch') or '').strip()
        ok, error, (new_repo, new_branch) = US.set_source(repo, branch)
        if not ok:
            return jsonify({'ok': False, 'error': error}), 400
        return jsonify({'ok': True, 'repo': new_repo, 'branch': new_branch,
                        'kind': US.source_kind(),
                        'hint': 'Источник сохранён — /update и автообновление '
                                'качают уже оттуда. Перезапуск не нужен.'})


    VOICE_STAY_PATH = os.path.join(_REPO_ROOT, 'config', 'voice_stay.json')

    def _voice_stay_load():
        try:
            if os.path.isfile(VOICE_STAY_PATH):
                with open(VOICE_STAY_PATH, encoding='utf-8') as f:
                    d = json.load(f) or {}
                return str(d.get('channel_id') or d.get('VOICE_CHANNEL_ID') or '').strip()
        except Exception as _ex:
            _log.debug('voice_stay load: %s', _ex)
        return str(os.environ.get('VOICE_CHANNEL_ID') or '').strip()

    def _voice_stay_save(channel_id: str):
        os.makedirs(os.path.dirname(VOICE_STAY_PATH), exist_ok=True)
        payload = {
            'channel_id': str(channel_id or '').strip(),
            'note': 'Бот заходит в этот голосовой канал при старте (main.py).',
        }
        with open(VOICE_STAY_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    @app.route('/api/bot-settings/voice-stay', methods=['GET', 'POST'])
    @login_required
    @role_required('owner')
    def api_bot_settings_voice_stay():
        """Голосовой канал 24/7: сохранить ID и (опционально) подключиться сейчас."""
        import web.app as _app
        if request.method == 'GET':
            cid = _voice_stay_load()
            return jsonify({
                'ok': True,
                'channel_id': cid,
                'bot_online': bool(_app.bot_instance),
                'demo': bool(getattr(_app, '_demo_mode', lambda: False)()),
            })

        data = _safe_json_obj()
        raw = str(data.get('channel_id') or '').strip()
        if raw and (not raw.isdigit() or len(raw) < 5 or len(raw) > 22):
            return jsonify({'ok': False, 'error': 'ID канала — только цифры Discord snowflake'}), 400
        saved = _voice_stay_save(raw)
        # Обновить in-process значение у main, если бот загружен в том же процессе
        try:
            import main as _main
            _main.VOICE_CHANNEL_ID = int(raw) if raw else None
        except Exception as _ex:
            _log.debug('voice_stay live update: %s', _ex)
        return jsonify({
            'ok': True,
            'channel_id': saved.get('channel_id') or '',
            'hint': 'Сохранено. При следующем старте main.py бот зайдёт в этот канал. '
                    '«Подключиться сейчас» — если бот уже онлайн.',
        })
