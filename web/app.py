import random 
import string 
from flask import Flask ,render_template ,request ,jsonify ,session ,redirect ,url_for ,send_from_directory 
import discord 
from discord .ext import commands 
import asyncio 
import json 
import os 
from functools import wraps 
import threading 
from datetime import datetime 

from datetime import timedelta 

# WebSocket импорты
try :
    from web .websocket_server import start_websocket_thread ,notify_ticket_created ,notify_ticket_updated ,notify_stats_updated 
    WEBSOCKET_ENABLED =True 
except ImportError :
    WEBSOCKET_ENABLED =False 
    print ('[WebSocket] Модуль не найден, real-time отключен')

import os as _os 
_BASE =_os .path .dirname (_os .path .abspath (__file__ ))
app =Flask (__name__ ,
template_folder =_os .path .join (_BASE ,'templates'),
static_folder =_os .path .join (_BASE ,'static'))

# Производительность: atomic yazma, TTL cache, toplu (batch) log flusher
from web import _store # noqa: E402
import atexit # noqa: E402

app .secret_key ="ultra-secret-key-change-this-in-production"
app .config ['TEMPLATES_AUTO_RELOAD']=True 
app .config ['SESSION_PERMANENT']=True 
app .config ['PERMANENT_SESSION_LIFETIME']=timedelta (days =30 )
app .jinja_env .auto_reload =True 

# Session: default Flask cookie session (itsdangerous imzali cookie).
# Старый: flask_session filesystem (her istekte dosya IO, 50 paralel istekte darboгaz).
# Новый: cookie, sifir disk IO, <500 byte. Oturum boyutu маленький oldugu icin sorun degil.
# Ileride Redis gerekirse SESSION_TYPE=redis eklenebilir.
_USE_FS_SESSION =_os .getenv ('USE_FS_SESSION','0')=='1'
if _USE_FS_SESSION :
    app .config ['SESSION_TYPE']='filesystem'
    app .config ['SESSION_FILE_DIR']=_os .path .join (_BASE ,'..','data','flask_sessions')
    app .config ['SESSION_FILE_THRESHOLD']=int (_os .getenv ('FLASK_SESSION_THRESHOLD','5000'))
    _os .makedirs (app .config ['SESSION_FILE_DIR'],exist_ok =True )
    from flask_session import Session 
    Session (app )

bot_instance =None 

# Rate Limiting 
from collections import defaultdict 
import time as _time 

_rate_limits =defaultdict (list )# ip: [timestamps]
RATE_LIMIT_WINDOW =60 # saniye
RATE_LIMIT_MAX =600 # на pencere max желание

def _check_rate_limit (ip ):
    now =_time .time ()
    window =_rate_limits [ip ]
    # Старый запись clear
    _rate_limits [ip ]=[t for t in window if now -t <RATE_LIMIT_WINDOW ]
    if len (_rate_limits [ip ])>=RATE_LIMIT_MAX :
        return False 
    _rate_limits [ip ].append (now )
    return True 

@app .before_request 
def before_request ():
    pass # Rate limit удалено

    # Panel Log 
def _log_login (username ,roles ,avatar ,discord_id ):
    """Вход yapan useryы сохранить."""
    try :
        os .makedirs ('data',exist_ok =True )
        f ='data/login_log.json'
        logs =_store .read_json (f ,default =[])
        if not isinstance (logs ,list ):
            logs =[]
            # Сервер infosini bot'tan al
        guild_name =None 
        guild_icon =None 
        if bot_instance and discord_id and discord_id .isdigit ():
            for g in bot_instance .guilds :
                m =g .get_member (int (discord_id ))
                if m :
                    guild_name =g .name 
                    guild_icon =str (g .icon .url )if g .icon else None 
                    break 
        logs .append ({
        'username':username ,
        'role':role ,
        'avatar':avatar ,
        'discord_id':discord_id ,
        'guild_name':guild_name ,
        'guild_icon':guild_icon ,
        'ip':request .remote_addr ,
        'timestamp':datetime .utcnow ().isoformat ()
        })
        _store .atomic_write_json (f ,logs [-200 :])
        _store .invalidate_path (f )
    except Exception :
        pass 

        # Массовая (batch) panel log flusher — POST/DELETE yolunu bloklamaz
_panel_log_flusher =_store .PeriodicFlush (
'data/panel_logs.json',
flush_interval =5.0 ,
max_entries =500 ,# 1000 -> 500: dosya шiшmesin
batch_threshold =50 ,
)
atexit .register (_panel_log_flusher .shutdown )


def _log_panel_action (action ,detail =''):
    try :
        _panel_log_flusher .append ({
        'username':session .get ('username','?'),
        'role':session .get ('role','?'),
        'action':action ,
        'detail':detail ,
        'ip':request .remote_addr ,
        'timestamp':datetime .utcnow ().isoformat (),
        })
    except Exception :
        pass 

        # ETag: GET + JSON + whitelist path'lerde tarayici/bot уровеньsinde cache
_ETAG_PATHS =(
'/api/logs',
'/api/warnings',
'/api/login-log',
'/api/stats',
'/api/guilds',
)


@app .after_request 
def after_request (response ):
# Sadece POST/DELETE iшlemleri logla — yюksek frekanslы GET polling'leri sessiz
    if request .method in ('POST','DELETE')and session .get ('logged_in'):
        path =request .path 
        # Login/logout hariч
        if path not in ('/login','/logout','/register'):
            _log_panel_action (f'{request.method} {path}','')

            # ETag: тот же icerik icin 304 dondur (network + JSON parse tasarrufu)
    if (request .method =='GET'
    and response .status_code ==200 
    and response .is_json 
    and request .path in _ETAG_PATHS ):
        try :
            data =response .get_json ()
            etag =_store .make_etag (data )
            if etag :
            # set_etag onu '"W/..."' formatina cevirir; biz de If-None-Match ile
            # tirnak dahil tam karsilastiriyoruz.
                response .set_etag (etag )
                response_etag =response .headers .get ('ETag')
                inm =request .headers .get ('If-None-Match')
                if inm and response_etag and inm .strip ()==response_etag :
                    response .status_code =304 
                    response .set_data (b'')
        except Exception as _ex :
            print (f"[ETAG] error on {request.path}: {_ex!r}",flush =True )

            # Tarayici cache'i bypass — admin panel icin kritik (gelistirme длительностьci)
    if request .path .startswith ('/static/'):
        response .headers ['Cache-Control']='no-cache, no-store, must-revalidate'
        response .headers ['Pragma']='no-cache'
        response .headers ['Expires']='0'
    elif request .path .startswith ('/api/')or response .is_json :
        response .headers ['Cache-Control']='no-store'
    else :
        response .headers ['Cache-Control']='no-cache, must-revalidate'

        # CSP: Cloudflare или proxy bazen cok sikili CSP ekler; kendi
        # header'imizi koyarak 'unsafe-eval' ve 'unsafe-inline' izni veriyoruz.
        # Bu admin paneli (trusted пользовательlar) oldugu icin inline JS/eval OK.
    if not response .headers .get ('Content-Security-Policy'):
        csp =(
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https: wss: ws: http:; "
        "frame-ancestors 'self'"
        )
        response .headers ['Content-Security-Policy']=csp 

    return response 
@app .errorhandler (Exception )
def _handle_unexpected_error (e ):
    from werkzeug .exceptions import HTTPException 
    if isinstance (e ,HTTPException ):
        return e 
    try :
        import traceback 
        print ("[WEB][ERR] Unhandled exception:",repr (e ),flush =True )
        traceback .print_exc ()
    except Exception :
        pass 
    return ("Internal Сервер Error",500 )

    # Sabit сервер ID — bot'un ilk bulduгu сервер ispolzuetsya, panelden mюmkюn izmenit
MAIN_GUILD_ID =os .getenv ('MAIN_GUILD_ID','1498837105915330562')

# Роли администратор (den nizkogo e visokomu)
ROLES ={
'uye':0 ,
'mod':1 ,
'admin':2 ,
'owner':3 
}

# Только sahip fiksirovan user как kполучает
USERS ={
'owner':{'password':'123','role':'owner'},
}

def _safe_avatar_url (value ):
    """Do заметок serve stale guild-profile avatar URLs stored in old JSON files."""
    if not isinstance (value ,str )or '/guilds/'in value :
        return 'https://cdn.discordapp.com/embed/avatars/0.png'
    return value 

    # Discord роли ID → panel роли — data/role_map.json
DISCORD_ROLE_MAP ={}
_ROLE_MAP_PATH ='data/role_map.json'

def _load_role_map ():
    global DISCORD_ROLE_MAP 
    try :
        if os .path .exists (_ROLE_MAP_PATH ):
            data =_store .read_json (_ROLE_MAP_PATH ,default ={})
            DISCORD_ROLE_MAP =data if isinstance (data ,dict )else {}
        else :
            DISCORD_ROLE_MAP ={}
    except :
        DISCORD_ROLE_MAP ={}

def _save_role_map ():
    try :
        os .makedirs ('data',exist_ok =True )
        _store .atomic_write_json (_ROLE_MAP_PATH ,DISCORD_ROLE_MAP )
        _store .invalidate_path (_ROLE_MAP_PATH )
    except :
        pass 

_load_role_map ()

def _get_role_from_discord (discord_id :str )->str :
    """Opredelit роль в paneli по Discord-ролям ve администрации"""
    if not bot_instance :
        return 'uye'
    try :
        gid =MAIN_GUILD_ID or (str (bot_instance .guilds [0 ].id )if bot_instance .guilds else None )
        if not gid :
            return 'uye'
        guild =bot_instance .get_guild (int (gid ))
        if not guild :
            return 'uye'
        member =guild .get_member (int (discord_id ))
        if not member :
            return 'uye'

            # 1. Rucnoy eшleme den role_map.json
        best_mapped ='uye'
        for discord_role in member .roles :
            mapped =DISCORD_ROLE_MAP .get (str (discord_role .id ))
            if mapped =='owner':
                return 'owner'
            if mapped =='admin':
                best_mapped ='admin'
            elif mapped =='mod'and best_mapped not in ('admin','owner'):
                best_mapped ='mod'
        if best_mapped !='uye':
            return best_mapped 

            # 2. Автоматически как по Discord-администрации
        perms =member .guild_permissions 
        if perms .administrator :
            return 'admin'
        if perms .ban_members or perms .kick_members or perms .manage_guild :
            return 'mod'
        if perms .manage_messages or perms .manage_channels :
            return 'mod'

        return 'uye'
    except Exception :
        return 'uye'

def login_required (f ):
    @wraps (f )
    def decorated_function (*args ,**kwargs ):
        if 'logged_in'not in session :
            return redirect (url_for ('login'))
            # Каждый 5 minutesda bir Discord роли canlы обновить (owner hariч)
        discord_id =session .get ('discord_id')
        if discord_id and session .get ('role')!='owner':
            import time as _t 
            last_check =session .get ('_role_checked',0 )
            if _t .time ()-last_check >300 :# 5 minutes
                live_role =_get_role_from_discord (discord_id )
                session ['role']=live_role 
                session ['_role_checked']=_t .time ()
                # members.json'u da обновить
                members_file ='data/members.json'
                if os .path .exists (members_file ):
                    try :
                        with open (members_file ,'r',encoding ='utf-8')as fp :
                            members =json .load (fp )
                        if discord_id in members :
                            members [discord_id ]['role']=live_role 
                            with open (members_file ,'w',encoding ='utf-8')as fp :
                                json .dump (members ,fp ,indent =2 ,ensure_ascii =False )
                    except Exception :
                        pass 
        return f (*args ,**kwargs )
    return decorated_function 

def role_required (min_role ):
    def decorator (f ):
        @wraps (f )
        def decorated_function (*args ,**kwargs ):
            if 'role'not in session :
                return jsonify ({'error':'Не автоматически'}),403 
            if ROLES .get (session ['role'],-1 )<ROLES .get (min_role ,999 ):
                return jsonify ({'error':'Нет доступ'}),403 
            return f (*args ,**kwargs )
        return decorated_function 
    return decorator 

