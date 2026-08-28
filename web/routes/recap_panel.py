# -*- coding: utf-8 -*-
"""Рекап канала (идеи #111-115): «что пропустил за ночь» — из панели.

Вся арифметика — чистые функции cogs/recap.py без переписываний:
normalize_message / content_words / reaction_score / build_recap /
recap_embed_fields; заголовок и «тихое» описание — как в _do_recap,
период валидируем его же правилом 1..720 с его же текстом.

Выборка истории — через цикл бота (_run_async), те же limit=1000 и after,
что у команды /recap. Офлайн — честный 409, а не фальшивые нули.

Сравнение окон: тот же build_recap с now, сдвинутым на период назад —
окно [N-2H, N-H) считается его же кодом; пул общий (подписано).

Чтение — mod+, отправка эмбеда в канал — admin+ (это постинг от имени бота).
CSV — BOM + точка с запятой, как остальные выгрузки.
"""
from datetime import datetime, timedelta, timezone

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
    discord,
)

from cogs import recap as RC
from services import text_format as tf

UTC = timezone.utc

HOURS_MIN = 1
HOURS_MAX = 24 * 30  # правило кога: 720 часов = 30 дней
HOURS_RULE_TEXT = 'Период — от 1 до 720 часов (30 дней).'
HISTORY_LIMIT = 1000  # лимит выборки команды /recap
PRESETS = (24, 24 * 7)


# ─────────────────────────────────────────────────────────────────────
# #111: период и канал
# ─────────────────────────────────────────────────────────────────────
def validate_hours(value):
    """Период с запроса — правило /recap 1..720 его же словами."""
    try:
        hours = int(str(value or '').strip())
    except (TypeError, ValueError):
        return False, HOURS_RULE_TEXT, 0
    if not HOURS_MIN <= hours <= HOURS_MAX:
        return False, HOURS_RULE_TEXT, 0
    return True, '', hours


def _guild(bot, gid):
    try:
        return bot.get_guild(int(gid)) if bot else None
    except Exception as _ex:
        _log.debug('recap: guild %s: %s', gid, _ex)
        return None


def find_channel(guild, channel_id):
    """Текстовый канал по ID; у него должна быть история (как у команды)."""
    try:
        cid = int(str(channel_id or '').strip())
    except (TypeError, ValueError):
        return None
    channel = guild.get_channel(cid) if guild else None
    if channel is None or not hasattr(channel, 'history'):
        return None
    return channel


# ─────────────────────────────────────────────────────────────────────
# #112: сборка 1:1 с /recap + сравнение с предыдущим окном (#115)
# ─────────────────────────────────────────────────────────────────────
def fetch_pool(channel, hours, now):
    """История канала циклом бота. Пул на два окна, limit/after — как у кога."""
    after = now - timedelta(hours=hours * 2)

    async def _collect():
        out = []
        async for msg in channel.history(limit=HISTORY_LIMIT, after=after):
            out.append(msg)
        return out
    return _run_async(_collect(), timeout=30)


def pack_recap(pool, hours, now):
    """Оба окна из готового пула — каждое через build_recap кога.

    build_recap отсекает только старьё (ts < since) и не режет по «now»,
    поэтому предыдущему окну отдаём честный срез [N-2H, N-H): без меток
    туда не кладём — ког такие считает только в текущем окне.
    """
    cur = RC.build_recap(pool, hours=hours, now=now)
    edge = now - timedelta(hours=hours)
    start = edge - timedelta(hours=hours)
    prev_pool = []
    for raw in pool or []:
        ts = RC.normalize_message(raw).get('created_at')
        if ts is not None and start <= ts < edge:
            prev_pool.append(raw)
    prev = RC.build_recap(prev_pool, hours=hours, now=edge)
    return {'now': now, 'cur': cur, 'prev': prev,
            'compare': compare_view(cur, prev), 'scanned': len(pool)}


def collect_recap(channel, hours, now=None):
    """Выборка истории + оба окна; now нужен, чтобы fetch и сборка совпали."""
    now = now or datetime.now(UTC)
    pool = fetch_pool(channel, hours, now)
    return pack_recap(pool, hours, now)


def compare_view(cur, prev):
    """Дельты окна к предыдущему такому же — для пульса канала."""
    return {
        'cur_total': cur['total'], 'prev_total': prev['total'],
        'delta_total': cur['total'] - prev['total'],
        'cur_authors': cur['unique_authors'], 'prev_authors': prev['unique_authors'],
        'delta_authors': cur['unique_authors'] - prev['unique_authors'],
    }


# ─────────────────────────────────────────────────────────────────────
# #113: предпросмотр эмбеда 1:1 с ответом бота
# ─────────────────────────────────────────────────────────────────────
def embed_spec(channel_name, recap, hours):
    """Заголовок, «тихое» описание и поля — как в _do_recap кога."""
    title = f'Рекап #{channel_name} · {tf.spell(hours, "час", "часа", "часов")}'
    if recap['total'] == 0:
        return {'title': title,
                'description': 'За период тихо — сообщений не было.', 'fields': []}
    fields = [{'name': name, 'value': tf.clamp_text(value, 1024),
               'inline': name in ('Сообщений', 'Участников', 'Пик активности')}
              for name, value in RC.recap_embed_fields(recap, hours)]
    return {'title': title, 'description': '', 'fields': fields}


