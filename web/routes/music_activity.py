# -*- coding: utf-8 -*-
"""Discord Embedded App (Activity): музыкальная панель в голосовом канале.

Встроенное приложение открывается внутри клиента Discord (iframe) и общается
с панелью через эти эндпоинты. Авторизация — не логин панели, а OAuth2-токен
Discord, который SDK передаёт приложению (Bearer-заголовок). Логика плеера —
та же, что у веб-панели /music (perform_music_action из music_panel).

Эндпоинты:
  POST /api/activity/music/token    — обменять code (SDK authorize) на access_token
  GET  /api/activity/music/state    — состояние плеера сервера
  POST /api/activity/music/control  — pause/resume/skip/shuffle/clear/volume/leave

Окружение (.env):
  ACTIVITY_CLIENT_ID, ACTIVITY_CLIENT_SECRET, ACTIVITY_REDIRECT_URI
"""
import os

from web.routes._common import _log, request, jsonify

from web.routes.music_panel import music_payload, perform_music_action, _bot, _cog


def _demo_mode():
    import web.app as _app
    return _app._demo_mode()


def _exchange_code(code, redirect_uri):
    """Обменять OAuth2 code на access_token. None — не удалось/не настроено."""
    client_id = str(os.environ.get('ACTIVITY_CLIENT_ID', '') or '').strip()
    secret = str(os.environ.get('ACTIVITY_CLIENT_SECRET', '') or '').strip()
    if not client_id or not secret:
        return None
    try:
        import requests as _rq
        r = _rq.post('https://discord.com/api/oauth2/token', data={
            'client_id': client_id,
            'client_secret': secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
            or str(os.environ.get('ACTIVITY_REDIRECT_URI', '') or '').strip(),
        }, timeout=10)
        if r.status_code == 200:
            return r.json().get('access_token')
    except Exception as _ex:
        _log.debug('music_activity: token exchange: %s', _ex)
    return None


def _activity_user(token):
    """Проверить Bearer-токен Discord → (user_id, username) или None."""
    if not token:
        return None
    try:
        import requests as _rq
        r = _rq.get('https://discord.com/api/v10/oauth2/@me',
                    headers={'Authorization': 'Bearer ' + token}, timeout=6)
        if r.status_code == 200:
            d = r.json()
            return str(d.get('id')), d.get('username')
    except Exception as _ex:
        _log.debug('music_activity: token check: %s', _ex)
    return None


def _bearer_token():
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return ''


def _demo_state():
    return {
        'success': True, 'offline': False,
        'connected': True, 'playing': True, 'paused': False,
        'channel': 'Голосовая · Музыка', 'volume': 80, 'volume_max': 100,
        'total': 3,
        'current': {'query': 'nightcore — legends never die', 'requester': 'ecobar'},
        'queue': [
            {'n': 1, 'query': 'phonk mix #42', 'requester': 'dragon'},
            {'n': 2, 'query': 'lofi hip hop radio', 'requester': 'hzdio'},
        ],
        'can_edit': True,
        'demo': True,
    }


def register(ctx):
    app = ctx.app

    @app.route('/api/activity/music/config')
    def activity_music_config():
        """Конфиг для фронтенда: client_id и redirect_uri (без секретов)."""
        redirect_uri = str(os.environ.get('ACTIVITY_REDIRECT_URI', '') or '').strip()
        if not redirect_uri:
            origin = request.headers.get('Origin') or request.host_url.rstrip('/')
            redirect_uri = origin + '/api/activity/music/token'
        return jsonify({
            'success': True,
            'client_id': str(os.environ.get('ACTIVITY_CLIENT_ID', '') or '').strip(),
            'redirect_uri': redirect_uri,
            'demo': _demo_mode(),
        })

    @app.route('/api/activity/music/token', methods=['POST'])
    def activity_music_token():
        data = request.get_json(silent=True) or {}
        code = str(data.get('code') or '').strip()
        redirect_uri = str(data.get('redirect_uri') or '').strip()
        if _demo_mode():
            return jsonify({'success': True, 'access_token': 'demo'})
        if not code:
            return jsonify({'success': False, 'error': 'Нет code'}), 400
        token = _exchange_code(code, redirect_uri)
        if not token:
            return jsonify({'success': False,
                            'error': 'Не удалось обменять code. Проверьте ACTIVITY_CLIENT_ID/SECRET и redirect URI.'}), 401
        return jsonify({'success': True, 'access_token': token})

    @app.route('/api/activity/music/state')
    def activity_music_state():
        token = _bearer_token()
        gid = request.args.get('guild_id') or ctx.active_guild_id()
        if _demo_mode() and token == 'demo':
            return jsonify(_demo_state())
        user = _activity_user(token) if token else None
        if user is None:
            return jsonify({'success': False, 'offline': True,
                            'error': 'Не удалось подтвердить пользователя Discord.'}), 401
        bot = _bot()
        if bot is None:
            return jsonify({'success': False, 'offline': True,
                            'error': 'Бот офлайн — очередь недоступна.'}), 503
        return jsonify(music_payload(gid, bot))

    @app.route('/api/activity/music/control', methods=['POST'])
    def activity_music_control():
        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '')
        gid = data.get('guild_id') or ctx.active_guild_id()
        token = _bearer_token()
        if _demo_mode() and token == 'demo':
            # демо: управление «применяется» локально — отдаём то же состояние
            return jsonify(_demo_state())
        user = _activity_user(token) if token else None
        if user is None:
            return jsonify({'success': False, 'offline': True,
                            'error': 'Не удалось подтвердить пользователя Discord.'}), 401
        bot = _bot()
        if bot is None or _cog(bot) is None:
            return jsonify({'success': False, 'offline': True,
                            'error': 'Бот офлайн — управление недоступно.'}), 503
        body, status = perform_music_action(bot, int(gid), action, data)
        return jsonify(body), status
