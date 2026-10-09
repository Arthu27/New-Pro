# -*- coding: utf-8 -*-
"""API Staff Manager для веб-панели (dropdown только из get_allowed_actions)."""
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
    # роли актёра из сессии / кэша
    actor_roles = session.get('discord_role_ids') or []
    target_roles = []
    try:
        from web import app as wa  # may fail — fallback empty
    except Exception:
        wa = None
    try:
        from services import members_cache as MC
        # нет ролей в MC — оставляем пусто; панель может дослать ?target_roles=
        pass
    except Exception:
        pass
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
    })
