# -*- coding: utf-8 -*-
"""Архиватор каналов (идеи #171-175): /archive в браузере.

Рендер общий с когом: cogs/archive.py Archive.generate_html — тот самый
HTML, что присылает команда /archive. TXT-бэкап повторяет /backup-channel
построчно («[гггг-мм-дд чч:мм:сс] автор: текст»); имена файлов теми же
шаблонами и тем же UTC, что у команд. Попутно в коге подчищены три
опечатки: «Всего Сообщение» → «Всего сообщений», турецкий атрибут
«низ="image"» → alt, и бессмысленное «message yedaddndi.» в ответе
backup-channel → «сообщений скопировано.».

- HTML-архив — канал/лимит как у /archive (manage_messages → mod+), телом
  ответа готовый файл, счётчик — в X-Archived-Count.
- TXT-бэкап — как /backup-channel (administrator → admin+), тот же формат
  строк и имя файла backup_<канал>_<ггггммдд>.txt.
- Предпросмотр — те же сообщения, что пойдут в файл: до 20 свежих строк,
  плюс счётчики сообщений/авторов/вложений/картинок.
- Каналы — живые текстовые каналы сервера через bot_instance; без бота —
  честный 409 «Бот не работает» (слова _run_async), без заглушек.
- CSV тех же сообщений (BOM, ;) — для таблиц и сверок.

Лимиты: дефолты команд (100 для HTML, 500 для TXT), панельный потолок 2000,
мусор сворачивается в дефолт — команда slash сама не даёт ерунды, панель
страхует форму.
"""
from datetime import datetime, timezone

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
)

from cogs.archive import Archive

ERR_BOT = 'Бот не работает'          # слова _run_async из _common
ERR_CHANNEL = 'Канал не найден'
DONE_FMT = '{n} сообщений заархивировано.'  # слова ответа /archive
MAX_LIMIT = 2000
DEFAULT_LIMIT = 100    # дефолт /archive
BACKUP_LIMIT = 500     # дефолт /backup-channel

_archiver = Archive(None)  # generate_html не трогает self.bot


def _limit(raw, default):
    """Лимит формы: мусор → дефолт команды, дальше кламп 1..2000."""
    try:
        n = int(str(raw if raw is not None else '').strip())
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_LIMIT))


async def _fetch_msgs(bot, gid, channel_id, limit):
    """Тот же обход, что у команды: history(limit=..., oldest_first=True).

    Возвращает (messages, channel); (None, None) — сервер потерян,
    (None, guild) — канал не найден.
    """
    guild = bot.get_guild(int(gid))
    if guild is None:
        return None, None
    channels = list(getattr(guild, 'text_channels', None)
                    or getattr(guild, 'channels', []))
    channel = next((c for c in channels if str(c.id) == str(channel_id)), None)
    if channel is None:
        return None, guild
    messages = [m async for m in channel.history(limit=limit,
                                                 oldest_first=True)]
    return messages, channel


def _stats(messages):
    """Счётчики превью: сообщения, авторы, вложения, картинки."""
    atts = [a for m in messages for a in getattr(m, 'attachments', [])]
    return {
        'count': len(messages),
        'authors': len({str(m.author) for m in messages}),
        'attachments': len(atts),
        'images': sum(1 for a in atts
                      if (getattr(a, 'content_type', '') or '').startswith('image')),
    }


def _rows(messages):
    """До 20 строк превью — из того же списка, что уйдёт в файл."""
    rows = []
    for m in messages[-20:]:
        rows.append({
            'author': str(m.author),
            'ts': m.created_at.strftime('%m-%d %H:%M'),
            'text': (m.content or '')[:120],
            'atts': len(getattr(m, 'attachments', [])),
        })
    return rows


def preview_view(bot_lookup, gid, channel_id, limit_raw):
    """Превью + счётчики. bot_lookup — функция, отдающая bot (или None)."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    limit = _limit(limit_raw, DEFAULT_LIMIT)
    try:
        messages, channel = _run_async(
            _fetch_msgs(bot, gid, channel_id, limit))
    except RuntimeError as exc:
        _log.debug('archive preview: %s', exc)
        return False, ERR_BOT, 409, None
    except Exception as exc:  # сеть Discord мигнула — честно в лог
        _log.debug('archive preview fetch: %s', exc)
        return False, ERR_CHANNEL, 404, None
    if messages is None:  # канал не нашёлся (или сервер уронили)
        return False, ERR_CHANNEL, 404, None
    return True, '', 200, {
        'channel': channel.name,
        'channel_id': str(channel.id),
        'limit': limit,
        'stats': _stats(messages),
        'rows': _rows(messages),
        'note': DONE_FMT.format(n=len(messages)),
    }


def channels_view(bot_lookup, gid):
    """Живые текстовые каналы гильдии для селекта."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    try:
        guild = bot.get_guild(int(gid))
    except Exception as exc:
        _log.debug('archive channels: %s', exc)
        return False, ERR_BOT, 409, None
    if guild is None:
        return False, ERR_CHANNEL, 404, None
    channels = [{'id': str(c.id), 'name': c.name}
                for c in getattr(guild, 'text_channels', [])]
    return True, '', 200, {'channels': channels}


