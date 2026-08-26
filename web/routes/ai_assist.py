# -*- coding: utf-8 -*-
"""AI-ассистент: стрим, анонсы, эмбеды (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


        # ── AI API ───────────────────────────────────────────────────────────────

    @app .route ('/api/ai/stream',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_ai_stream ():
        from web .ai_helper import ai_assistant 
        d =request .get_json (silent =True )or {}
        message =d .get ('message','').strip ()
        if not message :
            return jsonify ({'error':'Сообщение пусто'}),400 
        username =session .get ('username','anon')
        history_key =f'ai_history_{username}'
        history =session .get (history_key ,[])
        context ={'user_name':username ,'guild_name':'Hakumo Сервер'}
        answer ,new_history ,model_name ,_ =ai_assistant (message ,context ,history )
        # Храним только последние 6 пар сообщений (user + assistant),
        # чтобы session-cookie не превысил 4KB
        compact =[]
        for m in new_history [-12 :]:
            if m .get ('role')in ('user','assistant'):
                compact .append ({
                'role':m ['role'],
                'content':(m .get ('content')or '')[:500 ],
                })
        session [history_key ]=compact 
        return jsonify ({'ok':True ,'response':answer ,'history':new_history ,'model':model_name })


    @app .route ('/api/ai/assistant',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_ai_assistant ():
        from web .ai_helper import ai_assistant 
        d =request .get_json (silent =True )or {}
        message =d .get ('message','').strip ()
        if not message :
            return jsonify ({'error':'Сообщение пусто'}),400 
        username =session .get ('username','anon')
        history_key =f'ai_history_{username}'
        history =session .get (history_key ,[])
        context ={'user_name':username ,'guild_name':'Hakumo Сервер'}
        answer ,new_history ,model_name ,_ =ai_assistant (message ,context ,history )
        compact =[]
        for m in new_history [-12 :]:
            if m .get ('role')in ('user','assistant'):
                compact .append ({
                'role':m ['role'],
                'content':(m .get ('content')or '')[:500 ],
                })
        session [history_key ]=compact 
        return jsonify ({'ok':True ,'response':answer ,'history':new_history ,'model':model_name })


    @app .route ('/api/ai/clear',methods =['POST'])
    @login_required 
    def api_ai_clear ():
    # Очищаем историю только текущего пользователя
        username =session .get ('username','anon')
        session .pop (f'ai_history_{username}',None )
        return jsonify ({'ok':True })


    @app .route ('/api/ai/announcement',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_announcement ():
        from web .ai_helper import _call_text 
        d =request .get_json (silent =True )or {}
        topic =d .get ('topic','Общее объявление')
        tone =d .get ('tone','официальный')
        prompt = (
            f"Напиши профессиональное объявление для Discord-сервера на тему '{topic}', "
            f"тон: {tone}. Добавь заголовок и эмодзи. До 200 слов."
        )
        messages =[
        {"role":"system","content":"Ты — ассистент, пишущий эффектные объявления для Discord-сервера Hakumo. Пиши только текст объявления, без пояснений."},
        {"role":"user","content":prompt }
        ]
        announcement =_call_text (messages ,max_tokens =600 )
        return jsonify ({'ok':True ,'text':announcement ,'announcement':announcement ,'result':announcement })


    @app.route('/api/ai/mod-report', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ai_mod_report():
        from web.ai_helper import _call_text
        # Заказ владельца 2026-08-26: отчёт строится ТОЛЬКО на реальных
        # данных журнала (тот же источник, что страница «Отчёты»).
        # Нет данных — честный ответ без вызова модели. Никаких наказаний
        # ИИ не предлагает: муты/баны выдаёт только модератор-человек.
        try:
            from web.routes.mod_report import mod_report as _build
            rep = _build(active_guild_id(), days=7)
        except Exception as _ex:
            _log.debug("api_ai_mod_report(): подавлено: %s", _ex)
            rep = {'total': 0, 'mods_total': 0, 'per_mod': [], 'by_action': []}

        if not rep.get('total'):
            return jsonify({'ok': True, 'report':
                '📊 За последние 7 дней в журнале модерации нет ни одного действия.\n\n'
                'Это реальные данные из журнала бота — ничего выдуманного. '
                'Как только модераторы начнут работать через команды бота, '
                'здесь появится живая статистика.', 'text': '', 'result': ''})

        lines = ["Реальная статистика модерации за 7 дней (журнал бота):",
                 f"- Всего действий: {rep['total']}",
                 f"- Активных модераторов: {rep['mods_total']}",
                 "- По модераторам: " + ", ".join(f"{m} — {c}" for m, c in rep['per_mod'][:10]),
                 "- По типам действий: " + ", ".join(f"{a} — {c}" for a, c in rep['by_action'][:10])]
        messages = [
        {"role": "system", "content":
            "Ты — аналитик модерации Discord-сервера. Пишешь краткий отчёт СТРОГО по "
            "предоставленным цифрам. Запрещено: выдумывать факты, имена и числа; "
            "предлагать или рекомендовать наказания конкретным людям (муты/баны/варны "
            "выдаёт только модератор-человек). Нет данных по пункту — напиши «нет данных»."},
        {"role": "user", "content": "\n".join(lines) +
            "\n\nНапиши краткую оценку загрузки команды модерации по ЭТИМ цифрам."}
        ]
        report = _call_text(messages, max_tokens=700)
        return jsonify({'ok': True, 'report': report, 'text': report, 'result': report})


    @app .route ('/api/ai/embed',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_embed ():
        from web .ai_helper import _call_text 
        d =request .get_json (silent =True )or {}
        prompt =d .get ('prompt','Правила сервера embedi')
        messages =[
        {"role":"system","content":"Ты ассистент-дизайнер Discord-эмбедов. Придумай подходящие теме заголовок и описание эмбеда."},
        {"role":"user","content":prompt }
        ]
        res =_call_text (messages ,max_tokens =400 )
        embed_data ={
        "title":f"📌 {prompt.title()}",
        "description":res ,
        "color":"#dc143c"
        }
        return jsonify ({'ok':True ,'embed':embed_data })
