import random 
import string 
import hashlib 
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

# Сессия: стандартная Flask cookie session (подписанная itsdangerous cookie).
# Старый: flask_session filesystem (файловый IO на каждый запрос, узкое место при 50 параллельных).
# Новый: cookie, нулевой дисковый IO, <500 байт. Размер сессии мал, поэтому проблем нет.
# Позже, если понадобится Redis, можно добавить SESSION_TYPE=redis.
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
RATE_LIMIT_WINDOW =60 # секунды
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
def _log_login (username ,role ,avatar ,discord_id ):
    """Запоминает пользователей, вошедших в панель."""
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

        # Массовая (batch) запись логов панели — не блокирует POST/DELETE запросы
_panel_log_flusher =_store .PeriodicFlush (
'data/panel_logs.json',
flush_interval =5.0 ,
max_entries =500 ,
batch_threshold =50 ,
)
atexit .register (_panel_log_flusher .shutdown )


import re as _re

def _clean_md (value ):
    """Убрать markdown-разметку из строк, отображаемых в панели.

    Панель не рендерит Discord-markdown — иначе **жирный**, `код` и
    ## заголовки видны пользователю сырыми символами.
    """
    if not isinstance (value ,str )or not value :
        return value
    s =_re .sub (r'\*\*(.+?)\*\*',r'\1',value )
    s =_re .sub (r'__(.+?)__',r'\1',s )
    s =_re .sub (r'`{1,3}([^`]*)`{1,3}',r'\1',s )
    s =s .replace ('**','').replace ('__','')
    # Заголовки Discord (## и длиннее) — и в начале строк, и в середине текста;
    # одиночный # (хештеги) не трогаем
    s =_re .sub (r'#{2,6}\s*','',s )
    return s

_MD_FIELDS =('action','user_name','mod_name','target_name','reason','detail',
'content','title','body','message','user','moderator','mod','label')

def _clean_md_fields (obj ):
    """Очистить текстовые поля словаря от markdown (in place) и вернуть его."""
    try :
        for k in _MD_FIELDS :
            v =obj .get (k )
            if isinstance (v ,str )and ('**' in v or '__' in v or '`' in v or '#' in v ):
                obj [k ]=_clean_md (v )
    except Exception :
        pass
    return obj

