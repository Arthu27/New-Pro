# -*- coding: utf-8 -*-
"""Оформление карточки приветствия: темы авто-картинки, свой URL, живой пример.

Карточка рисуется ботом при входе/выходе участника (cogs/welcome_card.py
читает data/welcome_card.json через services/welcome_card_gen). Здесь —
только панельная сторона: прочитать/сохранить оформление и отдать
PNG-пример, чтобы владелец видел результат до того, как придёт участник.

Чтение — mod+, запись — admin+ (как оформление апелляций и лог-карточек).
"""
from web.routes._common import (
    _safe_json_obj,
    _log, render_template, session, request, jsonify, Response,
)

import os

from services import welcome_card_gen as WCG


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'mod_action', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('welcome-card: уведомление не ушло: %s', _ex)

    @app.route('/api/guild/<gid>/welcome-card/appearance')
    @login_required
    @role_required('mod')
    def api_welcome_card_appearance_get(gid):
        return jsonify({
            'success': True,
            'appearance': WCG.get_appearance(gid),
            'themes': [{'id': t, 'label': WCG.WELCOME_THEMES[t]['label']}
                       for t in WCG.WELCOME_THEME_ORDER],
        })

    @app.route('/api/guild/<gid>/welcome-card/appearance', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_welcome_card_appearance_post(gid):
        """Оформление карточки приветствия: авто (тема), свой URL или off."""
        data = _safe_json_obj()
        # Режим 'file' сохраняет ранее загруженный фон: клиент шлёт только
        # mode/theme/url, имя файла не перетираем пустой строкой
        cur = WCG.get_appearance(gid)
        data.setdefault('file', cur['file'])
        ap = WCG.normalize_appearance(data)
        url = ap['url']
        if ap['mode'] == 'url' and url:
            low = url.lower()
            if not low.startswith('https://'):
                return jsonify({'success': False,
                                'error': 'Картинка по URL — только по https:// (Discord не покажет http)'}), 400
            if any(bad in low for bad in ('localhost', '127.0.0.1', '0.0.0.0')):
                return jsonify({'success': False,
                                'error': 'Адрес картинки должен быть публичным'}), 400
            # Раньше ссылку получал только Discord — страницы Pinterest (pin.it,
            # /pin/…) показывались битой картинкой. Теперь панель сама скачивает
            # картинку (в т.ч. вытаскивая og:image со страницы пина) и хранит
            # как загруженный файл: работает везде и переживает чистки сайтов.
            res = WCG.resolve_image_url(url)
            if not res.get('ok'):
                return jsonify({'success': False, 'error': res.get('error')}), 400
            fname = 'по-ссылке' + os.path.splitext(res['direct_url'].split('?')[0])[1][:6] or '.jpg'
            saved = WCG.save_bg_file(gid, fname, res['data'])
            if not saved.get('ok'):
                return jsonify({'success': False, 'error': saved.get('error')}), 400
            ap = saved['appearance']
            ap['url'] = res['direct_url']   # прямая ссылка — для embed-ов
            ap = WCG.save_appearance(gid, ap)
            _notify(f'Фон по URL скачан и сохранён ({res["via"]})')
            _log.info('welcome-card: %s скачал фон по URL (%s) на %s',
                      session.get('username', '?'), res['via'], gid)
            return jsonify({'success': True, 'appearance': ap,
                            'message': 'Фон по ссылке скачан и сохранён '
                                       f'({res["via"]}) — Pinterest и '
                                       'картинки-страницы теперь работают'})
        ap = WCG.save_appearance(gid, ap)
        _notify(f'Оформление приветствия: {WCG.WELCOME_MODE_LABELS[ap["mode"]]}'
                + (f' ({ap["theme"]})' if ap['mode'] == 'auto' else ''))
        _log.info('welcome-card: %s обновил оформление на %s: %s',
                  session.get('username', '?'), gid, ap)
        theme_lbl = WCG.WELCOME_THEMES.get(ap['theme'], {}).get('label', ap['theme'])
        return jsonify({'success': True, 'appearance': ap,
                        'message': 'Оформление сохранено: ' +
                                   WCG.WELCOME_MODE_LABELS[ap['mode']] +
                                   (f' · тема «{theme_lbl}»' if ap['mode'] == 'auto' else '')})

    @app.route('/api/guild/<gid>/welcome-card/upload', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_welcome_card_upload(gid):
        """Загрузка файла фона карточки (multipart, поле 'file')."""
        f = request.files.get('file')
        if f is None or not f.filename:
            return jsonify({'success': False,
                            'error': 'Выберите файл картинки'}), 400
        try:
            data = f.stream.read(WCG.BG_MAX_BYTES + 1)
        except Exception:
            data = None
        if not data:
            return jsonify({'success': False,
                            'error': 'Не удалось прочитать файл'}), 400
        res = WCG.save_bg_file(gid, f.filename, data)
        if not res.get('ok'):
            return jsonify({'success': False, 'error': res['error']}), 400
        _notify('Загружен фон карточки приветствия')
        _log.info('welcome-card: %s загрузил фон %s на %s',
                  session.get('username', '?'), res['appearance']['file'], gid)
        return jsonify({'success': True, 'appearance': res['appearance'],
                        'message': 'Фон загружен — карточки будут рисоваться на вашей картинке'})

    @app.route('/api/guild/<gid>/welcome-card/preview.png')
    @login_required
    @role_required('mod')
    def api_welcome_card_preview(gid):
        """Живой предпросмотр карточки: тема авто или загруженный фон."""
        theme = request.args.get('theme')
        kind = str(request.args.get('kind') or 'welcome').strip().lower()
        if kind not in ('welcome', 'goodbye'):
            kind = 'welcome'
        try:
            ap = WCG.get_appearance(gid)
            bg = None
            if ap['mode'] == 'file':
                bg = WCG.load_bg_bytes(ap['file'])
            png = WCG.render_welcome_card(
                'Кипарис', 'Hakumo Demo', 1024,
                kind=kind, theme=theme or ap['theme'], bg_bytes=bg)
        except Exception as _ex:
            _log.debug('welcome-card preview: %s', _ex)
            png = None
        if not png:
            return jsonify({'success': False,
                            'error': 'Не удалось отрисовать пример'}), 500
        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp
