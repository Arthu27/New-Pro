# -*- coding: utf-8 -*-
"""Менеджер вебхуков в панели (идея #9).

Тот же файл data/webhooks_<gid>.json и тот же формат записи, что у кога
/webhook — созданные из Discord видны здесь и наоборот. Создание/отправка/
удаление исполняются в событийном цикле бота (run_coroutine_threadsafe),
как и остальные Discord-вызовы панели.

Безопасность: URL с секретным токеном наружу не уходит — в списке он
маскируется. Чтение mod+, запись admin+ (manage_webhooks у кога).
"""

import asyncio

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, os, json,
)


def hooks_file(gid):
    """Путь того же файла, что использует ког."""
    return f'data/webhooks_{gid}.json'


def load_hooks(gid):
    """Записи {wid: {...}}. Битый/не-словарь JSON — как пусто."""
    f = hooks_file(gid)
    if not os.path.exists(f):
        return {}
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as _ex:
        _log.debug("load_hooks(): битый файл, считаем пустым: %s", _ex)
        return {}
    return data if isinstance(data, dict) else {}


def save_hooks(gid, data):
    os.makedirs('data', exist_ok=True)
    tmp = hooks_file(gid) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    os.replace(tmp, hooks_file(gid))


def mask_url(url):
    """https://discord.com/api/webhooks/123/TOKEN → .../123/•••"""
    url = str(url or '')
    head, _, _tail = url.rpartition('/')
    return (head + '/•••') if head else '•••'


def hooks_payload(gid):
    hooks = []
    for wid, wh in load_hooks(gid).items():
        hooks.append({
            'id': str(wh.get('id') or wid),
            'name': str(wh.get('name') or ''),
            'channel_id': str(wh.get('channel_id') or ''),
            'channel_name': str(wh.get('channel_name') or ''),
            'url_masked': mask_url(wh.get('url')),
        })
    hooks.sort(key=lambda h: (h['channel_name'], h['name']))
    return {'success': True, 'hooks': hooks, 'total': len(hooks)}


async def deliver_webhook(url, content, username):
    """Отправка через aiohttp+discord.Webhook — способ самого кога."""
    import aiohttp
    import discord
    async with aiohttp.ClientSession() as sess:
        wh = discord.Webhook.from_url(url, session=sess)
        await wh.send(content=content, username=username or None)


def _run(bot, coro, timeout=15):
    """Синхронно дождаться корутины в цикле бота (паттерн community.py)."""
    fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return fut.result(timeout=timeout)


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/webhooks')
    @login_required
    @role_required('mod')
    def webhooks_page():
        return render_template('webhooks.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/webhooks')
    @login_required
    @role_required('mod')
    def api_webhooks_list():
        return jsonify(hooks_payload(ctx.active_guild_id()))

    @app.route('/api/webhooks/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_webhooks_create():
        """Создать вебхук в канале — та же запись, что у /webhook создать."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        import web.app as _app
        bot = _app.bot_instance
        if bot is None:
            return jsonify({'success': False, 'error': 'Бот офлайн'}), 503
        data = request.get_json(silent=True) or {}
        name = str(data.get('name') or '').strip()
        if not name or len(name) > 80:
            return jsonify({'success': False, 'error': 'имя — 1..80 символов'}), 400
        try:
            ch_id = int(data.get('channel_id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'channel_id — число'}), 400
        gid = _gid
        guild = bot.get_guild(gid)
        ch = guild.get_channel(ch_id) if guild else None
        if ch is None:
            return jsonify({'success': False, 'error': f'канал {ch_id} не найден в кэше'}), 404

        async def do_create():
            return await ch.create_webhook(name=name)

        try:
            wh = _run(bot, do_create())
        except Exception as _ex:
            _log.debug("api_webhooks_create(): Discord отказал: %s", _ex)
            return jsonify({'success': False,
                            'error': f'Discord не дал создать вебхук: {_ex}'}), 502
        hooks = load_hooks(gid)
        hooks[str(wh.id)] = {
            'id': str(wh.id), 'name': name,
            'url': wh.url, 'channel_id': str(ch.id),
            'channel_name': ch.name,
        }
        save_hooks(gid, hooks)
        return jsonify(hooks_payload(gid))

    @app.route('/api/webhooks/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_webhooks_delete():
        """Удалить: Discord-хук стирается по возможности, запись — всегда."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        wid = str(data.get('webhook_id') or '')
        gid = _gid
        hooks = load_hooks(gid)
        if wid not in hooks:
            return jsonify({'success': False, 'error': f'вебхук {wid} не найден'}), 404
        gone = hooks.pop(wid)
        import web.app as _app
        bot = _app.bot_instance
        if bot is not None and gone.get('channel_id'):
            guild = bot.get_guild(gid)
            ch = guild.get_channel(int(gone['channel_id'])) if guild else None
            if ch is not None:
                async def do_delete():
                    import discord
                    whs = await ch.webhooks()
                    wh = discord.utils.get(whs, id=int(wid))
                    if wh:
                        await wh.delete()
                try:
                    _run(bot, do_delete())
                except Exception as _ex:
                    _log.debug("api_webhooks_delete(): Discord-удаление не вышло: %s", _ex)
        save_hooks(gid, hooks)
        return jsonify(hooks_payload(gid))

    @app.route('/api/webhooks/send', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_webhooks_send():
        """Тестовое сообщение через вебхук (как /webhook отправить)."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        import web.app as _app
        bot = _app.bot_instance
        if bot is None:
            return jsonify({'success': False, 'error': 'Бот офлайн'}), 503
        data = request.get_json(silent=True) or {}
        wid = str(data.get('webhook_id') or '')
        message = str(data.get('message') or '').strip()
        if not message:
            return jsonify({'success': False, 'error': 'пустое сообщение'}), 400
        gid = _gid
        hooks = load_hooks(gid)
        wh = hooks.get(wid)
        if not wh:
            return jsonify({'success': False, 'error': f'вебхук {wid} не найден'}), 404
        try:
            _run(bot, deliver_webhook(wh.get('url'), message, wh.get('name')))
        except Exception as _ex:
            _log.debug("api_webhooks_send(): отправка упала: %s", _ex)
            return jsonify({'success': False,
                            'error': f'Discord не принял сообщение: {_ex}'}), 502
        return jsonify({'success': True, 'sent_to': str(wh.get('name', wid))})