def _log_panel_action (action ,detail =''):
    try :
        import time as _t 
        _panel_log_flusher .append ({
        'username':session .get ('username','?'),
        'role':session .get ('role','?'),
        'action':action ,
        'detail':detail ,
        'ip':request .remote_addr ,
        'timestamp':datetime .utcnow ().isoformat (),
        'ts':int (_t .time ()),
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
# Логировать только POST/DELETE-запросы — частые GET-опросы не трогаем
    if request .method in ('POST','DELETE')and session .get ('logged_in'):
        path =request .path 
        # Кроме login/logout
        if path not in ('/login','/logout','/register'):
            _log_panel_action (f'{request.method} {path}','')

            # ETag: для того же содержимого вернуть 304 (экономия сети и парсинга JSON)
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

            # Обход кэша браузера — критично для админ-панели (на время разработки)
    if request .path .startswith ('/static/'):
        response .headers ['Cache-Control']='no-cache, no-store, must-revalidate'
        response .headers ['Pragma']='no-cache'
        response .headers ['Expires']='0'
    elif request .path .startswith ('/api/')or response .is_json :
        response .headers ['Cache-Control']='no-store'
    else :
        response .headers ['Cache-Control']='no-cache, must-revalidate'

        # CSP: Cloudflare или прокси иногда добавляют слишком строгий CSP; своим
        # заголовком разрешаем 'unsafe-eval' и 'unsafe-inline'.
        # Это админ-панель (доверенные пользователи), поэтому inline JS/eval допустим.
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

    # Фиксированный ID сервера — используется первый найденный ботом сервер; меняется в панели
MAIN_GUILD_ID =os .getenv ('MAIN_GUILD_ID','')  # задаётся в .env; без него контекст берёт первый сервер бота

# Роли администратор (den nizkogo e visokomu)
ROLES ={
'uye':0 ,
'mod':1 ,
'admin':2 ,
'owner':3 
}

# Учётные данные владельца панели — приоритет:
#  1) data/panel_credentials.json (сменённый через панель, постоянный)
#  2) .env: PANEL_USER / PANEL_PASSWORD
#  3) Автогенерация надёжного случайного пароля (раньше был небезопасный "123")
_OWNER_CRED_PATH ='data/panel_credentials.json'

def _hash_pw (pw ):
    return hashlib .sha256 (str (pw ).encode ('utf-8')).hexdigest ()

def _load_owner_credentials ():
    user =(os .environ .get ('PANEL_USER','owner')or 'owner').strip ()or 'owner'
    try :
        saved =_store .read_json (_OWNER_CRED_PATH ,default =None )
    except Exception :
        saved =None 
    if isinstance (saved ,dict )and saved .get ('user')==user and saved .get ('password_hash'):
        return user ,saved ['password_hash'],False 
    env_pw =(os .environ .get ('PANEL_PASSWORD','')or '').strip ()
    if env_pw :
        return user ,_hash_pw (env_pw ),False 
    # Ничего не задано — генерируем надёжный случайный пароль и сохраняем его
    # (раньше здесь был небезопасный пароль по умолчанию "123").
    import secrets as _secrets 
    gen =_secrets .token_urlsafe (12 )
    pw_hash =_hash_pw (gen )
    try :
        _store .atomic_write_json (_OWNER_CRED_PATH ,{'user':user ,'password_hash':pw_hash })
        _store .invalidate_path (_OWNER_CRED_PATH )
        os .makedirs ('data',exist_ok =True )
        with open ('data/panel_credentials.txt','w',encoding ='utf-8')as f :
            f .write (f'Aether Panel — первый вход\nПользователь: {user}\nПароль: {gen}\n'
                      'После входа смените пароль в панели или задайте PANEL_PASSWORD в .env\n')
        try :
            os .chmod ('data/panel_credentials.txt',0o600 )
        except OSError :
            pass 
    except Exception as _e :
        print (f'[БЕЗОПАСНОСТЬ] Не удалось сохранить сгенерированный пароль: {_e}')
    print ('='*70 )
    print ('[БЕЗОПАСНОСТЬ] PANEL_PASSWORD не задан — сгенерирован надёжный пароль:')
    print (f'[БЕЗОПАСНОСТЬ]   Пользователь: {user}')
    print (f'[БЕЗОПАСНОСТЬ]   Пароль: {gen}')
    print ('[БЕЗОПАСНОСТЬ] Он также записан в data/panel_credentials.txt')
    print ('='*70 )
    return user ,pw_hash ,False 

_owner_user ,_owner_pw_hash ,_owner_using_default_pw =_load_owner_credentials ()

# Единственный зафиксированный пользователь-владелец
USERS ={
_owner_user :{'password_hash':_owner_pw_hash ,'role':'owner'},
}

def _pw_is_hash (value ):
    """64 hex karakterlik sha256 hash mi?"""
    return isinstance (value ,str )and len (value )==64 and all (c in '0123456789abcdef'for c in value )

def _pw_matches (stored ,plain ):
    """Проверка пароля участника — хэш-записи и старые открытые пароли."""
    stored =(stored or '')
    if _pw_is_hash (stored ):
        return stored ==_hash_pw (plain )
    return stored ==plain 

def _safe_avatar_url (value ):
    """Do заметок serve stale guild-profile avatar URLs stored in old JSON files."""
    if not isinstance (value ,str )or '/guilds/'in value :
        return 'https://cdn.discordapp.com/embed/avatars/0.png'
    return value 

    # ID роли Discord → роль панели — data/role_map.json
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

            # 1. Ручное сопоставление из role_map.json
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
            # Каждые 5 минут обновлять роль из Discord (кроме владельца)
        discord_id =session .get ('discord_id')
        if discord_id and session .get ('role')!='owner':
            import time as _t 
            last_check =session .get ('_role_checked',0 )
            if _t .time ()-last_check >300 :# 5 минут
                live_role =_get_role_from_discord (discord_id )
                session ['role']=live_role 
                session ['_role_checked']=_t .time ()
                # также обновить members.json
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
                return jsonify ({'error':'Нет доступа'}),403 
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
        return render_template ('welcome.html')
    if session .get ('role')=='uye':
        return render_template ('member_dashboard.html',role =session .get ('role'),username =session .get ('username'))
    return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/member-apply')
@login_required 
def member_apply_page ():
    return render_template ('member_apply.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/login',methods =['GET','POST'])
def login ():
# Автоматический вход по токену — БЕЗОПАСНОСТЬ: по умолчанию ВЫКЛЮЧЕНО.
    # За Cloudflare Tunnel/локальным прокси каждый запрос выглядит
    # как 127.0.0.1, поэтому проверка IP сама по себе не защищает.
    # Включить через .env: ENABLE_TOKEN_LOGIN=1
    token =request .args .get ('token')or request .form .get ('token')
    if token and os .environ .get ('ENABLE_TOKEN_LOGIN','0')=='1'and request .remote_addr in ('127.0.0.1','::1'):
        tokens_file ='data/tokens.json'
        if os .path .exists (tokens_file ):
            with open (tokens_file ,'r',encoding ='utf-8')as f :
                tokens =json .load (f )
            if token in tokens :
                t =tokens [token ]
                # срок действия 14 дней — старые постоянные токены больше не впускают
                _token_ok =True 
                try :
                    _created =datetime .fromisoformat (t .get ('created_at')or '')
                    if (datetime .utcnow ()-_created ).days >14 :
                        _token_ok =False 
                except Exception :
                    _token_ok =True 
                if not _token_ok :
                    return redirect (url_for ('login'))
                session .permanent =True 
                session ['logged_in']=True 
                session ['username']=t ['username']
                session ['role']=t ['role']
                session .modified =True 
                return redirect (url_for ('index'))

    if request .method =='POST':
        username =request .form .get ('username')
        password =request .form .get ('password')

        # Только зафиксированный пользователь-владелец
        if username in USERS and USERS [username ].get ('password_hash')==_hash_pw (password ):
            session .permanent =True 
            session ['logged_in']=True 
            session ['username']=username 
            session ['role']=USERS [username ]['role']
            _save_login_token (username ,USERS [username ]['role'])
            _log_login (username ,'owner',None ,None )
            return redirect (url_for ('index'))

            # Вход участника (по Discord ID) — роль определяется автоматически из Discord
        members_file ='data/members.json'
        if os .path .exists (members_file ):
            with open (members_file ,'r',encoding ='utf-8')as f :
                members =json .load (f )
            if username in members and _pw_matches (members [username ].get ('password'),password ):
                discord_id =username
                # Старый пароль в открытом виде? Обновить до хэша
                if not _pw_is_hash (members [username ].get ('password')):
                    members [username ]['password']=_hash_pw (password )
                    with open (members_file ,'w',encoding ='utf-8')as f :
                        json .dump (members ,f ,indent =2 ,ensure_ascii =False )
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

# 2FA — ожидающие сессии {session_token: {username, roles, expires}}
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
                    description =f'Ваш код проверки: **`{code}`**\n\nКод действует 5 минут.\nЕсли вы не входили в панель — проигнорируйте это сообщение.',
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
                return render_template ('register.html',error ='Время проверки истекло, попробуйте снова.',step =1 )
            pv =PENDING_VERIFICATIONS [discord_id ]
            if pv ['code']!=code :
                return render_template ('register.html',error ='Неверный код!',step =2 ,
                discord_id =discord_id ,password =pv ['password'])
                # Сохранить
            member_info =pv ['member_info']
            members_file ='data/members.json'
            os .makedirs ('data',exist_ok =True )
            members ={}
            if os .path .exists (members_file ):
                with open (members_file ,'r',encoding ='utf-8')as f :
                    members =json .load (f )
                    # Получить актуальную роль из Discord
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
            return render_template ('register.html',error ='Заполните все поля!',step =1 )
        if not discord_id .isdigit ()or not (17 <=len (discord_id )<=19 ):
            return render_template ('register.html',error ='Неверный Discord ID!',step =1 )
        if password !=password2 :
            return render_template ('register.html',error ='Пароли не совпадают!',step =1 )
        if len (password )<6 :
            return render_template ('register.html',error ='Пароль должен быть не короче 6 символов!',step =1 )

        if not bot_instance :
            return render_template ('register.html',error ='Бот сейчас офлайн, попробуйте позже.',step =1 )

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
            return render_template ('register.html',error ='Этот Discord ID не найден! Убедитесь, что Discord ID верный.',step =1 )

        members_file ='data/members.json'
        if os .path .exists (members_file ):
            with open (members_file ,'r',encoding ='utf-8')as f :
                members =json .load (f )
            if discord_id in members :
                return render_template ('register.html',error ='Этот Discord ID уже зарегистрирован!',step =1 )

                # DM с проверка kodu отправить
        code =''.join (random .choices (string .digits ,k =6 ))
        PENDING_VERIFICATIONS [discord_id ]={'code':code ,'password':_hash_pw (password ),'member_info':member_info }

        async def send_dm ():
            try :
                user =await bot_instance .fetch_user (int (discord_id ))
                e =discord .Embed (
                title =" Aether Panel — Запись Проверка",
                color =0xc8922a ,
                timestamp =datetime .utcnow ()
                )
                e .description =(
                "```ansi\n\u001b[1;33m ТРЕБУЕТСЯ ПРОВЕРКА КОДА \u001b[0m\n```\n"
                "\n\n"
                f"Привет **{member_info['display_name']}**! \n\n"
                "Чтобы зарегистрироваться в **Aether Panel**,\n"
                "введите код проверки на странице регистрации:\n\n"
                f"```fix\n{code}\n```\n\n"
                ""
                )
                e .add_field (name ="⏱ Действительность",value ="```10 минут```",inline =True )
                e .add_field (name =" Безопасность",value ="```Tek использовать```",inline =True )
                e .add_field (
                name =" Warning",
                value ="*Если вы не регистрировались — игнорируйте это сообщение и никому не передавайте код.*",
                inline =False 
                )
                e .set_footer (text ="Aether Panel • Доверие Запись Система")
                await user .send (embed =e )
            except Exception as ex :
                print (f"DM отправл: {ex}")

        asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop )

        return render_template ('register.html',step =2 ,discord_id =discord_id ,password =password ,
        info =f'На Discord DM пользователя {member_info["display_name"]} отправлен 6-значный код.')

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
    # Админская страница настроек уведомлений — только для персонала (mod+).
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
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
        return render_template ('login.html',error ='Время проверки истекло, выполните вход заново.')

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
        return render_template ('login.html',two_fa =True ,token =token ,error ='Неверный код!')

    return render_template ('login.html',two_fa =True ,token =token )

@app .route ('/logout')
def logout ():
    session .clear ()
    return redirect (url_for ('login'))

@app .route ('/api/add-member',methods =['POST'])
@login_required 
def api_add_member ():
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('admin',999 ):
        return jsonify ({'error':'Нет доступа'}),403 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    password =data .get ('password','').strip ()
    display_name =data .get ('display_name',discord_id )
    name =data .get ('name',discord_id )
    avatar =data .get ('avatar','')

    if not discord_id or not password or len (password )<6 :
        return jsonify ({'error':'Неверные данные'})

    members_file ='data/members.json'
    os .makedirs ('data',exist_ok =True )
    members ={}
    if os .path .exists (members_file ):
        with open (members_file ,'r',encoding ='utf-8')as f :
            members =json .load (f )

    if discord_id in members :
        return jsonify ({'error':'Этот ID уже зарегистрирован!'})

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
    import time as _t 
    # Запоминаем предыдущую отметку просмотра — по ней считаем «непрочитанное»
    try :
        prev_seen =float (session .get ('notif_seen_ts',0 )or 0 )
    except (TypeError ,ValueError ):
        prev_seen =0 
    # Открытие списка означает «всё просмотрено» — сбрасываем бейдж опроса
    # (float — как ts событий, иначе событие в ту же секунду выглядело бы непрочитанным)
    session ['notif_seen_ts']=_t .time ()

    result =[]
    # 1) Личные уведомления (notifications.json по discord_id)
    discord_id =session .get ('discord_id')
    notif_file ='data/notifications.json'
    if discord_id and os .path .exists (notif_file ):
        with open (notif_file ,'r',encoding ='utf-8')as f :
            notifs =json .load (f )
        my =notifs .get (discord_id ,[])
        # Снимок с исходными флагами — клиент должен увидеть, что было непрочитанным
        for n in my :
            item =dict (n )
            item ['system']=False
            item .setdefault ('link','')
            item ['title']=_clean_md (item .get ('title',''))
            item ['message']=_clean_md (item .get ('message',''))
            result .append (item )
        # Отмечаем прочитанными
        for n in my :
            n ['read']=True
        notifs [discord_id ]=my
        with open (notif_file ,'w',encoding ='utf-8')as f :
            json .dump (notifs ,f ,indent =2 ,ensure_ascii =False )

    # 2) Системные уведомления всему персоналу (broadcast в panel_logs.json)
    try :
        logs_file ='data/panel_logs.json'
        if os .path .exists (logs_file ):
            with open (logs_file ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for entry in raw [-80 :]:
                if not entry .get ('broadcast'):
                    continue
                ts =entry .get ('ts',0 )or 0
                result .append ({
                'title':_clean_md (entry .get ('action','Уведомление')),
                'message':_clean_md (entry .get ('detail','')),
                'from':'Система',
                'created_at':entry .get ('timestamp',''),
                'read':ts <=prev_seen ,
                'system':True,
                'link':entry .get ('link',''),
                'event':entry .get ('event',''),
                })
    except Exception :
        pass

    result .sort (key =lambda x :x .get ('created_at',''),reverse =True )
    return jsonify (result [:30 ])

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
        return jsonify ({'error':'Нет доступа'}),403 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    message =data .get ('message','').strip ()
    title =data .get ('title','Уведомление').strip ()
    if not discord_id or not message :
        return jsonify ({'error':'Недостаточно данных'})

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
        return jsonify ({'error':'Нет доступа'}),403 
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
    online =sum (1 for g in bot_instance .guilds for m in g .members if not m .bot and m .status !=discord .Status .offline )

    return jsonify ({
    'guilds':guilds ,
    'users':users ,
    'online':online ,
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
        'owner_id':str (g .owner_id ),
        'online':sum (1 for m in g .members if not m .bot and m .status !=discord .Status .offline ),
        'channels':len (g .channels ),
        'roles':len (g .roles ),
        'boost':g .premium_subscription_count or 0 ,
        }for g in bot_instance .guilds ]

        return jsonify (guilds )
    except Exception as e :
        print (f"Ошибка списка серверов: {e}")
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
            return jsonify ({'error':'Сервер не найден'}),404 
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
            return jsonify ({'error':'Сервер не найден'}),404 
        member =guild .get_member (int (member_id ))
        if not member :
            return jsonify ({'error':'Участник не найден'}),404 
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

        # Кэш 10 с — не перебирать guild.members повторно для того же ответа
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

            # Чтобы вернуть общее количество через метаданные пагинации, добавляем
            # заголовок X-Total-Count, который фронтенд может использовать при необходимости.
        total =len (cached )
        page =cached [offset :offset +limit ]
        resp =jsonify (page )
        resp .headers ['X-Total-Count']=str (total )
        resp .headers ['X-Limit']=str (limit )
        resp .headers ['X-Offset']=str (offset )
        return resp 
    except Exception as e :
        print (f"Ошибка списка участников: {e}")
        return jsonify ([])

@app .route ('/api/logs')
@login_required 
@role_required ('mod')
def api_logs ():
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

                    # Читаем кэш Discord-аудита (бот обновляет его раз в 30 сек — данные свежие)
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
        # Чистим markdown из видимых полей — панель разметку не рендерит
        for _ev in all_events :
            _clean_md_fields (_ev )
        return jsonify (all_events [:1000 ])
    except Exception as e :
        print (f"Ошибка чтения логов: {e}")
        return jsonify ([])

def _warn_db_append (guild_id :str ,user_id :str ,reason :str ,moderator :str ):
    """Дублирует предупреждение в SQLite (GuildData) — основное хранилище,
    которое читают Discord-команды бота (/warnings, пороги авто-наказаний)."""
    try :
        from db import GuildData
        wdb =GuildData ('warnings')
        warns =wdb .get (int (guild_id ),str (user_id ),[])
        if not isinstance (warns ,list ):
            warns =[]
        warns .append ({
        'id':len (warns )+1 ,
        'reason':reason or 'Не указана',
        'mod':moderator or '?',
        'mod_id':'',
        'timestamp':datetime .utcnow ().isoformat ()
        })
        wdb .set (int (guild_id ),str (user_id ),warns )
    except Exception as _e :
        print (f"Ошибка записи предупреждения в SQLite: {_e}")

def _panel_notify (event ,title ,body ):
    """Отправить событие в диспетчер уведомлений панели (fail-safe)."""
    try :
        from services .notification_dispatcher import notify_event
        sender =None
        try :
            from web .routes_extra import _notify_discord_sender as sender
        except Exception :
            sender =None
        return notify_event (event ,title ,body ,discord_sender =sender )
    except Exception :
        return {}

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
                # Пропускаем мусор: None / "null" / пустые / нечисловые / ID неверной длины
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
                            'reason':_clean_md (warn .get ('reason','Не указана')),
                            'moderator':_clean_md (warn .get ('moderator',warn .get ('mod','?'))),
                            'timestamp':warn .get ('timestamp','')
                            })

        all_warnings .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
        return jsonify (all_warnings [:200 ])
    except Exception as e :
        print (f"Ошибка предупреждений: {e}")
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
    reason =data .get ('reason','Бан через веб-панель')

    try :
        guild =discord .utils .get (bot_instance .guilds ,id =guild_id )
        if not guild :
            return jsonify ({'error':'Сервер не найден'})

        async def do ():
            user =await bot_instance .fetch_user (user_id )
            await guild .ban (user ,reason =f"{reason} (by {session.get('username')})")
            return user .name 

        name =asyncio .run_coroutine_threadsafe (do (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'success':True ,'message':f'{name} забанен'})
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
    reason =data .get ('reason','Кик через веб-панель')

    try :
        guild =discord .utils .get (bot_instance .guilds ,id =guild_id )
        if not guild :
            return jsonify ({'error':'Сервер не найден'})
        member =guild .get_member (user_id )
        if not member :
            return jsonify ({'error':'Участник не найден'})

        async def do ():
            await member .kick (reason =f"{reason} (by {session.get('username')})")
            return member .name 

        name =asyncio .run_coroutine_threadsafe (do (),bot_instance .loop ).result (timeout =10 )
        return jsonify ({'success':True ,'message':f'{name} кикнут'})
    except Exception as e :
        return jsonify ({'error':str (e )})

