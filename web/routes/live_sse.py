# -*- coding: utf-8 -*-
"""SSE-эндпоинт живых обновлений панели (services.live_bus).

Браузер открывает EventSource на /api/live?topics=g<gid>:*,dashboard и получает
короткое событие "tick" с топиком, когда данные реально поменялись. Это замена
опросу по таймеру: страница перечитывает себя только по сигналу.

Идёт через тот же Flask/порт/туннель, что и вся панель (обычный long-lived
HTTP-ответ), поэтому работает за доменом/cloudflared без отдельного порта.
Если SSE недоступен — фронт тихо остаётся на редком polling.
"""
import json
import queue
import time

from web.routes._common import _log, request, Response, jsonify

from services import live_bus


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required

    def _allowed_topics(raw, guild_id):
        """Список масок по запросу, всегда включая общий и серверный префикс."""
        out = set()
        for part in str(raw or '').split(','):
            p = part.strip()
            if p:
                out.add(p)
        if guild_id:
            out.add(f'g{guild_id}:*')
        out.add('dashboard')
        out.add('global')
        return list(out)

    @app.route('/api/live')
    @login_required
    def api_live_stream():
        try:
            guild_id = request.args.get('gid', '').strip()
            topics = _allowed_topics(request.args.get('topics', ''), guild_id)
        except Exception as ex:  # noqa: BLE001
            _log.debug('live/sse: разбор запроса: %s', ex)
            guild_id = ''
            topics = ['*']

        q, unsubscribe = live_bus.subscribe(topics)

        def _stream():
            # стартовое событие: пусть клиент сразу нарисует текущие данные
            yield 'retry: 5000\n'
            yield 'event: hello\ndata: {}\n\n'
            try:
                while True:
                    try:
                        topic = q.get(timeout=20)
                    except queue.Empty:
                        # комментарий-keepalive — прокси/туннель не рвут соединение
                        yield ': ping\n\n'
                        continue
                    except GeneratorExit:
                        break
                    payload = json.dumps({'topic': topic}, ensure_ascii=False)
                    yield f'event: tick\ndata: {payload}\n\n'
            finally:
                unsubscribe()

        resp = Response(_stream(), mimetype='text/event-stream')
        resp.headers['Cache-Control'] = 'no-cache, no-transform'
        resp.headers['X-Accel-Buffering'] = 'no'   # nginx/cloudflared не буферизуют
        resp.headers['Connection'] = 'keep-alive'
        return resp

    @app.route('/api/live/status')
    @login_required
    def api_live_status():
        return jsonify({'success': True,
                        'subscribers': live_bus.subscriber_count(),
                        'transport': 'sse'})
