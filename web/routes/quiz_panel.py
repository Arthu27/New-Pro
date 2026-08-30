# -*- coding: utf-8 -*-
"""Квиз в панели: библиотека вопросов и сезонный зачёт (1:1 с когом /квиз).

Панель пишет в то же хранилище GuildData('quiz'), что читает бот, и зовёт
РОВНО те же чистые функции кога: try_add_question / try_remove_question /
sorted_scores. Тексты ошибок одинаковые в Discord и в панели по построению.

Чтение (страница и состояние) — mod+. Запись — admin+, как assign-команды
кога (manage_guild): добавить/удалить вопрос, обнулить зачёт.
"""

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, os,
)

from db import GuildData
from cogs import quiz as Q


def _resolve_name(bot, gid, uid):
    """Имя из кэша бота; офлайн/не найден — честный фолбэк на ID."""
    if bot is not None:
        try:
            g = bot.get_guild(int(gid))
            m = g.get_member(int(uid)) if g else None
            if m is not None:
                return str(m.display_name)
        except Exception as _ex:
            _log.debug("_resolve_name(): кэш недоступен: %s", _ex)
    return f'ID {uid}'


def quiz_payload(gid, bot=None):
    """Единая картина квиза для панели: и GET, и ответы мутаций."""
    db = GuildData('quiz')
    questions = db.get(gid, 'questions', []) or []
    scores = db.get(gid, 'scores', {}) or {}
    top = []
    for uid, pts, correct, wins in Q.sorted_scores(scores)[:10]:
        top.append({'user_id': uid, 'name': _resolve_name(bot, gid, uid),
                    'points': pts, 'correct': correct, 'wins': wins})
    active = 0
    if bot is not None:
        try:
            cog = bot.get_cog('Quiz')
            if cog is not None:
                active = sum(1 for st in cog.sessions.values()
                             if not st.get('cancelled'))
        except Exception as _ex:
            _log.debug("quiz_payload(): сессии не прочитаны: %s", _ex)
    return {
        'success': True,
        'questions': [{'n': i, 'q': q.get('q', ''),
                       'answers': q.get('answers', []),
                       'added_by': q.get('added_by', ''),
                       'added_at': q.get('added_at', '')}
                      for i, q in enumerate(questions, 1)],
        'custom_count': len(questions),
        'builtin_count': len(Q.DEFAULT_QUESTIONS),
        'scores_top': top,
        'scores_total': len(scores),
        'sessions_active': active,
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/quiz')
    @login_required
    @role_required('mod')
    def quiz_page():
        return render_template('quiz.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/quiz/state')
    @login_required
    @role_required('mod')
    def api_quiz_state():
        import web.app as _app
        return jsonify(quiz_payload(ctx.active_guild_id(), bot=_app.bot_instance))

    @app.route('/api/quiz/questions/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_quiz_add():
        """Добавить вопрос. Формат — тот же, что у /квиз добавить:
        либо spec 'Вопрос? | ответ1 ; ответ2', либо пара question+answers[],
        из которой spec собирается байт-в-байт перед вызовом функции кога."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        spec = data.get('spec')
        if not spec:
            answers = data.get('answers')
            if isinstance(answers, str):
                answers = [a.strip() for a in answers.split(';')]
            spec = '%s | %s' % (data.get('question') or '',
                                ' ; '.join(a for a in (answers or []) if a))
        db = GuildData('quiz')
        gid = _gid
        questions = db.get(gid, 'questions', []) or []
        item, err = Q.try_add_question(questions, spec,
                                       added_by='panel:%s' % session.get('username'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        db.set(gid, 'questions', questions)
        import web.app as _app
        body = quiz_payload(gid, bot=_app.bot_instance)
        body['added'] = item
        return jsonify(body)

    @app.route('/api/quiz/questions/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_quiz_remove():
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        db = GuildData('quiz')
        gid = _gid
        questions = db.get(gid, 'questions', []) or []
        removed, err = Q.try_remove_question(questions, data.get('index'))
        if err:
            code = 400 if 'целое число' in err else 404
            return jsonify({'success': False, 'error': err}), code
        db.set(gid, 'questions', questions)
        import web.app as _app
        body = quiz_payload(gid, bot=_app.bot_instance)
        body['removed'] = removed
        return jsonify(body)

    @app.route('/api/quiz/scores/reset', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_quiz_reset():
        """Обнулить сезонный зачёт — тот же эффект, что у /квиз обнулить."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        gid = _gid
        GuildData('quiz').set(gid, 'scores', {})
        import web.app as _app
        return jsonify(quiz_payload(gid, bot=_app.bot_instance))
