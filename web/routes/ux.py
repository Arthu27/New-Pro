# -*- coding: utf-8 -*-
"""UX-пакет панели: глобальный поиск (Ctrl+K) и личные настройки.

Глобальный поиск /api/ux/search?q= — один запрос по всем сущностям панели:
видимые роли страницы (panel_menu 1:1 с сайдбаром), участники (ms_search_members
из _common), транскрипты (transcript_store + глубокие сниппеты 1:1 со страницей
транскриптов), триггеры (GuildData 'triggers' — то же хранилище, что читает ког),
объявления (_load_announcements из web.app — та же лента, что на /announcements).

Личные настройки /api/ux/prefs — тема/акцент/плотность, привязанные к учётке
панели (не к браузеру): зашёл с другого устройства — оформление то же.
Хранилище: data/panel_prefs.json, атомарная запись (tmp + os.replace), только
строго провалидированные ключи.
"""

from web.routes._common import (
    _log,
    ms_normalize_query, ms_search_members,
    session, request, jsonify, os, json,
)

from db import GuildData
from services import panel_menu, transcript_store

SEARCH_LIMIT = 5          # хитов на группу
MIN_QUERY = 2             # короче — не ищем (шум)
MAX_QUERY_LEN = 64
PREFS_PATH = 'data/panel_prefs.json'
THEMES = ('dark', 'light')


# ── Личные настройки (чистые функции — легко тестировать) ──────────────────

def load_prefs():
    """Прочитать все prefs {username: {...}}. Битый JSON — как пусто."""
    if not os.path.exists(PREFS_PATH):
        return {}
    try:
        with open(PREFS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as _ex:
        _log.debug("load_prefs(): битый файл, считаем пустым: %s", _ex)
        return {}
    return data if isinstance(data, dict) else {}


def save_prefs(data):
    """Атомарно записать prefs (tmp + os.replace, как у transcript_store)."""
    os.makedirs(os.path.dirname(PREFS_PATH), exist_ok=True)
    tmp = PREFS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREFS_PATH)


def validate_prefs_patch(patch):
    """Отфильтровать и провалидировать патч. Возвращает (clean, error)."""
    if not isinstance(patch, dict):
        return None, 'нужен JSON-объект'
    clean = {}
    if 'theme' in patch:
        if patch['theme'] not in THEMES:
            return None, f"тема: только {', '.join(THEMES)}"
        clean['theme'] = patch['theme']
    if 'accent' in patch:
        a = str(patch['accent'] or '').strip().lower()
        if not (len(a) == 7 and a.startswith('#')
                and all(c in '0123456789abcdef' for c in a[1:])):
            return None, 'акцент: нужен #rrggbb'
        clean['accent'] = a
    if 'compact' in patch:
        clean['compact'] = bool(patch['compact'])
    if 'radius' in patch:
        try:
            radius = int(patch['radius'])
        except (TypeError, ValueError):
            return None, 'radius: число 8..24'
        if not 8 <= radius <= 24:
            return None, 'radius: число 8..24'
        clean['radius'] = radius
    if 'scale' in patch:
        try:
            scale = float(patch['scale'])
        except (TypeError, ValueError):
            return None, 'scale: число 0.85..1.15'
        if not 0.85 <= scale <= 1.15:
            return None, 'scale: число 0.85..1.15'
        clean['scale'] = round(scale, 2)
    if not clean:
        return None, 'пустой патч (theme/accent/compact/radius/scale)'
    return clean, None


def merge_user_prefs(username, patch):
    """Применить патч к prefs пользователя. (prefs, error) — запись только при ок."""
    clean, err = validate_prefs_patch(patch)
    if err:
        return None, err
    data = load_prefs()
    cur = data.get(username) or {}
    cur.update(clean)
    data[username] = cur
    save_prefs(data)
    return cur, None


# ── Поисковые источники (чистые, собираются в /api/ux/search) ───────────────

def search_pages(role, query, limit=SEARCH_LIMIT):
    """Видимые этой роли страницы из panel_menu — 1:1 с сайдбаром."""
    q = str(query or '').strip().lower()
    if not q:
        return []
    out = []
    for grp in panel_menu.panel_groups_for(role):
        for it in grp.get('pages', []):
            hay = (it.get('label', '') + ' ' + grp.get('group', '')).lower()
            if q in hay:
                out.append({
                    'type': 'page', 'icon': it.get('icon') or 'fa-file',
                    'title': it.get('label', ''), 'sub': grp.get('group', ''),
                    'href': it.get('path', '/'),
                })
            if len(out) >= limit:
                return out
    return out