@app .route ('/favicon.ico')
def favicon ():
    favicon_path =os .path .join (app .root_path ,'static','favicon.ico')
    if not os .path .exists (favicon_path ):
        return '',204 # No Content
    return send_from_directory (os .path .join (app .root_path ,'static'),
    'favicon.ico',mimetype ='image/vnd.microsoft.icon')

@app .route ('/health')
def health_check ():
    """Health check endpoint для Docker и мониторинга"""
    try :
        bot_instance =getattr (app ,'_bot_instance',None )
        if bot_instance and bot_instance .is_ready ():
            return jsonify ({
            'status':'healthy',
            'bot':'ready',
            'guilds':len (bot_instance .guilds ),
            'latency':round (bot_instance .latency *1000 ,2 ),
            'timestamp':datetime .now ().isoformat ()
            }),200 
        else :
            return jsonify ({
            'status':'degraded',
            'bot':'connecting',
            'timestamp':datetime .now ().isoformat ()
            }),503 
    except Exception as e :
        return jsonify ({
        'status':'error',
        'error':str (e ),
        'timestamp':datetime .now ().isoformat ()
        }),500 

@app .route ('/')
def index ():
    if 'logged_in'not in session :
        return redirect (url_for ('login'))
    if session .get ('role')=='uye':
        return render_template ('member_dashboard.html',role =session .get ('role'),username =session .get ('username'))
    return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/member-apply')
@login_required 
def member_apply_page ():
    return render_template ('member_apply.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/login',methods =['GET','POST'])
def login ():
# Token с автоматически вход — только localhost'tan
    token =request .args .get ('token')or request .form .get ('token')
    if token and request .remote_addr in ('127.0.0.1','::1'):
        tokens_file ='data/tokens.json'
        if os .path .exists (tokens_file ):
            with open (tokens_file ,'r',encoding ='utf-8')as f :
                tokens =json .load (f )
            if token in tokens :
                t =tokens [token ]
                session .permanent =True 
                session ['logged_in']=True 
                session ['username']=t ['username']
                session ['role']=t ['role']
                session .modified =True 
                return redirect (url_for ('index'))

    if request .method =='POST':
        username =request .form .get ('username')
        password =request .form .get ('password')

        # Только sahip fiksirovan user
        if username in USERS and USERS [username ]['password']==password :
            session .permanent =True 
            session ['logged_in']=True 
            session ['username']=username 
            session ['role']=USERS [username ]['role']
            _save_login_token (username ,USERS [username ]['role'])
            _log_login (username ,'owner',None ,None )
            return redirect (url_for ('index'))

            # Участник вход (По Discord ID) — роли Discord'dan opredelyaetsya автоматически как
        members_file ='data/members.json'
        if os .path .exists (members_file ):
            with open (members_file ,'r',encoding ='utf-8')as f :
                members =json .load (f )
            if username in members and members [username ].get ('password')==password :
                discord_id =username 
                # members.json'da owner varsa Discord контроль yapma — роль koru
                stored_role =members [discord_id ].get ('role','uye')
                if stored_role =='owner':
                    live_role ='owner'
                else :
                    live_role =_get_role_from_discord (discord_id )
                    members [discord_id ]['role']=live_role 
                    with open (members_file ,'w',encoding ='utf-8')as f :
                        json .dump (members ,f ,indent =2 ,ensure_ascii =False )
                session .permanent =True 
                session ['logged_in']=True 
                session ['username']=members [discord_id ]['display_name']
                session ['role']=live_role 
                session ['discord_id']=discord_id 
                _save_login_token (discord_id ,live_role )
                _log_login (
                members [discord_id ]['display_name'],
                live_role ,
                members [discord_id ].get ('avatar'),
                discord_id 
                )
                return redirect (url_for ('index'))

        return render_template ('login.html',error ='Неверное имя пользователя или пароль!')
    return render_template ('login.html')

    # Geчici проверка kodlarы {discord_id: {code, data}}
PENDING_VERIFICATIONS ={}

# 2FA baddyen oturumlar {session_token: {username, roles, expires}}
PENDING_2FA ={}

def _require_2fa (username ,roles ):
    """2FA kodu создать ve DM отправить, token вернуть"""
    import secrets 
    token =secrets .token_hex (16 )
    code =''.join ([str (random .randint (0 ,9 ))for _ in range (6 )])
    expires =datetime .utcnow ().timestamp ()+300 # 5 minutes
    PENDING_2FA [token ]={'username':username ,'role':roles ,'code':code ,'expires':expires }

    # Discord DM отправить
    if bot_instance :
        members_file ='data/members.json'
        discord_id =None 
        if os .path .exists (members_file ):
            with open (members_file ,'r',encoding ='utf-8')as f :
                members =json .load (f )
            for did ,m in members .items ():
                if m .get ('name')==username or m .get ('display_name')==username :
                    discord_id =did 
                    break 

        if discord_id :
            async def send_2fa ():
                try :
                    user =await bot_instance .fetch_user (int (discord_id ))
                    embed =discord .Embed (
                    title =' Panel Вход Проверка',
                    description =f'Проверка kodun: **`{code}`**\n\nBu kod 5 minutes geчerlidir.\nEгer sen вход yapmadыysan bu сообщение dikkate alma.',
                    color =0xDC143C 
                    )
                    await user .send (embed =embed )
                except :
                    pass 
            asyncio .run_coroutine_threadsafe (send_2fa (),bot_instance .loop )

    return token ,code 

@app .route ('/register',methods =['GET','POST'])
def register ():
    if request .method =='POST':
        step =request .form .get ('step','1')
        discord_id =request .form .get ('discord_id','').strip ()
        password =request .form .get ('password','').strip ()
        password2 =request .form .get ('password2','').strip ()

        # ADIM 2: Kod проверка
        if step =='2':
            code =request .form .get ('code','').strip ()
            if discord_id not in PENDING_VERIFICATIONS :
                return render_template ('register.html',error ='Проверка длительность doldu, tekrar dene.',step =1 )
            pv =PENDING_VERIFICATIONS [discord_id ]
            if pv ['code']!=code :
                return render_template ('register.html',error ='Неверный kod!',step =2 ,
                discord_id =discord_id ,password =pv ['password'])
                # Сохранить
            member_info =pv ['member_info']
            members_file ='data/members.json'
            os .makedirs ('data',exist_ok =True )
            members ={}
            if os .path .exists (members_file ):
                with open (members_file ,'r',encoding ='utf-8')as f :
                    members =json .load (f )
                    # Discord'dan canlы роли al
            live_role =_get_role_from_discord (discord_id )
            members [discord_id ]={
            'password':pv ['password'],
            'display_name':member_info ['display_name'],
            'name':member_info ['name'],
            'avatar':member_info ['avatar'],
            'role':live_role ,
            'registered_at':datetime .utcnow ().isoformat ()
            }
            with open (members_file ,'w',encoding ='utf-8')as f :
                json .dump (members ,f ,indent =2 ,ensure_ascii =False )
            del PENDING_VERIFICATIONS [discord_id ]
            return redirect (url_for ('login')+'?success=1')

            # ADIM 1: Form проверка
        if not discord_id or not password :
            return render_template ('register.html',error ='Zapolnite все polya!',step =1 )
        if not discord_id .isdigit ()or not (17 <=len (discord_id )<=19 ):
            return render_template ('register.html',error ='Неверный Discord ID!',step =1 )
        if password !=password2 :
            return render_template ('register.html',error ='Paroller не sovpadayut!',step =1 )
        if len (password )<6 :
            return render_template ('register.html',error ='Parola en az 6 karakter olmalы!',step =1 )

        if not bot_instance :
            return render_template ('register.html',error ='Bot шimdi oflayn, poprobuyte после.',step =1 )

            # До cache'den ara, bulamazsa fetch_member с Discord API'den тянуть
        member_info =None 

        async def find_member ():
        # До все сервер cache'den ara
            for guild in bot_instance .guilds :
                m =guild .get_member (int (discord_id ))
                if m :
                    return {'display_name':m .display_name ,'name':str (m ),'avatar':str (m .display_avatar .url )}
                    # Cache'de yoksa fetch_member с API'den тянуть (каждый сервер для)
            for guild in bot_instance .guilds :
                try :
                    m =await guild .fetch_member (int (discord_id ))
                    if m :
                        return {'display_name':m .display_name ,'name':str (m ),'avatar':str (m .display_avatar .url )}
                except Exception :
                    continue 
                    # Hiчbir на сервере найден fetch_user с Discord usersыnы al
            try :
                user =await bot_instance .fetch_user (int (discord_id ))
                if user :
                    return {'display_name':user .display_name ,'name':str (user ),'avatar':str (user .display_avatar .url )}
            except Exception :
                pass 
            return None 

        import asyncio 
        member_info =asyncio .run_coroutine_threadsafe (find_member (),bot_instance .loop ).result (timeout =15 )

        if not member_info :
            return render_template ('register.html',error ='Bu Discord ID не найдено! Discord ID\'nin верно olduгundan emin ol.',step =1 )

        members_file ='data/members.json'
        if os .path .exists (members_file ):
            with open (members_file ,'r',encoding ='utf-8')as f :
                members =json .load (f )
            if discord_id in members :
                return render_template ('register.html',error ='Bu Discord ID zaten запись!',step =1 )

                # DM с проверка kodu отправить
        code =''.join (random .choices (string .digits ,k =6 ))
        PENDING_VERIFICATIONS [discord_id ]={'code':code ,'password':password ,'member_info':member_info }

        async def send_dm ():
            try :
                user =await bot_instance .fetch_user (int (discord_id ))
                e =discord .Embed (
                title =" Aether Panel — Запись Проверка",
                color =0xc8922a ,
                timestamp =datetime .utcnow ()
                )
                e .description =(
                "```ansi\n\u001b[1;33m КТО ПРОВЕРКА GEREKLИ \u001b[0m\n```\n"
                "\n\n"
                f"Merhaba **{member_info['display_name']}**! \n\n"
                "**Aether Panel**'e запись olmak для aшaгыdaki\n"
                "проверка kodunu запись sayfasыna gir:\n\n"
                f"```fix\n{code}\n```\n\n"
                ""
                )
                e .add_field (name ="⏱ Geчerlilik",value ="```10 minutes```",inline =True )
                e .add_field (name =" Безопасность",value ="```Tek использовать```",inline =True )
                e .add_field (
                name =" Warning",
                value ="*Если sen запись olmadыysan bu сообщение dikkate alma ve кто paylaшma.*",
                inline =False 
                )
                e .set_footer (text ="Aether Panel • Доверие Запись Система")
                await user .send (embed =e )
            except Exception as ex :
                print (f"DM отправл: {ex}")

        asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop )

        return render_template ('register.html',step =2 ,discord_id =discord_id ,password =password ,
        info =f'{member_info["display_name"]} adыna Discord DM с 6 haneli kod отправлено.')

    return render_template ('register.html',step =1 )

@app .route ('/my-applications')
@login_required 
def my_applications ():
    if session .get ('role')!='uye':
        return redirect (url_for ('index'))
    return render_template ('my_applications.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/notifications')
@login_required 
def notifications ():
    if session .get ('role')!='uye':
        return redirect (url_for ('index'))
    return render_template ('notifications.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/announcements')
@login_required 
def announcements ():
    if session .get ('role')!='uye':
        return redirect (url_for ('index'))
    return render_template ('announcements.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/2fa',methods =['GET','POST'])
def two_factor ():
    token =request .args .get ('token')or request .form .get ('token')
    if not token or token not in PENDING_2FA :
        return redirect (url_for ('login'))

    pending =PENDING_2FA [token ]
    if datetime .utcnow ().timestamp ()>pending ['expires']:
        del PENDING_2FA [token ]
        return render_template ('login.html',error ='Проверка длительность doldu, tekrar вход yap.')

    if request .method =='POST':
        code =request .form .get ('code','').strip ()
        if code ==pending ['code']:
            session .permanent =True 
            session ['logged_in']=True 
            session ['username']=pending ['username']
            session ['role']=pending ['role']
            del PENDING_2FA [token ]
            _log_panel_action ('2FA_LOGIN',pending ['username'])
            return redirect (url_for ('index'))
        return render_template ('login.html',two_fa =True ,token =token ,error ='Неверный kod!')

    return render_template ('login.html',two_fa =True ,token =token )

