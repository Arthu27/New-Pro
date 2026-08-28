# -*- coding: utf-8 -*-
"""Транскрипты тикетов в панели: поиск, просмотр, экспорт (txt/html).

Раньше эти роуты читали data/transcripts.json, в который НИКТО не писал,
а HTML-экспорт подставлял контент сообщений без экранирования (XSS).
Теперь запись ведёт services/transcript_store (ког закрытия + автозакрытие),
здесь — только тонкое HTTP-отображение поверх него. Доступ: персонал (mod+).
"""

from web.routes._common import render_template, session, request, jsonify, Response
from services import transcript_store as _ts


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    # ── TRANSCRIPTS API ──────────────────────────────────────────────────
    @app.route('/api/transcripts/stats', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_transcripts_stats():
        """Сводная статистика транскриптов (секция «Сводка» на странице)."""
        return jsonify({'success': True, 'stats': _ts.stats(_ts.load())})

    @app.route('/api/transcripts/search', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_transcripts_search():
        """Поиск транскриптов (фильтры: search/days/category)."""
        data = request.get_json(silent=True) or {}
        query = str(data.get('search', '') or '')
        records = _ts.filter_records(
            _ts.load(),
            search=query,
            days=str(data.get('days', '') or ''),
            category=str(data.get('category', '') or ''),
        )
        items = []
        for t in records[:100]:
            item = _ts.summary(t)
            if query.strip():
                found = _ts.snippets(t, query)
                if found:
                    item['snippets'] = found
            items.append(item)
        return jsonify({
            'success': True,
            'transcripts': items,
            'total': len(records),
        })

    @app.route('/api/transcripts/<transcript_id>', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_transcript_get(transcript_id):
        """Полный транскрипт по ID."""
        t = _ts.find(_ts.load(), transcript_id)
        if t is None:
            return jsonify({'success': False, 'error': 'Транскрипт не найден'}), 404
        return jsonify({'success': True, 'transcript': t})

    @app.route('/api/transcripts/<transcript_id>/export', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_transcript_export(transcript_id):
        """Экспорт: ?format=txt|html — автономные файлы; контент экранирован."""
        t = _ts.find(_ts.load(), transcript_id)
        if t is None:
            return jsonify({'success': False, 'error': 'Транскрипт не найден'}), 404
        fmt = (request.args.get('format') or 'txt').lower()
        if fmt == 'txt':
            return Response(
                _ts.render_txt(t), mimetype='text/plain; charset=utf-8',
                headers={'Content-Disposition':
                         f'attachment; filename="{_ts.export_filename(t, "txt")}"',
                         'Cache-Control': 'no-store'})
        if fmt == 'html':
            return Response(
                _ts.render_html(t), mimetype='text/html; charset=utf-8',
                headers={'Content-Disposition':
                         f'attachment; filename="{_ts.export_filename(t, "html")}"',
                         'Cache-Control': 'no-store'})
        return jsonify({'success': False, 'error': 'Поддерживаются форматы: txt, html'}), 400

    @app.route('/transcripts')
    @login_required
    @role_required('mod')
    def transcripts_page():
        """Страница транскриптов тикетов (только персонал)."""
        return render_template('transcripts.html',
                               role=session.get('role'),
                               username=session.get('username'))
