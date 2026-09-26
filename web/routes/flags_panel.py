# -*- coding: utf-8 -*-
"""Фичефлаги в панели (идея #8): управление флагами функций.

Все мутации идут через тот же синглтон feature_flag_manager и те же его
методы, что жмут slash-команды бота: create_flag / enable_flag /
disable_flag / save_flag (rollout) / delete_flag. Состояние синхронно с
ботом по файлу data/feature_flags.json.

Чтение (страница и состояние) — mod+. Управление — admin+, как
administrator-only slash-команды /flag-enable и компания в коге.
"""
import re

from flask import has_request_context

from web.routes._common import (
    _safe_json_obj,
    _log,
    render_template, session, request, jsonify,
)

from services.feature_flags import feature_flag_manager as _ffm

_KEY_RE = re.compile(r'^[a-z0-9_\-]{2,64}$')
_NAME_MAX = 80
_DESC_MAX = 200


def _flag_dict(flag):
    created = flag.created_at
    return {
        'key': flag.flag_key,
        'name': flag.name,
        'description': flag.description or '',
        'enabled': bool(flag.enabled),
        'rollout': int(flag.rollout_percentage),
        'environment': flag.environment,
        'created_at': created.isoformat() if hasattr(created, 'isoformat') else str(created),
        'created_by': flag.created_by or '',
    }


def flags_payload():
    """Весь реестр флагов одним снимком: и GET, и ответы мутаций."""
    flags = [_flag_dict(f) for f in _ffm.get_all_flags()]
    enabled = sum(1 for f in flags if f['enabled'])
    avg_rollout = round(sum(f['rollout'] for f in flags) / len(flags)) if flags else 0
    return {
        'success': True,
        'flags': flags,
        'total': len(flags),
        'enabled_count': enabled,
        'avg_rollout': avg_rollout,
        'can_edit': has_request_context() and session.get('role') in ('admin', 'owner'),
    }


def _validate_key(key):
    key = (key or '').strip()
    if not key:
        return None, 'Введите ключ флага.'
    if not _KEY_RE.match(key):
        return None, 'Ключ: строчные буквы, цифры, дефис или подчёркивание (2-64 символа).'
    return key, ''


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/feature-flags')
    @login_required
    @role_required('mod')
    def flags_page():
        return render_template('feature_flags.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/feature-flags/state')
    @login_required
    @role_required('mod')
    def api_flags_state():
        return jsonify(flags_payload())

    @app.route('/api/feature-flags/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_flags_create():
        data = _safe_json_obj()
        key, err = _validate_key(data.get('key'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        if _ffm.get_flag(key) is not None:
            return jsonify({'success': False,
                            'error': 'Флаг с таким ключом уже есть.'}), 409
        name = str(data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Введите название флага.'}), 400
        if len(name) > _NAME_MAX:
            return jsonify({'success': False,
                            'error': f'Название слишком длинное (максимум {_NAME_MAX}).'}), 400
        desc = str(data.get('description') or '').strip()
        if len(desc) > _DESC_MAX:
            return jsonify({'success': False,
                            'error': f'Описание слишком длинное (максимум {_DESC_MAX}).'}), 400
        flag = _ffm.create_flag(key, name, desc,
                                created_by='panel:%s' % session.get('username'))
        body = flags_payload()
        body['created'] = _flag_dict(flag)
        return jsonify(body)

    @app.route('/api/feature-flags/toggle', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_flags_toggle():
        """Включить/выключить — те же enable_flag/disable_flag, что у slash-команд."""
        data = _safe_json_obj()
        key, err = _validate_key(data.get('key'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        flag = _ffm.get_flag(key)
        if flag is None:
            return jsonify({'success': False, 'error': 'Флаг не найден.'}), 404
        ok = _ffm.disable_flag(key) if flag.enabled else _ffm.enable_flag(key)
        if not ok:
            return jsonify({'success': False, 'error': 'Не удалось переключить флаг.'}), 500
        return jsonify(flags_payload())

    @app.route('/api/feature-flags/rollout', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_flags_rollout():
        data = _safe_json_obj()
        key, err = _validate_key(data.get('key'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        flag = _ffm.get_flag(key)
        if flag is None:
            return jsonify({'success': False, 'error': 'Флаг не найден.'}), 404
        try:
            pct = int(data.get('percent'))
        except (TypeError, ValueError):
            return jsonify({'success': False,
                            'error': 'Процент должен быть целым числом.'}), 400
        if not 0 <= pct <= 100:
            return jsonify({'success': False,
                            'error': 'Процент выкатки — от 0 до 100.'}), 400
        flag.set_rollout_percentage(pct)
        _ffm.save_flag(flag)
        return jsonify(flags_payload())

    @app.route('/api/feature-flags/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_flags_delete():
        data = _safe_json_obj()
        key, err = _validate_key(data.get('key'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        flag = _ffm.get_flag(key)
        if flag is None:
            return jsonify({'success': False, 'error': 'Флаг не найден.'}), 404
        snapshot = _flag_dict(flag)  # для undo в тосте
        _ffm.delete_flag(key)
        body = flags_payload()
        body['removed'] = snapshot
        return jsonify(body)