@app .route ('/logout')
def logout ():
    session .clear ()
    return redirect (url_for ('login'))

@app .route ('/api/add-member',methods =['POST'])
@login_required 
def api_add_member ():
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('admin',999 ):
        return jsonify ({'error':'Нет доступ'}),403 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    password =data .get ('password','').strip ()
    display_name =data .get ('display_name',discord_id )
    name =data .get ('name',discord_id )
    avatar =data .get ('avatar','')

    if not discord_id or not password or len (password )<6 :
        return jsonify ({'error':'Неверный veriler'})

    members_file ='data/members.json'
    os .makedirs ('data',exist_ok =True )
    members ={}
    if os .path .exists (members_file ):
        with open (members_file ,'r',encoding ='utf-8')as f :
            members =json .load (f )

    if discord_id in members :
        return jsonify ({'error':'Bu ID zaten запись!'})

    members [discord_id ]={
    'password':password ,
    'display_name':display_name ,
    'name':name ,
    'avatar':avatar ,
    'registered_at':datetime .utcnow ().isoformat ()
    }
    with open (members_file ,'w',encoding ='utf-8')as f :
        json .dump (members ,f ,indent =2 ,ensure_ascii =False )

    return jsonify ({'success':True })

    # --- Участник API'leri ---

@app .route ('/api/my-applications')
@login_required 
def api_my_applications ():
    discord_id =session .get ('discord_id')
    if not discord_id :
        return jsonify ([])
    apps_file ='data/staff_apps.json'
    if not os .path .exists (apps_file ):
        return jsonify ([])
    with open (apps_file ,'r',encoding ='utf-8')as f :
        apps =json .load (f )
    my_apps =[a for a in apps .values ()if a .get ('user_id')==discord_id ]
    my_apps .sort (key =lambda x :x .get ('created_at',''),reverse =True )
    return jsonify (my_apps )

@app .route ('/api/my-notifications')
@login_required 
def api_my_notifications ():
    discord_id =session .get ('discord_id')
    if not discord_id :
        return jsonify ([])
    notif_file ='data/notifications.json'
    if not os .path .exists (notif_file ):
        return jsonify ([])
    with open (notif_file ,'r',encoding ='utf-8')as f :
        notifs =json .load (f )
    my =notifs .get (discord_id ,[])
    # Okundu iшaretle
    for n in my :
        n ['read']=True 
    notifs [discord_id ]=my 
    with open (notif_file ,'w',encoding ='utf-8')as f :
        json .dump (notifs ,f ,indent =2 ,ensure_ascii =False )
    return jsonify (list (reversed (my )))

@app .route ('/api/announcements')
@login_required 
def api_announcements ():
    ann_file ='data/announcements.json'
    if not os .path .exists (ann_file ):
        return jsonify ([])
    with open (ann_file ,'r',encoding ='utf-8')as f :
        anns =json .load (f )
    return jsonify (list (reversed (anns )))

@app .route ('/api/send-notification',methods =['POST'])
@login_required 
def api_send_notification ():
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
        return jsonify ({'error':'Нет доступ'}),403 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    message =data .get ('message','').strip ()
    title =data .get ('title','Уведомление').strip ()
    if not discord_id or not message :
        return jsonify ({'error':'Yetersiz verilerin'})

    notif_file ='data/notifications.json'
    os .makedirs ('data',exist_ok =True )
    notifs ={}
    if os .path .exists (notif_file ):
        with open (notif_file ,'r',encoding ='utf-8')as f :
            notifs =json .load (f )
    if discord_id not in notifs :
        notifs [discord_id ]=[]
    notifs [discord_id ].append ({
    'title':title ,
    'message':message ,
    'from':session .get ('username'),
    'created_at':datetime .utcnow ().isoformat (),
    'read':False 
    })
    with open (notif_file ,'w',encoding ='utf-8')as f :
        json .dump (notifs ,f ,indent =2 ,ensure_ascii =False )

        # DM отправить
    if bot_instance :
        async def send_dm ():
            try :
                user =await bot_instance .fetch_user (int (discord_id ))
                embed =discord .Embed (
                title =f" {title}",
                description =message ,
                color =0xdc143c 
                )
                embed .set_footer (text ="Aether Panel • Уведомление",icon_url =bot_instance .user .display_avatar .url )
                embed .timestamp =datetime .utcnow ()
                await user .send (embed =embed )
            except Exception as e :
                print (f"DM отправл: {e}")
        asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop )

    return jsonify ({'success':True })

@app .route ('/api/send-announcement',methods =['POST'])
@login_required 
def api_send_announcement ():
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
        return jsonify ({'error':'Нет доступ'}),403 
    data =request .get_json (silent =True )or {}
    title =data .get ('title','').strip ()
    message =data .get ('message','').strip ()
    if not title or not message :
        return jsonify ({'error':'Yetersiz verilerin'})

    ann_file ='data/announcements.json'
    os .makedirs ('data',exist_ok =True )
    anns =[]
    if os .path .exists (ann_file ):
        with open (ann_file ,'r',encoding ='utf-8')as f :
            anns =json .load (f )
    anns .append ({
    'title':title ,
    'message':message ,
    'from':session .get ('username'),
    'created_at':datetime .utcnow ().isoformat ()
    })
    with open (ann_file ,'w',encoding ='utf-8')as f :
        json .dump (anns ,f ,indent =2 ,ensure_ascii =False )
    return jsonify ({'success':True })

@app .route ('/users')
@login_required 
@role_required ('admin')
def users_page ():
    return render_template ('users.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/guilds')
@login_required 
@role_required ('mod')
def guilds_page ():
    return render_template ('guilds.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/logs')
@login_required 
@role_required ('mod')
def logs_page ():
    return render_template ('logs.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/warnings')
@login_required 
@role_required ('mod')
def warnings_page ():
    return render_template ('warnings.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/commands')
@login_required 
@role_required ('admin')
def commands_page ():
    return render_template ('commands.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/settings')
@login_required 
@role_required ('owner')
def settings_page ():
    return render_template ('settings.html',role =session .get ('role'),username =session .get ('username'))

    # API Endpoints
@app .route ('/api/login-log')
@login_required 
@role_required ('owner')
def api_login_log ():
    f ='data/login_log.json'
    if not os .path .exists (f ):
        return jsonify ([])
    try :
        logs =_store .cached_read_json (f ,ttl =5.0 ,default =[])
        # Owner kendi вход видеть — только diгer userlarы показать
        current_user =session .get ('username','')
        filtered =[l for l in logs if not (l .get ('username')==current_user and l .get ('role')=='owner')]
        for entry in filtered :
            entry ['avatar']=_safe_avatar_url (entry .get ('avatar'))
        return jsonify (list (reversed (filtered )))
    except Exception :
        return jsonify ([])

@app .route ('/api/stats')
@login_required 
def api_stats ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    guilds =len (bot_instance .guilds )
    users =sum (g .member_count or 0 for g in bot_instance .guilds )

    return jsonify ({
    'guilds':guilds ,
    'users':users ,
    'latency':round (bot_instance .latency *1000 ,2 ),
    'status':'online'
    })

@app .route ('/api/guilds')
@login_required 
def api_guilds ():
    if not bot_instance :
        return jsonify ([])

    try :
        guilds =[{
        'id':str (g .id ),
        'name':g .name ,
        'members':g .member_count ,
        'icon':str (g .icon .url )if g .icon else None ,
        'owner_id':str (g .owner_id )
        }for g in bot_instance .guilds ]

        return jsonify (guilds )
    except Exception as e :
        print (f"Сервер список Ошибки: {e}")
        return jsonify ([])

@app .route ('/api/leave-guild',methods =['POST'])
@login_required 
@role_required ('owner')
def api_leave_guild ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'}),503 
    data =request .get_json (silent =True )or {}
    guild_id =data .get ('guild_id')
    if not guild_id :
        return jsonify ({'error':'Neobhodim guild_id'}),400 
    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найдено'}),404 
        import asyncio 
        asyncio .run_coroutine_threadsafe (guild .leave (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'ok':True ,'name':guild .name })
    except Exception as e :
        return jsonify ({'error':str (e )}),500 

@app .route ('/api/guild/<guild_id>/member/<member_id>/nick',methods =['POST'])
@login_required 
@role_required ('mod')
def api_set_nick (guild_id ,member_id ):
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'}),503 
    data =request .get_json (silent =True )or {}
    nick =data .get ('nick','')
    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найдено'}),404 
        member =guild .get_member (int (member_id ))
        if not member :
            return jsonify ({'error':'Участник не найдено'}),404 
        import asyncio 
        asyncio .run_coroutine_threadsafe (
        member .edit (nick =nick or None ),
        bot_instance .loop 
        ).result (timeout =10 )
        return jsonify ({'ok':True ,'nick':nick })
    except Exception as e :
        return jsonify ({'error':str (e )}),500 

@app .route ('/api/guild/<guild_id>/members')
@login_required 
def api_guild_members (guild_id ):
    if not bot_instance :
        return jsonify ([])

    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ([])

            # Pagination: ?limit=50 (default), max 500
        try :
            limit =int (request .args .get ('limit',50 ))
        except (TypeError ,ValueError ):
            limit =50 
        try :
            offset =int (request .args .get ('offset',0 ))
        except (TypeError ,ValueError ):
            offset =0 
        limit =max (1 ,min (limit ,500 ))
        offset =max (0 ,offset )

        # 10s TTL cache — тот же icerik icin tekrar tekrar guild.members iterate etme
        cache_key =('members',int (guild_id ),guild .member_count )
        cached =_store ._cache .get (cache_key ,ttl =10.0 )
        if cached is None :
            cached =[]
            for m in list (guild .members ):
                created_at =discord .utils .snowflake_time (m .id )
                cached .append ({
                'id':str (m .id ),
                'name':m .name ,
                'display_name':m .display_name ,
                'discriminator':m .discriminator ,
                'avatar':str (m .display_avatar .url ),
                'joined_at':m .joined_at .isoformat ()if m .joined_at else None ,
                'created_at':created_at .isoformat (),
                'roles':[{'name':r .name ,'color':str (r .color )}for r in m .roles [1 :]],
                'bot':m .bot ,
                'status':str (m .status )if hasattr (m ,'status')else 'offline',
                'nick':m .nick ,
                'top_role':m .top_role .name if m .top_role else None ,
                })
            _store ._cache .set (cache_key ,cached ,ttl =10.0 )

            # Всего sayiyi pagination meta как dondurmek icin basit bir sarmalayici yerine
            # X-Total-Count header'i ekleyelim ki frontend tarafinda gerekirse kullanabilsin.
        total =len (cached )
        page =cached [offset :offset +limit ]
        resp =jsonify (page )
        resp .headers ['X-Total-Count']=str (total )
        resp .headers ['X-Limit']=str (limit )
        resp .headers ['X-Offset']=str (offset )
        return resp 
    except Exception as e :
        print (f"Участник список Ошибки: {e}")
        return jsonify ([])

