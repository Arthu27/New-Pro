# -*- coding: utf-8 -*-
"""AntiFake — защита от подделок (идеи #191-195): комната /antifake.

Всё через живой ког AntiFake (bot_instance.get_cog): его cfg()/set_cfg() —
та же память, что слушают on_member_join/on_message, поэтому переключатели
действуют сразу, без перезагрузки бота. Тексты — словами команд без
маркдауна: «Действие при подделке: X», «Порог похожести: N%», «Защищаемые
строки (N): a, b», «Осталось строк: N». Варианты действий — из
ACTION_CHOICES кога, подписи — из его ACTIONS_META.

Сухой прогон участника — 1:1 «/antifake test»: те же find_impersonation и
find_stolen_avatar, те же строки выводов («Имя похоже на X (совпадение
N%)», «Аватар скопирован с Y», «Чисто — подделки не найдено») — без
наказания, как и команда. Лаборатория строки гоняет normalize/similarity
кога по тем же защищаемым именам.

Страйки рекламы — через хелперы кога strike_view/clear_strikes (память и
файл те самые, STRIKE_WINDOW/STRIKE_LIMIT — его константы).

Без бота или без кога — честные 409, без заглушек. Чтение/лаборатория/
страйки/CSV — mod+; мутации и сухой прогон — admin+ (у команд administrator).
"""
import time
from datetime import datetime, timezone

from web.routes._common import (
    render_template, session, request, jsonify, Response,
)

from cogs import impersonation as IM

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


def status_payload(cog, guild, gid):
    """Карточка настроек 1:1 _cfg_embed + все honour-флаги кога."""
    cfg = cog.cfg(int(gid))
    action = str(cfg.get('action'))
    ch = guild.get_channel(int(cfg.get('log_channel_id', 0) or 0))
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
        'log_channel_name': str(getattr(ch, 'name', '') or '') if ch else None,
        'log_auto': ch is None,
        'protected_names': names,
        'protected_count': len(names),
        'strike_limit': IM.STRIKE_LIMIT,
        'strike_window_days': IM.STRIKE_WINDOW // 86400,
    }


def status_flow(bot_lookup, gid):
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    return True, '', 200, status_payload(cog, guild, gid)


def toggle_flow(bot_lookup, gid, key):
    """Переключатель флага; enabled — то же, что «/antifake on|off»."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    key = str(key or '')
    if key not in TOGGLES:
        return False, ERR_KEY, 400, None
    new_val = not bool(cog.cfg(int(gid)).get(key))
    cog.set_cfg(int(gid), key, new_val)
    return True, '', 200, {
        'message': f'{TOGGLES[key]}: {"вкл" if new_val else "выкл"}',
        'key': key, 'on': new_val,
        'status': status_payload(cog, guild, gid),
    }


def action_flow(bot_lookup, gid, value):
    """Действие при подделке 1:1 «/antifake action» (те же Choice)."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    choice = next((c for c in IM.ACTION_CHOICES if c.value == value), None)
    if choice is None:
        return False, ERR_ACTION, 400, None
    cog.set_cfg(int(gid), 'action', choice.value)
    return True, '', 200, {
        'message': f'Действие при подделке: {choice.name}',
        'action': choice.value,
        'status': status_payload(cog, guild, gid),
    }


def threshold_flow(bot_lookup, gid, percent):
    """Порог 1:1 «/antifake threshold» (Range 60–100 → доля)."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    try:
        pct = int(percent)
    except (TypeError, ValueError):
        return False, ERR_THRESHOLD, 400, None
    if not 60 <= pct <= 100:
        return False, ERR_THRESHOLD, 400, None
    cog.set_cfg(int(gid), 'threshold', pct / 100.0)
    return True, '', 200, {
        'message': f'Порог похожести: {pct}%',
        'threshold_pct': pct,
        'status': status_payload(cog, guild, gid),
    }


def protect_flow(bot_lookup, gid, text):
    """Добавить защищаемую строку 1:1 «/antifake protect»."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    text = str(text or '')
    cfg = cog.cfg(int(gid))
    arr = list(cfg.get('protected_names', []))
    if text.strip() and text not in arr:
        arr.append(text)
        cog.set_cfg(int(gid), 'protected_names', arr)
    return True, '', 200, {
        'message': f'Защищаемые строки ({len(arr)}): ' + ', '.join(arr),
        'protected_names': arr,
        'status': status_payload(cog, guild, gid),
    }


