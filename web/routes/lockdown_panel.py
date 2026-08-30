# -*- coding: utf-8 -*-
"""Панель «Локдаун» (идеи #121-125): красная кнопка из браузера.

Хранилище одно на двоих с ботом: GuildData('lockdown'), ключ 'state'
({channels: {cid: снимок прав}, since/by/reason}), пишет cogs/lockdown.py.

Вся логика — его чистые функции и его метод разбора целей:
- _resolve_targets: 'all'/'все'/#имя/123 с теми же алиасами;
- snapshot_overwrite -> apply_lock для замка, apply_restore для отката —
  снимок всегда ДО мутации, как в cmd_lock;
- семантика пропусков 1:1: уже закрытый — в пропуски, Forbidden/HTTPException
  — тоже (при откате канал остаётся под замком, «попробуем позже»);
- state_summary/is_locked — статус строкой кога;
- since/by/reason — его правила: since не перетирается, reason [:200].

Сами смены прав требуют цикл бота: офлайн — честный 409, состояние при
этом не трогаем (частичного замка не бывает — как у команды при смерти бота
посреди рейда, снимки остаются для отката).

Чтение и предпросмотр — mod+, замок/откат — admin+ (у команд manage_guild).
"""
import json
import os
from datetime import datetime, timezone

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
    discord,
)

from cogs import lockdown as LD
from services import text_format as tf

from db import GuildData

UTC = timezone.utc

DEFAULT_REASON = 'локдаун'  # дефолт команды /lockdown
NO_TARGET_TEXT = 'Не нашёл такой канал. `/lockdown #канал` или `/lockdown all`.'
OFFLINE_TEXT = ('Бот офлайн — панель не видит Discord. '
                'Предпросмотр и смена прав требуют живое подключение бота. '
                'Запустите бота, подождите статус «онлайн» и обновите страницу.')
OFFLINE_HINT = 'Что делать: запустите бота и нажмите «Обновить» на странице.'

PERM_LABELS = {True: 'разрешено', False: 'запрещено', None: 'наследуется'}


def _db():
    return GuildData('lockdown')


def _state(gid):
    return _db().get(gid, 'state', LD.empty_state()) or LD.empty_state()


def _save(gid, state):
    _db().set(gid, 'state', state)


def resolve_targets(guild, spec):
    """Цели — сам метод кога: self он не трогает, отдаём None."""
    if guild is None:
        return []
    return LD.Lockdown._resolve_targets(None, guild, spec, None)


# ─────────────────────────────────────────────────────────────────────
# #121: статус-центр
# ─────────────────────────────────────────────────────────────────────
def status_view(guild, state, now=None):
    """Сводка строкой /lockstatus + закрытые каналы со снимками прав."""
    rows = []
    for cid, saved in (state or {}).get('channels', {}).items():
        ch = None
        if guild is not None and str(cid).isdigit():
            try:
                ch = guild.get_channel(int(cid))
            except Exception as _ex:
                _log.debug('lockdown: канал %s: %s', cid, _ex)
        rows.append({
            'id': str(cid),
            'name': str(getattr(ch, 'name', '') or ''),
            'saved': saved if isinstance(saved, dict) else {},
        })
    return {
        'summary': LD.state_summary(state, now=now),
        'count': LD.state_locked_count(state),
        'channels': rows,
        'since': str(state.get('since') or '')[:16].replace('T', ' '),
        'by': str(state.get('by') or ''),
        'reason': str(state.get('reason') or ''),
    }


def saved_perms_view(saved):
    """Снимок человеком: какие права вернутся при откате."""
    return [{'perm': p, 'label': PERM_LABELS.get(saved.get(p), 'наследуется')}
            for p in LD.WATCHED_PERMS]


# ─────────────────────────────────────────────────────────────────────
# #122: предпросмотр целей
# ─────────────────────────────────────────────────────────────────────
def preview_targets(guild, state, spec):
    """Кого тронет замок по такому spec; уже закрытые подсвечены."""
    return [{'id': str(ch.id), 'name': str(getattr(ch, 'name', '') or ch.id),
             'already': LD.is_locked(state, ch.id)}
            for ch in resolve_targets(guild, spec)]


