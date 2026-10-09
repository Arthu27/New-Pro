# -*- coding: utf-8 -*-
"""API Staff Manager для веб-панели (dropdown + согласия)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

bp = Blueprint('staff_manager_api', __name__)


def _require_login():
    return bool(session.get('logged_in'))


@bp.get('/api/staff-manager/allowed')
def api_sm_allowed():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    try:
        from services.staff_manager.config import is_enabled, last_error
        from services.staff_manager.acl import (
            resolve_actor, resolve_target, get_allowed_actions,
        )
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    if not is_enabled():
        return jsonify({'ok': False, 'error': last_error() or 'disabled'}), 503

    target_id = request.args.get('target_id') or ''
    if not str(target_id).isdigit():
        return jsonify({'ok': False, 'error': 'target_id'}), 400

    actor_id = session.get('discord_id') or session.get('user_id') or 0
    actor_roles = session.get('discord_role_ids') or []
    target_roles = []
    raw = request.args.get('target_roles') or ''
    if raw:
        target_roles = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    raw_a = request.args.get('actor_roles') or ''
    if raw_a:
        actor_roles = [int(x) for x in raw_a.split(',') if x.strip().isdigit()]

    actor = resolve_actor(int(actor_id), actor_roles)
    target = resolve_target(int(target_id), target_roles)
    allowed = get_allowed_actions(actor, target)
    return jsonify({'ok': True, 'allowed': allowed})


@bp.get('/api/staff-manager/status')
def api_sm_status():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    from services.staff_manager.config import is_enabled, last_error, get_config
    cfg = get_config() or {}
    return jsonify({
        'ok': True,
        'enabled': is_enabled(),
        'error': last_error(),
        'branches': list((cfg.get('branches') or {}).keys()),
        'ladder': [x.get('key') for x in (cfg.get('ladder') or [])],
        'role_emojis': cfg.get('role_emojis') or {},
        'branch_emojis': cfg.get('branch_emojis') or {},
    })


@bp.get('/api/staff-manager/consents')
def api_sm_consents():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    from services.staff_manager.store import list_consents, ensure_tables
    ensure_tables()
    status = request.args.get('status') or None
    guild_id = request.args.get('guild_id') or session.get('guild_id') or 0
    if not str(guild_id).isdigit() or not int(guild_id):
        try:
            from config import Config
            guild_id = Config.MAIN_GUILD_ID
        except Exception:
            return jsonify({'ok': False, 'error': 'guild_id'}), 400
    rows = list_consents(int(guild_id), status=status, limit=100)
    return jsonify({'ok': True, 'consents': rows})


@bp.post('/api/staff-manager/consents/<consent_id>/cancel')
def api_sm_consent_cancel(consent_id: str):
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    from services.staff_manager.store import get_consent, claim_consent_decision
    c = get_consent(consent_id)
    if not c:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    actor_id = int(session.get('discord_id') or session.get('user_id') or 0)
    if actor_id and actor_id not in (
            int(c.get('initiator_id') or 0),
    ):
        # allow owners via session flag
        if not session.get('is_owner') and not session.get('is_staff_admin'):
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
    claimed = claim_consent_decision(consent_id, 'cancelled')
    if not claimed:
        return jsonify({'ok': False, 'error': c.get('status')}), 409
    return jsonify({'ok': True, 'consent': claimed})


def _guild_id():
    guild_id = request.args.get('guild_id') or session.get('guild_id') or 0
    if not str(guild_id).isdigit() or not int(guild_id):
        try:
            from config import Config
            guild_id = Config.MAIN_GUILD_ID
        except Exception:
            return 0
    return int(guild_id)


@bp.get('/api/staff-manager/history')
def api_sm_history():
    """Таймлайн истории (не таблица) — серверная пагинация."""
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    from services.staff_manager.store import list_actions_filtered, ensure_tables
    from services.staff_manager.bundles import (
        format_transition, format_actor_label, format_role_label,
    )
    from services.staff_manager.config import role_emoji, branch_emoji
    ensure_tables()
    guild_id = _guild_id()
    if not guild_id:
        return jsonify({'ok': False, 'error': 'guild_id'}), 400
    try:
        limit = min(50, max(1, int(request.args.get('limit') or 20)))
        offset = max(0, int(request.args.get('offset') or 0))
    except Exception:
        limit, offset = 20, 0
    target_id = request.args.get('target_id')
    rows = list_actions_filtered(
        guild_id,
        target_id=int(target_id) if target_id and str(target_id).isdigit() else None,
        action=request.args.get('action') or None,
        branch=request.args.get('branch') or None,
        limit=limit,
        offset=offset,
    )
    items = []
    for r in rows:
        items.append({
            'id': r.get('id'),
            'action': r.get('action'),
            'transition': format_transition(
                r.get('old_key') or '', r.get('new_key') or '',
                branch=r.get('branch') or ''),
            'branch': r.get('branch'),
            'branch_emoji': branch_emoji(r.get('branch') or ''),
            'actor_id': r.get('actor_id'),
            'actor_label': format_actor_label(
                str(r.get('actor_id')), r.get('actor_role_key'),
                branch=r.get('actor_branch')),
            'actor_role_key': r.get('actor_role_key'),
            'actor_role_emoji': role_emoji(
                r.get('actor_role_key') or '',
                branch=r.get('actor_branch')),
            'reason': r.get('reason'),
            'ok': bool(r.get('ok')),
            'created_at': r.get('created_at'),
            'target_id': r.get('target_id'),
        })
    return jsonify({
        'ok': True, 'items': items, 'limit': limit, 'offset': offset,
        'layout': 'timeline',
    })


@bp.get('/api/staff-manager/vacations')
def api_sm_vacations():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'auth'}), 401
    from services.staff_manager.store import list_vacations, ensure_tables
    from services.staff_manager.vacation import vacation_display
    ensure_tables()
    guild_id = _guild_id()
    if not guild_id:
        return jsonify({'ok': False, 'error': 'guild_id'}), 400
    status = request.args.get('status') or None
    rows = list_vacations(guild_id, status=status, limit=100)
    return jsonify({
        'ok': True,
        'vacations': [vacation_display(v) for v in rows],
    })
