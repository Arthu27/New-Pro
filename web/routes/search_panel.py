# -*- coding: utf-8 -*-
"""Поиск по серверу (идеи #181-185): /search в браузере.

Логика 1:1 cogs/search_cog.py — те же выражения: поиск подстрокой без
регистра по display_name участников, имени ролей и имени каналов; боты в
выдаче участников остаются (команда их не фильтрует), в выдачу идут первые
десять, а в «Найдено» — полное число, как в описании эмбеда. Тексты пустых
секций — словами команд без эмодзи: «Участник не найден!», «Роль не
найдена!», «Канал не найден!».

Префиксная «!search» в боте — заглушка («загружаются...»): панель вместо
заглушки даёт единый запрос сразу по трём видам — участники, роли, каналы
одним блоком.

Поиск работает на живом кэше гильдии (bot_instance): корутин нет, loop не
нужен; без бота — честный 409 «Бот не работает», без заглушек.

Чтение — mod+; поиск ничего не меняет, поэтому и CSV-выгрузка — mod+.
"""
from web.routes._common import (
    render_template, session, request, jsonify, Response,
)

ERR_BOT = 'Бот не работает'
ERR_GUILD = 'Сервер не найден'
ERR_QUERY = 'Запрос пустой'
NOTE_MEMBER = 'Участник не найден!'   # слова !searchuser
NOTE_ROLE = 'Роль не найдена!'        # слова !searchrole
NOTE_CHANNEL = 'Канал не найден!'     # слова !searchchannel
TOP = 10                              # столько полей показывает эмбед


def find_members(guild, q):
    """Выражение !searchuser 1:1: подстрока в display_name, без фильтра ботов."""
    found = [m for m in guild.members if q in (m.display_name or '').lower()]
    return found, [{'name': m.display_name, 'id': str(m.id)}
                   for m in found[:TOP]]


def find_roles(guild, q):
    """Выражение !searchrole 1:1: подстрока в имени роли."""
    found = [r for r in guild.roles if q in (r.name or '').lower()]
    return found, [{'name': r.name, 'id': str(r.id),
                    'members': len(getattr(r, 'members', []) or [])}
                   for r in found[:TOP]]


def find_channels(guild, q):
    """Выражение !searchchannel 1:1: подстрока в имени канала."""
    found = [c for c in guild.channels if q in (c.name or '').lower()]
    return found, [{'name': c.name, 'id': str(c.id)} for c in found[:TOP]]


def search_flow(bot_lookup, gid, query):
    """Единый запрос по трём видам; (ok, err, code, payload)."""
    q = str(query or '').strip().lower()
    if not q:
        return False, ERR_QUERY, 400, None
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_GUILD, 404, None
    members, member_items = find_members(guild, q)
    roles, role_items = find_roles(guild, q)
    channels, channel_items = find_channels(guild, q)
    return True, '', 200, {
        'query': q,
        'members': {'total': len(members), 'items': member_items,
                    'note': None if members else NOTE_MEMBER},
        'roles': {'total': len(roles), 'items': role_items,
                  'note': None if roles else NOTE_ROLE},
        'channels': {'total': len(channels), 'items': channel_items,
                     'note': None if channels else NOTE_CHANNEL},
    }


def csv_rows(payload):
    """Результаты поиска построчно: вид; id; имя; доп.столбец."""
    rows = []
    for it in payload['members']['items']:
        rows.append(('user', it['id'], it['name'], ''))
    for it in payload['roles']['items']:
        rows.append(('role', it['id'], it['name'], it['members']))
    for it in payload['channels']['items']:
        rows.append(('channel', it['id'], it['name'], ''))
    return rows


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _bot():
        import web.app as appmod
        return appmod.bot_instance

    @app.route('/search')
    @login_required
    @role_required('mod')
    def search_page():
        return render_template('search.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/search/query')
    @login_required
    @role_required('mod')
    def api_search_query(gid):
        ok, err, code, payload = search_flow(_bot, gid,
                                             request.args.get('q'))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/search/export.csv')
    @login_required
    @role_required('mod')
    def api_search_csv(gid):
        ok, err, code, payload = search_flow(_bot, gid,
                                             request.args.get('q'))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        body = '\ufeff' + 'kind;id;name;extra\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in csv_rows(payload))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=search_{gid}.csv')
        return resp
