# -*- coding: utf-8 -*-
"""Музыка в панели (идея #2): пульт плеера сервера.

Читает очередь и состояние голосового клиента прямо из кога (in-memory),
мутации зовут РОВНО те же операции, что и команды бота: pause/resume/stop
голосового клиента, чистые shuffle_queue/remove_track из cogs.music_cog,
очистка очереди — тем же присвоением, что делают !leave и !clearqueue.

Чтение (страница и состояние) — mod+. Управление — admin+, как
!clearqueue (manage_guild) в коге.
"""
import asyncio

from flask import has_request_context

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from cogs.music_cog import remove_track, shuffle_queue

_VOLUME_MIN = 0
_VOLUME_MAX = 200


def _bot():
    import web.app as _app
    return _app.bot_instance


def _cog(bot):
    return bot.get_cog('MusicCog') if bot is not None else None


def _run(bot, coro):
    """Синхронно исполнить корутину в цикле бота (как в панели вебхуков)."""
    fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return fut.result(timeout=8)


def _requester_name(req):
    if req is None:
        return ''
    name = getattr(req, 'display_name', None)
    if name:
        return str(name)
    return str(req)


def music_payload(gid, bot):
    """Единая картина плеера для панели: и GET, и ответы мутаций."""
    cog = _cog(bot)
    if cog is None:
        return {'success': False, 'offline': True, 'error': 'Музыкальный модуль не загружен.'}
    guild = bot.get_guild(int(gid))
    vc = getattr(guild, 'voice_client', None) if guild else None
    queue = cog.get_queue(int(gid)) or []
    playing = bool(vc and vc.is_playing())
    paused = bool(vc and vc.is_paused())
    connected = bool(vc and getattr(vc, 'is_connected', lambda: True)())
    volume = None
    if vc is not None:
        src = getattr(vc, 'source', None)
        volume = int(src.volume * 100) if src is not None else 100
    return {
        'success': True,
        'offline': False,
        'connected': connected,
        'playing': playing,
        'paused': paused,
        'channel': str(getattr(getattr(vc, 'channel', None), 'name', '') or ''),
        'volume': volume,
        'volume_max': _VOLUME_MAX,
        'total': len(queue),
        'current': ({
            'query': str(queue[0].get('query', '')),
            'requester': _requester_name(queue[0].get('requester')),
        } if queue else None),
        'queue': [{
            'n': i,
            'query': str(song.get('query', '')),
            'requester': _requester_name(song.get('requester')),
        } for i, song in enumerate(queue, 1)],
        'can_edit': has_request_context() and session.get('role') in ('admin', 'owner'),
    }


def _or_offline(gid):
    """(bot, cog, payload) либо готовый ответ 503."""
    bot = _bot()
    cog = _cog(bot)
    if bot is None or cog is None:
        return None, None, ({'success': False, 'offline': True,
                             'error': 'Бот офлайн — очередь недоступна.'}, 503)
    return bot, cog, None


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/music')
    @login_required
    @role_required('mod')
    def music_page():
        return render_template('music.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/music/state')
    @login_required
    @role_required('mod')
    def api_music_state():
        gid = int(ctx.active_guild_id())
        bot = _bot()
        if bot is None:
            import web.app as _app
            if _app._demo_mode():
                # демо: играет трек, два в очереди — плеер живой в превью
                return jsonify({
                    'success': True, 'offline': False,
                    'connected': True, 'playing': True, 'paused': False,
                    'channel': 'Голосовая · Музыка', 'volume': 80, 'volume_max': 100,
                    'total': 3,
                    'current': {'query': 'nightcore — legends never die', 'requester': 'ecobar'},
                    'queue': [
                        {'n': 1, 'query': 'phonk mix #42', 'requester': 'dragon'},
                        {'n': 2, 'query': 'lofi hip hop radio', 'requester': 'hzdio'},
                    ],
                    'can_edit': has_request_context() and session.get('role') in ('admin', 'owner'),
                })
            return jsonify({'success': False, 'offline': True,
                            'error': 'Бот офлайн — очередь недоступна.'}), 503
        return jsonify(music_payload(gid, bot))

    @app.route('/api/music/control', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_music_control():
        """Транспорт: те же операции, что pause/resume/skip/shuffle/leave/volume."""
        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '')
        bot, cog, offline = _or_offline(ctx.active_guild_id())
        if offline:
            return jsonify(offline[0]), offline[1]
        gid = int(ctx.active_guild_id())
        guild = bot.get_guild(gid)
        vc = getattr(guild, 'voice_client', None) if guild else None

        if action == 'pause':
            if not (vc and vc.is_playing()):
                return jsonify({'success': False, 'error': 'Сейчас ничего не играет.'}), 409
            vc.pause()
        elif action == 'resume':
            if not (vc and vc.is_paused()):
                return jsonify({'success': False, 'error': 'Сейчас нет трека на паузе.'}), 409
            vc.resume()
        elif action == 'skip':
            if not (vc and vc.is_playing()):
                return jsonify({'success': False, 'error': 'Сейчас ничего не играет.'}), 409
            vc.stop()
        elif action == 'shuffle':
            queue = cog.get_queue(gid)
            if len(queue) < 2:
                return jsonify({'success': False,
                                'error': 'В очереди должно быть минимум 2 трека.'}), 409
            cog.queues[gid] = shuffle_queue(queue)
        elif action == 'clear':
            cog.queues[gid] = []
        elif action == 'volume':
            try:
                vol = int(data.get('volume'))
            except (TypeError, ValueError):
                return jsonify({'success': False,
                                'error': 'Громкость должна быть целым числом.'}), 400
            if vol < _VOLUME_MIN or vol > _VOLUME_MAX:
                return jsonify({'success': False,
                                'error': 'Уровень громкости должен быть от 0 до 200%.'}), 400
            if not (vc and getattr(vc, 'source', None)):
                return jsonify({'success': False, 'error': 'Сейчас ничего не играет.'}), 409
            vc.source.volume = vol / 100
        elif action == 'leave':
            if not vc:
                return jsonify({'success': False,
                                'error': 'Бот сейчас не в голосовом канале.'}), 409
            try:
                _run(bot, vc.disconnect())
            except Exception as exc:
                _log.debug('music leave: %s', exc)
                return jsonify({'success': False,
                                'error': 'Не получилось отключиться от канала.'}), 500
            cog.queues[gid] = []
        else:
            return jsonify({'success': False, 'error': 'Неизвестное действие.'}), 400
        return jsonify(music_payload(gid, bot))

    @app.route('/api/music/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_music_remove():
        data = request.get_json(silent=True) or {}
        bot, cog, offline = _or_offline(ctx.active_guild_id())
        if offline:
            return jsonify(offline[0]), offline[1]
        gid = int(ctx.active_guild_id())
        queue = cog.get_queue(gid)
        ok, err, removed = remove_track(queue, data.get('index'))
        if not ok:
            code = 400 if 'целым числом' in err else 404
            return jsonify({'success': False, 'error': err}), code
        body = music_payload(gid, bot)
        body['removed'] = {'query': str(removed.get('query', ''))}
        return jsonify(body)
