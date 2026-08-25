# -*- coding: utf-8 -*-
"""Настройки карточек логов: включение, тема, акцент + живой предпросмотр.

Карточка рисуется ботом при отправке лога (cogs/logs.py:_safe_send читает
data/log_cards_<gid>.json через services/log_card.get_log_cards_cfg).
Здесь — только панельная сторона: прочитать/сохранить настройки и отдать
PNG-пример, чтобы владелец видел результат до того, как «поедет» в канал.

Чтение — mod+, запись — admin+ (как канал апелляций и редактор правил).
"""
from web.routes._common import (
    _log, render_template, session, request, jsonify, Response,
)

from services import log_card as LC

# Живой пример для предпросмотра: выглядит как настоящая mod-карточка.
PREVIEW_ROWS = (
    ('Пользователь', 'GhostBlade · 523456789012345678'),
    ('Модератор', 'sonya.staff'),
    ('Причина', 'Повторные провокации после предупреждения в #general'),
    ('Срок', 'предупреждение 2 из 3'),
)


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/guild/<gid>/log-cards/settings', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_log_cards_settings_get(gid):
        cfg = LC.get_log_cards_cfg(gid)
        return jsonify({'success': True, 'cfg': cfg,
                        'themes': [{'id': t, 'label': LC.LOG_CARD_THEMES[t]['label']}
                                   for t in LC.LOG_CARD_THEME_ORDER]})

    @app.route('/api/guild/<gid>/log-cards/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_log_cards_settings_post(gid):
        cfg = LC.save_log_cards_cfg(gid, request.get_json(silent=True) or {})
        _log.info('log-cards: %s обновил оформление на %s: %s',
                  session.get('username', '?'), gid, cfg)
        theme_lbl = LC.LOG_CARD_THEMES.get(cfg['theme'], {}).get('label', cfg['theme'])
        return jsonify({'success': True, 'cfg': cfg,
                        'message': f'Оформление сохранено: {theme_lbl}' +
                                   (' · свой акцент' if cfg['accent'] else '')})

    @app.route('/api/guild/<gid>/log-cards/preview.png')
    @login_required
    @role_required('mod')
    def api_log_cards_preview(gid):
        theme = request.args.get('theme')
        accent = request.args.get('accent')
        cat = str(request.args.get('cat') or 'mod')
        if cat not in LC.CATEGORY_STYLES:
            cat = 'mod'
        try:
            png = LC.render_log_card(
                cat, 'Пример: выдано предупреждение', PREVIEW_ROWS,
                color=0xE2455A, cat_name=cat,
                guild_name='Aether Demo', time_str='20:41 UTC',
                theme=theme, accent=accent, fmt='png')
        except Exception as _ex:
            _log.debug('log-cards preview: %s', _ex)
            png = None
        if not png:
            return jsonify({'success': False,
                            'error': 'Не удалось отрисовать пример'}), 500
        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp
