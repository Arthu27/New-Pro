# -*- coding: utf-8 -*-
"""Карточка участника 360° (идеи #106-110): всё досье одним экраном.

Агрегатор над подсистемами, которые в боте живут раздельно:
- активность и ранги — метод ProfileCog._data (cogs/profile.py) без
  переписываний: уровень/XP из services.gamification, сообщения/войс из
  leaderboard_<gid>.json и GuildData('voice_stats'), баланс — UserData('economy'),
  ранги — его же _rank (вне списка = len+1, числа совпадают с /profile);
- карма — чистые функции cogs/karma.py поверх GuildData('karma'): счёт,
  место в топе (полный проход top_rows), разброс по журналу благодарностей;
- предупреждения — зеркало data/warnings.json (load_warns_map из mod_control),
  свежие записи хвостом, как в /warnings бота;
- день рождения — schedule() панели дней рождения (та же num-формула кога:
  месяц*100+день, перенос года +1200);
- имена — журнал аудита (names_from_audit), запасной вариант — имя из записи
  дня рождения; при живом боте — display_name/аватар/дата входа с Discord.

ID принимаем как у мод-контроля: чистый или упоминание <@123> (тот же
validate_user_id, тот же текст ошибки).

Страница и чтение — mod+; мутаций здесь нет, карточка только собирает.
Экспорт — CSV с BOM и точкой с запятой, как остальные выгрузки панели.
"""
import json
from types import SimpleNamespace

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)
from web.routes.mod_control import (
    validate_user_id, names_from_audit, load_warns_map,
)
from web.routes.birthdays_panel import load_birthdays, schedule

from cogs import profile as PC
from cogs import karma as KC

from db import GuildData, UserData

SUGGEST_LIMIT = 8
WARN_RECENT = 5        # свежие варны карточки (зеркало хранит до 25 — как ког)
KARMA_TOP_SCAN = 100000  # место честное: проходим всю таблицу top_rows


def _karma_state(gid):
    return GuildData('karma').get(gid, 'state', KC.empty_state()) or KC.empty_state()


# ─────────────────────────────────────────────────────────────────────
# #106-107: активность 1:1 с карточкой /profile
# ─────────────────────────────────────────────────────────────────────
def activity_view(bot, gid, uid):
    """Данные блока — тот же ProfileCog._data, что рисует /profile.

    С живым ботом зовём его ког, без бота — лёгкий двойник только с .eco:
    метод больше ничего из self не трогает (проверено по cogs/profile.py).
    """
    cog = bot.get_cog('ProfileCog') if bot else None
    src = cog if cog is not None else SimpleNamespace(eco=UserData('economy'))
    return PC.ProfileCog._data(src, gid, int(uid))


def economy_view(uid):
    """Кошелёк и банк раздельно (карточка бота показывает только сумму)."""
    raw = UserData('economy').get(int(uid))
    if not isinstance(raw, dict):
        return {'balance': 0, 'bank': 0, 'total': 0}
    bal = int(raw.get('balance', 0) or 0)
    bank = int(raw.get('bank', 0) or 0)
    return {'balance': bal, 'bank': bank, 'total': bal + bank}


# ─────────────────────────────────────────────────────────────────────
# #108: репутация — карма + варны
# ─────────────────────────────────────────────────────────────────────
def karma_view(gid, uid):
    """Очки, место в общем топе и разброс по журналу — функции cogs/karma.py."""
    state = _karma_state(gid)
    rank = None
    for i, (row_uid, _score) in enumerate(KC.top_rows(state, limit=KARMA_TOP_SCAN), 1):
        if str(row_uid) == str(uid):
            rank = i
            break
    received = given = 0
    for th in state.get('thanks', []):
        if th.get('target') == int(uid):
            received += 1
        if th.get('giver') == int(uid):
            given += 1
    return {'score': KC.get_score(state, uid), 'rank': rank,
            'received': received, 'given': given}


def warns_view(gid, uid):
    """Свежие варны из зеркала: ког пишет по порядку, показываем с конца."""
    items = load_warns_map(gid).get(str(uid)) or []
    recent = [{
        'id': w.get('id'),
        'reason': str(w.get('reason') or 'Не указана'),
        'mod': str(w.get('mod') or '?'),
        'date': str(w.get('timestamp') or '')[:10],
    } for w in items[-WARN_RECENT:][::-1]]
    return {'count': len(items), 'recent': recent}


# ─────────────────────────────────────────────────────────────────────
# #109: события (день рождения, вход на сервер) и быстрые переходы
# ─────────────────────────────────────────────────────────────────────
def birthday_view(gid, uid, now=None):
    """Запись календаря ДР участника — та же num-формула и сортировка кога."""
    for entry in schedule(load_birthdays(gid), now=now):
        if entry['user_id'] == str(uid):
            return entry
    return None