@app .route ('/api/logs')
@login_required 
@role_required ('mod')
def api_logs ():
    audit_file ='data/audit_log.json'
    mod_file ='data/mod_data.json'
    all_events =[]
    filter_guild =request .args .get ('guild_id','')

    try :
        for log_file in ['data/audit_log.json','data/audit_log_backup.json']:
            data =_store .cached_read_json (log_file ,ttl =5.0 ,default ={})
            if not isinstance (data ,dict ):
                data ={}
            if data :
                for guild_id ,events in data .items ():
                    if filter_guild and guild_id !=filter_guild :
                        continue 
                    for ev in events :
                        ev ['guild_id']=guild_id 
                        all_events .append (ev )
                if all_events :
                    break 

        mod_data =_store .cached_read_json (mod_file ,ttl =5.0 ,default ={})
        if isinstance (mod_data ,dict ):
            for guild_id ,case in mod_data .get ('case',{}).items ():
                if filter_guild and guild_id !=filter_guild :
                    continue 
                for case in case :
                    all_events .append ({
                    'guild_id':guild_id ,
                    'category':'mod',
                    'action':case .get ('action','?').capitalize (),
                    'user_id':str (case .get ('user_id','')),
                    'user_name':str (case .get ('user_id','')),
                    'mod_name':str (case .get ('mod_id','')),
                    'reason':case .get ('reason',''),
                    'timestamp':case .get ('timestamp',''),
                    })

                    # Discord audit cache'den oku (bot 30sn'de bir обновл — быстрый)
        cache_file ='data/discord_audit_cache.json'
        cache =_store .cached_read_json (cache_file ,ttl =3.0 ,default ={})
        if isinstance (cache ,dict )and cache :
            existing_ts ={e .get ('timestamp','')for e in all_events }
            for gid ,events in cache .items ():
                if filter_guild and gid !=filter_guild :
                    continue 
                for ev in events :
                    ev_copy =dict (ev )
                    ev_copy ['guild_id']=gid 
                    if not ev_copy .get ('timestamp'):
                        continue 
                    if ev_copy ['timestamp']not in existing_ts :
                        all_events .append (ev_copy )

        all_events .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
        return jsonify (all_events [:1000 ])
    except Exception as e :
        print (f"Log Ошибки: {e}")
        return jsonify ([])

@app .route ('/api/warnings')
@login_required 
@role_required ('mod')
def api_warnings ():
    warns_file ='data/warnings.json'
    all_warnings =[]
    filter_guild =request .args .get ('guild_id','')

    try :
        data =_store .cached_read_json (warns_file ,ttl =5.0 ,default ={})
        if isinstance (data ,dict ):

                for guild_id ,guild_warns in data .items ():
                # None / "null" / boш / numeric olmayan / kыsa-длинный ID'leri atla
                    if (not isinstance (guild_id ,str )or not guild_id 
                    or not guild_id .isdigit ()or not (17 <=len (guild_id )<=22 )):
                        continue 
                    if filter_guild and guild_id !=filter_guild :
                        continue 
                    if not isinstance (guild_warns ,dict ):
                        continue 
                    for user_id ,warns in guild_warns .items ():
                        if (not isinstance (user_id ,str )or not user_id 
                        or not user_id .isdigit ()or not (17 <=len (user_id )<=22 )):
                            continue 
                        if not isinstance (warns ,list ):
                            continue 
                        for warn in warns [-10 :]:
                            if not isinstance (warn ,dict ):
                                continue 
                            all_warnings .append ({
                            'guild_id':guild_id ,
                            'user_id':user_id ,
                            'reason':warn .get ('reason','Не belirtildi'),
                            'moderator':warn .get ('moderator',warn .get ('mod','?')),
                            'timestamp':warn .get ('timestamp','')
                            })

        all_warnings .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
        return jsonify (all_warnings [:200 ])
    except Exception as e :
        print (f"Warning Ошибки: {e}")
        return jsonify ([])

@app .route ('/api/user/<user_id>')
@login_required 
@role_required ('mod')
def api_user_info (user_id ):
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    try :
        future =asyncio .run_coroutine_threadsafe (
        bot_instance .fetch_user (int (user_id )),bot_instance .loop 
        )
        user =future .result (timeout =10 )
        return jsonify ({
        'id':str (user .id ),
        'name':user .name ,
        'discriminator':user .discriminator ,
        'avatar':str (user .display_avatar .url ),
        'created_at':user .created_at .isoformat (),
        'bot':user .bot 
        })
    except :
        return jsonify ({'error':'Пользователь не найден'})

@app .route ('/api/command/ban',methods =['POST'])
@login_required 
@role_required ('admin')
def api_ban ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    data =request .get_json (silent =True )or {}
    guild_id =int (data .get ('guild_id'))
    user_id =int (data .get ('user_id'))
    reason =data .get ('reason','Ban с web-panel')

    try :
        guild =discord .utils .get (bot_instance .guilds ,id =guild_id )
        if not guild :
            return jsonify ({'error':'Сервер не найдено'})

        async def do ():
            user =await bot_instance .fetch_user (user_id )
            await guild .ban (user ,reason =f"{reason} (by {session.get('username')})")
            return user .name 

        name =asyncio .run_coroutine_threadsafe (do (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'success':True ,'message':f'{name} banlandы'})
    except Exception as e :
        return jsonify ({'error':str (e )})

@app .route ('/api/command/kick',methods =['POST'])
@login_required 
@role_required ('admin')
def api_kick ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    data =request .get_json (silent =True )or {}
    guild_id =int (data .get ('guild_id'))
    user_id =int (data .get ('user_id'))
    reason =data .get ('reason','Kick с web-panel')

    try :
        guild =discord .utils .get (bot_instance .guilds ,id =guild_id )
        if not guild :
            return jsonify ({'error':'Сервер не найдено'})
        member =guild .get_member (user_id )
        if not member :
            return jsonify ({'error':'Участник не найдено'})

        async def do ():
            await member .kick (reason =f"{reason} (by {session.get('username')})")
            return member .name 

        name =asyncio .run_coroutine_threadsafe (do (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'success':True ,'message':f'{name} atыldы'})
    except Exception as e :
        return jsonify ({'error':str (e )})

@app .route ('/api/command/warn',methods =['POST'])
@login_required 
@role_required ('mod')
def api_warn ():
    data =request .get_json (silent =True )or {}
    guild_id =data .get ('guild_id')
    user_id =data .get ('user_id')
    reason =(data .get ('reason')or 'Warning с web-panel').strip ()or 'Sebep belirtilmedi'

    # Validasyon: guild_id ve user_id numeric ve dolu olmalы
    if not guild_id or not str (guild_id ).strip ():
        return jsonify ({'error':'guild_id необходимо'}),400 
    if not user_id or not str (user_id ).strip ():
        return jsonify ({'error':'user_id необходимо'}),400 
    guild_id =str (guild_id ).strip ()
    user_id =str (user_id ).strip ()
    if not (guild_id .isdigit ()and user_id .isdigit ()):
        return jsonify ({'error':'guild_id ve user_id sayыsal olmalы'}),400 
    if not (17 <=len (guild_id )<=22 and 17 <=len (user_id )<=22 ):
        return jsonify ({'error':'guild_id ve user_id geчersiz (Discord ID 17-22 haneli olmalы)'}),400 
    if len (reason )>500 :
        return jsonify ({'error':'reason много длинный (max 500 karakter)'}),400 

    warns_file ='data/warnings.json'
    os .makedirs ('data',exist_ok =True )

    if os .path .exists (warns_file ):
        with open (warns_file ,'r',encoding ='utf-8')as f :
            try :
                warns =json .load (f )
            except json .JSONDecodeError :
                warns ={}
    else :
        warns ={}

        # Bozuk/istenmeyen anahtarlarы (None, "null", boш dict olmayan) atla
    if not isinstance (warns ,dict ):
        warns ={}

    if guild_id not in warns or not isinstance (warns [guild_id ],dict ):
        warns [guild_id ]={}
    if user_id not in warns [guild_id ]or not isinstance (warns [guild_id ][user_id ],list ):
        warns [guild_id ][user_id ]=[]

    warns [guild_id ][user_id ].append ({
    'reason':reason ,
    'moderator':session .get ('username'),
    'timestamp':datetime .utcnow ().isoformat ()
    })

    _store .atomic_write_json (warns_file ,warns )
    _store .invalidate_path (warns_file )

    return jsonify ({'success':True ,'message':'Warning добавлено'})

@app .route ('/api/modstats')
@login_required 
@role_required ('mod')
def api_modstats ():
    stats_file ='data/mod_stats.json'
    if os .path .exists (stats_file ):
        with open (stats_file ,'r')as f :
            return jsonify (json .load (f ))
    return jsonify ({})

@app .route ('/send-command')
@login_required 
@role_required ('admin')
def send_command_page ():
    return render_template ('send_command.html',
    role =session .get ('role'),
    username =session .get ('username'),
    main_guild_id =MAIN_GUILD_ID )

@app .route ('/execute-command')
@login_required 
@role_required ('admin')
def execute_command_page ():
    return render_template ('execute_command.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/api/execute-command',methods =['POST'])