# ─────────────────────────────────────────────────────────────────────
# #115: выгрузка
# ─────────────────────────────────────────────────────────────────────
def recap_csv_rows(channel_name, pack, hours):
    """Строки выгрузки: поля эмбеда без markdown-звёзд + сравнение окон."""
    cur, cmp = pack['cur'], pack['compare']
    rows = [
        ('Канал', f'#{channel_name}'),
        ('Период (часов)', str(hours)),
        ('Просмотрено сообщений в истории', str(pack['scanned'])),
    ]
    for name, value in RC.recap_embed_fields(cur, hours):
        rows.append((name, str(value).replace('**', '')))
    rows.append(('Сравнение: сообщений окном раньше', str(cmp['prev_total'])))
    rows.append(('Сравнение: разница', f"{cmp['delta_total']:+d}"))
    rows.append(('Сравнение: участников окном раньше', str(cmp['prev_authors'])))
    rows.append(('Сравнение: разница участников', f"{cmp['delta_authors']:+d}"))
    return rows


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'mod_action', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('recap: уведомление не ушло: %s', _ex)

    def _live(gid):
        """(error, status) | (None-ошибка, bot, guild) — склейка границ живости."""
        import web.app as appmod
        bot = appmod.bot_instance
        guild = _guild(bot, gid)
        if guild is None:
            return {'success': False,
                    'error': 'Бот офлайн — рекап собирается через живого бота'}, 409, None, None
        return None, 200, bot, guild

    def _channel_or_error(guild, raw_id):
        channel = find_channel(guild, raw_id)
        if channel is None:
            return None, ({'success': False, 'error': 'Текстовый канал не найден'}, 404)
        return channel, None

    def _collect_or_error(channel, hours):
        """Ошибки выборки — словами _do_recap кога."""
        try:
            return collect_recap(channel, hours), None
        except discord.Forbidden:
            return None, ({'success': False,
                           'error': f'Нет доступа к истории #{channel.name}.'}, 403)
        except discord.HTTPException as _ex:
            _log.debug('recap: history HTTP: %s', _ex)
            return None, ({'success': False,
                           'error': 'Discord не отдал историю канала — попробуйте позже.'}, 502)
        except RuntimeError as _ex:
            _log.debug('recap: цикл бота: %s', _ex)
            return None, ({'success': False, 'error': str(_ex)}, 409)

    @app.route('/recap')
    @login_required
    @role_required('mod')
    def recap_page():
        return render_template('recap.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_send=session.get('role') in ('admin', 'owner'),
                               presets=PRESETS)

    @app.route('/api/guild/<gid>/recap/build', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_recap_build(gid):
        data = request.get_json(silent=True) or {}
        ok, err, hours = validate_hours(data.get('hours'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        err_d, status, _bot, guild = _live(gid)
        if err_d:
            return jsonify(err_d), status
        channel, err_t = _channel_or_error(guild, data.get('channel_id'))
        if err_t:
            return jsonify(err_t[0]), err_t[1]
        pack, err_c = _collect_or_error(channel, hours)
        if err_c:
            return jsonify(err_c[0]), err_c[1]
        return jsonify({
            'success': True,
            'channel': {'id': str(channel.id), 'name': str(channel.name)},
            'hours': hours,
            'quiet': pack['cur']['total'] == 0,
            'scanned': pack['scanned'],
            'recap': pack['cur'],
            'compare': pack['compare'],
            'embed': embed_spec(channel.name, pack['cur'], hours),
        })

    @app.route('/api/guild/<gid>/recap/send', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_recap_send(gid):
        data = request.get_json(silent=True) or {}
        ok, err, hours = validate_hours(data.get('hours'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        err_d, status, _bot, guild = _live(gid)
        if err_d:
            return jsonify(err_d), status
        channel, err_t = _channel_or_error(guild, data.get('channel_id'))
        if err_t:
            return jsonify(err_t[0]), err_t[1]
        pack, err_c = _collect_or_error(channel, hours)
        if err_c:
            return jsonify(err_c[0]), err_c[1]
        spec = embed_spec(channel.name, pack['cur'], hours)

        async def _send():
            embed = discord.Embed(title=spec['title'], color=RC.COLOR,
                                  timestamp=pack['now'])
            if spec['description']:
                embed.description = spec['description']
            for fld in spec['fields']:
                embed.add_field(name=fld['name'], value=fld['value'],
                                inline=fld['inline'])
            await channel.send(embed=embed)
        try:
            _run_async(_send(), timeout=15)
        except Exception as _ex:
            _log.debug('recap: отправка не ушла: %s', _ex)
            return jsonify({'success': False,
                            'error': 'Не удалось отправить — проверьте права бота в канале'}), 502
        _notify(f'Рекап отправлен в #{channel.name} ({hours} ч)')
        return jsonify({'success': True, 'quiet': pack['cur']['total'] == 0})

    @app.route('/api/guild/<gid>/recap/export.csv')
    @login_required
    @role_required('mod')
    def api_recap_export(gid):
        ok, err, hours = validate_hours(request.args.get('hours'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        err_d, status, _bot, guild = _live(gid)
        if err_d:
            return jsonify(err_d), status
        channel, err_t = _channel_or_error(guild, request.args.get('channel'))
        if err_t:
            return jsonify(err_t[0]), err_t[1]
        pack, err_c = _collect_or_error(channel, hours)
        if err_c:
            return jsonify(err_c[0]), err_c[1]
        rows = recap_csv_rows(channel.name, pack, hours)
        body = '\ufeff' + 'Показатель;Значение\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=recap_{channel.id}_{gid}.csv')
        return resp