@app .route ('/api/command/warn',methods =['POST'])
@login_required 
@role_required ('mod')
def api_warn ():
    data =request .get_json (silent =True )or {}
    guild_id =data .get ('guild_id')
    user_id =data .get ('user_id')
    reason =(data .get ('reason')or 'Предупреждение через веб-панель').strip ()or 'Причина не указана'

    # Валидация: guild_id и user_id должны быть числовыми и непустыми
    if not guild_id or not str (guild_id ).strip ():
        return jsonify ({'error':'guild_id необходимо'}),400 
    if not user_id or not str (user_id ).strip ():
        return jsonify ({'error':'user_id необходимо'}),400 
    guild_id =str (guild_id ).strip ()
    user_id =str (user_id ).strip ()
    if not (guild_id .isdigit ()and user_id .isdigit ()):
        return jsonify ({'error':'guild_id и user_id должны быть числами'}),400 
    if not (17 <=len (guild_id )<=22 and 17 <=len (user_id )<=22 ):
        return jsonify ({'error':'guild_id и user_id недействительны (Discord ID — 17–22 цифры)'}),400 
    if len (reason )>500 :
        return jsonify ({'error':'Причина слишком длинная (макс. 500 символов)'}),400 

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

        # Отбрасываем битые данные (None, "null", не-словари)
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
    _warn_db_append (guild_id ,user_id ,reason ,session .get ('username'))
    # Уведомление персонала по настроенным каналам (веб/Discord/email)
    _panel_notify ('warn',f"Предупреждение выдано (ID {user_id })",
    f"Модератор: {session .get ('username')} · Причина: {reason }")

    return jsonify ({'success':True ,'message':'Предупреждение добавлено'})

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
    # Поиск сервера
        guild =None 
        for g in bot_instance .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 

        if not guild :
            return jsonify ({'error':'Сервер не найден'})

        async def execute ():
            if command =='ban':
                user =await bot_instance .fetch_user (int (data .get ('user_id')))
                if not guild .me .guild_permissions .ban_members :
                    raise Exception ('У бота нет права на бан участников')
                await guild .ban (user ,reason =data .get ('reason','Бан через веб-панель'))
            elif command =='kick':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
                if not guild .me .guild_permissions .kick_members :
                    raise Exception ('У бота нет права Kick')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Роль целевого пользователя выше роли бота')
                await member .kick (reason =data .get ('reason','Кик через веб-панель'))
            elif command =='timeout':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
                if not guild .me .guild_permissions .moderate_members :
                    raise Exception ('У бота нет права Mute (Moderate Members)')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Роль целевого пользователя выше роли бота')
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
                'reason':data .get ('reason','Предупреждение через веб-панель'),
                'moderator':session .get ('username'),
                'timestamp':datetime .utcnow ().isoformat ()
                })
                with open (warns_file ,'w',encoding ='utf-8')as wf :
                    json .dump (warns ,wf ,ensure_ascii =False )
                _store .invalidate_path (warns_file )
                _warn_db_append (gid_str ,uid_str ,data .get ('reason','Предупреждение через веб-панель'),session .get ('username'))
                # Уведомление персонала по настроенным каналам (веб/Discord/email)
                _panel_notify ('warn',f"Предупреждение выдано (ID {uid_str })",
                f"Модератор: {session .get ('username')} · Причина: {data .get ('reason','Предупреждение через веб-панель')}")
                # Отправить DM о предупреждении
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
                            e_dm =discord .Embed (title =' Вы получили предупреждение',description =dm_msg ,color =0xc8922a )
                            e_dm .set_footer (text =guild .name )
                            await member .send (embed =e_dm )
                        except Exception :
                            pass 
            elif command =='jail':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
                    # Поиск jail-роли
                jail_role =discord .utils .get (guild .roles ,name ='Jail')
                if not jail_role :
                    raise Exception ('Роль Jail не найдена. Сначала создайте роль Jail или настройте /jail-setup.')
                    # Сохранить текущие роли, выдать jail-роль
                jail_data_file =f'data/jail_{guild.id}.json'
                jail_data ={}
                if os .path .exists (jail_data_file ):
                    with open (jail_data_file ,'r',encoding ='utf-8')as jf :
                        jail_data =json .load (jf )
                uid_str =str (member .id )
                jail_data [uid_str ]={
                'role':[str (r .id )for r in member .roles [1 :]],
                'reason':data .get ('reason','Jail через веб-панель'),
                'mod':session .get ('username'),
                'timestamp':datetime .utcnow ().isoformat ()
                }
                with open (jail_data_file ,'w',encoding ='utf-8')as jf :
                    json .dump (jail_data ,jf ,indent =2 ,ensure_ascii =False )
                    # Снять все роли, выдать jail-роль
                roles_to_remove =[r for r in member .roles [1 :]if r !=jail_role and not r .managed ]
                await member .remove_roles (*roles_to_remove ,reason ='Jail')
                await member .add_roles (jail_role ,reason =data .get ('reason','Jail через веб-панель'))
                # DM отправить
                try :
                    e_dm =discord .Embed (title =' Jail-наказание',description =f'Вы получили jail-наказание на сервере **{guild.name}**.\n**Причина:** {data.get("reason", "Не указана")}',color =0xe74c3c )
                    await member .send (embed =e_dm )
                except Exception :
                    pass 
            elif command =='unjail':
                member =guild .get_member (int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
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
                    raise Exception ('Участник не найден на сервере')
                await member .timeout (None ,reason ='Снятие мута через веб-панель')
            elif command =='unban':
                uid =data .get ('user_id')
                if not uid :
                    raise Exception ('Пользователь ID необходимо')
                user =await bot_instance .fetch_user (int (uid ))
                await guild .unban (user ,reason =data .get ('reason','Снятие бана через веб-панель'))
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
                "```ansi\n\u001b[1;34m Aether ПОДДЕРЖКА СИСТЕМА \u001b[0m\n```\n"
                f"{_divider()}\n\n"
                "Возникла проблема? Нажми кнопку ниже!\n\n"
                f"{_divider()}"
                )
                e .set_footer (text =f"{guild.name} • Поддержка Система",icon_url =guild .icon .url if guild .icon else None )
                await ch .send (embed =e ,view =TicketView ())
            elif command in ('текст','zar','rastgele'):
                pass # Развлекательные команды выполняются в Discord, панель только запускает
                # Jail kategorisi, канал ve роль создать
                jail_cat =discord .utils .get (guild .categories ,name ='Наказание Комната')
                if not jail_cat :
                    jail_cat =await guild .create_category ('Наказание Комната')
                jail_role =discord .utils .get (guild .roles ,name ='Jail')
                if not jail_role :
                    jail_role =await guild .create_role (name ='Jail',color =discord .Color (0x2c2c2c ))
                    # Запретить jail-роль во всех каналах
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
                    raise Exception ('Канал не найден')
                if not guild .me .guild_permissions .manage_messages :
                    raise Exception ('У бота нет права управления сообщениями')
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
            return jsonify ({'success':True ,'message':'Jail-система настроена! Категория, канал и роль созданы.'})
        return jsonify ({'success':True ,'message':'Действие успешно применено.'})
    except Exception as e :
        print (f"Ошибка выполнения команды: {e}")
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
        # Роли участника (кроме everyone)
        member_role_ids =[str (r .id )for r in member .roles [1 :]]
        # Все сервер роли
        all_roles =[{'id':str (r .id ),'name':r .name ,'color':str (r .color )}for r in guild .roles if r .name !='@everyone']
        all_roles .reverse ()
        has_roles =[r for r in all_roles if r ['id']in member_role_ids ]
        missing_roles =[r for r in all_roles if r ['id']not in member_role_ids ]
        return jsonify ({'has':has_roles ,'missing':missing_roles })
    except Exception as e :
        print (f"Ошибка получения ролей участника: {e}")
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
    # Поиск сервера
        guild =None 
        for g in bot_instance .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 

        if not guild :
            return jsonify ({'error':'Сервер не найден'})

            # Поиск канала
        channel =guild .get_channel (int (channel_id ))

        if not channel or not isinstance (channel ,discord .TextChannel ):
            return jsonify ({'error':'Канал не найден или это не текстовый канал'})

            # Отправка сообщения — используем собственный event loop бота
        async def send ():
            await channel .send (message )

        import asyncio 
        asyncio .run_coroutine_threadsafe (send (),bot_instance .loop )

        return jsonify ({'success':True ,'message':'Сообщение отправлено'})
    except Exception as e :
        print (f"Ошибка отправки сообщения: {e}")
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
        return jsonify ({'error':'Файл заявок отсутствует'})
    with open (apps_file ,'r',encoding ='utf-8')as f :
        data =json .load (f )
    if app_id not in data :
        return jsonify ({'error':'Заявка не найдена'})
    req =request .get_json (silent =True )or {}
    action =req .get ('action')# 'approve' or 'reject'
    note =req .get ('note','')
    data [app_id ]['status']='approved'if action =='approve'else 'rejected'
    data [app_id ]['reviewed_by']=session .get ('username')
    data [app_id ]['review_note']=note 
    with open (apps_file ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,indent =2 ,ensure_ascii =False )

        # При одобрении выдать Discord-роль + отправить DM
    role_info ={'assigned':None ,'error':None }
    if bot_instance :
        app_data =data [app_id ]
        async def send_dm ():
            try :
                if action =='approve':
                    # Маппинг: первая Discord-роль из role_map.json, привязанная к 'mod'/'admin'
                    try :
                        gid =str (app_data .get ('guild_id')or MAIN_GUILD_ID or '')
                        guild =bot_instance .get_guild (int (gid ))if gid .isdigit ()else None
                        if not guild and bot_instance .guilds :guild =bot_instance .guilds [0 ]
                        if guild :
                            member =guild .get_member (int (app_data ['user_id']))
                            if not member :
                                try :member =await guild .fetch_member (int (app_data ['user_id']))
                                except Exception :member =None
                            target =None
                            for rid ,prole in DISCORD_ROLE_MAP .items ():
                                if prole in ('mod','admin')and guild .get_role (int (rid )):
                                    target =guild .get_role (int (rid ));break
                            if member and target :
                                await member .add_roles (target ,reason ='Заявка одобрена (Aether Panel)')
                                role_info ['assigned']=target .name
                            elif not target :
                                role_info ['error']='not_mapped'
                    except Exception as _role_err :
                        role_info ['error']=str (_role_err )[:120 ]
                user =await bot_instance .fetch_user (int (app_data ['user_id']))
                if action =='approve':
                    embed =discord .Embed (
                    title =" Заявка одобрена!",
                    description ="Поздравляем! Ваша заявка в администрацию рассмотрена и **одобрена**.\nАдминистрация свяжется с вами в ближайшее время.",
                    color =0x2ecc71 
                    )
                    embed .add_field (name =" Рассмотрел",value =session .get ('username','?'),inline =True )
                    embed .add_field (name =" Заявка ID",value =f"`{app_id}`",inline =True )
                    if role_info ['assigned']:
                        embed .add_field (name =" Выдана роль",value =role_info ['assigned'],inline =True )
                    if note :
                        embed .add_field (name =" Not",value =note ,inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Aether Panel • Система заявок",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime .utcnow ()
                else :
                    embed =discord .Embed (
                    title =" Заявка отклонена",
                    description ="К сожалению, ваша заявка в администрацию на этот раз не принята.\nВы можете подать её снова позже.",
                    color =0xe74c3c 
                    )
                    embed .add_field (name =" Рассмотрел",value =session .get ('username','?'),inline =True )
                    embed .add_field (name =" Заявка ID",value =f"`{app_id}`",inline =True )
                    embed .add_field (name =" Red Причина",value =note if note else "Не belirtildi",inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Aether Panel • Система заявок",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime .utcnow ()
                await user .send (embed =embed )
            except Exception as e :
                print (f"DM отправл: {e}")
        try :
            asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop ).result (timeout =15 )
        except Exception :
            pass

    resp ={'success':True }
    if action =='approve':
        resp ['role_assigned']=role_info ['assigned']
        if role_info ['error']=='not_mapped':
            resp ['role_note']='no_mapped_role'
    return jsonify (resp )

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

@app .context_processor
def inject_panel_menu ():
    """Expose the visible sidebar menu for the current panel role."""
    from services .panel_menu import panel_groups_for
    role =session .get ('role','uye')
    menu =panel_groups_for (role )if role in ('owner','admin','mod')else []
    return {'panel_menu':menu ,'panel_role':role }

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
    # Только Arthur или пользователь с owner-ролью
    if username !='Arthur'and session .get ('role')!='owner':
        return jsonify ({'error':'Нет доступа'}),403 
    data =request .get_json (silent =True )or {}
    target =data .get ('target','').strip ()# какой hesabыn parolasi deгiшecek
    new_pass =data .get ('new_password','').strip ()
    if not target or not new_pass or len (new_pass )<4 :
        return jsonify ({'error':'Неверные данные'})
    if target in USERS :
        USERS [target ]['password_hash']=_hash_pw (new_pass )
        try :
            os .makedirs ('data',exist_ok =True )
            _store .atomic_write_json (_OWNER_CRED_PATH ,{'user':target ,'password_hash':USERS [target ]['password_hash']})
        except Exception as e :
            print (f'[ВНИМАНИЕ] Не удалось сохранить пароль владельца постоянно: {e}')
        return jsonify ({'success':True ,'message':f'Пароль {target} обновлён (сохранён постоянно)'})
        # поиск в members.json
    members_file ='data/members.json'
    if os .path .exists (members_file ):
        with open (members_file ,'r',encoding ='utf-8')as f :
            members =json .load (f )
        if target in members :
            members [target ]['password']=_hash_pw (new_pass )
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
        'error':'Бот ещё не готов, повторите попытку через несколько секунд.'
        })
    data =request .get_json (silent =True )or {}
    guild_id =str (data .get ('guild_id',''))
    user_id =str (data .get ('user_id',''))
    if not guild_id or not user_id :
        return jsonify ({'error':'Yetersiz parametrov'}),400 
    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
        member =guild .get_member (int (user_id ))
        if not member :
            return jsonify ({'found':False ,'error':'Вы не участник этого сервера! Не можете подать заявку.'})
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
            return jsonify ({'error':f'Поле {field} обязательно'}),400 

    apps_file ='data/staff_apps.json'
    os .makedirs ('data',exist_ok =True )
    apps ={}
    if os .path .exists (apps_file ):
        with open (apps_file ,'r',encoding ='utf-8')as f :
            apps =json .load (f )

            # Проверка ожидающей заявки
    uid =str (data ['discord_id'])
    for app_data in apps .values ():
        if app_data .get ('user_id')==uid and app_data .get ('status')=='pending':
            return jsonify ({'error':'У вас уже есть заявка на рассмотрении!'}),400 

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

    # Уведомление персонала о новой заявке (веб/Discord/email)
    _panel_notify ('staff_apply',
    f"Новая заявка в персонал: {data ['discord_name']}",
    f"ID: {uid } · возраст: {data ['yas']} · опыт: {str (data ['tecrube'])[:120 ]}")

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
                embed .add_field (name =" Возраст",value =data ['yas'],inline =True )
                embed .add_field (name ="⏰ Активен",value =data ['активен'],inline =True )
                embed .add_field (name =" Опыт",value =f"```{data['tecrube']}```",inline =False )
                embed .add_field (name =" Почему Администратор?",value =f"```{data['почему']}```",inline =False )
                if data .get ('ekstra'):
                    embed .add_field (name =" Дополнительно",value =f"```{data['ekstra']}```",inline =False )
                embed .set_footer (text =f"Заявка ID: {app_id} • {guild.name}")
                view =StaffReviewView ()
                msg =await channel .send (embed =embed ,view =view )
                apps [app_id ]['message_id']=str (msg .id )
                with open (apps_file ,'w',encoding ='utf-8')as f :
                    json .dump (apps ,f ,indent =2 ,ensure_ascii =False )
            except Exception as e :
                print (f"Ошибка отправки сообщения в Discord: {e}")
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
    """Получить сопоставление ролей + список ролей сервера"""
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
    """Добавить/изменить сопоставление роли.
    panel_role: 'uye' | 'mod' | 'admin' | 'owner'  (uye = снять сопоставление, авто-определение)
    """
    data =request .get_json (silent =True )or {}
    role_id =str (data .get ('role_id','')).strip ()
    panel_role =data .get ('panel_role','').strip ()
    if not role_id or panel_role not in ('mod','admin','owner','uye'):
        return jsonify ({'error':'Неверные данные'}),400 
    if panel_role =='uye':
        DISCORD_ROLE_MAP .pop (role_id ,None )
    else :
        DISCORD_ROLE_MAP [role_id ]=panel_role 
    _save_role_map ()
    _log_panel_action ('ROLE_MAP_SET',f'{role_id} → {panel_role or "uye"}'if panel_role else f'{role_id} → uye')
    return jsonify ({'success':True })