# ─────────────────────────────────────────────────────────────────────
# #123/#124: замок и откат — семантика команд кога
# ─────────────────────────────────────────────────────────────────────
def _set_overwrite(ch, role, overwrite, reason):
    """Один set_permissions через цикл бота (sync-враппер хендлеров)."""
    async def _do():
        await ch.set_permissions(role, overwrite=overwrite, reason=reason)
    _run_async(_do(), timeout=15)


def lock_flow(bot, gid, guild, spec, reason, by, now=None):
    """/lockdown из панели: снимки до замка, пропуски, метаданные как у кога.

    (ok, err, payload). Каналы бьём последовательно — как команда в своём
    цикле; при сбое канала он уходит в пропуски без снимка.
    """
    now = now or datetime.now(UTC)
    reason = str(reason if reason is not None else DEFAULT_REASON)
    state = _state(gid)
    targets = resolve_targets(guild, spec)
    if not targets:
        return False, NO_TARGET_TEXT, None
    role = guild.default_role
    locked, skipped = [], []
    for ch in targets:
        cid = str(ch.id)
        if cid in state['channels']:
            skipped.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid),
                            'why': 'уже под замком'})
            continue
        try:
            ow = ch.overwrites_for(role)
            saved = LD.snapshot_overwrite(ow)          # снимок ДО мутации
            _set_overwrite(ch, role, LD.apply_lock(ow),
                           f'Локдаун: {reason[:120]}')
            state['channels'][cid] = saved
            locked.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid)})
        except (discord.Forbidden, discord.HTTPException) as _ex:
            _log.warning('lockdown: #%s на %s не закрылся: %s', cid, gid, _ex)
            state['channels'].pop(cid, None)
            skipped.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid),
                            'why': 'нет прав у бота'})
    if locked:
        state['since'] = state['since'] or now.isoformat()
        state['by'] = str(by)
        state['reason'] = reason[:200]
        _save(gid, state)
    return True, '', {
        'title': 'Локдаун включён' if locked else 'Локдаун: ничего не закрылось',
        'line': tf.spell(len(locked), 'канал закрыт', 'канала закрыто', 'каналов закрыто'),
        'locked': locked, 'skipped': skipped,
        'summary': LD.state_summary(state, now=now),
    }


def unlock_flow(bot, gid, guild, spec, now=None):
    """/unlockdown из панели: откат снимком, при ошибке канал остаётся."""
    now = now or datetime.now(UTC)
    state = _state(gid)
    targets = resolve_targets(guild, spec)
    if not targets:
        return False, 'Не нашёл такой канал.', None
    role = guild.default_role
    restored, missing = [], []
    for ch in targets:
        cid = str(ch.id)
        saved = state['channels'].pop(cid, None)
        if saved is None:
            missing.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid),
                            'why': 'не был под замком'})
            continue
        try:
            ow = ch.overwrites_for(role)
            _set_overwrite(ch, role, LD.apply_restore(ow, saved),
                           'Локдаун: откат прав')
            restored.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid)})
        except (discord.Forbidden, discord.HTTPException) as _ex:
            _log.warning('lockdown: #%s на %s не открылся: %s', cid, gid, _ex)
            state['channels'][cid] = saved  # остаётся под замком, попробуем позже
            missing.append({'id': cid, 'name': str(getattr(ch, 'name', '') or cid),
                            'why': 'нет прав у бота'})
    if not state['channels']:
        state.update({'since': None, 'by': None, 'reason': None})
    _save(gid, state)
    return True, '', {
        'title': 'Локдаун снят' if restored else 'Локдаун: нечего открывать',
        'line': tf.spell(len(restored), 'канал открыт', 'канала открыто', 'каналов открыто'),
        'restored': restored, 'missing': missing,
        'summary': LD.state_summary(state, now=now),
    }


# ─────────────────────────────────────────────────────────────────────
# #125: выгрузка
# ─────────────────────────────────────────────────────────────────────
def csv_rows(guild, state):
    """Что закрыло, когда и какие права вернутся."""
    view = status_view(guild, state)
    rows = []
    for row in view['channels']:
        labels = saved_perms_view(row['saved'])
        rows.append((
            row['id'], row['name'] or '—',
            ' | '.join(f"{p['perm']}: {p['label']}" for p in labels),
            view['since'], view['by'], view['reason'],
        ))
    return rows