def unprotect_flow(bot_lookup, gid, text):
    """Убрать строку 1:1 «/antifake unprotect»."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    text = str(text or '')
    cfg = cog.cfg(int(gid))
    arr = [x for x in cfg.get('protected_names', []) if x != text]
    cog.set_cfg(int(gid), 'protected_names', arr)
    return True, '', 200, {
        'message': f'Осталось строк: {len(arr)}',
        'protected_names': arr,
        'status': status_payload(cog, guild, gid),
    }


def test_member_flow(bot_lookup, gid, user_id):
    """Сухой прогон 1:1 «/antifake test» — те же проверки, без наказания."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, ERR_NUMBER, 400, None
    member = guild.get_member(uid)
    if member is None:
        return False, ERR_MEMBER, 404, None
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
        'member': {'name': member.display_name, 'id': str(member.id)},
        'clean': not findings,
        'verdict': CLEAN_TEXT if not findings else None,
        'findings': findings,
    }


def lab_flow(bot_lookup, gid, text):
    """Лаборатория строки: normalize/similarity кога по защищаемым именам.

    Вердикт считается по всем именам (как find_impersonation), в выдачу —
    двадцать ближайших.
    """
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    text = str(text or '').strip()
    if not text:
        return False, ERR_TEXT, 400, None
    norm = IM.normalize(text)
    thr = float(cog.cfg(int(gid)).get('threshold', 0.85))
    rows = []
    verdict = False
    for tid, orig, norig, _mem in cog.protected_names(guild):
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


def strikes_flow(bot_lookup, gid):
    """Страйки рекламы через strike_view кога; окно и лимит — его же."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    return True, '', 200, strikes_payload(cog, guild, gid)


def strikes_payload(cog, guild, gid):
    now = time.time()
    entries = []
    for uid, arr in cog.strike_view(int(gid)).items():
        marks = [float(t) for t in arr]
        active = [t for t in marks if now - t < IM.STRIKE_WINDOW]
        member = guild.get_member(int(uid)) if uid.isdigit() else None
        entries.append({
            'user_id': uid,
            'name': str(member.display_name) if member else None,
            'total': len(marks),
            'active': len(active),
            'last_at': (datetime.fromtimestamp(max(marks), UTC)
                        .strftime('%Y-%m-%d %H:%M') if marks else ''),
        })
    entries.sort(key=lambda e: (-e['active'], -e['total'], e['user_id']))
    return {'success': True, 'entries': entries,
            'limit': IM.STRIKE_LIMIT,
            'window_days': IM.STRIKE_WINDOW // 86400}


def clear_strikes_flow(bot_lookup, gid, user_id):
    """Обнулить страйки участника (хелпер кога clear_strikes)."""
    ok, err, code, cog, guild = _ctx(bot_lookup, gid)
    if not ok:
        return False, err, code, None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, ERR_NUMBER, 400, None
    n = cog.clear_strikes(int(gid), uid)
    if not n:
        return False, NO_STRIKES, 404, None
    member = guild.get_member(uid)
    return True, '', 200, {
        'message': f'Снято страйков: {n}.',
        'removed': n,
        'member': str(member.display_name) if member else None,
        'strikes': strikes_payload(cog, guild, gid),
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
        ok, err, code, cog, guild = _ctx(_bot, gid)
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        payload = strikes_payload(cog, guild, gid)
        body = '\ufeff' + 'user_id;name;active;total;last_at\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in (
            e['user_id'], e['name'] or '', e['active'], e['total'],
            e['last_at'])) for e in payload['entries'])
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=antifake_strikes_{gid}.csv')
        return resp
