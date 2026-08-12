# -*- coding: utf-8 -*-
"""Левелинг API (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── LEVELING API ─────────────────────────────────────
    @app .route ('/api/leveling/config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_leveling_config ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if request .method =='POST':
            cfg =cog .load_config (guild_id )
            patch =request .get_json (silent =True )or {}
            for k ,v in patch .items ():
                cfg [k ]=v 
            cog .save_config (guild_id ,cfg )
            return jsonify ({'ok':True ,'config':cfg })
        return jsonify (cog .load_config (guild_id ))


    @app .route ('/api/leveling/stats')
    @login_required 
    def api_leveling_stats ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement ,level_from_xp 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        users =data .get ('users',{})
        top =sorted (users .items (),key =lambda x :x [1 ].get ('xp',0 ),reverse =True )[:10 ]
        top_list =[]
        for uid ,u in top :
            member =bot .get_guild (int (guild_id )).get_member (int (uid ))if bot .get_guild (int (guild_id ))else None 
            level ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            top_list .append ({
            'name':member .display_name if member else f'User#{uid}',
            'level':level ,
            'xp':u .get ('xp',0 )
            })
        max_lvl =0 
        for u in users .values ():
            lvl ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            if lvl >max_lvl :
                max_lvl =lvl 
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({
        'total_users':len (users ),
        'max_level':max_lvl ,
        'total_xp':sum (u .get ('xp',0 )for u in users .values ()),
        'total_achievements':sum (len (v )for v in data .get ('achievements',{}).values ()),
        'total_ach_available':len (ACHIEVEMENTS ),
        'top':top_list 
        })


    @app .route ('/api/leveling/achievements')
    @login_required 
    def api_leveling_achievements ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        username =session .get ('username','')
        # Find user's unlocked achievements
        unlocked =[]
        for uid ,achs in data .get ('achievements',{}).items ():
            try :
                g =bot .get_guild (int (guild_id ))
                if g :
                    m =g .get_member (int (uid ))
                    if m and m .display_name ==username :
                        unlocked =achs 
                        break 
            except Exception as _ex:
                _log.debug("api_leveling_achievements(): подавлено: %s", _ex)
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({'unlocked':unlocked ,'catalog':ACHIEVEMENTS })


    @app .route ('/api/leveling/rewards')
    @login_required 
    def api_leveling_rewards ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        cfg =cog .load_config (guild_id )
        return jsonify ({'rewards':cfg .get ('level_rewards',{})})
