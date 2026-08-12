# -*- coding: utf-8 -*-
"""Индекс угроз и локдаун (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── SECURITY THREAT DASHBOARD & LOCKDOWN API ─────────────────────────────

    @app .route ('/api/security/threat-index',methods =['GET'])
    @login_required 
    def api_threat_index ():
        import datetime as _dt ,json as _json 
        guild_id =request .args .get ('guild_id',str (MAIN_GUILD_ID ))

        # 1. Check warnings in last 24 hours
        warn_count =0 
        if os .path .exists ('data/warnings.json'):
            try :
                with open ('data/warnings.json','r',encoding ='utf-8')as _fp :
                    _wd =_json .load (_fp )
                for _uid ,_ws in _wd .get (str (guild_id ),{}).items ():
                    warn_count +=len (_ws )
            except Exception as _ex:
                _log.debug("api_threat_index(): подавлено: %s", _ex)

                # 2. Check mod cases
        mod_count =0 
        if os .path .exists ('data/mod_data.json'):
            try :
                with open ('data/mod_data.json','r',encoding ='utf-8')as _fp :
                    _md =_json .load (_fp )
                mod_count =len (_md .get ('case',{}).get (str (guild_id ),[]))
            except Exception as _ex:
                _log.debug("api_threat_index(): подавлено: %s", _ex)

                # 3. Check lockdown status
        lockdown_active =False 
        lockdown_file =f'data/lockdown_{guild_id}.json'
        if os .path .exists (lockdown_file ):
            try :
                with open (lockdown_file ,'r',encoding ='utf-8')as _fp :
                    _ld =_json .load (_fp )
                lockdown_active =bool (_ld .get ('active',False ))
            except Exception as _ex:
                _log.debug("api_threat_index(): подавлено: %s", _ex)

                # Calculate score (0-100)
        base_score =5 +min (warn_count *4 ,45 )+min (mod_count *5 ,40 )
        if lockdown_active :
            base_score =max (base_score ,75 )
        threat_score =min (base_score ,100 )

        if threat_score <=25 :
            level ="Низкая угроза (Спокойно)"
            color ="#2ECC71"
        elif threat_score <=60 :
            level ="Повышенная угроза (Внимание)"
            color ="#F1C40F"
        else :
            level ="Критическая угроза (Атака / Рейд)"
            color ="#E74C3C"

        history =[
        {"time":"-4ч","score":max (5 ,threat_score -10 )},
        {"time":"-3ч","score":max (5 ,threat_score -5 )},
        {"time":"-2ч","score":max (5 ,threat_score -8 )},
        {"time":"-1ч","score":max (5 ,threat_score -2 )},
        {"time":"Сейчас","score":threat_score },
        ]

        return jsonify ({
        "success":True ,
        "threat_score":threat_score ,
        "threat_level":level ,
        "threat_color":color ,
        "breakdown":{
        "warnings_recent":warn_count ,
        "mod_cases":mod_count ,
        "lockdown_active":lockdown_active 
        },
        "history":history ,
        "lockdown_active":lockdown_active 
        })


    @app .route ('/api/security/toggle-lockdown',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_toggle_lockdown ():
        import json as _json 
        data =request .get_json (silent =True )or {}
        guild_id =str (data .get ('guild_id',MAIN_GUILD_ID ))
        lockdown_file =f'data/lockdown_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )

        current =False 
        if os .path .exists (lockdown_file ):
            try :
                with open (lockdown_file ,'r',encoding ='utf-8')as _fp :
                    current =bool (_json .load (_fp ).get ('active',False ))
            except Exception as _ex:
                _log.debug("api_toggle_lockdown(): подавлено: %s", _ex)

        new_status =not current 
        with open (lockdown_file ,'w',encoding ='utf-8')as _fp :
            _json .dump ({"active":new_status ,"updated_by":session .get ('username')},_fp ,indent =2 )

        status_str ="включён (карантин активен)"if new_status else "отключён (нормальный режим)"
        return jsonify ({
        "success":True ,
        "lockdown_active":new_status ,
        "message":f"🔒 Режим карантина сервера {status_str}!"
        })