def search_members(bot, guild_id, query, limit=SEARCH_LIMIT):
    """Участники сервера через ms_search_members (та же выдача, что у member-search)."""
    if not bot or not guild_id:
        from web .routes ._common import demo_members_search
        from urllib.parse import quote
        q = quote(str(query or ''), safe='')
        return [{
            'type': 'member', 'icon': 'fa-user',
            'title': str(m.get('display_name') or m.get('name') or m.get('id')),
            'sub': 'ID ' + str(m.get('id', '')),
            'href': '/member-search?q=' + q,
        } for m in demo_members_search(str(query or ''), limit=limit)]
    try:
        guild = bot.get_guild(int(guild_id))
    except (TypeError, ValueError):
        guild = None
    if not guild:
        return []
    hits = ms_search_members(list(getattr(guild, 'members', []) or []), query, limit=limit)
    from urllib.parse import quote
    q = quote(str(query or ''), safe='')
    return [{
        'type': 'member', 'icon': 'fa-user',
        'title': str(getattr(m, 'display_name', '') or getattr(m, 'name', '') or m.id),
        'sub': 'ID ' + str(getattr(m, 'id', '')),
        'href': '/member-search?q=' + q,
    } for m in hits]


def search_transcripts(query, limit=SEARCH_LIMIT):
    """Транскрипты: тот же filter_records + snippets, что и страница /transcripts."""
    q = str(query or '').strip()
    if not q:
        return []
    records = transcript_store.filter_records(transcript_store.load(), search=q)
    from urllib.parse import quote
    out = []
    for t in records[:limit]:
        snip = transcript_store.snippets(t, q, limit=1)
        if snip:
            s0 = snip[0]
            sub = s0['before'] + s0['match'] + s0['after']
        else:
            sub = transcript_store.category_label(t.get('category'))
        out.append({
            'type': 'transcript', 'icon': 'fa-file-lines',
            'title': str(t.get('id', '—')),
            'sub': sub,
            'href': '/transcripts?text=' + quote(q, safe=''),
        })
    return out


def search_triggers(guild_id, query, limit=SEARCH_LIMIT):
    """Триггеры автоответов — то же хранилище GuildData('triggers'), что у кога."""
    q = str(query or '').strip().lower()
    if not q or not guild_id:
        return []
    state = GuildData('triggers').get(int(guild_id), 'state',
                                      {'next_id': 1, 'items': [], 'cooldown': 30})
    out = []
    for it in state.get('items', []):
        if q in str(it.get('trigger', '')).lower():
            out.append({
                'type': 'trigger', 'icon': 'fa-bolt',
                'title': str(it.get('trigger', '')),
                'sub': 'автоответ №%s → %s' % (it.get('id'), str(it.get('response', ''))[:60]),
                'href': '/antifake',
            })
        if len(out) >= limit:
            break
    return out


def search_announcements(query, limit=SEARCH_LIMIT):
    """Объявления из живой ленты web.app._load_announcements (та же, что на странице)."""
    q = str(query or '').strip().lower()
    if not q:
        return []
    import web.app as _app
    try:
        anns = _app._load_announcements()
    except Exception as _ex:
        _log.debug("search_announcements(): лента недоступна: %s", _ex)
        return []
    out = []
    for a in anns:
        if q in str(a.get('title', '')).lower() or q in str(a.get('message', '')).lower():
            status = 'доставлено' if a.get('delivered') else 'черновик'
            out.append({
                'type': 'announcement', 'icon': 'fa-bullhorn',
                'title': str(a.get('title', 'Без заголовка')),
                'sub': status + ' · ' + str(a.get('channel_name', '')),
                'href': '/announcements',
            })
        if len(out) >= limit:
            break
    return out


GROUPS_META = (
    ('pages', 'Страницы'),
    ('members', 'Участники'),
    ('transcripts', 'Транскрипты'),
    ('triggers', 'Триггеры'),
    ('announcements', 'Объявления'),
)


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/ux/search')
    @login_required
    @role_required('mod')
    def api_ux_search():
        """Глобальный поиск по панели: один инпут — все сущности."""
        q = ms_normalize_query(request.args.get('q', ''))
        if len(q) < MIN_QUERY:
            return jsonify({'query': q, 'groups': [], 'total': 0})
        import web.app as _app
        bot = _app.bot_instance
        gid = ctx.active_guild_id()
        found = {
            'pages': search_pages(session.get('role'), q),
            'members': search_members(bot, gid, q),
            'transcripts': search_transcripts(q),
            'triggers': search_triggers(gid, q),
            'announcements': search_announcements(q),
        }
        groups = [{'key': k, 'title': t, 'items': found[k]}
                  for k, t in GROUPS_META if found[k]]
        return jsonify({'query': q, 'groups': groups,
                        'total': sum(len(g['items']) for g in groups)})

    @app.route('/api/ux/prefs', methods=['GET'])
    @login_required
    def api_ux_prefs_get():
        """Личные настройки оформления текущей учётки панели."""
        return jsonify({'success': True,
                        'prefs': load_prefs().get(session.get('username'), {})})

    @app.route('/api/ux/prefs', methods=['POST'])
    @login_required
    def api_ux_prefs_post():
        """Сохранить theme/accent/compact за учёткой (следует за пользователем)."""
        prefs, err = merge_user_prefs(session.get('username'),
                                      request.get_json(silent=True))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'prefs': prefs})