def member_view(bot, gid, uid):
    """Живой участник (ник, аватар, вход, роли) — только когда бот онлайн."""
    if not bot:
        return None
    try:
        guild = bot.get_guild(int(gid))
        member = guild.get_member(int(uid)) if guild else None
    except Exception as _ex:
        _log.debug('member_card: live-данные недоступны: %s', _ex)
        return None
    if member is None:
        return None
    joined = getattr(member, 'joined_at', None)
    top = getattr(member, 'top_role', None)
    avatar = getattr(member, 'display_avatar', None)
    return {
        'display_name': str(getattr(member, 'display_name', '') or ''),
        'avatar_url': str(avatar.url) if avatar else '',
        'joined_at': joined.date().isoformat() if joined else '',
        'roles': max(0, len(getattr(member, 'roles', []) or []) - 1),  # без @everyone
        'top_role': str(getattr(top, 'name', '') or ''),
        'booster': bool(getattr(member, 'premium_since', None)),
    }


def identity_view(bot, gid, uid):
    """Имя: живой ник → журнал аудита → запись ДР. Источник показываем честно."""
    member = member_view(bot, gid, uid)
    if member and member['display_name']:
        return member, member['display_name'], 'discord'
    name = names_from_audit(gid).get(str(uid))
    if name:
        return member, name, 'audit'
    raw = load_birthdays(gid).get(str(uid))
    if isinstance(raw, dict) and raw.get('name'):
        return member, str(raw['name']), 'birthday'
    return member, '', ''


def quick_links(uid):
    """Куда углубиться: только страницы, что реально есть в панели."""
    return [
        {'path': f'/karma?user={uid}', 'label': 'Карма: журнал', 'icon': 'fa-hand-holding-heart'},
        {'path': '/leveling', 'label': 'Уровни', 'icon': 'fa-arrow-trend-up'},
        {'path': '/economy', 'label': 'Экономика', 'icon': 'fa-coins'},
        {'path': '/birthdays', 'label': 'Дни рождения', 'icon': 'fa-cake-candles'},
        {'path': '/warnings', 'label': 'Предупреждения', 'icon': 'fa-triangle-exclamation'},
        {'path': '/member-notes', 'label': 'Заметки', 'icon': 'fa-note-sticky'},
    ]


def card_view(bot, gid, uid):
    """Всё досье участника одной сборкой."""
    member, name, name_src = identity_view(bot, gid, uid)
    return {
        'user_id': str(uid),
        'name': name,
        'name_source': name_src,
        'member': member,
        'activity': activity_view(bot, gid, uid),
        'economy': economy_view(uid),
        'karma': karma_view(gid, uid),
        'warns': warns_view(gid, uid),
        'birthday': birthday_view(gid, uid),
        'links': quick_links(uid),
    }


# ─────────────────────────────────────────────────────────────────────
# #110: автодополнение и выгрузка
# ─────────────────────────────────────────────────────────────────────
def _name_pool(gid):
    """Все известные имена сервера: аудит, демо-участники, XP, дни рождения."""
    pool = names_from_audit(gid)
    # демо: участники, которых видно в подсказках логина — ищем по обоим никам
    from web.routes._common import DEMO_MEMBERS
    for dm in DEMO_MEMBERS:
        uid = str(dm.get('id'))
        for key in ('display_name', 'name'):
            if dm.get(key):
                pool.setdefault(uid, str(dm[key]))
    # демо-имена из подсказок логина (тот же набор, что в /api/login/suggest)
    for uid, nm in (
        ('987430047889637426', 'Owner'),
        ('1406597367695806564', 'ecobar'),
        ('1483484518563188767', 'dragon'),
        ('1461513653650981054', 'hzdio'),
        ('859341577452257330', 'oberaru'),
        ('1465744556183126242', 'meow_meow'),
    ):
        pool.setdefault(uid, nm)
    # имена из таблицы лидеров (xp)
    try:
        with open(f'data/xp_{gid}.json', encoding='utf-8') as fp:
            xp = json.load(fp)
        if isinstance(xp, dict):
            for uid, u in xp.items():
                if isinstance(u, dict) and u.get('name'):
                    pool.setdefault(str(uid), str(u['name']))
    except Exception as _ex:
        _log.debug('_name_pool(): xp %s: %s', gid, _ex)
    for uid, info in load_birthdays(gid).items():
        if isinstance(info, dict) and info.get('name'):
            pool.setdefault(str(uid), str(info['name']))
    return pool


def suggest(gid, query, limit=SUGGEST_LIMIT):
    """Автодополнение: @-поиск по именам из аудита, XP, ДР и демо-списка.

    Символ @ отбрасывается (стиль Discord-упоминаний): '@sonya' ищет 'sonya'.
    Голый '@' (пусто после @) возвращает верх пула — можно сразу кликнуть
    по человеку, не набирая имя.
    """
    raw = str(query or '').strip()
    q = raw.lower()
    if q.startswith('@'):
        q = q[1:].lstrip()
    if not raw:
        return []
    pool = _name_pool(gid)
    if not q:
        hits = [{'user_id': str(u), 'name': str(n)} for u, n in pool.items()]
        hits.sort(key=lambda h: (h['name'].lower(), h['user_id']))
        return hits[:limit]
    hits = []
    for uid, name in pool.items():
        if q in str(name).lower() or q in str(uid):
            hits.append({'user_id': str(uid), 'name': str(name)})
    hits.sort(key=lambda h: (h['name'].lower(), h['user_id']))
    return hits[:limit]