@app .route ('/api/role-map/<role_id>',methods =['DELETE'])
@login_required 
@role_required ('admin')
def api_delete_role_map (role_id ):
    """Удалить сопоставление роли"""
    if role_id in DISCORD_ROLE_MAP :
        del DISCORD_ROLE_MAP [role_id ]
        _save_role_map ()
        _log_panel_action ('ROLE_MAP_DELETE',role_id )
    return jsonify ({'success':True })

# ── Panel menu visibility (sidebar categories & rooms per panel) ──
@app .route ('/api/panel-menu')
@login_required
@role_required ('owner')
def api_panel_menu_get ():
    """Return the full MENU + current visibility config for mod/admin panels."""
    from services .panel_menu import MENU ,get_config ,CONFIGURABLE
    cfg =get_config ()
    return jsonify ({
    'success':True ,
    'menu':MENU ,
    'config':cfg ,
    'configurable':list (CONFIGURABLE ),
    })

@app .route ('/api/panel-menu',methods =['POST'])
@login_required
@role_required ('owner')
def api_panel_menu_set ():
    """Save per-panel visibility: {role: {groups:[...], items:[...]}}."""
    from services .panel_menu import get_config ,save_config ,CONFIGURABLE
    data =request .get_json (silent =True )or {}
    role =str (data .get ('role','')).strip ()
    if role not in CONFIGURABLE :
        return jsonify ({'success':False ,'error':'Неверная роль'}),400
    groups =data .get ('groups',[])
    items =data .get ('items',[])
    if not isinstance (groups ,list )or not isinstance (items ,list ):
        return jsonify ({'success':False ,'error':'Неверный формат'}),400
    cfg =get_config ()
    cfg [role ]={'groups':[str (g )for g in groups ],'items':[str (i )for i in items ]}
    save_config (cfg )
    _log_panel_action ('PANEL_MENU_SET',f'{role} → {len(groups)} групп, {len(items)} страниц')
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
            embed .description =f"Здравствуйте, **{member_info['display_name']}**!\n\nВаш PIN-код для входа в панель:\n\n```fix\n{code}\n```\nДействителен в течение 5 минут."
            embed .set_footer (text ="Aether Panel")
            await u .send (embed =embed )
        asyncio .run_coroutine_threadsafe (send_pin (),bot_instance .loop ).result (timeout =10 )
        tests .append ({'name':'Отправка PIN-кода','status':'ok','detail':'Отправлено в ЛС'})
    except Exception :
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
    author =data .get ('author','')
    author_icon =data .get ('author_icon','')
    fields =data .get ('fields',[]) or []
    guild =bot_instance .get_guild (guild_id )
    if not guild :return jsonify ({'error':'Сервер не найден'})
    channel =bot_instance .get_channel (channel_id )
    if not channel :return jsonify ({'error':'Канал не найден'})
    async def send_it ():
        try :color =discord .Color (int (color_hex ,16 ))
        except :color =discord .Color (0xdc143c )
        embed =discord .Embed (color =color )
        if title :embed .title =title
        if description :embed .description =description
        if footer :embed .set_footer (text =footer )
        if image_url :embed .set_image (url =image_url )
        if thumbnail_url :embed .set_thumbnail (url =thumbnail_url )
        if author :
            if author_icon :
                embed .set_author (name =author ,icon_url =author_icon )
            else :
                embed .set_author (name =author )
        if isinstance (fields ,list ):
            for f in fields [:25 ]:
                if not isinstance (f ,dict )or not (f .get ('name')or f .get ('value')):
                    continue
                embed .add_field (name =f .get ('name','')or '\u200b',value =f .get ('value','')or '\u200b',inline =bool (f .get ('inline',False )))
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
    """Обработать голосовые команды от voice_listener.py"""
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
        # Вместо создания фейкового объекта сообщения — используем ai_chat cog напрямую
        cog =bot_instance .get_cog ('AIChat')
        if not cog :
            return 'AIChat cog не найден'
            # правильно вызываем _detect_owner_intent
            # Для этого нужен фейковый объект сообщения — используем DM-канал
        async for msg in dm .history (limit =1 ):
        # Нашли реальное сообщение — запускаем распознавание intent'а
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

        # Проверяем запись участника
    members_file ='data/members.json'
    if not os .path .exists (members_file ):
        return jsonify ({'error':'Запись участника не найдена'})
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
        return jsonify ({'error':'Сейчас бот офлайн, попробуйте позже'})

    async def send_dm ():
        user =await bot_instance .fetch_user (int (discord_id ))
        await user .send (
        f" **Ваш код сброса пароля:** `{code}`\n"
        "Этот код действует 5 минут. Введите его в панели, чтобы сбросить пароль.\n"
        "Если вы не запрашивали сброс — проигнорируйте это сообщение."
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
        return jsonify ({'error':'Пароль должен быть не короче 6 символов'})

    entry =_reset_codes .get (discord_id )
    if not entry :
        return jsonify ({'error':'Сначала запросите код'})
    if _time .time ()>entry ['expires']:
        del _reset_codes [discord_id ]
        return jsonify ({'error':'Срок действия кода истёк, запросите новый'})
    if entry ['code']!=code :
        return jsonify ({'error':'Неверный код'})

        # Parolayi обновить
    members_file ='data/members.json'
    with open (members_file ,'r',encoding ='utf-8')as f :
        members =json .load (f )
    if discord_id not in members :
        return jsonify ({'error':'Пользователь не найден'})
    members [discord_id ]['password']=_hash_pw (new_pass )
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
    """Опрос непрочитанных уведомлений панели для текущего пользователя.

    Возвращает список событий (системные broadcast-уведомления + действия
    самого пользователя) и счётчик непрочитанных для бейджа колокольчика.
    Отметка «просмотрено» ставится при открытии выпадающего списка
    (/api/my-notifications) через session['notif_seen_ts'].
    """
    import os ,json ,time as _t 
    cutoff_ts =request .args .get ('since',0 )
    try :
        cutoff_ts =int (cutoff_ts )
    except (TypeError ,ValueError ):
        cutoff_ts =0 
    try :
        seen_ts =float (session .get ('notif_seen_ts',0 )or 0 )
    except (TypeError ,ValueError ):
        seen_ts =0 
    notifs =[]
    # 1) ТОЛЬКО системные broadcast-уведомления — ровно тот же набор, что
    # показывает выпадающий список (/api/my-notifications). Действия самого
    # пользователя сюда НЕ входят: иначе бейдж кричал «есть сообщение», а
    # список был пуст («Нет уведомлений») — классическая рассинхронизация.
    try :
        f ='data/panel_logs.json'
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                raw =json .load (fp )
            for entry in raw [-80 :]:
                if not entry .get ('broadcast'):
                    continue
                ts =entry .get ('ts',0 )or 0 
                if ts <=cutoff_ts :
                    continue 
                notifs .append ({
                'id':f"pl-{ts}-{len(notifs)}",
                'title':_clean_md (entry .get ('action','Уведомление')),
                'body':_clean_md (entry .get ('detail','')),
                'icon':'🔔',
                'ts':ts ,
                'kind':'notify',
                'link':entry .get ('link',''),
                })
    except Exception :
        pass 
    # 2) (убрано) temp-действия самого пользователя: себе уведомления не нужны,
    # они и есть в ленте активности
    # 3) личные уведомления (notifications.json по discord_id)
    personal_unread =0 
    try :
        discord_id =session .get ('discord_id')
        nf ='data/notifications.json'
        if discord_id and os .path .exists (nf ):
            with open (nf ,'r',encoding ='utf-8')as fp :
                pers =json .load (fp ).get (discord_id ,[])
            personal_unread =len ([n for n in pers if not n .get ('read')])
    except Exception :
        pass 
    notifs .sort (key =lambda x :x .get ('ts',0 ),reverse =True )
    unread =len ([n for n in notifs if n .get ('ts',0 )>seen_ts ])+personal_unread 
    return jsonify ({'notifications':notifs [:20 ],'unread':unread ,'ts':int (_t .time ()*1000 )})


@app .route ('/api/activity-feed')
@login_required
def api_activity_feed ():
    """Rich recent panel activity (newest first) for the activity drawer.

    Собирает события из нескольких источников и нормализует их в единый
    формат с иконкой, цветом и типом — чтобы лента была информативной.
    """
    import os, json, time as _t

    items = []

    def push(icon, title, user, detail, ts, evtype='system', color=None, link=''):
        if not ts: return
        items.append({
            'icon': icon, 'title': _clean_md(title), 'user': _clean_md(user) or '—',
            'detail': _clean_md(detail) or '', 'ts': ts, 'type': evtype, 'color': color,
            'link': link,
        })

    # 1) Логи входа в панель
    try:
        f = 'data/login_log.json'
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                raw = json.load(fp)
            for e in raw[-20:]:
                ts = e.get('ts', 0)
                if not ts:
                    try:
                        ts = int(datetime.fromisoformat(e.get('timestamp','')).timestamp())
                    except Exception:
                        ts = 0
                push('🔐', 'Вход в панель', e.get('username'), f"Роль: {e.get('role','?')}", ts, 'auth', link='/logs')
    except Exception:
        pass

    # 2) Действия модерации (audit + mod_data)
    try:
        f = 'data/audit_log.json'
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            for gid, events in data.items():
                for ev in events[-15:]:
                    ts = 0
                    try:
                        ts = int(datetime.fromisoformat(ev.get('timestamp','')).timestamp())
                    except Exception:
                        ts = 0
                    act = (ev.get('action') or '').lower()
                    icon = '🛡'
                    evtype = 'mod'
                    if 'бан' in act or 'ban' in act: icon = '🔨'
                    elif 'мут' in act or 'mute' in act: icon = '🔇'
                    elif 'кик' in act or 'kick' in act: icon = '👢'
                    elif 'роль' in act: icon = '🎭'
                    elif 'канал' in act: icon = '📁'
                    elif 'сообщ' in act or 'message' in act: icon = '💬'
                    elif 'голос' in act or 'voice' in act: icon = '🎙'
                    push(icon, ev.get('action','Действие'), ev.get('user_name') or ev.get('mod_name'),
                         ev.get('reason',''), ts, evtype, link='/logs')
    except Exception:
        pass

    # 3) Предупреждения (warnings.json)
    try:
        f = 'data/warnings.json'
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            for gid, users in data.items():
                for uid, warns in users.items():
                    for w in warns[-5:]:
                        ts = 0
                        try:
                            ts = int(datetime.fromisoformat(w.get('timestamp','')).timestamp())
                        except Exception:
                            ts = 0
                        push('⚠️', 'Предупреждение', w.get('moderator') or w.get('mod') or uid,
                             w.get('reason',''), ts, 'warn', link='/warnings')
    except Exception:
        pass

    # 4) Тикеты (ai_tickets_*.json)
    try:
        for fn in os.listdir('data'):
            if fn.startswith('ai_tickets_') and fn.endswith('.json'):
                with open(os.path.join('data', fn), 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                for tid, tk in data.items():
                    ts = 0
                    try:
                        ts = int(datetime.fromisoformat(tk.get('created_at','')).timestamp())
                    except Exception:
                        ts = 0
                    push('🎫', 'Тикет: '+ (tk.get('category') or 'общий'),
                         tk.get('user_name'), tk.get('description','')[:80], ts, 'ticket', link='/ticket-search')
    except Exception:
        pass

    # 5) Панель-логи (POST-действия) — broadcast-события пропускаем:
    # они уже попадают из истории уведомлений (источник 6) с иконками и ссылками
    try:
        f = 'data/panel_logs.json'
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                raw = json.load(fp)
            for e in raw[-40:]:
                if e.get('broadcast'):
                    continue
                push('🖥', e.get('action','Действие'), e.get('username'), e.get('detail',''), e.get('ts',0), 'panel', link='/logs')
    except Exception:
        pass

    # 6) События диспетчера уведомлений (история с иконками и ссылками)
    try:
        f = 'data/notification_history.json'
        _ev_type = {'ticket_open':'ticket','ticket_message':'ticket','ticket_close':'ticket',
                    'priority_change':'ticket','assignment':'ticket','warn':'warn',
                    'mod_action':'mod','staff_apply':'panel','test':'system'}
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                hist = json.load(fp)
            for h in hist[-30:]:
                ts = 0
                try:
                    ts = int(datetime.fromisoformat(h.get('created_at','')).timestamp())
                except Exception:
                    ts = 0
                push(h.get('icon','🔔'), h.get('title','Уведомление'), 'Система',
                     h.get('body',''), ts, _ev_type.get(h.get('event',''),'system'),
                     link=h.get('link',''))
    except Exception:
        pass

    # Сортировка — новые сверху
    items.sort(key=lambda x: x.get('ts') or 0, reverse=True)
    return jsonify({'items': items[:80]})


    # WebSocket Server Initialization 
if WEBSOCKET_ENABLED :
    try :
    # Запуск WebSocket сервера в отдельном потоке
        ws_thread =start_websocket_thread (host ='localhost',port =8765 )
        print ('[WebSocket] Сервер инициализирован')
    except Exception as e :
        print (f'[WebSocket] Ошибка инициализации: {e}')
        WEBSOCKET_ENABLED =False 