CSV_HEADER = 'channel_id;channel;restore_perms;locked_since;locked_by;reason'


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def _demo_channels():
    """Текстовые каналы демо-структуры — локдаун работает в превью без бота."""
    try:
        with open(os.path.join('data', 'demo_channels.json'), encoding='utf-8') as fp:
            demo = json.load(fp)
    except Exception as _ex:
        _log.debug('lockdown: demo_channels.json: %s', _ex)
        demo = []
    return [{'id': str(c.get('id')), 'name': str(c.get('name') or '')}
            for c in demo if c.get('type') == 'text']


def _demo_targets(state, spec):
    rows = [{'id': ch['id'], 'name': ch['name'], 'already': LD.is_locked(state, ch['id'])}
            for ch in _demo_channels()]
    if spec and str(spec) != 'all':
        rows = [r for r in rows if r['id'] == str(spec)]
    return rows


def _demo_lock_flow(gid, spec, reason, by):
    """Имитация замка в превью: снимки {perm: None} и метаданные как у кога."""
    state = _state(gid)
    targets = _demo_targets(state, spec)
    if not targets:
        return False, NO_TARGET_TEXT, None
    locked, skipped = [], []
    for t in targets:
        cid = t['id']
        if cid in state['channels']:
            skipped.append({'id': cid, 'name': t['name'], 'why': 'уже под замком'})
            continue
        state['channels'][cid] = {p: None for p in LD.WATCHED_PERMS}
        locked.append({'id': cid, 'name': t['name']})
    if locked:
        state['since'] = datetime.now(UTC).isoformat()
        state['by'] = by
        state['reason'] = str(reason if reason is not None else DEFAULT_REASON)
    _save(gid, state)
    line = ('%d канал(ов) под замком' % len(locked)) if locked else 'Всё уже было под замком'
    return True, '', {'locked': bool(locked), 'line': line, 'skipped': skipped, 'missing': []}