def _utc_now():
    """Тот же приём, что в команде: UTC-время без tzinfo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def html_name(channel_name):
    """Имя файла тем шаблоном, что у /archive."""
    return f'archive_{channel_name}_{_utc_now().strftime("%Y%m%d_%H%M%S")}.html'


def html_flow(bot_lookup, gid, channel_id, limit_raw):
    """HTML-архив: generate_html кога + имя файла команды."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    limit = _limit(limit_raw, DEFAULT_LIMIT)
    try:
        messages, channel = _run_async(
            _fetch_msgs(bot, gid, channel_id, limit))
    except Exception as exc:
        _log.debug('archive html fetch: %s', exc)
        return False, ERR_BOT, 409, None
    if messages is None:
        return False, ERR_CHANNEL, 404, None
    html = _archiver.generate_html(messages, channel)
    resp = Response(html.encode('utf-8'),
                    mimetype='text/html; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f'attachment; filename={html_name(channel.name)}')
    resp.headers['X-Archived-Count'] = str(len(messages))
    return True, '', 200, resp


def txt_line(m):
    """Строка бэкапа в точности как в backup_channel."""
    ts = m.created_at.strftime('%Y-%m-%d %H:%M:%S')
    return f'[{ts}] {m.author}: {m.content}'


def txt_name(channel_name):
    """Имя файла тем шаблоном, что у /backup-channel."""
    return f'backup_{channel_name}_{_utc_now().strftime("%Y%m%d")}.txt'


def txt_flow(bot_lookup, gid, channel_id, limit_raw):
    """TXT-бэкап: построчный формат и лимит-дефолт /backup-channel."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    limit = _limit(limit_raw, BACKUP_LIMIT)
    try:
        messages, channel = _run_async(
            _fetch_msgs(bot, gid, channel_id, limit))
    except Exception as exc:
        _log.debug('archive txt fetch: %s', exc)
        return False, ERR_BOT, 409, None
    if messages is None:
        return False, ERR_CHANNEL, 404, None
    content = '\n'.join(txt_line(m) for m in messages)
    resp = Response(content.encode('utf-8'),
                    mimetype='text/plain; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f'attachment; filename={txt_name(channel.name)}')
    resp.headers['X-Archived-Count'] = str(len(messages))
    return True, '', 200, resp


def csv_rows(messages):
    return [(m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
             str(m.author), m.content or '',
             len(getattr(m, 'attachments', []))) for m in messages]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def csv_flow(bot_lookup, gid, channel_id, limit_raw):
    """CSV тех же сообщений — выгрузка для таблиц."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    limit = _limit(limit_raw, DEFAULT_LIMIT)
    try:
        messages, channel = _run_async(
            _fetch_msgs(bot, gid, channel_id, limit))
    except Exception as exc:
        _log.debug('archive csv fetch: %s', exc)
        return False, ERR_BOT, 409, None
    if messages is None:
        return False, ERR_CHANNEL, 404, None
    body = '\ufeff' + 'timestamp;author;content;attachments\n'
    body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                      for row in csv_rows(messages))
    resp = Response(body, mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f'attachment; filename=archive_{channel.name}_{gid}.csv')
    resp.headers['X-Archived-Count'] = str(len(messages))
    return True, '', 200, resp


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _bot():
        import web.app as appmod
        bot = appmod.bot_instance
        return bot if bot is not None and getattr(bot, 'loop', None) else None

    def _respond(flow, gid, *args):
        ok, err, code, payload = flow(_bot, gid, *args)
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return payload

    @app.route('/archive')
    @login_required
    @role_required('mod')
    def archive_page():
        return render_template('archive.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_txt=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/archive/channels')
    @login_required
    @role_required('mod')
    def api_archive_channels(gid):
        ok, err, code, payload = channels_view(_bot, gid)
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/archive/preview')
    @login_required
    @role_required('mod')
    def api_archive_preview(gid):
        ok, err, code, payload = preview_view(
            _bot, gid, request.args.get('channel'), request.args.get('limit'))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/archive/html')
    @login_required
    @role_required('mod')
    def api_archive_html(gid):
        return _respond(html_flow, gid, request.args.get('channel'),
                        request.args.get('limit'))

    @app.route('/api/guild/<gid>/archive/txt')
    @login_required
    @role_required('admin')
    def api_archive_txt(gid):
        return _respond(txt_flow, gid, request.args.get('channel'),
                        request.args.get('limit'))

    @app.route('/api/guild/<gid>/archive/csv')
    @login_required
    @role_required('mod')
    def api_archive_csv(gid):
        return _respond(csv_flow, gid, request.args.get('channel'),
                        request.args.get('limit'))
