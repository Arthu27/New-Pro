# -*- coding: utf-8 -*-
"""Центр уведомлений панели: настройки каналов и событий, тест, история.

Хранилище и правила — services/notification_dispatcher
(data/notification_settings.json, data/notification_history.json).
Дефолты единые — диспетчерские (раньше здесь жила копия-сирота,
расходившаяся с EVENTS при каждом новом событии).

Идеи #71-75: события новых панелей в переключателях, фильтры истории,
сводка доставки по каналам, строгая валидация настроек.

Чтение, история и тестовый пинг — mod+, сохранение настроек — admin+.
"""
import json
import os

from web.routes._common import (
    _notify_discord_sender, _log,
    render_template, session, redirect, url_for, request, jsonify,
)

SETTINGS_FILE = 'data/notification_settings.json'
HISTORY_FILE = 'data/notification_history.json'


def _read_dict(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as _ex:
        _log.debug('notifications: %s не читается: %s', path, _ex)
        return {}
    return data if isinstance(data, dict) else {}


def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required

    # ── NOTIFICATIONS API ────────────────────────────────────────────
    @app.route('/api/notifications/settings', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_notifications_settings_get():
        """Настройки уведомлений — дефолты диспетчера поверх файла."""
        from services.notification_dispatcher import load_settings
        return jsonify({'success': True, 'settings': load_settings()})

    @app.route('/api/notifications/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_notifications_settings_post():
        """Сохранить настройки: строгая валидация, чужие ключи целы."""
        from services.notification_dispatcher import validate_settings
        settings, err = validate_settings(request.get_json(silent=True),
                                          base=_read_dict(SETTINGS_FILE))
        if settings is None:
            return jsonify({'success': False, 'error': err}), 400
        os.makedirs('data', exist_ok=True)
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as _ex:
            _log.debug('notifications: %s не пишется: %s', SETTINGS_FILE, _ex)
            return jsonify({'success': False,
                            'error': 'Файл настроек не записался'}), 500
        return jsonify({'success': True, 'settings': settings})

    @app.route('/api/notifications/test', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_notifications_test():
        """Тестовое уведомление по всем настроенным каналам."""
        try:
            from services.notification_dispatcher import send_test
            channels = send_test(discord_sender=_notify_discord_sender)
            return jsonify({'success': True, 'channels': channels})
        except Exception as _ex:
            _log.debug('notifications test: %s', _ex)
            return jsonify({'success': False,
                            'error': 'Тест не ушёл — смотрите логи'}), 500

    @app.route('/api/notifications/history', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_notifications_history():
        """История уведомлений: фильтры ?event=/?outcome=, сводка доставки."""
        from services.notification_dispatcher import (
            EVENTS, filter_history, delivery_stats)
        loaded = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                if isinstance(raw, list):
                    loaded = raw
            except Exception as _ex:
                _log.debug('notifications: %s не читается: %s',
                           HISTORY_FILE, _ex)
        history = [h for h in loaded if isinstance(h, dict)]
        # Сортировка по дате (новые первые)
        history.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Чистим markdown из видимых полей — панель разметку не рендерит
        try:
            import web.app as _app
            for _h in history:
                _app._clean_md_fields(_h)
        except Exception as _ex:
            _log.debug('notifications history: _clean_md_fields: %s', _ex)

        event = (request.args.get('event') or '').strip() or None
        outcome = (request.args.get('outcome') or '').strip() or None
        if outcome not in (None, 'ok', 'fail'):
            outcome = None  # битый фильтр мягко снимаем
        filtered = filter_history(history, event=event, outcome=outcome)

        return jsonify({
            'success': True,
            'notifications': filtered[:50],  # Максимум 50
            'total': len(history),
            'filters': {'event': event, 'outcome': outcome},
            'events': {key: label
                       for key, (_flag, label, _icon) in EVENTS.items()},
            'delivery': delivery_stats(history),
        })

    @app.route('/notifications')
    @login_required
    def notifications_page():
        """Страница настроек уведомлений (только персонал)"""
        if ROLES.get(session.get('role'), -1) < ROLES.get('mod', 999):
            return redirect(url_for('index'))
        return render_template('notifications.html',
                               role=session.get('role'),
                               username=session.get('username'))
