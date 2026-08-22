# -*- coding: utf-8 -*-
"""AntiFake — защита от подделок (идеи #191-195): комната /antifake.

Источники данных — ФАЙЛЫ кога (data/antifake.json, data/antifake_strikes.json):
панель и бот могут жить в разных процессах, поэтому читаем/пишем файлы напрямую,
а живой ког (если он в этом же процессе) синхронизируем его методами — его
память слушают on_member_join/on_message, переключатели действуют сразу.

Страйки рекламы — ровно тот же файл, что пишет ког (_add_strike):
{guild_id: {user_id: [метки]}}. Никакого смешивания гильдий/участников —
каждая запись лежит под своим ключом, окно STRIKE_WINDOW считает активные.

Без бота (демо-предпросмотр) работают: статус, тумблеры, порог, защищаемые
строки, лаборатория, страйки, сброс страйков, CSV — всё пишется в файлы.
"""
import time
from datetime import datetime, timezone

from web.routes._common import (
    render_template, session, request, jsonify, Response,
)

from cogs import impersonation as IM
from logger import get_logger

_log = get_logger('antifake_panel')

UTC = timezone.utc

ERR_BOT = 'Бот не работает'
ERR_GUILD = 'Сервер не найден'
ERR_COG = 'Модуль AntiFake не загружен'
ERR_MEMBER = 'Участник не найден!'
ERR_NUMBER = 'ID — число'
ERR_TEXT = 'Текст пустой'
ERR_KEY = 'Неизвестная настройка'
ERR_ACTION = 'Неизвестное действие'
ERR_THRESHOLD = 'Порог — целое от 60 до 100'
NO_STRIKES = 'Страйков не было.'
CLEAN_TEXT = 'Чисто — подделки не найдено'   # строка «/antifake test» (без эмодзи)

TOGGLES = {
    'enabled': 'Система',
    'check_join': 'Проверка при входе',
    'check_update': 'Проверка смены имени',
    'check_ads': 'Анти-реклама',
    'exempt_staff': 'Иммунитет персонала',
    'dm_notify': 'DM-уведомления',
    'strike_timeout': 'Авто-таймаут за страйки',
}


# ── Файловые источники (те же, что у кога) ────────────────────────────────
def _cfg_file(gid):
    """Конфиг гильдии из data/antifake.json (DEFAULT_CFG + записанное)."""
    data = IM._load_json(IM.CFG_PATH, {})
    rec = data.get(str(gid)) if isinstance(data, dict) else None
    cfg = dict(IM.DEFAULT_CFG)
    if isinstance(rec, dict):
        cfg.update(rec)
    return cfg