@login_required 
@role_required ('admin')
def api_execute_command ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    data =request .get_json (silent =True )or {}
    command =data .get ('command')
    guild_id =data .get ('guild_id')

    try :
    # Сервер найти
        guild =None 
        for g in bot_instance .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 

        if not guild :
            return jsonify ({'error':'Сервер не найдено'})

        async def execute ():
            if command =='ban':
                user =await bot_instance .fetch_user (int (data .get ('user_id')))
                if not guild .me .guild_permissions .ban_members :
                    raise Exception ('Botun Ban администратор нет')
                await guild .ban (user ,reason =data .get ('reason','Ban с web-panel'))
            elif command =='kick':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник на сервере не найдено')
                if not guild .me .guild_permissions .kick_members :
                    raise Exception ('Botun Kick администратор нет')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Hedef usernыn роль bottan высокий')
                await member .kick (reason =data .get ('reason','Kick с web-panel'))
            elif command =='timeout':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник на сервере не найдено')
                if not guild .me .guild_permissions .moderate_members :
                    raise Exception ('Botun Mute (Moderate Members) администратор нет')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Hedef usernыn роль bottan высокий')
                duration =int (data .get ('duration',60 ))
                from datetime import timedelta as _td 
                await member .timeout (discord .utils .utcnow ()+_td (minutes =duration ),reason =data .get ('reason'))
            elif command =='warn':
                warns_file ='data/warnings.json'
                os .makedirs ('data',exist_ok =True )
                warns ={}
                if os .path .exists (warns_file ):
                    with open (warns_file ,'r',encoding ='utf-8')as wf :
                        warns =json .load (wf )
                gid_str =str (guild .id )
                uid_str =str (data .get ('user_id'))
                if gid_str not in warns :
                    warns [gid_str ]={}
                if uid_str not in warns [gid_str ]:
                    warns [gid_str ][uid_str ]=[]
                warns [gid_str ][uid_str ].append ({
                'reason':data .get ('reason','Warning с web-panel'),
                'moderator':session .get ('username'),
                'timestamp':datetime .utcnow ().isoformat ()
                })
                with open (warns_file ,'w',encoding ='utf-8')as wf :
                    json .dump (warns ,wf ,ensure_ascii =False )
                _store .invalidate_path (warns_file )
                # Warning DM отправить
                member =guild .get_member (int (data .get ('user_id')))
                if member :
                    dm_file =f'data/warn_dm_{guild.id}.json'
                    dm_msg =None 
                    if os .path .exists (dm_file ):
                        with open (dm_file ,'r',encoding ='utf-8')as df :
                            dm_cfg =json .load (df )
                        dm_msg =dm_cfg .get ('message')
                    if dm_msg :
                        dm_msg =dm_msg .replace ('{user}',member .display_name )
                        dm_msg =dm_msg .replace ('{reason}',data .get ('reason','Не belirtildi'))
                        dm_msg =dm_msg .replace ('{mod}',session .get ('username','?'))
                        dm_msg =dm_msg .replace ('{сервер}',guild .name )
                        try :
                            e_dm =discord .Embed (title =' Siz aldыnыz предупреждение',description =dm_msg ,color =0xc8922a )
                            e_dm .set_footer (text =guild .name )
                            await member .send (embed =e_dm )
                        except Exception :
                            pass 
            elif command =='jail':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник на сервере не найдено')
                    # Jail роли найти
                jail_role =discord .utils .get (guild .roles ,name ='Jail')
                if not jail_role :
                    raise Exception ('Jail роль не найдено. До "Jail Kur" команду чalышtыr.')
                    # Текущий роли сохранить, jail роль ver
                jail_data_file =f'data/jail_{guild.id}.json'
                jail_data ={}
                if os .path .exists (jail_data_file ):
                    with open (jail_data_file ,'r',encoding ='utf-8')as jf :
                        jail_data =json .load (jf )
                uid_str =str (member .id )
                jail_data [uid_str ]={
                'role':[str (r .id )for r in member .roles [1 :]],
                'reason':data .get ('reason','Djeyl с web-panel'),
                'mod':session .get ('username'),
                'timestamp':datetime .utcnow ().isoformat ()
                }
                with open (jail_data_file ,'w',encoding ='utf-8')as jf :
                    json .dump (jail_data ,jf ,indent =2 ,ensure_ascii =False )
                    # Все роли al, jail роль ver
                roles_to_remove =[r for r in member .roles [1 :]if r !=jail_role and not r .managed ]
                await member .remove_roles (*roles_to_remove ,reason ='Jail')
                await member .add_roles (jail_role ,reason =data .get ('reason','Djeyl с web-panel'))
                # DM отправить
                try :
                    e_dm =discord .Embed (title =' Jail Наказание',description =f'**{guild.name}** сервер jail наказание aldыnыz.\n**Причина:** {data.get("reason", "Не belirtildi")}',color =0xe74c3c )
                    await member .send (embed =e_dm )
                except Exception :
                    pass 
            elif command =='unjail':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник на сервере не найдено')
                jail_role =discord .utils .get (guild .roles ,name ='Jail')
                jail_data_file =f'data/jail_{guild.id}.json'
                if os .path .exists (jail_data_file ):
                    with open (jail_data_file ,'r',encoding ='utf-8')as jf :
                        jail_data =json .load (jf )
                    uid_str =str (member .id )
                    if uid_str in jail_data :
                        old_role_ids =jail_data [uid_str ].get ('role',[])
                        roles_to_restore =[guild .get_role (int (rid ))for rid in old_role_ids if guild .get_role (int (rid ))]
                        roles_to_restore =[r for r in roles_to_restore if r and not r .managed ]
                        if jail_role :
                            await member .remove_roles (jail_role ,reason ='Unjail')
                        await member .add_roles (*roles_to_restore ,reason ='Unjail')
                        del jail_data [uid_str ]
                        with open (jail_data_file ,'w',encoding ='utf-8')as jf :
                            json .dump (jail_data ,jf ,indent =2 ,ensure_ascii =False )
                elif jail_role :
                    await member .remove_roles (jail_role ,reason ='Unjail')
            elif command =='untimeout':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник на сервере не найдено')
                await member .timeout (None ,reason ='Razmut с web-panel')
            elif command =='unban':
                uid =data .get ('user_id')
                if not uid :
                    raise Exception ('Пользователь ID необходимо')
                user =await bot_instance .fetch_user (int (uid ))
                await guild .unban (user ,reason =data .get ('reason','Razban с web-panel'))
            elif command =='lock':
                ch =guild .get_channel (int (data .get ('channel_id',0 )))or guild .text_channels [0 ]
                await ch .set_permissions (guild .default_role ,send_messages =False )
            elif command =='unlock':
                ch =guild .get_channel (int (data .get ('channel_id',0 )))or guild .text_channels [0 ]
                await ch .set_permissions (guild .default_role ,send_messages =True )
            elif command =='clearwarns':
                uid_str =str (data .get ('user_id'))
                gid_str =str (guild .id )
                warns_file ='data/warnings.json'
                if os .path .exists (warns_file ):
                    with open (warns_file ,'r',encoding ='utf-8')as wf :
                        warns =json .load (wf )
                    if gid_str in warns and uid_str in warns [gid_str ]:
                        warns [gid_str ][uid_str ]=[]
                        with open (warns_file ,'w',encoding ='utf-8')as wf :
                            json .dump (warns ,wf ,ensure_ascii =False )
                        _store .invalidate_path (warns_file )
            elif command =='ticket_panel':
                from cogs .ticket import TicketView 
                ch =guild .get_channel (int (data .get ('channel_id',0 )))
                if not ch :
                    ch =guild .text_channels [0 ]
                from cogs .embed_utils import _divider 
                e =discord .Embed (title =" ПОДДЕРЖКА СИСТЕМА",color =0x5865F2 )
                e .description =(
                f"```ansi\n\u001b[1;34m Aether ПОДДЕРЖКА СИСТЕМА \u001b[0m\n```\n"
                f"{_divider()}\n\n"
                "Bir sorunla mы приветствие? Клик butona aшaгыda!\n\n"
                f"{_divider()}"
                )
                e .set_footer (text =f"{guild.name} • Поддержка Система",icon_url =guild .icon .url if guild .icon else None )
                await ch .send (embed =e ,view =TicketView ())
            elif command in ('текст','zar','rastgele'):
                pass # Eгlence команды Discord'dan чalышыr, panel только tetikler
                # Jail kategorisi, канал ve роль создать
                jail_cat =discord .utils .get (guild .categories ,name ='Наказание Комната')
                if not jail_cat :
                    jail_cat =await guild .create_category ('Наказание Комната')
                jail_role =discord .utils .get (guild .roles ,name ='Jail')
                if not jail_role :
                    jail_role =await guild .create_role (name ='Jail',color =discord .Color (0x2c2c2c ))
                    # Все channellardan Jail роли engelle
                for ch in guild .channels :
                    try :
                        await ch .set_permissions (jail_role ,send_messages =False ,read_messages =False )
                    except Exception :
                        pass 
                        # Jail канал создать
                jail_ch =discord .utils .get (guild .text_channels ,name ='jail')
                if not jail_ch :
                    overwrites ={
                    guild .default_role :discord .PermissionOverwrite (read_messages =False ),
                    jail_role :discord .PermissionOverwrite (read_messages =True ,send_messages =False ),
                    guild .me :discord .PermissionOverwrite (read_messages =True ,send_messages =True )
                    }
                    jail_ch =await guild .create_text_channel ('jail',category =jail_cat ,overwrites =overwrites )
                return 'setup_done'
            elif command =='clear':
                channel =guild .get_channel (int (data .get ('channel_id')))
                if not channel :
                    raise Exception ('Канал не найдено')
                if not guild .me .guild_permissions .manage_messages :
                    raise Exception ('Botun Сообщение Управление администратор нет')
                await channel .purge (limit =int (data .get ('amount',10 )))
            elif command =='role':
                member =guild .get_member (int (data .get ('user_id')))
                role =guild .get_role (int (data .get ('role_id')))
                if not member :
                    raise Exception ('Участник не найден')
                if not role :
                    raise Exception ('Роль не найдена')
                if not guild .me .guild_permissions .manage_roles :
                    raise Exception ('У бота нет права «Управление ролями»')
                if role >=guild .me .top_role :
                    raise Exception ('Эта роль выше самой высокой роли бота')
                action =data .get ('action','add')
                if action =='remove':
                    await member .remove_roles (role )
                else :
                    await member .add_roles (role )

        import asyncio 
        result =asyncio .run_coroutine_threadsafe (execute (),bot_instance .loop ).result (timeout =15 )

        if result =='setup_done':
            return jsonify ({'success':True ,'message':'Jail система kuruldu! Kategori, channel ve роли создано.'})
        return jsonify ({'success':True ,'message':'Действие успешно применено.'})
    except Exception as e :
        print (f"Команда чalышtыrma Ошибки: {e}")
        import traceback 
        traceback .print_exc ()
        return jsonify ({'error':str (e )})

@app .route ('/api/guild/<guild_id>/member/<member_id>/роли')
@login_required 
@role_required ('mod')
def api_member_roles (guild_id ,member_id ):
    if not bot_instance :
        return jsonify ([])
    try :
        guild =next ((g for g in bot_instance .guilds if str (g .id )==str (guild_id )),None )
        if not guild :
            return jsonify ([])
        member =guild .get_member (int (member_id ))
        if not member :
            return jsonify ([])
            # Участник sahip olduгu роли (everyone hariч)
        member_role_ids =[str (r .id )for r in member .roles [1 :]]
        # Все сервер роли
        all_roles =[{'id':str (r .id ),'name':r .name ,'color':str (r .color )}for r in guild .roles if r .name !='@everyone']
        all_roles .reverse ()
        has_roles =[r for r in all_roles if r ['id']in member_role_ids ]
        missing_roles =[r for r in all_roles if r ['id']not in member_role_ids ]
        return jsonify ({'has':has_roles ,'missing':missing_roles })
    except Exception as e :
        print (f"Участник роли Ошибки: {e}")
        return jsonify ([])

@app .route ('/api/send-message',methods =['POST'])
@login_required 
@role_required ('admin')
def api_send_message ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})

    data =request .get_json (silent =True )or {}
    guild_id =data .get ('guild_id')
    channel_id =data .get ('channel_id')
    message =data .get ('message')

    try :
    # Сервер найти
        guild =None 
        for g in bot_instance .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 

        if not guild :
            return jsonify ({'error':'Сервер не найдено'})

            # Канал найти
        channel =guild .get_channel (int (channel_id ))

        if not channel or not isinstance (channel ,discord .TextChannel ):
            return jsonify ({'error':'Канал не найдено или metin канал не'})

            # Сообщение отправить - bot'un kendi event loop'unu использовать
        async def send ():
            await channel .send (message )

        import asyncio 
        asyncio .run_coroutine_threadsafe (send (),bot_instance .loop )

        return jsonify ({'success':True ,'message':'Сообщение отправлено'})
    except Exception as e :
        print (f"Сообщение отправл Ошибки: {e}")
        import traceback 
        traceback .print_exc ()
        return jsonify ({'error':str (e )})

@app .route ('/staff-apps')
@login_required 
@role_required ('admin')
def staff_apps_page ():
    return render_template ('staff_apps.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/api/staff-apps')
@login_required 
@role_required ('admin')
def api_staff_apps ():
    apps_file ='data/staff_apps.json'
    if not os .path .exists (apps_file ):
        return jsonify ([])
    with open (apps_file ,'r',encoding ='utf-8')as f :
        data =json .load (f )
    apps =list (data .values ())
    apps .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
    return jsonify (apps )