def resolve_user_ref(gid, raw):
    """ID или ИМЯ участника → user_id. Имя ищется в аудите, ДР и демо-списке.

    Принимает упоминание в стиле Discord: '@sonya' ≡ 'sonya'.
    Возвращает (uid, None) при однозначном совпадении, иначе (None, ошибка):
    участник не найден или найдено несколько — просим уточнить.
    """
    raw = str(raw or '').strip()
    if raw.startswith('@'):
        raw = raw[1:].lstrip()
    if not raw:
        return None, 'Введите ID или имя участника'
    ok, _err, uid = validate_user_id(raw)
    if ok:
        return uid, None
    pool = _name_pool(gid)
    q = raw.lower()
    exact = [u for u, n in pool.items() if str(n).lower() == q]
    hits = exact or [u for u, n in pool.items() if q in str(n).lower()]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, 'Участник «%s» не найден ни по ID, ни по имени' % raw
    preview = '; '.join('%s (%s)' % (pool[u], u) for u in sorted(hits)[:3])
    return None, 'Найдено несколько: %s. Уточните имя или введите ID.' % preview


def card_csv_rows(card):
    """Плоские строки выгрузки карточки."""
    a, eco, km = card['activity'], card['economy'], card['karma']
    rows = [
        ('Профиль', 'ID', card['user_id']),
        ('Профиль', 'Имя', card['name'] or '—'),
        ('Профиль', 'Уровень', str(a['level'])),
        ('Профиль', 'Опыт', f"{a['xp']} из {a['xp_needed']}"),
        ('Активность', 'Сообщения', str(a['messages'])),
        ('Активность', 'Голос (сек)', str(a['voice_seconds'])),
        ('Активность', 'Место по сообщениям', str(a['rank_messages'])),
        ('Активность', 'Место по голосу', str(a['rank_voice'])),
        ('Активность', 'Место по богатству', str(a['rank_balance'])),
        ('Экономика', 'Кошелёк', str(eco['balance'])),
        ('Экономика', 'Банк', str(eco['bank'])),
        ('Экономика', 'Всего', str(eco['total'])),
        ('Карма', 'Очки', str(km['score'])),
        ('Карма', 'Место в топе', str(km['rank'] or '—')),
        ('Карма', 'Благодарностей получено', str(km['received'])),
        ('Карма', 'Благодарностей отправлено', str(km['given'])),
    ]
    w = card['warns']
    rows.append(('Модерация', 'Варнов', str(w['count'])))
    for item in w['recent']:
        rows.append(('Модерация', f"Варн #{item['id']}",
                     f"{item['date']} · {item['reason']} · {item['mod']}"))
    b = card['birthday']
    if b:
        rows.append(('День рождения', 'Дата', str(b['date'])))
        rows.append(('День рождения', 'Через (дней, по формуле бота)', str(b['days_until'])))
        if b.get('age') is not None:
            rows.append(('День рождения', 'Исполнится лет', str(b['age'])))
    m = card['member']
    if m:
        rows.append(('Discord', 'На сервере с', m['joined_at'] or '—'))
        rows.append(('Discord', 'Ролей', str(m['roles'])))
        if m['top_role']:
            rows.append(('Discord', 'Высшая роль', m['top_role']))
    return rows


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/member-card')
    @login_required
    @role_required('mod')
    def member_card_page():
        return render_template('member_card.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/member-card/lookup')
    @login_required
    @role_required('mod')
    def api_mc_lookup(gid):
        import web.app as appmod
        raw = (request.args.get('user') or '').strip()
        uid, err = resolve_user_ref(gid, raw)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True,
                        'card': card_view(appmod.bot_instance, gid, uid)})

    @app.route('/api/guild/<gid>/member-card/suggest')
    @login_required
    @role_required('mod')
    def api_mc_suggest(gid):
        return jsonify({'success': True,
                        'items': suggest(gid, request.args.get('q'))})

    @app.route('/api/guild/<gid>/member-card/export')
    @login_required
    @role_required('mod')
    def api_mc_export(gid):
        import web.app as appmod
        raw = (request.args.get('user') or '').strip()
        uid, err = resolve_user_ref(gid, raw)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        card = card_view(appmod.bot_instance, gid, uid)
        body = '\ufeff' + 'Раздел;Показатель;Значение\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in card_csv_rows(card))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=member_card_{uid}_{gid}.csv')
        return resp
