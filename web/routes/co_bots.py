# -*- coding: utf-8 -*-
"""Совместные боты: основной + Event (войсе-stay).

Токен Event-бота пишется только в локальный .env. Канал/stay —
config/event_voice_stay.json. Запуск обоих — start.bat → main.py.
"""
from web.routes._common import (
    _safe_json_obj, _run_async, _log,
    render_template, session, request, jsonify,
    os, json,
)


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/co-bots')
    @login_required
    @role_required('owner')
    def co_bots_page():
        return render_template(
            'co_bots.html',
            role=session.get('role'),
            username=session.get('username'),
        )

    @app.route('/api/co-bots', methods=['GET'])
    @login_required
    @role_required('owner')
    def api_co_bots_get():
        import web.app as _app
        from services.event_voice_bot import event_bot_status
        from services.env_file import mask_secret

        main = {
            'online': False,
            'name': '',
            'id': '',
            'token_set': bool((os.environ.get('TOKEN') or '').strip()),
            'token_hint': mask_secret(os.environ.get('TOKEN') or ''),
            'voice_channel_id': '',
            'voice_connected': False,
        }
        bot = getattr(_app, 'bot_instance', None)
        if bot is not None and not getattr(bot, 'is_closed', lambda: True)():
            try:
                main['online'] = bool(bot.is_ready()) if hasattr(bot, 'is_ready') else True
            except Exception:
                main['online'] = True
            u = getattr(bot, 'user', None)
            if u is not None:
                main['name'] = str(getattr(u, 'name', '') or '')
                try:
                    main['id'] = str(u.id)
                except Exception:
                    pass
            for v in list(getattr(bot, 'voice_clients', None) or []):
                try:
                    if v.is_connected():
                        main['voice_connected'] = True
                        main['voice_channel_id'] = str(
                            getattr(getattr(v, 'channel', None), 'id', '') or '')
                        break
                except Exception:
                    pass
        if not main['voice_channel_id']:
            try:
                repo = os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))))
                p = os.path.join(repo, 'config', 'voice_stay.json')
                if os.path.isfile(p):
                    with open(p, encoding='utf-8') as fh:
                        d = json.load(fh) or {}
                    main['voice_channel_id'] = str(d.get('channel_id') or '')
            except Exception as _ex:
                _log.debug('co-bots main voice cfg: %s', _ex)
            env_v = (os.environ.get('VOICE_CHANNEL_ID') or '').strip()
            if env_v and env_v not in ('0', 'none'):
                main['voice_channel_id'] = env_v

        return jsonify({
            'ok': True,
            'main': main,
            'event': event_bot_status(),
            'hint': 'Оба бота стартуют одной командой: start.bat '
                    '(main.py поднимает основной + Event, если токен задан).',
        })

    @app.route('/api/co-bots/event', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_co_bots_event_save():
        """Сохранить токен (в .env) и/или канал/stay (JSON)."""
        from services.env_file import upsert_env_keys
        from services.event_voice_bot import (
            save_event_voice_cfg, event_bot_status, event_bot_token)

        data = _safe_json_obj() or {}
        token = data.get('token', None)
        # не перезаписываем токен, если поле оставили пустым «не менять»
        token_clear = bool(data.get('token_clear'))
        channel_id = data.get('channel_id', None)
        stay = data.get('stay_enabled', None)

        if token is not None and str(token).strip():
            rep = upsert_env_keys({'EVENT_BOT_TOKEN': str(token).strip()})
            if not rep.get('ok'):
                return jsonify({'ok': False, 'error': rep.get('error') or 'env'}), 400
        elif token_clear:
            rep = upsert_env_keys({'EVENT_BOT_TOKEN': ''})
            if not rep.get('ok'):
                return jsonify({'ok': False, 'error': rep.get('error') or 'env'}), 400

        if channel_id is not None or stay is not None:
            raw_cid = None if channel_id is None else str(channel_id).strip()
            if raw_cid is not None and raw_cid and (
                    not raw_cid.isdigit() or len(raw_cid) < 5 or len(raw_cid) > 22):
                return jsonify({
                    'ok': False,
                    'error': 'ID канала — Discord snowflake (цифры)',
                }), 400
            stay_b = None if stay is None else bool(stay)
            save_event_voice_cfg(
                channel_id=raw_cid if channel_id is not None else None,
                stay_enabled=stay_b)

        st = event_bot_status()
        need_restart = bool(token is not None and str(token or '').strip()) or token_clear
        return jsonify({
            'ok': True,
            'event': st,
            'token_set': bool(event_bot_token()),
            'hint': ('Токен сохранён в .env. Перезапусти start.bat, '
                     'чтобы Event-бот поднялся с новым токеном.')
            if need_restart else
            'Сохранено. Канал/stay применятся на лету, если Event-бот онлайн.',
            'need_restart': need_restart,
        })

    @app.route('/api/co-bots/event/voice-join', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_co_bots_event_voice_join():
        from services.event_voice_bot import (
            ensure_voice_joined, get_event_client, event_bot_status,
            _resolve_event_voice_channel_id)

        data = _safe_json_obj() or {}
        raw = str(data.get('channel_id') or '').strip()
        cid = int(raw) if raw.isdigit() else _resolve_event_voice_channel_id()
        client = get_event_client()
        if client is None or client.is_closed():
            return jsonify({
                'ok': False,
                'error': 'Event-бот офлайн. Задай EVENT_BOT_TOKEN и запусти start.bat.',
                'event': event_bot_status(),
            }), 503
        ok, msg = _run_async(ensure_voice_joined(client, cid))
        return jsonify({
            'ok': bool(ok),
            'message' if ok else 'error': msg,
            'event': event_bot_status(),
        }), (200 if ok else 400)