@app .route ('/api/staff-apps/<app_id>/review',methods =['POST'])
@login_required 
@role_required ('admin')
def api_review_staff_app (app_id ):
    apps_file ='data/staff_apps.json'
    if not os .path .exists (apps_file ):
        return jsonify ({'error':'Dosya нет'})
    with open (apps_file ,'r',encoding ='utf-8')as f :
        data =json .load (f )
    if app_id not in data :
        return jsonify ({'error':'Заявка не найдено'})
    req =request .get_json (silent =True )or {}
    action =req .get ('action')# 'approve' or 'reject'
    note =req .get ('note','')
    data [app_id ]['status']='approved'if action =='approve'else 'rejected'
    data [app_id ]['reviewed_by']=session .get ('username')
    data [app_id ]['review_note']=note 
    with open (apps_file ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,indent =2 ,ensure_ascii =False )

        # Discord DM отправить
    if bot_instance :
        app_data =data [app_id ]
        async def send_dm ():
            try :
                user =await bot_instance .fetch_user (int (app_data ['user_id']))
                if action =='approve':
                    embed =discord .Embed (
                    title =" Заявка подтвердитьndы!",
                    description ="Tebrikler! Администратор заявка incelendi ve **подтвердитьndы**.\nEn краткий длительность с администрацией iletiшime geчilecek.",
                    color =0x2ecc71 
                    )
                    embed .add_field (name =" Иnceleyen",value =session .get ('username','?'),inline =True )
                    embed .add_field (name =" Заявка ID",value =f"`{app_id}`",inline =True )
                    if note :
                        embed .add_field (name =" Not",value =note ,inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Aether Panel • Заявка Система",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime .utcnow ()
                else :
                    embed =discord .Embed (
                    title =" Заявка отклонено",
                    description ="Юzgюnюz, администратор заявка bu sefer принять edilmedi.\nDaha после tekrar baшvurabilirsin.",
                    color =0xe74c3c 
                    )
                    embed .add_field (name =" Иnceleyen",value =session .get ('username','?'),inline =True )
                    embed .add_field (name =" Заявка ID",value =f"`{app_id}`",inline =True )
                    embed .add_field (name =" Red Причина",value =note if note else "Не belirtildi",inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Aether Panel • Заявка Система",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime .utcnow ()
                await user .send (embed =embed )
            except Exception as e :
                print (f"DM отправл: {e}")
        asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop )

    return jsonify ({'success':True })

@app .route ('/api/tunnel-url')
@login_required 
def api_tunnel_url ():
    try :
        _tunnel_path =os .path .join (os .path .dirname (os .path .abspath (__file__ )),'..','tunnel_url.txt')
        _tunnel_path =os .path .normpath (_tunnel_path )
        if os .path .exists (_tunnel_path ):
            with open (_tunnel_path ,'r',encoding ='utf-8')as f :
                url =f .read ().strip ()
            if url :
                return jsonify ({'url':url })
    except :
        pass 
    return jsonify ({'url':None })

def _save_login_token (username ,roles ):
    """Пользователь для постоянный token создать/обновить"""
    tokens_file ='data/tokens.json'
    os .makedirs ('data',exist_ok =True )
    tokens ={}
    if os .path .exists (tokens_file ):
        with open (tokens_file ,'r',encoding ='utf-8')as f :
            tokens =json .load (f )
            # Пользователя текущий tokenыnы найти или новый создать
    existing =next ((t for t ,v in tokens .items ()if v .get ('username')==username ),None )
    if not existing :
        existing =''.join (random .choices (string .ascii_letters +string .digits ,k =48 ))
    tokens [existing ]={'username':username ,'role':roles ,'created_at':datetime .utcnow ().isoformat ()}
    with open (tokens_file ,'w',encoding ='utf-8')as f :
        json .dump (tokens ,f ,indent =2 ,ensure_ascii =False )
    return existing 

@app .context_processor 
def inject_guild_id ():
    """Expose the active guild to templates without hard-coding an ID."""
    configured =str (MAIN_GUILD_ID or '')
    guilds =getattr (bot_instance ,'guilds',None )if bot_instance else None 
    if guilds :
    # A copied .env commonly contains a departed server's ID. Use the
    # configured guild only while the bot is actually connected to it.
        gid =configured if any (str (g .id )==configured for g in guilds )else str (guilds [0 ].id )
    else :
        gid =configured 
    return {'main_guild_id':gid ,'MAIN_GUILD_ID':gid }

def set_bot_instance (bot ):
    global bot_instance 
    bot_instance =bot 

@app .route ('/api/my-token')
@login_required 
def api_my_token ():
    """Вернуть токен автоматического входа для вошедшего пользователя"""
    username =session .get ('username')
    role =session .get ('role')
    token =_save_login_token (username ,role )
    return jsonify ({'token':token })

@app .route ('/api/change-password',methods =['POST'])
@login_required 
def api_change_password ():
    username =session .get ('username')
    # Только Arthur или owner роли userlar
    if username !='Arthur'and session .get ('role')!='owner':
        return jsonify ({'error':'Нет доступ'}),403 
    data =request .get_json (silent =True )or {}
    target =data .get ('target','').strip ()# какой hesabыn parolasi deгiшecek
    new_pass =data .get ('new_password','').strip ()
    if not target or not new_pass or len (new_pass )<4 :
        return jsonify ({'error':'Неверный veriler'})
    if target in USERS :
        USERS [target ]['password']=new_pass 
        return jsonify ({'success':True ,'message':f'{target} parolasi обновлено'})
        # members.json'da ara
    members_file ='data/members.json'
    if os .path .exists (members_file ):
        with open (members_file ,'r',encoding ='utf-8')as f :
            members =json .load (f )
        if target in members :
            members [target ]['password']=new_pass 
            with open (members_file ,'w',encoding ='utf-8')as f :
                json .dump (members ,f ,indent =2 ,ensure_ascii =False )
            return jsonify ({'success':True ,'message':f'{target} parolasi обновлено'})
    return jsonify ({'error':'Пользователь не найден'})

    # PUBLIC ROUTES (вход gerektirmez) 

@app .route ('/apply')
def public_apply ():
    return render_template ('public_apply.html')

@app .route ('/api/public/check-member',methods =['POST'])
def api_check_member ():
    if not bot_instance :
    # Frontend'in 503 с kыrыlmamasы для 200 dёn.
    # Bot hazыr olana userya anlaшыlыr bir message показ.
        return jsonify ({
        'found':False ,
        'error':'Bot пока hazыr не, birkaч saniye после tekrar dene.'
        })
    data =request .get_json (silent =True )or {}
    guild_id =str (data .get ('guild_id',''))
    user_id =str (data .get ('user_id',''))
    if not guild_id or not user_id :
        return jsonify ({'error':'Yetersiz parametrov'}),400 
    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найдено'}),404 
        member =guild .get_member (int (user_id ))
        if not member :
            return jsonify ({'found':False ,'error':'Bu на сервере участник deгilsin! Заявка yapamazsыn.'})
        return jsonify ({
        'found':True ,
        'id':str (member .id ),
        'name':str (member ),
        'display_name':member .display_name ,
        'avatar':str (member .display_avatar .url ),
        'joined_at':member .joined_at .isoformat ()if member .joined_at else None 
        })
    except Exception as e :
        return jsonify ({'error':str (e )}),500 

@app .route ('/api/public/guilds')
def api_public_guilds ():
    if not bot_instance :
        return jsonify ([])
    guilds =[{'id':str (g .id ),'name':g .name ,
    'icon':str (g .icon .url )if g .icon else None ,
    'members':g .member_count }
    for g in bot_instance .guilds ]
    return jsonify (guilds )

@app .route ('/api/public/apply',methods =['POST'])
def api_public_apply ():
    data =request .get_json (silent =True )or {}
    required =['discord_id','discord_name','guild_id','yas','tecrube','почему','активен']
    for field in required :
        if not data .get (field ):
            return jsonify ({'error':f'{field} zorunlu'}),400 

    apps_file ='data/staff_apps.json'
    os .makedirs ('data',exist_ok =True )
    apps ={}
    if os .path .exists (apps_file ):
        with open (apps_file ,'r',encoding ='utf-8')as f :
            apps =json .load (f )

            # Baddyen заявка контроль
    uid =str (data ['discord_id'])
    for app_data in apps .values ():
        if app_data .get ('user_id')==uid and app_data .get ('status')=='pending':
            return jsonify ({'error':'Zaten baddyen bir заявка есть!'}),400 

    app_id =str (int (datetime .utcnow ().timestamp ()))
    guild_id =str (data ['guild_id'])

    app_entry ={
    'app_id':app_id ,
    'user_id':uid ,
    'user_name':data ['discord_name'],
    'display_name':data ['discord_name'],
    'avatar':f"https://cdn.discordapp.com/embed/avatars/{int(uid) % 6}.png",
    'guild_id':guild_id ,
    'guild_name':data .get ('guild_name',''),
    'timestamp':datetime .utcnow ().isoformat (),
    'status':'pending',
    'source':'web',
    'answers':{
    'yas':data ['yas'],
    'tecrube':data ['tecrube'],
    'почему':data ['почему'],
    'активен':data ['активен'],
    'ekstra':data .get ('ekstra','—')
    },
    'message_id':None ,
    'reviewed_by':None ,
    'review_note':None 
    }
    apps [app_id ]=app_entry 

    with open (apps_file ,'w',encoding ='utf-8')as f :
        json .dump (apps ,f ,indent =2 ,ensure_ascii =False )

        # Discord в канал отправить
    if bot_instance :
        async def send_to_discord ():
            try :
                from cogs .staff_apply import APPLY_CHANNEL_ID ,StaffReviewView 
                guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
                if not guild :
                    return 
                channel =guild .get_channel (APPLY_CHANNEL_ID )
                if not channel :
                    return 
                embed =discord .Embed (
                title =" НОВЫЙ АДМИНИСТРАТОР ЗАЯВКА • Web",
                color =0xDC143C ,
                timestamp =datetime .utcnow ()
                )
                embed .add_field (name =" Пользователь",value =f"`{data['discord_name']}` (ID: `{uid}`)",inline =True )
                embed .add_field (name =" Yaш",value =data ['yas'],inline =True )
                embed .add_field (name ="⏰ Активен",value =data ['активен'],inline =True )
                embed .add_field (name =" Tecrюbe",value =f"```{data['tecrube']}```",inline =False )
                embed .add_field (name =" Почему Администратор?",value =f"```{data['почему']}```",inline =False )
                if data .get ('ekstra'):
                    embed .add_field (name =" Ekstra",value =f"```{data['ekstra']}```",inline =False )
                embed .set_footer (text =f"Заявка ID: {app_id} • {guild.name}")
                view =StaffReviewView ()
                msg =await channel .send (embed =embed ,view =view )
                apps [app_id ]['message_id']=str (msg .id )
                with open (apps_file ,'w',encoding ='utf-8')as f :
                    json .dump (apps ,f ,indent =2 ,ensure_ascii =False )
            except Exception as e :
                print (f"Discord отправл Ошибки: {e}")
        import asyncio 
        asyncio .run_coroutine_threadsafe (send_to_discord (),bot_instance .loop )

    return jsonify ({'success':True ,'app_id':app_id })

from web .routes_extra import register_extra_routes 
register_extra_routes (app ,ROLES ,login_required ,role_required ,MAIN_GUILD_ID )

# Роли Map API 
@app .route ('/api/role-map')
@login_required 
@role_required ('admin')
def api_get_role_map ():
    """Al eшleme роль + liste роль сервер"""
    guild_roles =[]
    if bot_instance :
        gid =MAIN_GUILD_ID or (str (bot_instance .guilds [0 ].id )if bot_instance .guilds else None )
        if gid :
            guild =bot_instance .get_guild (int (gid ))
            if guild :
                for r in sorted (guild .roles ,key =lambda x :x .position ,reverse =True ):
                    if r .name =='@everyone':
                        continue 
                    guild_roles .append ({
                    'id':str (r .id ),
                    'name':r .name ,
                    'color':str (r .color ),
                    'position':r .position ,
                    'members':r .members .__len__ ()if hasattr (r .members ,'__len__')else 0 ,
                    })
    return jsonify ({
    'role_map':DISCORD_ROLE_MAP ,
    'guild_roles':guild_roles ,
    })

@app .route ('/api/role-map',methods =['POST'])
@login_required 
@role_required ('admin')
def api_set_role_map ():
    """Добавить/izmenit eшleme роли"""
    data =request .get_json (silent =True )or {}
    role_id =str (data .get ('role_id','')).strip ()
    panel_role =data .get ('panel_role','').strip ()
    if not role_id or panel_role not in ('mod','admin','owner'):
        return jsonify ({'error':'Неверный veriler'}),400 
    DISCORD_ROLE_MAP [role_id ]=panel_role 
    _save_role_map ()
    _log_panel_action ('ROLE_MAP_SET',f'{role_id} → {panel_role}')
    return jsonify ({'success':True })

@app .route ('/api/role-map/<role_id>',methods =['DELETE'])
@login_required 
@role_required ('admin')
def api_delete_role_map (role_id ):
    """Удалить eшleme роли"""
    if role_id in DISCORD_ROLE_MAP :
        del DISCORD_ROLE_MAP [role_id ]
        _save_role_map ()
        _log_panel_action ('ROLE_MAP_DELETE',role_id )
    return jsonify ({'success':True })

    # Discord PIN Login API 
_login_pins ={}

@app .route ('/api/login/suggest',methods =['GET','POST'])
def api_login_suggest ():
    query =(request .args .get ('q')or (request .get_json (silent =True )or {}).get ('q','')or '').strip ()
    query_clean =query .lstrip ('@').lower ()

    suggestions =[]
    seen_ids =set ()

    # 1. Live Discord bot members if online
    if bot_instance :
        for guild in bot_instance .guilds :
            for m in guild .members :
                if m .bot :continue 
                if not query_clean or query_clean in m .name .lower ()or query_clean in m .display_name .lower ()or query_clean in str (m .id ):
                    if m .id not in seen_ids :
                        seen_ids .add (m .id )
                        suggestions .append ({
                        'id':str (m .id ),
                        'name':m .name ,
                        'display_name':m .display_name ,
                        'avatar':str (m .display_avatar .url )if hasattr (m ,'display_avatar')else 'https://cdn.discordapp.com/embed/avatars/0.png'
                        })
                        if len (suggestions )>=12 :break 
            if len (suggestions )>=12 :break 

            # 2. Offline / supplemental check from members.json
    if len (suggestions )<12 and os .path .exists ('data/members.json'):
        try :
            with open ('data/members.json','r',encoding ='utf-8')as f :
                mdata =json .load (f )
            for uid_str ,minfo in mdata .items ():
                if uid_str in seen_ids :continue 
                mname =minfo .get ('display_name',minfo .get ('username',uid_str ))
                if not query_clean or query_clean in mname .lower ()or query_clean in str (uid_str ):
                    seen_ids .add (uid_str )
                    suggestions .append ({
                    'id':str (uid_str ),
                    'name':minfo .get ('username',mname ),
                    'display_name':mname ,
                    'avatar':_safe_avatar_url (minfo .get ('avatar'))
                    })
                    if len (suggestions )>=12 :break 
        except :
            pass 

            # 3. Always provide demo/known members if empty so dropdown is never blank
    if not suggestions :
        demo_members =[
        {'id':'987430047889637426','name':'owner','display_name':'Owner','avatar':'https://cdn.discordapp.com/embed/avatars/0.png'},
        {'id':'1406597367695806564','name':'ecobar','display_name':'Ecobar','avatar':'https://cdn.discordapp.com/embed/avatars/1.png'},
        {'id':'1483484518563188767','name':'dragon','display_name':'Dragon','avatar':'https://cdn.discordapp.com/embed/avatars/2.png'},
        {'id':'1461513653650981054','name':'hzdio','display_name':'HzDio','avatar':'https://cdn.discordapp.com/embed/avatars/3.png'},
        {'id':'859341577452257330','name':'oberaru','display_name':'Oberaru','avatar':'https://cdn.discordapp.com/embed/avatars/4.png'},
        {'id':'1465744556183126242','name':'meow_meow','display_name':'Meow Meow','avatar':'https://cdn.discordapp.com/embed/avatars/5.png'},
        ]
        for dm in demo_members :
            if not query_clean or query_clean in dm ['name'].lower ()or query_clean in dm ['id']:
                suggestions .append (dm )

    return jsonify ({'success':True ,'suggestions':suggestions })

@app .route ('/api/discord-check',methods =['POST'])
def api_discord_check ():
    if not bot_instance :
        return jsonify ({'success':False ,'error':'Бот Discord сейчас не в сети или не подключен.','tests':[]})
    data =request .get_json (silent =True )or {}
    query =str (data .get ('query','')).strip ()
    if not query :
        return jsonify ({'success':False ,'error':'Пожалуйста, введите корректный Discord ID или @имя пользователя.','tests':[]})
    tests =[]
    discord_id =None 
    member_info =None 
    user =None 
    try :
        if query .isdigit ()and 17 <=len (query )<=19 :
            discord_id =query 
            for guild in bot_instance .guilds :
                m =guild .get_member (int (discord_id ))
                if m :
                    user =m 
                    break 
            if not user :
                try :
                    user =asyncio .run_coroutine_threadsafe (bot_instance .fetch_user (int (discord_id )),bot_instance .loop ).result (timeout =10 )
                except :
                    pass 
        else :
            uname =query .lstrip ('@').lower ()
            for guild in bot_instance .guilds :
                for m in guild .members :
                    if m .name .lower ()==uname or m .display_name .lower ()==uname :
                        user =m 
                        discord_id =str (m .id )
                        break 
                if user :
                    break 
        if not user or not discord_id :
            tests .append ({'name':'Поиск пользователя','status':'fail','detail':'Not found'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Пользователь не найден.'})
        member_info ={'display_name':getattr (user ,'display_name',str (user )),'name':str (user ),'avatar':str (user .display_avatar .url )if hasattr (user ,'display_avatar')else ''}
        tests .append ({'name':'Поиск пользователя','status':'ok','detail':member_info ['display_name']})
    except Exception as e :
        tests .append ({'name':'Поиск пользователя','status':'fail','detail':str (e )})
        return jsonify ({'success':False ,'tests':tests ,'error':str (e )})
    try :
        in_guild =False 
        guild_name =None 
        for guild in bot_instance .guilds :
            m =guild .get_member (int (discord_id ))
            if m :
                in_guild =True 
                guild_name =guild .name 
                break 
        if in_guild :
            tests .append ({'name':'Участник сервера','status':'ok','detail':guild_name })
        else :
            tests .append ({'name':'Участник сервера','status':'warn','detail':'Не найден на сервере'})
    except :
        tests .append ({'name':'Участник сервера','status':'warn','detail':'Ошибка проверки'})
    try :
        is_bot =getattr (user ,'bot',False )
        if is_bot :
            tests .append ({'name':'Проверка на бота','status':'fail','detail':'Аккаунт бота'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Боты не могут авторизоваться.'})
        else :
            tests .append ({'name':'Проверка на бота','status':'ok','detail':'Пользователь'})
    except :
        tests .append ({'name':'Проверка на бота','status':'warn','detail':'Ошибка проверки'})
    try :
        created =discord .utils .snowflake_time (int (discord_id ))
        age_days =(datetime .utcnow ()-created ).days 
        if age_days <7 :
            tests .append ({'name':'Возраст аккаунта','status':'fail','detail':f'{age_days}d (too new)'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Вход запрещен: аккаунт зарегистрирован менее 7 дней назад.'})
        else :
            tests .append ({'name':'Возраст аккаунта','status':'ok','detail':f'{age_days}d'})
    except :
        tests .append ({'name':'Возраст аккаунта','status':'warn','detail':'Неизвестно'})
    try :
        code =''.join (random .choices (string .digits ,k =6 ))
        import time as _t 
        _login_pins [discord_id ]={'code':code ,'expires':_t .time ()+300 ,'member_info':member_info }
        async def send_pin ():
            u =await bot_instance .fetch_user (int (discord_id ))
            embed =discord .Embed (title ='Aether — Код авторизации',color =0xc8922a ,timestamp =datetime .utcnow ())
            embed .description =f"Hello **{member_info['display_name']}**!\n\nВаш PIN-код для входа в панель:\n\n```fix\n{code}\n```\nДействителен в течение 5 минут."
            embed .set_footer (text ="Aether Panel")
            await u .send (embed =embed )
        asyncio .run_coroutine_threadsafe (send_pin (),bot_instance .loop ).result (timeout =10 )
        tests .append ({'name':'Отправка PIN-кода','status':'ok','detail':'Отправлено в ЛС'})
    except Exception as e :
        tests .append ({'name':'Отправка PIN-кода','status':'fail','detail':'DM failed'})
        return jsonify ({'success':False ,'tests':tests ,'error':'Не удалось отправить PIN-код: личные сообщения закрыты или бот заблокирован.'})
    return jsonify ({'success':True ,'discord_id':discord_id ,'display_name':member_info ['display_name'],'avatar':member_info ['avatar'],'tests':tests })

@app .route ('/api/discord-login',methods =['POST'])
def api_discord_login ():
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    pin =str (data .get ('pin','')).strip ()
    if not discord_id or not pin :
        return jsonify ({'success':False ,'error':'Не заполнены обязательные поля.'})
    entry =_login_pins .get (discord_id )
    if not entry :
        return jsonify ({'success':False ,'error':'Для этого пользователя не найден активный PIN-код.'})
    import time as _t 
    if _t .time ()>entry ['expires']:
        del _login_pins [discord_id ]
        return jsonify ({'success':False ,'error':'Срок действия PIN-кода истек. Пожалуйста, отправьте новый код.'})
    if entry ['code']!=pin :
        return jsonify ({'success':False ,'error':'Введен неверный PIN-код.'})
    member_info =entry ['member_info']
    del _login_pins [discord_id ]
    members_file ='data/members.json'
    os .makedirs ('data',exist_ok =True )
    members ={}
    if os .path .exists (members_file ):
        with open (members_file ,'r',encoding ='utf-8')as f :
            members =json .load (f )
    if discord_id not in members :
        live_role =_get_role_from_discord (discord_id )
        members [discord_id ]={'display_name':member_info ['display_name'],'name':member_info ['name'],'avatar':member_info ['avatar'],'role':live_role ,'password':'','registered_at':datetime .utcnow ().isoformat ()}
        with open (members_file ,'w',encoding ='utf-8')as f :
            json .dump (members ,f ,indent =2 ,ensure_ascii =False )
    stored_role =members [discord_id ].get ('role','uye')
    if stored_role =='owner':
        live_role ='owner'
    else :
        live_role =_get_role_from_discord (discord_id )
    session .permanent =True 
    session ['logged_in']=True 
    session ['username']=member_info ['display_name']
    session ['role']=live_role 
    session ['discord_id']=discord_id 
    session .modified =True 
    _save_login_token (discord_id ,live_role )
    _log_login (member_info ['display_name'],live_role ,member_info ['avatar'],discord_id )
    return jsonify ({'success':True ,'redirect':'/'})

@app .route ('/custom-embeds')
@login_required 
@role_required ('admin')
def custom_embeds_page ():
    return render_template ('custom_embeds.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/api/send-embed',methods =['POST'])
@login_required 
@role_required ('admin')
def api_send_embed ():
    if not bot_instance :return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
    data =request .get_json (silent =True )or {}
    guild_id =int (data .get ('guild_id',0 ))
    channel_id =int (data .get ('channel_id',0 ))
    title =data .get ('title','')
    description =data .get ('description','')
    color_hex =data .get ('color','#dc143c').lstrip ('#')
    footer =data .get ('footer','')
    image_url =data .get ('image_url','')
    thumbnail_url =data .get ('thumbnail_url','')
    guild =bot_instance .get_guild (guild_id )
    if not guild :return jsonify ({'error':'Сервер не найдено'})
    channel =bot_instance .get_channel (channel_id )
    if not channel :return jsonify ({'error':'Канал не найдено'})
    async def send_it ():
        try :color =discord .Color (int (color_hex ,16 ))
        except :color =discord .Color (0xdc143c )
        embed =discord .Embed (color =color )
        if title :embed .title =title 
        if description :embed .description =description 
        if footer :embed .set_footer (text =footer )
        if image_url :embed .set_image (url =image_url )
        if thumbnail_url :embed .set_thumbnail (url =thumbnail_url )
        await channel .send (embed =embed )
        return {'success':True }
    try :
        result =asyncio .run_coroutine_threadsafe (send_it (),bot_instance .loop ).result (timeout =10 )
        return jsonify (result )
    except Exception as e :
        return jsonify ({'error':str (e )})

        # Bot Контроль API'leri 
@app .route ('/api/bot/restart',methods =['POST'])
@login_required 
@role_required ('owner')
def api_bot_restart ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
    _log_panel_action ('BOT_RESTART',session .get ('username'))
    import threading ,time ,os ,sys 
    def do_restart ():
        time .sleep (1 )
        os .execv (sys .executable ,[sys .executable ]+sys .argv )
    threading .Thread (target =do_restart ,daemon =True ).start ()
    return jsonify ({'success':True })


@app .route ('/api/bot/diagnose',methods =['POST'])
@login_required 
@role_required ('admin')
def api_bot_diagnose ():
    """Run a quick health diagnose. Returns a list of issues found."""
    issues =[]
    try :
        if not bot_instance :
            issues .append ('Бот Discord не подключен')
        else :
        # Memory check
            try :
                import psutil ,os as _os 
                proc =psutil .Process (_os .getpid ())
                mem_mb =proc .memory_info ().rss /1024 /1024 
                if mem_mb >700 :
                    issues .append (f'Высокое потребление памяти: {round(mem_mb, 1)}MB')
            except Exception :
                pass 
                # Latency check
            try :
                lat =bot_instance .latency *1000 
                if lat >800 :
                    issues .append (f'Высокий Discord latency: {round(lat, 0)}ms')
            except Exception :
                pass 
                # Guild count
            try :
                guilds =list (bot_instance .guilds )
                if not guilds :
                    issues .append ('Бот не на ни одном сервере')
            except Exception :
                issues .append ('Не удалось получить список серверов')
    except Exception as e :
        issues .append (f'Ошибка диагностики: {e}')
    return jsonify ({'issues':issues ,'health':'ok'if not issues else 'warn'})


@app .route ('/api/bot/gc',methods =['POST'])
@login_required 
@role_required ('owner')
def api_bot_gc ():
    """Force Python garbage collection, free memory."""
    import gc 
    before =sum (1 for _ in gc .get_objects ())
    collected =gc .collect ()
    after =sum (1 for _ in gc .get_objects ())
    freed =before -after 
    _log_panel_action ('BOT_GC',session .get ('username'))
    return jsonify ({
    'success':True ,
    'collected':collected ,
    'freed':freed ,
    'before':before ,
    'after':after ,
    })

@app .route ('/api/bot/sync',methods =['POST'])
@login_required 
@role_required ('admin')
def api_bot_sync ():
    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
    async def do ():
    # Guild-specific sync (anыnda etkili) + global sync
        synced_guilds =[]
        for guild in bot_instance .guilds :
            try :
                await bot_instance .tree .sync (guild =guild )
                synced_guilds .append (guild .name )
            except Exception :
                pass 
        await bot_instance .tree .sync ()
        return synced_guilds 
    try :
        guilds =asyncio .run_coroutine_threadsafe (do (),bot_instance .loop ).result (timeout =30 )
        _log_panel_action ('BOT_SYNC',session .get ('username'))
        return jsonify ({'success':True ,'synced_guilds':guilds })
    except Exception as e :
        return jsonify ({'error':str (e )})

        # Global Aramama 
@app .route ('/api/search')
@login_required 
@role_required ('mod')
def api_global_search ():
    q =request .args .get ('q','').strip ().lower ()
    if not q or len (q )<2 :
        return jsonify ([])

    results =[]

    # Участники
    if bot_instance :
        for guild in bot_instance .guilds :
            for member in guild .members :
                if q in member .display_name .lower ()or q in str (member .id ):
                    results .append ({
                    'type':'member',
                    'icon':'',
                    'title':member .display_name ,
                    'subtitle':f'{guild.name} • ID: {member.id}',
                    'url':f'/users?search={member.id}'
                    })
                    if len (results )>=5 :
                        break 

                        # Warninglar
    warns_file ='data/warnings.json'
    if os .path .exists (warns_file ):
        with open (warns_file ,'r',encoding ='utf-8')as f :
            warns =json .load (f )
        for guild_id ,guild_warns in warns .items ():
            for uid ,user_warns in guild_warns .items ():
                for w in user_warns :
                    if q in w .get ('reason','').lower ()or q in uid :
                        results .append ({
                        'type':'warning',
                        'icon':'',
                        'title':f'Warning: {w.get("reason", "?")}',
                        'subtitle':f'Пользователь: {uid}',
                        'url':'/warnings'
                        })
                        break 

                        # Loglar
    audit_file ='data/audit_log.json'
    if os .path .exists (audit_file ):
        with open (audit_file ,'r',encoding ='utf-8')as f :
            logs =json .load (f )
        for guild_id ,events in logs .items ():
            for ev in reversed (events [-200 :]):
                if (q in ev .get ('action','').lower ()or 
                q in ev .get ('user_name','').lower ()or 
                q in ev .get ('reason','').lower ()):
                    results .append ({
                    'type':'log',
                    'icon':'',
                    'title':f'{ev.get("action", "?")} — {ev.get("user_name", "?")}',
                    'subtitle':ev .get ('reason',''),
                    'url':'/logs'
                    })
                    if len (results )>=15 :
                        break 

    return jsonify (results [:15 ])

    # Голос Команда Endpoint (voice_listener.py для) 
VOICE_SECRET =os .getenv ('VOICE_SECRET','Aether-voice-2024')

@app .route ('/api/voice-command',methods =['POST'])
def api_voice_command ():
    """voice_listener.py'den gelen sesli команды iшle"""
    data =request .get_json (silent =True )or {}
    if not data or data .get ('secret')!=VOICE_SECRET :
        return jsonify ({'error':'Unauthorized'}),401 
    command =data .get ('command','').strip ()
    if not command :
        return jsonify ({'error':'Команда пусто'}),400 

    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'}),503 

    OWNER_ID_INT =int (os .getenv ('OWNER_ID','987430047889637426'))

    async def dispatch ():
        owner =await bot_instance .fetch_user (OWNER_ID_INT )
        dm =await owner .create_dm ()
        # Фейковый bir message nesnesi создан yerine, верно ai_chat cog'unu чтяжелый
        cog =bot_instance .get_cog ('AIChat')
        if not cog :
            return 'AIChat cog не найдено'
            # _detect_owner_intent'i верно чтяжелый
            # Bunun для фейковый bir message nesnesi lazыm — DM channelыnы использовать
        async for msg in dm .history (limit =1 ):
        # Gerчek bir message bulduk, intent'i чalышtыr
            result =await cog ._detect_owner_intent (command ,msg )
            if not result :
            # Handler eшleшmedi, normal AI'ya отправить
                await dm .send (command )
            return 'OK'
            # История message yoksa direkt DM at
        await dm .send (command )
        return 'OK (DM sent)'

    try :
        result =asyncio .run_coroutine_threadsafe (dispatch (),bot_instance .loop ).result (timeout =15 )
        return jsonify ({'success':True ,'result':result })
    except Exception as e :
        return jsonify ({'error':str (e )}),500 


if __name__ =='__main__':
    app .run (host ='0.0.0.0',port =5000 ,debug =True )

    # Parola Sыfыrlama (login страница для) 
import random as _random 
_reset_codes ={}# {discord_id: {code, expires}}

@app .route ('/api/forgot-password',methods =['POST'])
def api_forgot_password ():
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    if not discord_id :
        return jsonify ({'error':'Neobhodim Discord ID'})

        # Участник запись mы контроль et
    members_file ='data/members.json'
    if not os .path .exists (members_file ):
        return jsonify ({'error':'Запись участник не найдено'})
    with open (members_file ,'r',encoding ='utf-8')as f :
        members =json .load (f )
    if discord_id not in members :
        return jsonify ({'error':'Bu По Discord ID запись hesap нет'})

        # 6 haneli kod юret
    code =''.join ([str (_random .randint (0 ,9 ))for _ in range (6 )])
    import time as _time 
    _reset_codes [discord_id ]={'code':code ,'expires':_time .time ()+300 }# 5 minutes

    # Bot с DM отправить
    if not bot_instance :
        return jsonify ({'error':'Bot шu an offline, более после tekrar dene'})

    async def send_dm ():
        user =await bot_instance .fetch_user (int (discord_id ))
        await user .send (
        f" **Parola Sыfыrlama Kodun:** `{code}`\n"
        f"Bu kod 5 minutes geчerlidir. Panelde bu kodu girerek parolani sыfыrlayabilirsin.\n"
        f"Если bu желание sen yapmadыysan bu сообщение игнорировать."
        )
    try :
        asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'success':True })
    except Exception as e :
        return jsonify ({'error':f'DM отправл: {e}'})


@app .route ('/api/reset-password',methods =['POST'])
def api_reset_password ():
    import time as _time 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    code =str (data .get ('code','')).strip ()
    new_pass =str (data .get ('new_password','')).strip ()

    if not discord_id or not code or not new_pass :
        return jsonify ({'error':'Yetersiz informacii'})
    if len (new_pass )<6 :
        return jsonify ({'error':'Parola olmalы olmak не menee 6 simvolov'})

    entry =_reset_codes .get (discord_id )
    if not entry :
        return jsonify ({'error':'До sorguite kod'})
    if _time .time ()>entry ['expires']:
        del _reset_codes [discord_id ]
        return jsonify ({'error':'Kodun длительность dolmuш, tekrar talep et'})
    if entry ['code']!=code :
        return jsonify ({'error':'Неверный kod'})

        # Parolayi обновить
    members_file ='data/members.json'
    with open (members_file ,'r',encoding ='utf-8')as f :
        members =json .load (f )
    if discord_id not in members :
        return jsonify ({'error':'Пользователь не найден'})
    members [discord_id ]['password']=new_pass 
    with open (members_file ,'w',encoding ='utf-8')as f :
        json .dump (members ,f ,indent =2 ,ensure_ascii =False )

    del _reset_codes [discord_id ]
    return jsonify ({'success':True })


    # NOTIFICATIONS & ACTIVITY FEED 
    # These endpoints back the polling code in base.html so the panel can
    # surface toast notifications and the activity drawer without
    # 404-ing in the browser console.

@app .route ('/api/notifications/poll')
@login_required 
def api_notifications_poll ():
    """Lightweight poll for unread panel notifications for the current user."""
    username =session .get ('username','anon')
    cutoff_ts =request .args .get ('since',0 )
    try :
        cutoff_ts =int (cutoff_ts )
    except (TypeError ,ValueError ):
        cutoff_ts =0 
    notifs =[]
    # 1) panel_logs.json -> recent mod-style actions attributed to the user
    try :
        import os ,json ,time as _t 
        f ='data/panel_logs.json'
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for entry in raw [-30 :]:
                ts =entry .get ('ts',0 )or 0 
                if ts >cutoff_ts and (entry .get ('user')==username or entry .get ('target_user')==username ):
                    notifs .append ({
                    'id':f"pl-{ts}",
                    'title':entry .get ('action','Действие'),
                    'body':entry .get ('detail',''),
                    'icon':'',
                    'ts':ts ,
                    'kind':'mod',
                    })
    except Exception :
        pass 
        # 2) temp moderation activity
    try :
        import os ,json ,time as _t 
        f ='data/temp_mod_log.json'
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for entry in raw [-30 :]:
                ts =entry .get ('ts',0 )or 0 
                if ts >cutoff_ts and entry .get ('mod')==username :
                    notifs .append ({
                    'id':f"tm-{ts}-{entry.get('user_id', '')}",
                    'title':f"Временное {entry.get('action', 'действие')}",
                    'body':entry .get ('reason',''),
                    'icon':'⏱',
                    'ts':ts ,
                    'kind':'temp',
                    })
    except Exception :
        pass 
    notifs .sort (key =lambda x :x .get ('ts',0 ),reverse =True )
    return jsonify ({'notifications':notifs [:20 ],'ts':int (__import__ ('time').time ()*1000 )})


@app .route ('/api/activity-feed')
@login_required 
def api_activity_feed ():
    """Recent panel activity (newest first) for the activity drawer."""
    import os ,json 
    items =[]
    try :
        f ='data/panel_logs.json'
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for e in raw [-50 :]:
                items .append ({
                'icon':'',
                'title':e .get ('action','Действие'),
                'user':e .get ('user',''),
                'detail':e .get ('detail',''),
                'ts':e .get ('ts',0 ),
                })
    except Exception :
        pass 
    try :
        f ='data/temp_mod_log.json'
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for e in raw [-30 :]:
                items .append ({
                'icon':'⏱',
                'title':f"Временное {e.get('action', 'действие')}",
                'user':e .get ('mod',''),
                'detail':e .get ('reason',''),
                'ts':e .get ('ts',0 ),
                })
    except Exception :
        pass 
    items .sort (key =lambda x :x .get ('ts',0 )or 0 ,reverse =True )
    return jsonify ({'items':items [:60 ]})


    # WebSocket Server Initialization 
if WEBSOCKET_ENABLED :
    try :
    # Запуск WebSocket сервера в отдельном потоке
        ws_thread =start_websocket_thread (host ='localhost',port =8765 )
        print ('[WebSocket] Сервер инициализирован')
    except Exception as e :
        print (f'[WebSocket] Ошибка инициализации: {e}')
        WEBSOCKET_ENABLED =False 