def _save_cfg_file(gid, cfg):
    data = IM._load_json(IM.CFG_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data[str(gid)] = cfg
    IM._save_json(IM.CFG_PATH, data)


def _strikes_file():
    data = IM._load_json(IM.STRIKES_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_strikes_file(data):
    IM._save_json(IM.STRIKES_PATH, data)


def _demo_members():
    try:
        from web.routes._common import DEMO_MEMBERS
        return list(DEMO_MEMBERS)
    except Exception as _ex:
        _log.debug('_demo_members(): подавлено: %s', _ex)
        return []


def _demo_mode():
    try:
        import web.app as appmod
        return bool(appmod._demo_mode())
    except Exception as _ex:
        _log.debug('_demo_mode(): подавлено: %s', _ex)
        return False


def _ctx(bot_lookup, gid):
    """(ok, err, code, cog, guild) — живой ког и гильдия из кэша бота."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_GUILD, 404, None, None
    cog = bot.get_cog('AntiFake')
    if cog is None:
        return False, ERR_COG, 409, None, None
    return True, '', 200, cog, guild


def _names_lookup(bot, guild, gid):
    """uid → имя: живой кэш бота → демо-участники. Без бота — демо."""
    def f(uid):
        if bot is not None and guild is not None:
            try:
                m = guild.get_member(int(uid))
                if m is not None:
                    return str(m.display_name)
            except Exception as _ex:
                _log.debug('_names_lookup(%s): подавлено: %s', uid, _ex)
        if _demo_mode():
            for dm in _demo_members():
                if str(dm.get('id')) == str(uid):
                    return str(dm.get('display_name') or dm.get('name') or uid)
        return None
    return f


def status_payload(cfg, guild, gid):
    """Карточка настроек из конфига (живой ког или файл — одна форма)."""
    action = str(cfg.get('action'))
    ch_name = ''
    try:
        cid = int(cfg.get('log_channel_id', 0) or 0)
    except (TypeError, ValueError):
        cid = 0
    if cid:
        if guild is not None:
            ch = guild.get_channel(cid)
            ch_name = str(getattr(ch, 'name', '') or '') if ch is not None else ''
        if not ch_name and _demo_mode():
            try:
                import json as _json
                with open('data/demo_channels.json', encoding='utf-8') as fp:
                    chans = _json.load(fp)
                for c in chans:
                    if str(c.get('id')) == str(cid):
                        ch_name = str(c.get('name') or '')
                        break
            except Exception as _ex:
                _log.debug('status_payload(): демо-каналы: %s', _ex)
    names = list(cfg.get('protected_names', []))
    return {
        'success': True,
        'enabled': bool(cfg.get('enabled')),
        'action': action,
        'action_label': IM.ACTIONS_META.get(action, action),
        'actions': [{'value': c.value, 'name': c.name}
                    for c in IM.ACTION_CHOICES],
        'threshold_pct': int(float(cfg.get('threshold', 0.85)) * 100),
        'toggles': [{'key': k, 'label': lbl, 'on': bool(cfg.get(k))}
                    for k, lbl in TOGGLES.items()],
        'log_channel_id': str(cfg.get('log_channel_id', 0) or 0),
        'log_channel_name': ch_name or None,
        'log_auto': not bool(ch_name),
        'protected_names': names,
        'protected_count': len(names),
        'strike_limit': IM.STRIKE_LIMIT,
        'strike_window_days': IM.STRIKE_WINDOW // 86400,
    }


def status_flow(bot_lookup, gid):
    bot = bot_lookup()
    guild = bot.get_guild(int(gid)) if bot is not None else None
    cog = bot.get_cog('AntiFake') if bot is not None else None
    if cog is not None:
        cfg = cog.cfg(int(gid))
    else:
        cfg = _cfg_file(gid)
    return True, '', 200, status_payload(cfg, guild, gid)


def _mutate_cfg(bot_lookup, gid, key, value):
    """Запись настройки: живой ког (синхронно в файл) или файл напрямую."""
    bot = bot_lookup()
    cog = bot.get_cog('AntiFake') if bot is not None else None
    if cog is not None:
        cog.set_cfg(int(gid), key, value)
    else:
        cfg = _cfg_file(gid)
        cfg[key] = value
        _save_cfg_file(gid, cfg)


def toggle_flow(bot_lookup, gid, key):
    key = str(key or '')
    if key not in TOGGLES:
        return False, ERR_KEY, 400, None
    cfg = _cfg_file(gid)
    new_val = not bool(cfg.get(key))
    _mutate_cfg(bot_lookup, gid, key, new_val)
    return True, '', 200, {
        'message': f'{TOGGLES[key]}: {"вкл" if new_val else "выкл"}',
        'key': key, 'on': new_val,
        'status': status_flow(bot_lookup, gid)[3],
    }


def action_flow(bot_lookup, gid, value):
    choice = next((c for c in IM.ACTION_CHOICES if c.value == value), None)
    if choice is None:
        return False, ERR_ACTION, 400, None
    _mutate_cfg(bot_lookup, gid, 'action', choice.value)
    return True, '', 200, {
        'message': f'Действие при подделке: {choice.name}',
        'action': choice.value,
        'status': status_flow(bot_lookup, gid)[3],
    }


def threshold_flow(bot_lookup, gid, percent):
    try:
        pct = int(percent)
    except (TypeError, ValueError):
        return False, ERR_THRESHOLD, 400, None
    if not 60 <= pct <= 100:
        return False, ERR_THRESHOLD, 400, None
    _mutate_cfg(bot_lookup, gid, 'threshold', pct / 100.0)
    return True, '', 200, {
        'message': f'Порог похожести: {pct}%',
        'threshold_pct': pct,
        'status': status_flow(bot_lookup, gid)[3],
    }


def protect_flow(bot_lookup, gid, text):
    text = str(text or '')
    cfg = _cfg_file(gid)
    arr = list(cfg.get('protected_names', []))
    if text.strip() and text not in arr:
        arr.append(text)
        _mutate_cfg(bot_lookup, gid, 'protected_names', arr)
    return True, '', 200, {
        'message': f'Защищаемые строки ({len(arr)}): ' + ', '.join(arr),
        'protected_names': arr,
        'status': status_flow(bot_lookup, gid)[3],
    }


def unprotect_flow(bot_lookup, gid, text):
    text = str(text or '')
    cfg = _cfg_file(gid)
    arr = [x for x in cfg.get('protected_names', []) if x != text]
    _mutate_cfg(bot_lookup, gid, 'protected_names', arr)
    return True, '', 200, {
        'message': f'Осталось строк: {len(arr)}',
        'protected_names': arr,
        'status': status_flow(bot_lookup, gid)[3],
    }


def _protected_name_items(bot, guild, gid):
    """[(user_id|None, имя, норма)] — персонал + защищаемые строки.

    Без бота (демо) персонал берём из демо-участников со статусами.
    """
    items = []
    cfg = _cfg_file(gid)
    if bot is not None and guild is not None:
        for m in getattr(guild, 'members', []):
            if getattr(m, 'bot', False):
                continue
            roles = getattr(m, 'roles', []) or []
            if not any(str(getattr(r, 'permissions', '')).lower() != '' for r in roles):
                pass
            for n in {m.display_name, m.nick, m.global_name, m.name} - {None, ''}:
                nn = IM.normalize(n)
                if len(nn) >= 4:
                    items.append((m.id, n, nn))
    elif _demo_mode():
        for dm in _demo_members():
            n = str(dm.get('display_name') or dm.get('name') or '')
            nn = IM.normalize(n)
            if len(nn) >= 4:
                items.append((dm.get('id'), n, nn))
    for s in cfg.get('protected_names', []):
        nn = IM.normalize(str(s))
        if len(nn) >= 4:
            items.append((None, str(s), nn))
    return items


def test_member_flow(bot_lookup, gid, user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, ERR_NUMBER, 400, None
    bot = bot_lookup()
    guild = bot.get_guild(int(gid)) if bot is not None else None
    cog = bot.get_cog('AntiFake') if bot is not None else None
    member = None
    name = ''
    if guild is not None:
        member = guild.get_member(uid)
        name = str(getattr(member, 'display_name', '') or '') if member else ''
    # живой ког — 1:1 «/antifake test» (имя + украденный аватар)
    if member is not None and cog is not None:
        hit = cog.find_impersonation(member)
        stolen = cog.find_stolen_avatar(member)
        findings = []
        if hit:
            findings.append({'kind': 'name',
                             'text': f'Имя похоже на {hit[0]} '
                                     f'(совпадение {int(hit[2] * 100)}%)'})
        if stolen:
            findings.append({'kind': 'avatar',
                             'text': f'Аватар скопирован с {stolen.display_name}'})
        return True, '', 200, {
            'member': {'name': name, 'id': str(uid)},
            'clean': not findings,
            'verdict': CLEAN_TEXT if not findings else None,
            'findings': findings,
        }
    if member is None and _demo_mode():
        for dm in _demo_members():
            if str(dm.get('id')) == str(uid):
                name = str(dm.get('display_name') or dm.get('name') or uid)
                break
    if not name:
        return False, ERR_MEMBER, 404, None
    cfg = _cfg_file(gid)
    thr = float(cfg.get('threshold', 0.85))
    norm = IM.normalize(name)
    findings = []
    for tid, orig, norig in _protected_name_items(bot, guild, gid):
        sc = IM.similarity(norm, norig) if norm else 0.0
        if norm and sc >= thr:
            findings.append({'kind': 'name',
                             'text': f'Имя похоже на {orig} '
                                     f'(совпадение {int(sc * 100)}%)'})
            break
    return True, '', 200, {
        'member': {'name': name, 'id': str(uid)},
        'clean': not findings,
        'verdict': CLEAN_TEXT if not findings else None,
        'findings': findings,
    }


def lab_flow(bot_lookup, gid, text):
    text = str(text or '').strip()
    if not text:
        return False, ERR_TEXT, 400, None
    bot = bot_lookup()
    guild = bot.get_guild(int(gid)) if bot is not None else None
    cfg = _cfg_file(gid)
    thr = float(cfg.get('threshold', 0.85))
    norm = IM.normalize(text)
    rows = []
    verdict = False
    for tid, orig, norig in _protected_name_items(bot, guild, gid):
        sc = IM.similarity(norm, norig) if norm else 0.0
        if norm and sc >= thr:
            verdict = True
        rows.append({'name': orig, 'source': 'member' if tid else 'string',
                     'score_pct': round(sc * 100),
                     'catch': bool(norm) and sc >= thr})
    rows.sort(key=lambda r: -r['score_pct'])
    return True, '', 200, {
        'text': text,
        'norm': norm,
        'confusables': IM.has_confusables(text),
        'threshold_pct': int(thr * 100),
        'catch': verdict,
        'protected_total': len(rows),
        'matches': rows[:20],
    }


# ── Страйки: ровно файл кога, ничего не смешивается ───────────────────────
def strikes_flow(bot_lookup, gid):
    bot = bot_lookup()
    guild = bot.get_guild(int(gid)) if bot is not None else None
    names = _names_lookup(bot, guild, gid)
    data = _strikes_file()
    g = data.get(str(gid), {}) if isinstance(data, dict) else {}
    now = time.time()
    entries = []
    for uid, arr in g.items():
        if not isinstance(arr, list):
            arr = []
        marks = []
        for t in arr:
            try:
                marks.append(float(t))
            except (TypeError, ValueError) as _ex:
                _log.debug('strikes_flow(%s): битая метка %r: %s', uid, t, _ex)
                continue
        marks.sort(reverse=True)
        active = [t for t in marks if now - t < IM.STRIKE_WINDOW]
        entries.append({
            'user_id': str(uid),
            'name': names(str(uid)),
            'total': len(marks),
            'active': len(active),
            'history': [datetime.fromtimestamp(t, UTC).strftime('%Y-%m-%d %H:%M')
                        for t in marks[:10]],
            'last_at': (datetime.fromtimestamp(max(marks), UTC)
                        .strftime('%Y-%m-%d %H:%M') if marks else ''),
        })
    entries.sort(key=lambda e: (-e['active'], -e['total'], e['user_id']))
    return True, '', 200, {
        'success': True,
        'entries': entries,
        'limit': IM.STRIKE_LIMIT,
        'window_days': IM.STRIKE_WINDOW // 86400,
    }


def clear_strikes_flow(bot_lookup, gid, user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, ERR_NUMBER, 400, None
    data = _strikes_file()
    g = data.setdefault(str(gid), {})
    arr = g.pop(str(uid), None) or []
    _save_strikes_file(data)
    # синхронизация живой памяти кога (если он в этом процессе)
    bot = bot_lookup()
    if bot is not None:
        cog = bot.get_cog('AntiFake')
        if cog is not None:
            try:
                cog.clear_strikes(int(gid), uid)
            except Exception as _ex:
                _log.debug('clear_strikes_flow(): синк кога: %s', _ex)
    n = len(arr)
    if not n:
        return False, NO_STRIKES, 404, None
    bot2 = bot_lookup()
    guild = bot2.get_guild(int(gid)) if bot2 is not None else None
    names = _names_lookup(bot2, guild, gid)
    member = names(str(uid))
    payload = strikes_flow(bot_lookup, gid)[3]
    return True, '', 200, {
        'message': f'Снято страйков: {n}.',
        'removed': n,
        'member': member,
        'strikes': payload,
    }


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

    def _json():
        return request.get_json(silent=True) or {}

    def _reply(result):
        ok, err, code, payload = result
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/antifake')
    @login_required
    @role_required('mod')
    def antifake_page():
        return render_template('antifake.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/antifake/status')
    @login_required
    @role_required('mod')
    def api_antifake_status(gid):
        return _reply(status_flow(_bot, gid))

    @app.route('/api/guild/<gid>/antifake/toggle', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_toggle(gid):
        return _reply(toggle_flow(_bot, gid, _json().get('key')))

    @app.route('/api/guild/<gid>/antifake/action', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_action(gid):
        return _reply(action_flow(_bot, gid, _json().get('action')))

    @app.route('/api/guild/<gid>/antifake/threshold', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_threshold(gid):
        return _reply(threshold_flow(_bot, gid, _json().get('percent')))

    @app.route('/api/guild/<gid>/antifake/protect', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_protect(gid):
        return _reply(protect_flow(_bot, gid, _json().get('text')))

    @app.route('/api/guild/<gid>/antifake/unprotect', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_unprotect(gid):
        return _reply(unprotect_flow(_bot, gid, _json().get('text')))

    @app.route('/api/guild/<gid>/antifake/test', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_test(gid):
        return _reply(test_member_flow(_bot, gid, _json().get('user_id')))

    @app.route('/api/guild/<gid>/antifake/lab', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_antifake_lab(gid):
        return _reply(lab_flow(_bot, gid, _json().get('text')))

    @app.route('/api/guild/<gid>/antifake/strikes')
    @login_required
    @role_required('mod')
    def api_antifake_strikes(gid):
        return _reply(strikes_flow(_bot, gid))

    @app.route('/api/guild/<gid>/antifake/strikes/clear', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_antifake_strikes_clear(gid):
        return _reply(clear_strikes_flow(_bot, gid, _json().get('user_id')))

    @app.route('/api/guild/<gid>/antifake/strikes.csv')
    @login_required
    @role_required('mod')
    def api_antifake_strikes_csv(gid):
        ok, err, code, payload = strikes_flow(_bot, gid)
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        body = '\ufeff' + 'user_id;name;active;total;last_at\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in (
            e['user_id'], e['name'] or '', e['active'], e['total'],
            e['last_at'])) for e in payload['entries'])
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=antifake_strikes_{gid}.csv')
        return resp
