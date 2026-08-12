# -*- coding: utf-8 -*-
"""AI-модерация API (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── AI MODERATION API ─────────────────────────────────────
    @app .route ('/api/ai-mod/config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_mod_config ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if request .method =='POST':
            cfg =cog .load_config (guild_id )
            patch =request .get_json (silent =True )or {}
            for k ,v in patch .items ():
                if isinstance (v ,dict )and k in cfg :
                    cfg [k ].update (v )
                else :
                    cfg [k ]=v 
            cog .save_config (guild_id ,cfg )
            return jsonify ({'ok':True })
        return jsonify (cog .load_config (guild_id ))


    @app .route ('/api/ai-mod/stats')
    @login_required 
    def api_ai_mod_stats ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        history =cog .load_history (guild_id )
        from collections import Counter 
        import time as _t 
        action_counter =Counter (h .get ('action')for h in history )
        last_24h =sum (1 for h in history if _t .time ()-h .get ('ts',0 )<86400 )
        return jsonify ({
        'total':len (history ),
        'last_24h':last_24h ,
        'bans':action_counter .get ('ban',0 ),
        'mutes':action_counter .get ('mute',0 ),
        'kicks':action_counter .get ('kick',0 ),
        'warns':action_counter .get ('warn',0 ),
        })


    @app .route ('/api/ai-mod/test',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_mod_test ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        cfg =cog .load_config (guild_id )
        d =request .get_json (silent =True )or {}
        text =d .get ('text','')
        matches =cog .detect_toxic (text ,cfg .get ('languages',['ru','tr','en']),cfg .get ('sensitivity',0.7 ))
        if not matches :
            return jsonify ({'clean':True })
        severity_order =['mild','spam','moderate','discrimination','severe']
        top =max (matches ,key =lambda m :severity_order .index (m [0 ]))
        return jsonify ({
        'clean':False ,
        'severity':top [0 ],
        'matches':len (matches ),
        'patterns':[p [1 ]for p in matches ]
        })