def _demo_unlock_flow(gid, spec):
    state = _state(gid)
    if not state.get('channels'):
        return False, 'Ни один канал не под замком', None
    restored = []
    for t in _demo_targets(state, spec):
        cid = t['id']
        if cid in state['channels']:
            state['channels'].pop(cid, None)
            restored.append({'id': cid, 'name': t['name']})
    _save(gid, state)
    line = ('%d канал(ов) открыто' % len(restored)) if restored else 'Нечего открывать'
    return True, '', {'restored': bool(restored), 'line': line, 'missing': []}


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
            _log.debug('lockdown: уведомление не ушло: %s', _ex)

    def _guild(bot, gid):
        if not bot:
            return None
        try:
            return bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('lockdown: guild %s: %s', gid, _ex)
            return None

    @app.route('/lockdown')
    @login_required
    @role_required('mod')
    def lockdown_page():
        return render_template('lockdown.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/lockdown/status')
    @login_required
    @role_required('mod')
    def api_ld_status(gid):
        import web.app as appmod
        st = _state(gid)
        guild = _guild(appmod.bot_instance, gid)
        demo = appmod.bot_instance is None and appmod._demo_mode()
        view = status_view(guild, st)
        for row in view['channels']:
            row['saved_view'] = saved_perms_view(row['saved'])
        if demo:
            # имена каналов в превью берём из демо-структуры
            names = {c['id']: c['name'] for c in _demo_channels()}
            for row in view['channels']:
                if not row['name']:
                    row['name'] = names.get(row['id'], '')
        return jsonify({'success': True, 'status': view,
                        'bot_online': appmod.bot_instance is not None,
                        'demo': demo,
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/lockdown/preview', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ld_preview(gid):
        import web.app as appmod
        guild = _guild(appmod.bot_instance, gid)
        if guild is None:
            if appmod._demo_mode():
                spec = (request.get_json(silent=True) or {}).get('spec')
                rows = _demo_targets(_state(gid), spec)
                if not rows:
                    return jsonify({'success': False, 'error': NO_TARGET_TEXT,
                            'hint': 'Проверьте список каналов выше: цель должна быть в выпадающем списке или «all».'}), 404
                return jsonify({'success': True, 'targets': rows})
            return jsonify({'success': False, 'error': OFFLINE_TEXT, 'hint': OFFLINE_HINT}), 409
        spec = (request.get_json(silent=True) or {}).get('spec')
        rows = preview_targets(guild, _state(gid), spec)
        if not rows:
            return jsonify({'success': False, 'error': NO_TARGET_TEXT,
                            'hint': 'Проверьте список каналов выше: цель должна быть в выпадающем списке или «all».'}), 404
        return jsonify({'success': True, 'targets': rows})

    @app.route('/api/guild/<gid>/lockdown/lock', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ld_lock(gid):
        import web.app as appmod
        # Классическое разрешение: локдаун — действие «Локдаун» (тот же
        # тумблер, что у /lock и /unlock).
        from web.routes._common import viewer_member, acl_action_allowed
        _member = viewer_member(appmod.bot_instance, gid)
        if not acl_action_allowed(gid, _member, 'lockdown'):
            return jsonify({'success': False,
                            'error': 'Нет права: «Локдаун» не разрешено вашей '
                                     'роли (настройка — «Права команд»)'}), 403
        guild = _guild(appmod.bot_instance, gid)
        if guild is None:
            if appmod._demo_mode():
                data = request.get_json(silent=True) or {}
                ok, err, payload = _demo_lock_flow(
                    gid, data.get('spec') or 'all', data.get('reason'),
                    session.get('username', '?'))
                if not ok:
                    return jsonify({'success': False, 'error': err}), 404
                if payload['locked']:
                    _notify(f"Локдаун: {payload['line']}")
                return jsonify({'success': True, **payload})
            return jsonify({'success': False, 'error': OFFLINE_TEXT, 'hint': OFFLINE_HINT}), 409
        data = request.get_json(silent=True) or {}
        spec = data.get('spec') or 'all'
        try:
            ok, err, payload = lock_flow(appmod.bot_instance, gid, guild, spec,
                                         data.get('reason'),
                                         session.get('username', '?'))
        except RuntimeError as _ex:
            _log.debug('lockdown: цикл бота: %s', _ex)
            return jsonify({'success': False, 'error': str(_ex)}), 409
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        if payload['locked']:
            _notify(f"Локдаун: {payload['line']}")
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/lockdown/unlock', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ld_unlock(gid):
        import web.app as appmod
        # Снятие локдауна — то же действие «Локдаун».
        from web.routes._common import viewer_member, acl_action_allowed
        _member = viewer_member(appmod.bot_instance, gid)
        if not acl_action_allowed(gid, _member, 'lockdown'):
            return jsonify({'success': False,
                            'error': 'Нет права: «Локдаун» не разрешено вашей '
                                     'роли (настройка — «Права команд»)'}), 403
        guild = _guild(appmod.bot_instance, gid)
        if guild is None:
            if appmod._demo_mode():
                data = request.get_json(silent=True) or {}
                ok, err, payload = _demo_unlock_flow(gid, data.get('spec') or 'all')
                if not ok:
                    return jsonify({'success': False, 'error': err}), 404
                if payload['restored']:
                    _notify(f"Локдаун снят: {payload['line']}")
                return jsonify({'success': True, **payload})
            return jsonify({'success': False, 'error': OFFLINE_TEXT, 'hint': OFFLINE_HINT}), 409
        data = request.get_json(silent=True) or {}
        spec = data.get('spec') or 'all'
        try:
            ok, err, payload = unlock_flow(appmod.bot_instance, gid, guild, spec)
        except RuntimeError as _ex:
            _log.debug('lockdown: цикл бота: %s', _ex)
            return jsonify({'success': False, 'error': str(_ex)}), 409
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        if payload['restored']:
            _notify(f"Локдаун снят: {payload['line']}")
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/lockdown/export.csv')
    @login_required
    @role_required('mod')
    def api_ld_export(gid):
        import web.app as appmod
        rows = csv_rows(_guild(appmod.bot_instance, gid), _state(gid))
        body = '\ufeff' + CSV_HEADER + '\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=lockdown_{gid}.csv')
        return resp
