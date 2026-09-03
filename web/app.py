
from logger import get_logger

# Конфигурация (.env или DOTENV_PATH) — ДО чтения любых переменных окружения
# ниже (SECRET_KEY, PANEL_USER/PANEL_PASSWORD, MAIN_GUILD_ID): иначе панель
# стартовала с пустым окружением и генерировала случайный пароль, игнорируя .env.
import config as _root_config  # noqa: F401

_log = get_logger("app")

import random 
import string 
import hashlib 
import math 
from flask import Flask ,render_template ,request ,session ,redirect ,url_for ,send_from_directory ,Response ,g 
# jsonify ВСЕХ ответов панели — из web.routes._common: снежинки Discord
# (>2^53) уходят клиенту строкой, иначе JS ломает цифры id.
from web.routes._common import jsonify ,role_member_counts
import discord 
from discord .ext import commands 
import asyncio 
import json 
import os 
from functools import wraps 
from urllib.parse import quote_plus
import threading 
from datetime import datetime, timezone

from datetime import timedelta 

# WebSocket импорты
try :
    from web .websocket_server import start_websocket_thread ,notify_stats_updated 
    WEBSOCKET_ENABLED =True 
except ImportError :
    WEBSOCKET_ENABLED =False 
    print ('[WebSocket] Модуль не найден, real-time отключен')

import os as _os 
_BASE =_os .path .dirname (_os .path .abspath (__file__ ))
app =Flask (__name__ ,
template_folder =_os .path .join (_BASE ,'templates'),
static_folder =_os .path .join (_BASE ,'static'))
# Страницы доступны и со слэшем на конце (/dashboard/ = /dashboard) —
# иначе пользователь, дописавший «/», получает 404.
app .url_map .strict_slashes =False

# Панель за внешним прокси/туннелем (Cloudflare Tunnel для личного домена):
# WEB_BEHIND_PROXY=1 → честные https:// и хост из X-Forwarded-*, иначе
# редиректы/куки собираются как http://localhost и фронт ломается.
if (_os .environ .get ('WEB_BEHIND_PROXY','')or '').strip ().lower ()in ('1','true','yes','on'):
    try :
        from werkzeug .middleware .proxy_fix import ProxyFix 
        app .wsgi_app =ProxyFix (app .wsgi_app ,x_proto =1 ,x_host =1 ,x_for =1 )
        print ('[ВЕБ] WEB_BEHIND_PROXY=1 — режим внешнего домена включён (ProxyFix)')
    except Exception as _pfe :
        print (f'[ВЕБ] ProxyFix не применён: {_pfe}')


def _behind_proxy ():
    # WEB_BEHIND_PROXY=1 ставит scripts/setup_panel_tunnel.bat в .env, но только
    # если нашёл .env — иначе просит дописать руками, и тогда http->https и HSTS
    # молча не включаются (internet.nl: «redirect: no», «HSTS: None»). Поэтому
    # дополнительно определяем Cloudflare по заголовку CF-RAY: его добавляет сам
    # Cloudflare на каждый запрос, так что работа не зависит от .env.
    if (_os .environ .get ('WEB_BEHIND_PROXY','')or '').strip ().lower ()in ('1','true','yes','on'):
        return True
    try :
        return bool (request .headers .get ('CF-RAY'))
    except Exception :
        return False


@app .before_request
def _force_https_public():
    # Браузер писал «домен не защищён»: http://hakumods.xyz никуда не вёл.
    # За туннелем жёстко перекидываем http → https (локалку не трогаем).
    if not _behind_proxy ():
        return None
    if request .headers .get ('X-Forwarded-Proto','https')!='http':
        return None
    host =(request .host or '').lower ()
    if not host or host .startswith (('localhost','127.','0.0.0.0','[::1]')):
        return None
    return redirect ('https://'+host +request .full_path .rstrip ('?'),code =301)

# Производительность: атомарная запись, TTL-кэш, пакетный (batch) флашер логов
from web import _store # noqa: E402
from web .demo_mode import demo_mode_active # noqa: E402
from services .audit_labels import human_action # noqa: E402
import atexit # noqa: E402

# Секретный ключ сессий. Приоритет:
#  1) SECRET_KEY из .env
#  2) случайный ключ, сгенерированный один раз и сохранённый в data/flask_secret.key
# Хардкодить ключ в коде НЕЛЬЗЯ — зная его, любой может подделать cookie
# сессии и войти в панель как owner (панель публикуется через Cloudflare Tunnel).
def _load_secret_key ():
    env_key =( _os .environ .get ('SECRET_KEY','')or '').strip ()
    if env_key :
        return env_key
    # если ключ не задан — сгенерировать и сохранить, чтобы сессии жили между рестартами
    key_path =_os .path .abspath (_os .path .join (_BASE ,'..','data','flask_secret.key'))
    try :
        _os .makedirs (_os .path .dirname (key_path ),exist_ok =True )
        if _os .path .exists (key_path ):
            with open (key_path ,'r',encoding ='utf-8')as f :
                saved =f .read ().strip ()
            if len (saved )>=32 :
                return saved
        import secrets as _secrets
        new_key =_secrets .token_urlsafe (48)
        with open (key_path ,'w',encoding ='utf-8')as f :
            f .write (new_key)
        try :
            _os .chmod (key_path ,0o600)
        except OSError as _ex:
            _log.debug("_load_secret_key(): подавлено: %s", _ex)
        print ('[БЕЗОПАСНОСТЬ] Сгенерирован новый SECRET_KEY -> data/flask_secret.key')
        return new_key
    except Exception as _e :
        # последний резерв — случайный ключ на время запуска
        # (все сессии сбросятся при рестарте, но это безопасно)
        print (f'[БЕЗОПАСНОСТЬ] Не удалось сохранить SECRET_KEY ({_e}), используется временный')
        import secrets as _secrets
        return _secrets .token_urlsafe (48)

app .secret_key =_load_secret_key ()
# Усиление защиты сессии (cookie) панели
app .config ['SESSION_COOKIE_HTTPONLY']=True   # JS не может прочитать cookie (anti-XSS кражи)
app .config ['SESSION_COOKIE_SAMESITE']='Lax'  # cookie не уходит с cross-site формами (anti-CSRF)
# Secure-cookie имеет смысл только за HTTPS-туннелем; на голом http://localhost
# включение сломало бы вход (браузер не отправил бы cookie).
if _os .getenv ('PANEL_HTTPS','0')=='1':
    app .config ['SESSION_COOKIE_SECURE']=True 
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

# Защита от перебора паролей: нарастающая пауза после неверных попыток входа
# (ключ: IP + логин). Полной блокировки нет намеренно — за туннелем Cloudflare
# у всех пользователей один remote_addr, и агрессивный lockout выключил бы
# панель для всех.
_login_fails =defaultdict (list )# (ip, username) -> [timestamps]

def _throttle_failed_login (username ):
    key =(request .remote_addr or '?',(username or '').lower ())
    now =_time .time ()
    fails =[t for t in _login_fails [key ]if now -t <900 ]
    fails .append (now )
    _login_fails [key ]=fails
    _time .sleep (min (3.0 ,0.5 *len (fails )))

def _demo_mode ():
    """Демо-режим предпросмотра: вход в панель без пароля (DEMO_MODE=1).

    Только для показа панели без бота (предпросмотр до настройки).
    Стоп-правила — в web.demo_mode.demo_mode_active: демо игнорируется,
    если бот подключён, задан TOKEN или MAIN_GUILD_ID указывает на
    настоящий сервер (заказ владельца: «панель грузит фейк и чужой
    сервер» — это была демо-фабрикация при забытом DEMO_MODE=1).
    Сознательный override для витрины поверх боевого .env: DEMO_FORCE=1.
    """
    return demo_mode_active (bot_connected =bot_instance is not None )


def _demo_counts ():
    """Реальные числа демо-витрины: (участников, в сети, каналов, ролей).

    Раньше в заглушках было зашито 1247/213/16/24 — витрина показывала
    «1247 участников», а /users перечислял 9 настоящих демо-людей;
    каналов в демо 18, а счётчик говорил 16. Цифры теперь берутся из тех
    же файлов, что и сами страницы, поэтому счётчики и списки не спорят.
    """
    total ,online ,channels ,roles =1 ,1 ,0 ,0
    try :
        from web .routes ._common import DEMO_MEMBERS
        total =len (DEMO_MEMBERS )or 1
        online =sum (1 for m in DEMO_MEMBERS
                     if str (m .get ('status')or '').lower ()in ('online','idle','dnd'))
        online =online or max (1 ,total //3 )
    except Exception as _ex :
        _log .debug ("_demo_counts(): участники: %s",_ex )
    try :
        with open ('data/demo_channels.json',encoding ='utf-8')as _f :
            _ch =json .load (_f )
        channels =len (_ch )if isinstance (_ch ,list )else len (_ch .get ('channels',[]))
    except Exception as _ex :
        _log .debug ("_demo_counts(): каналы: %s",_ex )
    try :
        import glob as _glob
        for _p in _glob .glob ('data/demo_roles_*.json'):
            with open (_p ,encoding ='utf-8')as _f :
                _rl =json .load (_f )
            roles =len (_rl )if isinstance (_rl ,list )else len (_rl .get ('roles',[]))
            break
    except Exception as _ex :
        _log .debug ("_demo_counts(): роли: %s",_ex )
    return total ,online ,channels ,roles

# Версия сборки: считаем ОДИН раз при старте. За жизнь процесса код не
# меняется (обновление перезапускает процесс), а дёргать git на каждый
# запрос — значит замедлять каждую страницу.
_BUILD_INFO ={'sha':None ,'branch':None }
try :
    from services import self_update as _SU
    _bot_root =os .path .dirname (os .path .dirname (os .path .abspath (__file__ )))
    _BUILD_INFO ['sha']=_SU .local_sha (_bot_root )
    _BUILD_INFO ['branch']=_SU .running_branch (_bot_root )
except Exception as _bi_ex:
    _log .debug ('build info недоступна: %s',_bi_ex )


@app .context_processor
def inject_build_info ():
    _sha =_BUILD_INFO .get ('sha')or ''
    return {'build_sha':_sha [:7 ],'build_branch':_BUILD_INFO .get ('branch')or ''}


@app .context_processor
def inject_demo_mode ():
    return {'demo_mode':_demo_mode ()}


# Авто-версии статики: ?v= по времени изменения файла — браузер сам подхватит
# свежий JS/CSS после каждого обновления, вручную номера больше не крутим.
@app .context_processor
def inject_panel_ws ():
    """Внешний WebSocket-адрес для live-обновлений панели.

    Пусто (default) — браузер сам строит ws://хост:8765 и работает только
    локально; при панели за доменом/туннелем укажи в .env:
    PANEL_WS_URL=wss://panel.example.com/ws (если проброшен порт 8765)
    — и live-канал (тикеты, статистика) оживёт и через домен.
    """
    return {'panel_ws_url': (os .environ .get ('PANEL_WS_URL','')or '').strip ()}


@app .context_processor
def inject_static_versions ():
    def static_v (filename ):
        try :
            return str (int (os .path .getmtime (os .path .join (
            os .path .dirname (os .path .abspath (__file__)),'static',filename ))))
        except OSError :
            return '1'
    return {'static_v':static_v }


# ── Индикатор сборки: коммит, который реально задеплоен ──────────────
_BUILD_COMMIT =None
try :
    _root =os .path .dirname (os .path .dirname (os .path .abspath (__file__)))
    with open (os .path .join (_root ,'.git','HEAD'),encoding ='utf-8') as _fh :
        _head =_fh .read ().strip ()
    if _head .startswith ('ref:'):
        _ref =_head .split (' ',1)[1].strip ()
        _path =os .path .join (_root ,'.git',*_ref .split ('/'))
        with open (_path ,encoding ='utf-8') as _fh :
            _BUILD_COMMIT =_fh .read ().strip ()[:7]
    else :
        _BUILD_COMMIT =_head [:7]
except Exception :
    _BUILD_COMMIT =None

@app .context_processor
def inject_build_commit ():
    return {'build_commit':_BUILD_COMMIT or ''}


@app .before_request 
def before_request ():
    # Замер длительности запроса: медленные видны в логе сразу, с путём и
    # временем. Без этого «панель тормозит» невозможно разобрать по фактам.
    g ._req_started =_time .time ()
    # Демо-режим: автоматический вход владельцем без логина и пароля.
    # Авторизация при этом не удаляется — она просто не требуется, пока
    # поднят флаг DEMO_MODE=1.
    if _demo_mode ()and 'logged_in'not in session :
        session .permanent =True 
        session ['logged_in']=True 
        session ['username']='demo'
        session ['role']='owner'
        # демо-сервер 777 — тот же id, что отдаёт /api/guilds в демо
        session ['selected_guild']=str (MAIN_GUILD_ID or '777')
        session ['main_guild_id']=str (MAIN_GUILD_ID )if MAIN_GUILD_ID else ''
        session .modified =True 

    # Панель управляет ТОЛЬКО сервером из MAIN_GUILD_ID. Если бот состоит
    # в нескольких серверах, чужой ID в адресе (/api/guild/<id>/...) или в
    # ?guild_id=... не даёт доступа к данным другого сервера.
    if MAIN_GUILD_ID:
        _req_gid = (request .view_args or {}).get('guild_id') \
            or request .args .get ('guild_id')
        if _req_gid and str (_req_gid )!=str (MAIN_GUILD_ID ):
            if request .path .startswith ('/api/'):
                return jsonify ({
                'success':False ,
                'error':('Панель управляет сервером из MAIN_GUILD_ID. '
                         'Другие серверы бота недоступны.')}),404
            return redirect ('/?denied=' +quote_plus ('чужой сервер'))

    # CSRF-защита без токенов во всех шаблонах: запросы на запись (POST/PUT/
    # DELETE/PATCH) с чужим Origin/Referer отклоняются. Браузер всегда шлёт
    # Origin на cross-site POST, а панель же работает same-origin, поэтому
    # легитимные формы не страдают. Клиенты без Origin (curl/скрипты)
    # не блокируем — их и так не волнует содержимое cookie.
    if request .method in ('POST','PUT','DELETE','PATCH'):
        _src =request .headers .get ('Origin')or request .headers .get ('Referer')
        if _src :
            try :
                from urllib.parse import urlparse 
                _netloc =urlparse (_src ).netloc 
                if _netloc and _netloc !=request .host :
                    _log_panel_action ('CSRF_BLOCK',f'{request .path} origin={_netloc}')
                    return jsonify ({'success':False ,'error':'Запрос с другого origin запрещён'}),403 
            except Exception as _ex:
                _log.debug("before_request(): подавлено: %s", _ex)

    # Panel Log 
def _log_login (username ,role ,avatar ,discord_id ):
    """Запоминает пользователей, вошедших в панель."""
    try :
        os .makedirs ('data',exist_ok =True )
        f ='data/login_log.json'
        logs =_store .read_json (f ,default =[])
        if not isinstance (logs ,list ):
            logs =[]
            # Берём информацию о сервере от бота
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
        'timestamp':datetime.now(timezone.utc).isoformat ()
        })
        _store .atomic_write_json (f ,logs [-200 :])
        _store .invalidate_path (f )
    except Exception as _ex:
        _log.debug("_log_login(): подавлено: %s", _ex)

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
    except Exception as _ex:
        _log.debug("_clean_md_fields(): подавлено: %s", _ex)
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
        'timestamp':datetime.now(timezone.utc).isoformat (),
        'ts':int (_t .time ()),
        })
    except Exception as _ex:
        _log.debug("_log_panel_action(): подавлено: %s", _ex)

        # ETag: GET + JSON + whitelist path'lerde tarayici/bot уровеньsinde cache
_ETAG_PATHS =(
'/api/logs',
'/api/warnings',
'/api/login-log',
'/api/stats',
'/api/guilds',
)


# Порог «медленного» запроса в лог. SSE (/api/live) держится открытым
# всегда — его не измеряем, иначе лог будет состоять из него одного.
_SLOW_REQUEST_S = 1.0


@app .after_request 
def after_request (response ):
    try :
        _t0 =getattr (g ,'_req_started',None )
        if _t0 and request .path !='/api/live':
            _dt =_time .time ()-_t0
            if _dt >=_SLOW_REQUEST_S :
                _log .warning ('[SLOW] %s %s — %.2f с (статус %s)',
                               request .method ,request .path ,_dt ,response .status_code )
    except Exception as _ex :
        _log .debug ('after_request(): замер времени подавлен: %s',_ex )
    # HSTS за туннелем: браузер запоминает, что домен — только https.
    try :
        if _behind_proxy ()and request .headers .get ('X-Forwarded-Proto','')=='https':
            response .headers .setdefault ('Strict-Transport-Security','max-age=31536000; includeSubDomains')
    except Exception as _ex :
        _log .debug ("after_request(): HSTS подавлен: %s",_ex )
    # «Бот офлайн» из ~40 эндпоинтов подменяем на человеческую подсказку —
    # сухое «Ошибка: Бот офлайн» в тосте владелец читает как «кнопки сломаны».
    # Меняем ТОЛЬКО голый литерал (хвост-варианты вида «Бот офлайн — ...» не трогаем).
    try :
        if response .is_json :
            _d =response .get_json (silent =True )
            if isinstance (_d ,dict )and _d .get ('error')=='Бот офлайн':
                # Бот может быть ЖИВ, но панель запущена отдельным процессом
                # (start_panel + start_bot / gunicorn / VDS): действие требует
                # бота в этом процессе. Это не «бот выключен» — объясняем точно.
                _remote_alive =False
                if bot_instance is None :
                    try :
                        from services import bot_bridge as _bb
                        _remote_alive =_bb .state_status ()=='online'
                    except Exception :
                        _remote_alive =False
                if _remote_alive :
                    _d ['error']=('Бот работает, но панель запущена отдельным '
                                  'процессом — действие выполняется только при '
                                  'запуске панели вместе с ботом (start.bat / start.sh)')
                else :
                    _d ['error']='Бот офлайн — запусти его через start.bat и попробуй ещё раз'
                response .set_data (json .dumps (_d ,ensure_ascii =False ))
    except Exception as _ex:
        _log .debug ("after_request(): офлайн-подсказка подавлена: %s",_ex )
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
        response .headers ['Cache-Control']='no-cache, no-store, must-revalidate'

        # Базовые защитные заголовки на каждый ответ
    response .headers ['X-Content-Type-Options']='nosniff'
    if not response .headers .get ('X-Frame-Options'):
        response .headers ['X-Frame-Options']='SAMEORIGIN'
    response .headers ['Referrer-Policy']='strict-origin-when-cross-origin'

        # CSP: Cloudflare или прокси иногда добавляют слишком строгий CSP; своим
        # заголовком разрешаем 'unsafe-eval' и 'unsafe-inline'.
        # Это админ-панель (доверенные пользователи), поэтому inline JS/eval допустим.
        # Все скрипты/стили/шрифты вендорены локально → 'self', внешние домены
        # остались только для Discord-аватарок (img-src https:) и API/WS (connect-src).
    # За прокси (бой) — строгая политика: connect-src только 'self' плюс wss:
    # live-канал живёт на отдельном порту, а другой порт — это другой origin,
    # поэтому 'self' его не покрывает. Внешних fetch с фронта нет (все идут на
    # /api/...), так что голые схемы https:/http:/ws: из политики убраны —
    # internet.nl отдельно ругается на «'http:' scheme» и на «'https:' without
    # a specific main domain». Локально live-канал идёт по ws: — там они нужны.
    _strict =_behind_proxy ()
    _connect =("'self' wss:" if _strict else "'self' https: wss: ws: http:")
    _img =("'self' data: https://*.discordapp.com https://*.discordapp.net "
           "https://discord.com" if _strict else "'self' data: https:")
    if not response .headers .get ('Content-Security-Policy'):
        csp =(
        "default-src 'self'; "
        # Cloudflare Web Analytics подставляет beacon.min.js со своего
        # домена — без него в консоли ошибка CSP, а статистика не собирается.
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src " +_img +"; "
        "connect-src " +_connect +"; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'"
        )
        response .headers ['Content-Security-Policy']=csp 

    # Discord Embedded App (Activity): страница музыкальной панели открывается
    # внутри клиента Discord (iframe), поэтому разрешаем Discord встраивать её.
    # X-Frame-Options убираем (он не умеет списка доменов), управление — через
    # frame-ancestors. Для всего остального правила прежние.
    if request .path .startswith ('/static/activity/'):
        response .headers .pop ('X-Frame-Options',None )
        response .headers ['Content-Security-Policy']=(
        "default-src 'self'; "
        # Cloudflare Web Analytics подставляет beacon.min.js со своего
        # домена — без него в консоли ошибка CSP, а статистика не собирается.
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src " +_img +"; "
        "connect-src " +_connect +"; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors https://discord.com https://*.discord.com https://discordapp.com"
        )

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
    except Exception as _ex:
        _log.debug("_handle_unexpected_error(): подавлено: %s", _ex)
    return ("Internal Сервер Error",500 )

    # Фиксированный ID сервера — используется первый найденный ботом сервер; меняется в панели
def _norm_guild_id(raw):
    """ID сервера из .env → чистые цифры.

    Хозяева вставляют значение с пробелами/кавычками/комментарием
    ('123 ', '\"123\"', '123 # мой сервер'): сравнение гейта
    /api/guild/<id> шло против грязной строки, и панель отвечала
    404 «Другие серверы бота недоступны» на все живые API. config.py
    бота чистит ID числом давно (clean_number) — панель делает то же.
    """
    return ''.join(
        ch for ch in str(raw or '') if '0' <= ch <= '9')


MAIN_GUILD_ID = _norm_guild_id(os.getenv('MAIN_GUILD_ID', ''))  # задаётся в .env; без него контекст берёт первый сервер бота


def _panel_guild ():
    """Сервер, которым управляет панель.

    При заданном MAIN_GUILD_ID — строго он (бот может состоять в нескольких
    серверах, но вход/подсказки/регистрация имеют смысл только для людей
    основного сервера). Без MAIN_GUILD_ID (панель ещё не настроена) берём
    первый сервер бота. Возвращает discord.Guild или None.
    """
    if not bot_instance :
        return None
    if MAIN_GUILD_ID :
        try :
            g =bot_instance .get_guild (int (MAIN_GUILD_ID ))
        except (TypeError ,ValueError ):
            g =None
        return g
    try :
        return bot_instance .guilds [0 ]if bot_instance .guilds else None
    except Exception :
        return None


def _is_bot_owner (discord_id )->bool :
    """ID входит в список владельцев бота (OWNER_ID/OWNER_IDS из .env)?"""
    try :
        owners =_root_config .Config .all_owner_ids ()
        return bool (owners )and int (discord_id )in owners
    except Exception :
        return False


def _main_guild_id_str ():
    """ID основного сервера строкой (MAIN_GUILD_ID, иначе первый сервер бота)."""
    if MAIN_GUILD_ID :
        return str (MAIN_GUILD_ID )
    try :
        if bot_instance and bot_instance .guilds :
            return str (bot_instance .guilds [0 ].id )
    except Exception as _ex :
        _log .debug ("_main_guild_id_str(): %s", _ex )
    return ''


def _record_on_main_guild (record ):
    """Запись {..., 'guild_id': ...} относится к основному серверу?

    Если сервер в записи неизвестен (None/'' — старые данные до привязки),
    считаем её своей, чтобы не прятать легитимные записи на единственном
    сервере. Чужие guild_id отсекаются.
    """
    gid =str ((record or {}).get ('guild_id')or '').strip ()
    main =_main_guild_id_str ()
    if not gid :
        return True
    if not main :
        return True
    return gid ==main

# Роли панели (от низшей к высшей). Куратор — старший модератор:
# видит всё модерское + тикеты/сообщество, настраивается владельцем
# так же, как модератор и администратор (доступ к меню, маппинг ролей).
ROLES ={
'uye':0 ,
'mod':1 ,
'curator':2 ,
'admin':3 ,
'owner':4 
}

# Русские названия ролей — для шапки панели, логов и ИИ-помощника.
ROLE_LABELS ={
'uye':'Участник',
'mod':'Модератор',
'curator':'Куратор',
'admin':'Администратор',
'owner':'Владелец'
}


# ── Видимость уведомлений и ленты активности ──────────────────────────────
# Минимальная роль, которой видны колокольчик и лента, настраивается
# владельцем в панели «Панели и роли» (/panel-access). По умолчанию —
# только персонал (mod+): участники не видят штабных уведомлений.
_PANEL_VIS_PATH ='data/panel_visibility.json'

def _panel_visibility ():
    try :
        v =_store .cached_read_json (_PANEL_VIS_PATH ,ttl =10.0 ,default ={})
        return v if isinstance (v ,dict )else {}
    except Exception :
        return {}

def _vis_allowed (kind ):
    v =_panel_visibility ()
    min_role =str (v .get (kind )or 'mod').strip ()
    if min_role not in ROLES :
        min_role ='mod'
    role =str (session .get ('role','uye')or 'uye')
    return ROLES .get (role ,-1 )>=ROLES .get (min_role ,1 )

@app .context_processor
def inject_visibility ():
    return {
    'vis_notifications':_vis_allowed ('notifications_min_role'),
    'vis_activity':_vis_allowed ('activity_min_role'),
    'role_label':ROLE_LABELS .get (session .get ('role','uye'),'Участник'),
    }

# Учётные данные владельца панели — приоритет:
#  1) data/panel_credentials.json (сменённый через панель, постоянный)
#  2) .env: PANEL_USER / PANEL_PASSWORD
#  3) Автогенерация надёжного случайного пароля (раньше был небезопасный "123")
_OWNER_CRED_PATH ='data/panel_credentials.json'

# ── Хэширование паролей ─────────────────────────────────────────────────────
# НОВОЕ: солёный scrypt (werkzeug) вместо голого SHA-256. SHA-256 без соли
# уязвим к rainbow-таблицам в случае утечки members.json. Старые хэши
# (sha256 и даже plaintext) по-прежнему ПРИНИМАЮТСЯ на входе, но при первом
# успешном логине прозрачно апгрейдятся до scrypt — миграция без боли.
from werkzeug.security import generate_password_hash as _wz_gen, check_password_hash as _wz_check  # noqa: E402

def _sha256_legacy (pw ):
    """Старый формат: sha256 без соли — только для проверки старых записей."""
    return hashlib .sha256 (str (pw ).encode ('utf-8')).hexdigest ()

def _hash_pw (pw ):
    """Новый формат: scrypt с солью (werkzeug). Каждый вызов даёт новый
    хэш (случайная соль) — сравнивать ТОЛЬКО через _pw_matches.
    Если scrypt недоступен (редкие лимиты OpenSSL) — pbkdf2-sha256:600k."""
    try :
        return _wz_gen (str (pw ))
    except Exception :
        return _wz_gen (str (pw ),method ='pbkdf2:sha256:600000')

def _pw_is_hash (value ):
    """64 hex karakterlik sha256 hash mi?"""
    return isinstance (value ,str )and len (value )==64 and all (c in '0123456789abcdef'for c in value )

def _pw_is_strong (value ):
    """Современный солёный хэш werkzeug (scrypt:/pbkdf2:)?"""
    return isinstance (value ,str )and value .startswith (('scrypt:','pbkdf2:'))

def _read_owner_record ():
    """Вся запись владельца (не только пароль): user, password_hash и т.д."""
    try :
        rec =_store .read_json (_OWNER_CRED_PATH ,default ={})
        return rec if isinstance (rec ,dict )else {}
    except Exception :
        return {}

def _pw_matches (stored ,plain ):
    """Проверка пароля: новые солёные хэши + старые sha256 + древний plaintext.

    Пароль '' (пустой, у импортированных записей) никогда не пускает.
    """
    stored =(stored or '')
    if not plain :
        return False 
    if _pw_is_strong (stored ):
        try :
            return _wz_check (stored ,str (plain ))
        except Exception :
            return False 
    if _pw_is_hash (stored ):
        return stored ==_sha256_legacy (plain )
    return stored ==plain 

# Поля-реликты удалённых механик (форс-смена пароля, TOTP 2FA) — при первом
# же старте стираем их из сохранённой записи, чтобы файл не тащил хвосты.
_OWNER_RECORD_LEGACY_KEYS =('must_change_password','totp_secret')

def _load_owner_credentials ():
    user =(os .environ .get ('PANEL_USER','owner')or 'owner').strip ()or 'owner'
    # Демо-режим: пароль ВСЕГДА из env. Файл panel_credentials.json мог остаться
    # от тестов или старого запуска со случайным паролем — тогда «Сменить пароль»
    # не принимал бы верный текущий пароль (env перекрывался файлом).
    if _demo_mode ():
        env_pw_d =(os .environ .get ('PANEL_PASSWORD','')or '').strip ()
        if env_pw_d :
            return user ,_hash_pw (env_pw_d )
    try :
        saved =_store .read_json (_OWNER_CRED_PATH ,default =None )
    except Exception :
        saved =None 
    if isinstance (saved ,dict )and saved .get ('user')==user and saved .get ('password_hash'):
        if any (k in saved for k in _OWNER_RECORD_LEGACY_KEYS ):
            for _k in _OWNER_RECORD_LEGACY_KEYS :
                saved .pop (_k ,None )
            try :
                _store .atomic_write_json (_OWNER_CRED_PATH ,saved )
                _store .invalidate_path (_OWNER_CRED_PATH )
            except Exception as _ex:
                _log.debug("_load_owner_credentials(): подавлено: %s", _ex)
        return user ,saved ['password_hash']
    env_pw =(os .environ .get ('PANEL_PASSWORD','')or '').strip ()
    if env_pw :
        return user ,_hash_pw (env_pw )
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
            f .write (f'Hakumo Panel — первый вход\nПользователь: {user}\nПароль: {gen}\n'
                      'Пароль можно сменить в панели (Профиль → Сменить пароль) '
                      'или задать PANEL_PASSWORD в .env\n')
        try :
            os .chmod ('data/panel_credentials.txt',0o600 )
        except OSError as _ex:
            _log.debug("_load_owner_credentials(): подавлено: %s", _ex)
    except Exception as _e :
        print (f'[БЕЗОПАСНОСТЬ] Не удалось сохранить сгенерированный пароль: {_e}')
    print ('='*70 )
    print ('[БЕЗОПАСНОСТЬ] PANEL_PASSWORD не задан — сгенерирован надёжный пароль:')
    print (f'[БЕЗОПАСНОСТЬ]   Пользователь: {user}')
    print (f'[БЕЗОПАСНОСТЬ]   Пароль: {gen}')
    print ('[БЕЗОПАСНОСТЬ] Он также записан в data/panel_credentials.txt')
    print ('[БЕЗОПАСНОСТЬ] Сменить пароль можно в любой момент: Профиль → Сменить пароль.')
    print ('='*70 )
    return user ,pw_hash 

_owner_user ,_owner_pw_hash =_load_owner_credentials ()

# Единственный зафиксированный пользователь-владелец
USERS ={
_owner_user :{'password_hash':_owner_pw_hash ,'role':'owner'},
}

# ── Смена пароля владельца (только по желанию, из панели) ──────────────────
def complete_owner_password_change (new_password ):
    """Смена пароля owner'а: свежий scrypt-хэш в json + USERS (работает без
    рестарта), txt-подсказка с протухшим сгенерированным паролем удаляется."""
    rec =_read_owner_record ()
    rec ['user']=_owner_user 
    rec ['password_hash']=_hash_pw (new_password )
    for _k in _OWNER_RECORD_LEGACY_KEYS :
        rec .pop (_k ,None )
    _store .atomic_write_json (_OWNER_CRED_PATH ,rec )
    _store .invalidate_path (_OWNER_CRED_PATH )
    USERS [_owner_user ]['password_hash']=rec ['password_hash']
    try :
        if os .path .exists ('data/panel_credentials.txt'):
            os .remove ('data/panel_credentials.txt')
    except OSError as _e :
        _log .debug ('complete_owner_password_change: txt cleanup: %s',_e )
    return True 

# Примечание: _pw_is_hash / _pw_matches / _hash_pw определены выше,
# рядом с загрузкой учётных данных (см. блок «Хэширование паролей»).

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
    except Exception:
        DISCORD_ROLE_MAP ={}

def _save_role_map ():
    try :
        os .makedirs ('data',exist_ok =True )
        _store .atomic_write_json (_ROLE_MAP_PATH ,DISCORD_ROLE_MAP )
        _store .invalidate_path (_ROLE_MAP_PATH )
    except Exception as _ex:
        _log.debug("_save_role_map(): подавлено: %s", _ex)

# Стартовые роли из config/role_seed.json — применяем ОДИН раз при старте
# панели (роли персонала и роль бана заданы до выкатки), затем грузим карту.
try:
    from services.role_seed import apply_role_seed as _apply_role_seed
    _seed_rep = _apply_role_seed()
    if _seed_rep.get('applied') and _seed_rep.get('role_map_added'):
        print(f"[РОЛИ] Применён стартовый сид ролей: {_seed_rep['role_map_added']}")
except Exception as _seed_ex:
    _log.debug("role_seed при старте панели: %s", _seed_ex)

_load_role_map ()

def _get_role_from_discord (discord_id :str )->str :
    """Opredelit роль в paneli по Discord-ролям ve администрации"""
    if not bot_instance :
        return 'uye'
    # 00. Владельцы БОТА (OWNER_ID + OWNER_IDS из .env) — всегда
    # владельцы панели, даже если сервер чужой: бот и панель
    # принадлежат тем, кто их запускает.
    try :
        from config import Config as _Cfg
        _owners =_Cfg .all_owner_ids ()
        if _owners and int (discord_id )in _owners :
            return 'owner'
    except Exception as _ex:
        _log.debug("web: подавлено: {_ex}", _ex)
        pass
    try :
        gid =MAIN_GUILD_ID or (str (bot_instance .guilds [0 ].id )if bot_instance .guilds else None )
        if not gid :
            return 'uye'
        guild =bot_instance .get_guild (int (gid ))
        if not guild :
            return 'uye'
        member =_resolve_guild_member (guild ,int (discord_id ))
        if not member :
            return 'uye'

            # 0. Создатель сервера — всегда владелец панели. Без этого
            # ловили «я разрешил все, а прав нет»: Discord-админка даёт
            # панели лишь роль «администратор», а разделы «Доступ»
            # требуют именно владельца.
        if getattr (guild ,'owner_id',None )and int (discord_id )==int (guild .owner_id ):
            return 'owner'

            # 1. Ручное сопоставление из role_map.json
        best_mapped ='uye'
        for discord_role in member .roles :
            mapped =DISCORD_ROLE_MAP .get (str (discord_role .id ))
            if mapped =='owner':
                return 'owner'
            if mapped =='admin':
                best_mapped ='admin'
            elif mapped =='curator'and best_mapped not in ('admin','owner'):
                best_mapped ='curator'
            elif mapped =='mod'and best_mapped not in ('curator','admin','owner'):
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
            # Каждые 5 минут обновлять роль из Discord — ВСЕХ, включая
            # владельца: доступ обязан зависеть от живых ролей сервера, а
            # не от того, что когда-то записали в сессию или members.json.
        discord_id =session .get ('discord_id')
        if discord_id :
            import time as _t 
            last_check =session .get ('_role_checked',0 )
            # Бот офлайн — НЕ понижаем роль по живым данным Discord (иначе
            # пока бот перезапускается, админы панели падают до «Участника»)
            _bot_online =bool (bot_instance and getattr (bot_instance ,'guilds',None ))
            if _bot_online and _t .time ()-last_check >300 :# 5 минут
                live_role =_get_role_from_discord (discord_id )
                session ['_role_checked']=_t .time ()
                # Роли больше нет (человек вышел с сервера или роли сняли)
                # — сессию гасим: без роли в панели делать нечего.
                if live_role =='uye':
                    session .clear ()
                    if request .path .startswith ('/api/'):
                        return jsonify ({'success':False ,'error':'Доступ к панели потерян: на сервере нет роли модератора.'}),403
                    return redirect (url_for ('login'))
                session ['role']=live_role 
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
                    except Exception as _ex:
                        _log.debug("decorated_function(): подавлено: %s", _ex)
        return f (*args ,**kwargs )
    return decorated_function 

def role_required (min_role ):
    def decorator (f ):
        @wraps (f )
        def decorated_function (*args ,**kwargs ):
            if 'role'not in session :
                if request .path .startswith ('/api/'):
                    return jsonify ({'success':False ,'error':'Не авторизован'}),403
                return redirect (url_for ('login'))
            if ROLES .get (session ['role'],-1 )<ROLES .get (min_role ,999 ):
                need =ROLE_LABELS .get (min_role ,min_role )
                why ='Владелец панели — создатель сервера и владелец бота (OWNER_ID в .env); перезайдите в панель.'
                if request .path .startswith ('/api/'):
                    return jsonify ({'success':False ,
                    'error':f'Нужна роль «{need}» панели. {why}'}),403
                return redirect ('/?denied='+quote_plus (need ))
            return f (*args ,**kwargs)
        return decorated_function
    return decorator

@app .route ('/favicon.ico')
def favicon ():
    favicon_path =os .path .join (app .root_path ,'static','favicon.ico')
    if not os .path .exists (favicon_path ):
        return '',204 # No Content
    return send_from_directory (os .path .join (app .root_path ,'static'),
    'favicon.ico',mimetype ='image/vnd.microsoft.icon')

# security.txt (RFC 9116): internet.nl требует файл в /.well-known/security.txt
# с полями Contact и Expires. Без него исследователю, нашедшему уязвимость,
# некуда написать. Файл публичный — без @login_required.
# Контакт берётся из SECURITY_CONTACT в .env (почта вида mailto:you@example.com
# или страница с формой); по умолчанию — сам сайт, чтобы файл был валидным
# даже до настройки.
@app .route ('/.well-known/security.txt')
def security_txt ():
    import datetime as _dt
    contact =( _os .environ .get ('SECURITY_CONTACT','')or '').strip ()
    host =(request .host or 'hakumods.xyz')
    if not contact :
        contact ='https://'+host +'/'
    # Expires обязан быть в будущем и не дальше года — считаем от текущей даты,
    # иначе файл через год станет «протухшим» и проверка снова упадёт.
    expires =(_dt .datetime .now (_dt .timezone .utc )+_dt .timedelta (days =330 )
              ).strftime ('%Y-%m-%dT%H:%M:%S.000Z')
    body =(
    'Contact: '+contact +'\n'
    'Expires: '+expires +'\n'
    'Preferred-Languages: ru, en\n'
    'Canonical: https://'+host +'/.well-known/security.txt\n'
    )
    return Response (body ,mimetype ='text/plain',
                     headers ={'Cache-Control':'public, max-age=3600'})


@app .route ('/health')
def health_check ():
    """Health check endpoint для Docker и мониторинга"""
    try :
        global bot_instance 
        if bot_instance and bot_instance .is_ready ():
            lat_val = 0.0
            if bot_instance.latency is not None:
                try:
                    if math.isfinite(bot_instance.latency):
                        lat_val = round(bot_instance.latency * 1000, 2)
                except Exception:
                    lat_val = 0.0
            return jsonify ({
            'status':'healthy',
            'bot':'ready',
            'guilds':len (bot_instance .guilds ),
            'latency':lat_val ,
            'timestamp':datetime .now (timezone.utc).isoformat ()
            }),200 
        if _demo_mode ():
            # демо-режим: мониторинг видит здоровый сервис панели
            return jsonify ({
            'status':'healthy',
            'bot':'demo',
            'guilds':1 ,
            'latency':round (12 + (_time .time ()*10 %19 ),2 ),
            'timestamp':datetime .now (timezone.utc).isoformat ()
            }),200 
        # Панель отдельным процессом от бота: здоровье по пульсу бота
        # (data/bot_state.json) — мониторинг не врёт «degraded», когда бот жив.
        try :
            from services import bot_bridge as _bb
            _st =_bb .read_state ()
            if _bb .state_status (_st )=='online':
                return jsonify ({
                'status':'healthy',
                'bot':'ready',
                'guilds':len (_bb .guild_ids (_st )),
                'latency':_st .get ('latency_ms')or 0 ,
                'remote':True ,
                'timestamp':datetime .now (timezone.utc).isoformat ()
                }),200 
        except Exception as _hex :
            _log .debug ('health: remote bridge: %s',_hex )
        return jsonify ({
        'status':'degraded',
        'bot':'connecting',
        'timestamp':datetime .now (timezone.utc).isoformat ()
        }),503 
    except Exception as e :
        return jsonify ({
        'status':'error',
        'error':str (e ),
        'timestamp':datetime .now (timezone.utc).isoformat ()
        }),500 

@app .route ('/welcome')
def welcome_page ():
    """Публичная страница-визитка: доступна всегда, даже в демо-режиме с автовходом."""
    return render_template ('welcome.html')


@app .route ('/')
def index ():
    # Главная = дашборд. Цифры «Модерации сегодня» рендерятся сервером.
    from web .routes .dashboard import _today_mod_stats
    if 'logged_in'not in session :
        return render_template ('welcome.html')
    if session .get ('role')=='uye':
        return render_template ('member_dashboard.html',role =session .get ('role'),username =session .get ('username'))
    return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'),today_stats =_today_mod_stats ())

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
                    if _created .tzinfo is None :
                        _created =_created .replace (tzinfo =timezone .utc )
                    else :
                        _created =_created .astimezone (timezone .utc )
                    if (datetime .now (timezone .utc )-_created ).days >14 :
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
        # Сравнение через _pw_matches: хэш солёный (scrypt), == не подходит
        if username in USERS and _pw_matches (USERS [username ].get ('password_hash'),password ):
            session .permanent =True 
            session ['logged_in']=True 
            session ['username']=username 
            session ['role']=USERS [username ]['role']
            # Реальному входу тоже нужен выбранный сервер — раньше его
            # ставил только демо-логин, и страница уходила в редирект
            # вечно редиректили на выбор сервера.
            session ['selected_guild']=str (MAIN_GUILD_ID )if MAIN_GUILD_ID else None 
            session .modified =True 
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
                # Стало слабое хранилище пароля (plaintext или старый sha256)?
                # Молча апгрейдим до scrypt — пользователь ничего не замечает.
                if not _pw_is_strong (members [username ].get ('password')):
                    members [username ]['password']=_hash_pw (password )
                    with open (members_file ,'w',encoding ='utf-8')as f :
                        json .dump (members ,f ,indent =2 ,ensure_ascii =False )
                # БЕЗОПАСНОСТЬ: роль берём ТОЛЬКО живьём из Discord.
                # Раньше сохранённое role=='owner' в members.json
                # отменяло проверку Discord — и любой, кого однажды
                # записали владельцем, заходил в панель по паролю, даже
                # если его давно нет на сервере и ролей у него нет.
                live_role =_get_role_from_discord (discord_id )
                if live_role =='uye':
                    _throttle_failed_login (username )
                    return render_template (
                        'login.html',
                        error ='Пароль верный, но доступа к панели нет: '
                              'нужна роль модератора на сервере.')
                members [discord_id ]['role']=live_role 
                with open (members_file ,'w',encoding ='utf-8')as f :
                    json .dump (members ,f ,indent =2 ,ensure_ascii =False )
                session .permanent =True 
                session ['logged_in']=True 
                session ['username']=members [discord_id ]['display_name']
                session ['role']=live_role 
                session ['discord_id']=discord_id 
                # тот же выбранный сервер, что и у входа владельца
                session ['selected_guild']=str (MAIN_GUILD_ID )if MAIN_GUILD_ID else None 
                session .modified =True 
                _save_login_token (discord_id ,live_role )
                _log_login (
                members [discord_id ]['display_name'],
                live_role ,
                members [discord_id ].get ('avatar'),
                discord_id 
                )
                return redirect (url_for ('index'))

        _throttle_failed_login (username )
        return render_template ('login.html',error ='Неверное имя пользователя или пароль!')
    return render_template ('login.html')

    # Geчici проверка kodlarы {discord_id: {code, data}}
PENDING_VERIFICATIONS ={}

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
            'registered_at':datetime.now(timezone.utc).isoformat ()
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

            # Сначала ищем в кэше, если нет — тянем fetch_member через Discord API
        member_info =None 

        async def find_member ():
        # Ищем СТРОГО на основном сервере панели. Регистрация доступна только
        # его участникам; раньше перебирались все сервера и в конце дёргался
        # fetch_user — так доступ создавал себе человек не с нашего сервера.
            panel_guild =_panel_guild ()
            if panel_guild is None :
                return None
            try :
                m =await _resolve_guild_member_async (panel_guild ,int (discord_id ))
            except Exception as _ex:
                _log.debug("find_member(): подавлено: %s", _ex)
                m =None
            if m and not getattr (m ,'bot',False ):
                return {'display_name':m .display_name ,'name':str (m ),'avatar':str (m .display_avatar .url )}
            return None 

        import asyncio 
        member_info =asyncio .run_coroutine_threadsafe (find_member (),bot_instance .loop ).result (timeout =15 )

        if not member_info :
            return render_template ('register.html',error ='Этот Discord ID не найден на основном сервере. Регистрация доступна только его участникам — проверьте ID и что вы на сервере.',step =1 )

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
                title =" Hakumo Panel — Запись Проверка",
                color =0xc8922a ,
                timestamp =datetime.now(timezone.utc)
                )
                e .description =(
                "```ansi\n\u001b[1;33m ТРЕБУЕТСЯ ПРОВЕРКА КОДА \u001b[0m\n```\n"
                "\n\n"
                f"Привет **{member_info['display_name']}**! \n\n"
                "Чтобы зарегистрироваться в **Hakumo Panel**,\n"
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
                e .set_footer (text ="Hakumo Panel • Доверие Запись Система")
                await user .send (embed =e )
            except Exception as ex :
                print (f"DM не отправлено: {ex}")

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

@app .route ('/announcements')
@login_required 
def announcements ():
    # История объявлений: участнику — чистая лента, персоналу (mod+)
    # дополнительно статусы доставки в Discord и кнопка «Дослать».
    return render_template ('announcements.html',role =session .get ('role'),username =session .get ('username'),
    can_manage =(ROLES .get (session .get ('role'),-1 )>=ROLES .get ('mod',999 )))

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
    # Хранится только солёный scrypt-хэш — пароль в открытом виде не пишем
    'password':_hash_pw (password ),
    'display_name':display_name ,
    'name':name ,
    'avatar':avatar ,
    'registered_at':datetime.now(timezone.utc).isoformat ()
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
    my_apps =[a for a in apps .values ()
              if a .get ('user_id')==discord_id and _record_on_main_guild (a )]
    my_apps .sort (key =lambda x :x .get ('created_at',''),reverse =True )
    return jsonify (my_apps )

@app .route ('/api/my-notifications')
@login_required 
def api_my_notifications ():
    if not _vis_allowed ('notifications_min_role'):
        return jsonify ([])
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
    except Exception as _ex:
        _log.debug("api_my_notifications(): подавлено: %s", _ex)

    result .sort (key =lambda x :x .get ('created_at',''),reverse =True )
    return jsonify (result [:30 ])

# ── Объявления: хранилище и честная доставка в Discord ────────────────────
_ANN_FILE ='data/announcements.json'

def _new_announcement_id ():
    return 'ann-%d-%s'%(int (_time .time ()*1000 ),
    ''.join (random .choices (string .ascii_lowercase +string .digits ,k =4 )))

def _load_announcements ():
    """Читает ленту объявлений. Битый/не-список JSON — как пусто.
    Старые записи без id (до кнопки «Дослать») получают id один раз —
    иначе неудачную доставку из старой ленты уже не переадресовать."""
    if not os .path .exists (_ANN_FILE ):
        return []
    try :
        with open (_ANN_FILE ,'r',encoding ='utf-8')as f :
            data =json .load (f )
    except Exception as _ex :
        _log .debug ("_load_announcements(): битый файл, считаем пустым: %s",_ex )
        return []
    if not isinstance (data ,list ):
        return []
    if any (isinstance (a ,dict )and a .get ('channel_id')and not a .get ('id')for a in data ):
        seen ={str (a .get ('id'))for a in data if isinstance (a ,dict )and a .get ('id')}
        for a in data :
            if not (isinstance (a ,dict )and a .get ('channel_id')and not a .get ('id')):
                continue
            nid =_new_announcement_id ()
            while nid in seen :
                nid =_new_announcement_id ()
            seen .add (nid )
            a ['id']=nid
        _save_announcements (data )
        _log .debug ("_load_announcements(): старым записям выданы id (миграция «Дослать»)")
    return [a for a in data if isinstance (a ,dict )]

def _save_announcements (anns ):
    os .makedirs ('data',exist_ok =True )
    tmp =_ANN_FILE +'.tmp'
    with open (tmp ,'w',encoding ='utf-8')as f :
        json .dump (anns ,f ,indent =2 ,ensure_ascii =False )
    os .replace (tmp ,_ANN_FILE )
    # Живой пуш: лента объявлений изменилась — открытая страница /announcements
    # обновится сразу, без опроса по таймеру.
    try :
        from services .live_bus import publish_global
        publish_global ('announcements')
    except Exception as _live_ex :
        _log .debug ('_save_announcements live-push: %s',_live_ex )

def _deliver_announcement_embed (guild_id ,channel_id ,title ,message ,author ):
    """Отправляет эмбед объявления в канал и ЖДЁТ результата (а не в никуда).
    Возвращает (ok, error, channel_name)."""
    if not bot_instance :
        return False ,'Бот Discord не в сети',None
    try :
        guild =next ((g for g in bot_instance .guilds if str (g .id )==str (guild_id )),None )
        channel =guild .get_channel (int (channel_id ))if guild else None
        if not channel :
            return False ,'Канал не найден',None
        embed =discord .Embed (title =title ,description =message ,color =0xF2B33D ,
        timestamp =datetime .now (timezone .utc ))
        embed .set_footer (text =f"Объявление · {author}")

        async def _send_ann ():
            await channel .send (embed =embed )

        asyncio .run_coroutine_threadsafe (_send_ann (),bot_instance .loop ).result (timeout =10 )
        return True ,None ,getattr (channel ,'name',None )
    except Exception as e :
        return False ,str (e ),None

@app .route ('/api/announcements')
@login_required 
def api_announcements ():
    return jsonify (list (reversed (_load_announcements ())))

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
    'created_at':datetime.now(timezone.utc).isoformat (),
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
                embed .set_footer (text ="Hakumo Panel • Уведомление",icon_url =bot_instance .user .display_avatar .url )
                embed .timestamp =datetime.now(timezone.utc)
                await user .send (embed =embed )
            except Exception as e :
                print (f"DM не отправлено: {e}")
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
        return jsonify ({'error':'Недостаточно данных'})

    # Опциональная доставка в Discord-канал (объявление живёт не только в панели).
    # Доставку ждём честно: ошибка уйдёт в ответ, а не в никуда.
    guild_id =str (data .get ('guild_id')or '')
    channel_id =str (data .get ('channel_id')or '')
    delivered =False
    deliver_error =None
    channel_name =None
    if channel_id :
        delivered ,deliver_error ,channel_name =_deliver_announcement_embed (
        guild_id ,channel_id ,title ,message ,session .get ('username','панель'))

    anns =_load_announcements ()
    anns .append ({
    'id':_new_announcement_id (),
    'title':title ,
    'message':message ,
    'from':session .get ('username'),
    'guild_id':guild_id or None ,
    'channel_id':channel_id or None ,
    'channel_name':channel_name ,
    'delivered':delivered ,
    'deliver_error':deliver_error ,
    'created_at':datetime.now(timezone.utc).isoformat ()
    })
    _save_announcements (anns )
    if not channel_id :
        text ='Объявление опубликовано в ленте панели'
    elif delivered :
        text ='Объявление опубликовано и доставлено в Discord'
    else :
        text =f'Опубликовано в ленте, но в Discord не ушло: {deliver_error}'
    return jsonify ({'success':True ,'delivered':delivered ,'deliver_error':deliver_error ,'message':text })

@app .route ('/api/announcements/retry',methods =['POST'])
@login_required 
def api_announcements_retry ():
    """«Дослать»: повторная доставка объявления, которое не дошло до Discord.
    Ошибка снова честно возвращается (нест-200) — API Guard сам покажет тост."""
    if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
        return jsonify ({'error':'Нет доступа'}),403
    data =request .get_json (silent =True )or {}
    ann_id =str (data .get ('id')or '').strip ()
    if not ann_id :
        return jsonify ({'error':'Не указан id объявления'}),400
    anns =_load_announcements ()
    rec =next ((a for a in anns if str (a .get ('id')or '')==ann_id ),None )
    if rec is None :
        return jsonify ({'error':'Объявление не найдено'}),404
    if not rec .get ('channel_id'):
        return jsonify ({'error':'Объявление публиковалось только в ленте панели — доставлять некуда'}),400
    if rec .get ('delivered'):
        return jsonify ({'error':'Объявление уже доставлено'}),400
    ok ,err ,ch_name =_deliver_announcement_embed (
    rec .get ('guild_id')or '',str (rec .get ('channel_id')),
    str (rec .get ('title','')),str (rec .get ('message','')),
    str (rec .get ('from')or session .get ('username','панель')))
    rec ['delivered']=ok
    rec ['deliver_error']=err
    if ch_name :
        rec ['channel_name']=ch_name
    if ok :
        rec ['redelivered_at']=datetime .now (timezone .utc ).isoformat ()
        rec ['redelivered_by']=session .get ('username')
    _save_announcements (anns )
    if not ok :
        return jsonify ({'delivered':False ,'error':f'Снова не ушло: {err}'}),502
    return jsonify ({'success':True ,'delivered':True ,
    'message':f'Доставлено в #{ch_name}'if ch_name else 'Доставлено в Discord'})

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

@app .route ('/logs/export')
@login_required 
@role_required ('mod')
def logs_export_download ():
    """Журнал модерации автономным HTML-файлом: /logs/export?days=7&category=&mod="""
    from services import log_export as _lx
    gid =request .args .get ('guild_id')or MAIN_GUILD_ID or (str (bot_instance .guilds [0 ].id )if bot_instance and bot_instance .guilds else '')
    days =request .args .get ('days','7')
    category =request .args .get ('category')or None
    mod =request .args .get ('mod')or None
    guild =None
    if bot_instance and gid :
        guild =bot_instance .get_guild (int (gid ))
    guild_name =guild .name if guild else 'Сервер'
    events =_lx .load_events (gid or 0 )
    filtered =_lx .filter_events (events ,days =days ,category =category ,mod =mod )
    parts =[f'период: {days} дн.']
    if category :parts .append (f'категория: {category}')
    if mod :parts .append (f'модератор: {mod}')
    html_doc =_lx .render_html (filtered ,guild_name =guild_name ,filters_desc =', '.join (parts ))
    headers ={
    'Content-Disposition':f'attachment; filename="{_lx.export_filename(guild_name)}"',
    'Cache-Control':'no-store',
    }
    return html_doc ,200 ,headers 

@app .route ('/warnings')
@login_required 
@role_required ('mod')
def warnings_page ():
    return render_template ('warnings.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/commands')
@login_required 
@role_required ('mod')
def commands_page ():
    return render_template ('commands.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/command-switches')
@login_required 
@role_required ('admin')
def command_switches_page ():
    """Ярлык из «Настройки»: та же страница «Команды» с тумблерами
    (рендерим на месте, не редирект — меню и аудит видят 200)."""
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

def _bot_connection_truth (bot ):
    """Правда о шлюзе бота: (status, presence).

    Жалоба 30.08.2026: «панель пишет, что данные отправляет, а бот офлайн».
    Причина: /api/stats всегда отвечал status='online', пока объект бота
    существует — даже с отвалившимся шлюзом. Теперь честно:
      online   — шлюз жив, бот готов;
      starting — объект есть, но готовности ещё нет (подключается);
      offline  — бота нет или шлюз закрыт.
    presence — чем бот ВЫГЛЯДИТ в Discord (online/idle/dnd/invisible):
    бот с presence=idle подключён, но кажется «не в сети».
    """
    if bot is None :
        return 'offline','offline'
    try :
        if bot .is_closed ():
            return 'offline',str (getattr (bot ,'status','offline')or 'offline')
    except AttributeError :
        _log .debug ("_bot_connection_truth(): стаб без is_closed — считаем живым")
    except Exception :
        return 'offline','offline'
    try :
        if not bot .is_ready ():
            return 'starting','offline'
    except AttributeError :
        _log .debug ("_bot_connection_truth(): стаб без is_ready — считаем готовым")
    except Exception :
        return 'starting','offline'
    return 'online',str (getattr (bot ,'status','online')or 'online')


# Короткий кэш сводки /api/stats: виджет пинга опрашивает её постоянно
# (и раньше — каждые 3 сек с КАЖДОЙ открытой вкладки), а подсчёт online
# перебирает всех участников всех серверов. 5 секунд свежести достаточно
# для индикатора; нагрузка на event-loop падает в разы. Ключ кэша включает
# идентичность объекта бота и правдивый статус соединения — при смене
# состояния (offline→starting→online) ответ не залипает.
_STATS_CACHE = {'key': None, 'ts': 0.0, 'payload': None}


@app .route ('/api/stats')
@login_required
def api_stats ():
    _truth_status = None
    if bot_instance :
        try :
            _truth_status ,_ =_bot_connection_truth (bot_instance )
        except Exception :
            _truth_status = None
    _cache_key =(id (bot_instance ),_truth_status )
    _cache_age =_time .time () -_STATS_CACHE .get ('ts',0.0 )
    if (_STATS_CACHE .get ('payload')is not None
            and _STATS_CACHE .get ('key')==_cache_key and _cache_age <5.0 ):
        return jsonify (_STATS_CACHE ['payload'])
    if not bot_instance :
        # демо: типичные счётчики (welcome и дашборд живые в превью)
        if _demo_mode ():
            return jsonify ({
            'guilds':1 ,
            'users':_demo_counts ()[0] ,
            'online':_demo_counts ()[1] ,
            'latency':round (12 + (_time .time ()*10 %19 ),2 ),
            'status':'online'
            })
        # Панель отдельным процессом от бота: правда — из пульса бота
        # (data/bot_state.json, services.bot_bridge). Раньше тут всегда был
        # «offline», хотя бот работал — шапка/дашборд/диагностика врали.
        try :
            from services import bot_bridge as _bb
            _st =_bb .read_state ()
            _st_status =_bb .state_status (_st )
            if _st_status in ('online','starting'):
                _guilds =_bb .guild_ids (_st )
                _users =0
                for _g in (_st .get ('guilds')or []):
                    try :
                        _users +=int (_g .get ('member_count')or 0 )
                    except Exception as _mcex :
                        _log .debug ('api_stats(): member_count: %s',_mcex )
                return jsonify ({
                'guilds':len (_guilds ),
                'users':_users ,
                # presences (сколько участников «в сети») из пульса не видны —
                # их знает только живой кэш бота; 0 честнее, чем выдумывать.
                'online':0 ,
                'latency':_st .get ('latency_ms')or 0 ,
                'status':_st_status ,
                'presence':'online' if _st_status =='online'else 'offline',
                'remote':True
                })
        except Exception as _sex :
            _log .debug ('api_stats(): remote bridge: %s',_sex )
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.',
        'status':'offline','presence':'offline'})

    guilds =len (bot_instance .guilds )
    # кэш гильдий может быть частичным (холодный старт, переподключение):
    # member_count/members не обязаны существовать в каждый момент
    users =sum (getattr (g ,'member_count',0 )or 0 for g in bot_instance .guilds )
    online =0
    for g in bot_instance .guilds :
        for m in (getattr (g ,'members',None )or []):
            try :
                if not m .bot and m .status !=discord .Status .offline :
                    online +=1
            except AttributeError :
                _log .debug ("api_stats(): член без статуса в кэше — пропущен")
    lat_val = 0.0
    if bot_instance.latency is not None:
        try:
            if math.isfinite(bot_instance.latency):
                lat_val = round(bot_instance.latency * 1000, 2)
        except Exception:
            lat_val = 0.0

    _status ,_presence =_bot_connection_truth (bot_instance )
    _payload = {
    'guilds':guilds ,
    'users':users ,
    'online':online ,
    'latency':lat_val ,
    'status':_status ,        # online | starting | offline — правда о шлюзе
    'presence':_presence      # чем бот выглядит в Discord (idle выглядит «не в сети»)
    }
    _STATS_CACHE ['key'] =(id (bot_instance ),_status )
    _STATS_CACHE ['ts'] =_time .time ()
    _STATS_CACHE ['payload'] =_payload
    return jsonify (_payload)

@app .route ('/api/guilds')
@login_required 
def api_guilds ():
    if not bot_instance :
        # Демо-режим: главный сервер с типичными числами.
        # Пустой список ломал выбор сервера на десятках страниц —
        # они обнуляли selectedGuild и переставали грузить что-либо.
        if _demo_mode ():
            return jsonify ([{
            # MAIN_GUILD_ID бывает пуст (панель до настройки .env) — тогда
            # дефолт 777, иначе селекторы получали сервер с id='' и ломались.
            'id':str (MAIN_GUILD_ID or '777'),
            'name':'Главный сервер',
            'members':_demo_counts ()[0] ,
            'icon':None ,
            'owner_id':'987430047889637426',
            'online':_demo_counts ()[1] ,
            'channels':_demo_counts ()[2] ,
            'roles':_demo_counts ()[3] ,
            'boost':7 ,
            }])
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

        # Панель показывает ТОЛЬКО главный сервер (MAIN_GUILD_ID): другие
        # серверы бота в селекторах не светятся, даже если бот на них есть
        if MAIN_GUILD_ID :
            guilds =[g for g in guilds if g ['id']==str (MAIN_GUILD_ID )]
            if not guilds :
                # бота нет на главном сервере — держим один пункт-заглушку,
                # чтобы селекторы не обнулялись (пустой список их ломал)
                guilds =[{
                'id':str (MAIN_GUILD_ID ),
                'name':'Главный сервер',
                'members':0 ,'icon':None ,'owner_id':'', 'online':0 ,
                'channels':0 ,'roles':0 ,'boost':0 ,
                }]

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
        return jsonify ({'error':'Требуется guild_id'}),400 
    if MAIN_GUILD_ID and str (guild_id )==str (MAIN_GUILD_ID ):
        return jsonify ({'error':'Это главный сервер панели (MAIN_GUILD_ID) — покинуть его нельзя.'}),400 
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
        member =_resolve_guild_member (guild ,member_id )
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
# Состав сервера — данные не публичные (ники, роли, даты входа, статусы).
# Раньше здесь была только авторизация: страница /users закрыта ролью admin,
# но любой залогиненный (включая низшую роль uye) забирал весь список
# запросом к API напрямую. Порог = mod, потому что этот же список читают
# /member-notes (mod) и /chat (owner); ниже mod — 403.
@role_required ('mod')
def api_guild_members (guild_id ):
    if not bot_instance :
        # демо-предпросмотр без бота: отдаём демо-участников —
        # иначе /users, заметки и наблюдение пустовали без видимой причины
        if _demo_mode ():
            try :
                from web .routes ._common import DEMO_MEMBERS
                return jsonify ([{
                'id':str (m .get ('id')),
                'name':str (m .get ('name')or m .get ('id')),
                'display_name':str (m .get ('display_name')or m .get ('name')or m .get ('id')),
                'discriminator':'0',
                'avatar':str (m .get ('avatar')or ''),
                'joined_at':m .get ('joined_at'),
                'created_at':None ,
                'roles':[{'name':str (r .get ('name')or ''),'color':str (r .get ('color')or 0)}for r in (m .get ('roles')or [])],
                'bot':False ,'status':m .get ('status','offline'),'nick':None ,
                'top_role':str ((m .get ('roles')or [{'name':''}])[0 ].get ('name')or '')if (m .get ('roles')or [])else None ,
                }for m in DEMO_MEMBERS ])
            except Exception as _ex :
                _log.debug("api_guild_members(): демо: %s", _ex )
        return jsonify ([])

    try :
        guild =None
        try :
            guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        except (TypeError ,ValueError ):
            guild =None

            # Пагинация: ?limit=1000 (по умолчанию), БЕЗ потолка.
        # Владелец растит сервер: 20 000 участников — это не предел, поэтому
        # искусственного обрыва списка нет вообще. Лимит ограничен только
        # реальным размером состава — сколько людей на сервере, столько и
        # отдадим одним запросом. Срез cached[offset:offset+limit] на
        # «безумный» limit не падает, Python просто отдаст остаток списка.
        try :
            limit =int (request .args .get ('limit',1000 ))
        except (TypeError ,ValueError ):
            limit =1000 
        try :
            offset =int (request .args .get ('offset',0 ))
        except (TypeError ,ValueError ):
            offset =0 
        limit =max (1 ,limit )
        offset =max (0 ,offset )

        # Состав участников живёт В ФАЙЛЕ (services/member_store.py): бот
        # сохраняет его и правит событийно (вошёл/вышел), поэтому панель
        # отдаёт список мгновенно и не выкачивает гильдию заново. Живой кэш
        # discord.py нужен только для статуса «в сети» здесь и сейчас.
        from services import member_store as MS
        store_total =MS .count (guild_id )
        live_members =list (getattr (guild ,'members',[])or [])if guild else []
        # Кэш 10 с — не пересобирать ПОЛНЫЙ список для каждой страницы:
        # ключ без offset/limit, иначе каждая пачка заново разворачивала бы
        # все 20 000 участников (O(n²) на пагинации).
        cache_key =('members',str (guild_id ),store_total ,len (live_members ))
        cached =_store ._cache .get (cache_key ,ttl =10.0 )
        if cached is None :
            if store_total :
                rows =MS .snapshot (guild_id )
                live_by_id ={str (m .id ):m for m in live_members }
                for row in rows :
                    lm =live_by_id .get (row ['id'])
                    if lm is not None :
                        row ['status']=str (getattr (lm ,'status','')or row .get ('status','offline'))
                cached =rows
            elif live_members :
                # Файл ещё не засеян (первый запуск) — берём живой кэш,
                # а member_sync сохранит состав в файл сразу после докачки.
                cached =[]
                for m in live_members :
                    created_at =discord .utils .snowflake_time (m .id )
                    cached .append ({
                    'id':str (m .id ),
                    'name':m .name ,
                    'display_name':m .display_name ,
                    'discriminator':m .discriminator ,
                    'avatar':str (m .display_avatar .url ),
                    'joined_at':m .joined_at .isoformat ()if m .joined_at else None ,
                    'created_at':created_at .replace (tzinfo =timezone .utc ).isoformat (),
                    'roles':[{'name':r .name ,'color':str (r .color )}for r in m .roles [1 :]],
                    'bot':m .bot ,
                    'status':str (m .status )if hasattr (m ,'status')else 'offline',
                    'nick':m .nick ,
                    'top_role':m .top_role .name if m .top_role else None ,
                    })
            else :
                cached =[]
            _store ._cache .set (cache_key ,cached ,ttl =10.0 )

            # Чтобы вернуть общее количество через метаданные пагинации, добавляем
            # заголовок X-Total-Count, который фронтенд может использовать при необходимости.
        total =len (cached )
        page =cached [offset :offset +limit ]
        resp =jsonify (page )
        resp .headers ['X-Total-Count']=str (total )
        resp .headers ['X-Limit']=str (limit )
        resp .headers ['X-Offset']=str (offset )
        # Сколько людей на сервере ПО ДИСКОРДУ и сколько бот уже держит в кэше.
        # На больших серверах кэш наполняется фоново (services/member_sync.py),
        # поэтому панель честно показывает «загружено N из M», а не выдаёт
        # частичный список за полный.
        # Сколько людей на сервере ПО ДИСКОРДУ и сколько мы реально отдаём.
        # Состав теперь живёт в файле (services/member_store.py), поэтому
        # список полный даже когда бот не в сети или кэш гильдии не наполнен.
        try :
            _gc =int (getattr (guild ,'member_count',0 )or 0 )
        except (TypeError ,ValueError ):
            _gc =0 
        if not _gc :
            _gc =store_total 
        resp .headers ['X-Guild-Count']=str (_gc )
        resp .headers ['X-Cached-Count']=str (total )
        resp .headers ['X-Stored-Count']=str (store_total )
        resp .headers ['X-Stored-At']=str (MS .saved_at (guild_id ))
        resp .headers ['X-Chunked']='1' if (getattr (guild ,'chunked',False )or store_total )else '0'
        return resp 
    except Exception as e :
        print (f"Ошибка списка участников: {e}")
        return jsonify ([])

def _ts_to_utc_iso (ts ):
    """Метку события → ISO со смещением (UTC).

    Продюсеры пишут UTC двумя способами: naive (logs.py:
    now(timezone.utc).replace(tzinfo=None)) и aware ('+00:00'). Браузер
    naive-строку читает как ЛОКАЛЬНОЕ время — свежему событию накидывался
    сдвиг на размер пояса (у владельца +4 часа). Наивное трактуем как UTC.
    """
    s =(ts or '').strip ()
    if not s :
        return ''
    try :
        dt =datetime .fromisoformat (s .replace ('Z','+00:00'))
    except (ValueError ,TypeError ):
        return s 
    if dt .tzinfo is None :
        dt =dt .replace (tzinfo =timezone .utc )
    return dt .astimezone (timezone .utc ).isoformat ()

def _ts_sort_key (ev ):
    """Ключ сортировки по мгновению: непарсящиеся метки — в самый низ.

    Метки приводим к aware-UTC: в данных бывают и naive, и aware строки,
    их сравнение иначе роняет сортировку (TypeError).
    """
    try :
        dt =datetime .fromisoformat (ev .get ('timestamp')or '')
    except (ValueError ,TypeError ):
        return datetime .min .replace (tzinfo =timezone .utc )
    if dt .tzinfo is None :
        dt =dt .replace (tzinfo =timezone .utc )
    else :
        dt =dt .astimezone (timezone .utc )
    return dt 

def _epoch_from_ts (value ):
    """ISO-метка → epoch-секунды. Naive считаем UTC (так пишут все наши хранилища) —
    иначе .timestamp() трактует её как локальное время и лента событий «уезжает»
    на величину пояса сервера. Мусор → 0.
    """
    s =(str (value or '')).strip ()
    if not s :
        return 0 
    try :
        dt =datetime .fromisoformat (s .replace ('Z','+00:00'))
    except (ValueError ,TypeError ):
        return 0 
    if dt .tzinfo is None :
        dt =dt .replace (tzinfo =timezone .utc )
    return int (dt .timestamp ())

def _guild_name_map (gid ):
    """uid → имя: общий резолвер из _common (файл имён → демо → кэш бота)."""
    try :
        from web .routes ._common import name_map_for
        return name_map_for (gid ,bot_instance )
    except Exception as _ex :
        _log.debug("_guild_name_map(%s): подавлено: %s", gid ,_ex )
        return {}

@app .route ('/api/logs')
@login_required 
@role_required ('mod')
def api_logs ():
    mod_file ='data/mod_data.json'
    all_events =[]
    filter_guild =request .args .get ('guild_id','')
    # Панель управляет одним сервером: при заданном MAIN_GUILD_ID журнал
    # всегда ограничен им — записи других серверов/демо-заглушек сюда не
    # попадают, даже если лежат рядом в файлах.
    if MAIN_GUILD_ID :
        filter_guild =str (MAIN_GUILD_ID )

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

        # Нормализуем метки к UTC со смещением — иначе браузер считает
        # naive-метку локальным временем и сдвигает на размер пояса (+4 ч).
        for _ev in all_events :
            _ev ['timestamp']=_ts_to_utc_iso (_ev .get ('timestamp'))
            _ev ['action']=human_action (_ev .get ('action'))
            _clean_md_fields (_ev )

        # Имена вместо ID: цель и модератор резолвятся из карты имён гильдии.
        _nm ={}
        for _ev in all_events :
            _gid =str (_ev .get ('guild_id')or '')
            if _gid and _gid not in _nm :
                _nm [_gid ]=_guild_name_map (_gid )
            _map =_nm .get (_gid )or {}
            _uid =str (_ev .get ('user_id')or '').strip ()
            _un =str (_ev .get ('user_name')or '').strip ()
            if _uid and (not _un or _un ==_uid or _un .isdigit ()):
                _ev ['user_name']=_map .get (_uid )or _uid
            _mid =str (_ev .get ('mod_id')or '').strip ()
            if _mid and not str (_ev .get ('mod_name')or '').strip ():
                _ev ['mod_name']=_map .get (_mid )or _mid
        all_events .sort (key =_ts_sort_key ,reverse =True )
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
        'timestamp':datetime.now(timezone.utc).isoformat ()
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
    # та же изоляция, что в /api/logs: варны — только главного сервера
    if MAIN_GUILD_ID :
        filter_guild =str (MAIN_GUILD_ID )

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
                            'timestamp':_ts_to_utc_iso (warn .get ('timestamp'))
                            })

        # Имена вместо ID: цель и модератор резолвятся через карту имён гильдии
        try :
            from web .routes ._common import name_map_for
            _wm ={}
            for _w in all_warnings :
                _g =str (_w .get ('guild_id')or '')
                if _g and _g not in _wm :
                    _wm [_g ]=name_map_for (_g )
                _map =_wm .get (_g )or {}
                _uid =str (_w .get ('user_id')or '')
                _w ['user_name']=_map .get (_uid )or _uid
                _mod =str (_w .get ('moderator')or '').strip ()
                if _mod and _mod .isdigit ():
                    _w ['moderator']=_map .get (_mod )or _mod
        except Exception as _ex :
            print (f'[WARNINGS] Имена: {_ex }')
        all_warnings .sort (key =_ts_sort_key ,reverse =True )
        return jsonify (all_warnings [:200 ])
    except Exception as e :
        print (f"Ошибка предупреждений: {e}")
        return jsonify ([])

@app .route ('/api/user/<int:user_id>')
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
    except Exception:
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
        member =_resolve_guild_member (guild ,user_id )
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
    'timestamp':datetime.now(timezone.utc).isoformat ()
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
    # Без MAIN_GUILD_ID в .env страница не должна быть мёртвой — берём
    # первый сервер бота (как делают остальные страницы панели).
    _gid =MAIN_GUILD_ID or (str (bot_instance .guilds [0 ].id )if bot_instance and bot_instance .guilds else '')
    return render_template ('send_command.html',
    role =session .get ('role'),
    username =session .get ('username'),
    main_guild_id =_gid )

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
                member =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
                if not guild .me .guild_permissions .kick_members :
                    raise Exception ('У бота нет права Kick')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Роль целевого пользователя выше роли бота')
                await member .kick (reason =data .get ('reason','Кик через веб-панель'))
            elif command =='timeout':
                member =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
                if not member :
                    raise Exception ('Участник не найден на сервере')
                if not guild .me .guild_permissions .moderate_members :
                    raise Exception ('У бота нет права Mute (Moderate Members)')
                if member .top_role >=guild .me .top_role :
                    raise Exception ('Роль целевого пользователя выше роли бота')
                duration =int (data .get ('duration',60 ))
                from datetime import timedelta as _td 
                await member .timeout (datetime.now(timezone.utc)+_td (minutes =duration ),reason =data .get ('reason'))
            elif command =='warn':
                warns_file ='data/warnings.json'
                # Доказательство (ссылка на сообщение/скрин) — в канал
                # доказательств и в панель: как у варнов из Discord-приложения.
                _proof_link =(str (data .get ('proof')or '')).strip ()
                if _proof_link :
                    try :
                        from cogs .proof_cog import try_deliver_proof as _tdp
                        class _PanelMod :
                            id =0
                            def __str__ (self ):
                                return f"{session .get ('username')} (панель)"
                            @property
                            def display_name (self ):
                                return str (self )
                        _pv =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
                        if _pv is None :
                            _pv =await bot_instance .fetch_user (int (data .get ('user_id')))
                        await _tdp (bot_instance ,guild ,_PanelMod (),_pv ,'варн',
                        data .get ('reason','Предупреждение через веб-панель'),link =_proof_link )
                    except Exception as _pex :
                        _log .debug ("warn proof: подавлено: %s",_pex )

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
                'timestamp':datetime.now(timezone.utc).isoformat ()
                })
                with open (warns_file ,'w',encoding ='utf-8')as wf :
                    json .dump (warns ,wf ,ensure_ascii =False )
                _store .invalidate_path (warns_file )
                _warn_db_append (gid_str ,uid_str ,data .get ('reason','Предупреждение через веб-панель'),session .get ('username'))
                # Уведомление персонала по настроенным каналам (веб/Discord/email)
                _panel_notify ('warn',f"Предупреждение выдано (ID {uid_str })",
                f"Модератор: {session .get ('username')} · Причина: {data .get ('reason','Предупреждение через веб-панель')}")
                # Отправить DM о предупреждении
                member =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
                if member :
                    dm_file =f'data/warn_dm_{guild.id}.json'
                    dm_msg =None 
                    if os .path .exists (dm_file ):
                        with open (dm_file ,'r',encoding ='utf-8')as df :
                            dm_cfg =json .load (df )
                        dm_msg =dm_cfg .get ('message')
                    if dm_msg :
                        dm_msg =dm_msg .replace ('{user}',member .display_name )
                        dm_msg =dm_msg .replace ('{reason}',data .get ('reason','Не указана'))
                        dm_msg =dm_msg .replace ('{mod}',session .get ('username','?'))
                        dm_msg =dm_msg .replace ('{сервер}',guild .name )
                        try :
                            e_dm =discord .Embed (title =' Вы получили предупреждение',description =dm_msg ,color =0xc8922a )
                            e_dm .set_footer (text =guild .name )
                            await member .send (embed =e_dm )
                        except Exception as _ex:
                            _log.debug("execute(): подавлено: %s", _ex)
            elif command =='jail':
                member =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
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
                'timestamp':datetime.now(timezone.utc).isoformat ()
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
                except Exception as _ex:
                    _log.debug("execute(): подавлено: %s", _ex)
            elif command =='unjail':
                member =_resolve_guild_member_async (guild ,int (data .get ('user_id')))
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
                    except Exception as _ex:
                        _log.debug("execute(): подавлено: %s", _ex)
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
    message =(data .get ('message')or '').strip ()

    # Валидация до похода в Discord — честные ответы панели
    if not message :
        return jsonify ({'error':'Пустое сообщение'}),400
    if len (message )>2000 :
        return jsonify ({'error':'Сообщение длиннее 2000 символов — Discord такое не примет. Сократите или разбейте на части.'}),400

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
        # Ждём РЕАЛЬНОГО результата доставки: если Discord отказал
        # (нет прав, упал канал) — ошибка уйдёт в панель, а не в никуда.
        future =asyncio .run_coroutine_threadsafe (send (),bot_instance .loop )
        future .result (timeout =10 )

        return jsonify ({'success':True ,'message':'Сообщение отправлено'})
    except Exception as e :
        print (f"Ошибка отправки сообщения: {e}")
        return jsonify ({'error':f'Не доставлено: {e}'})

@app .route ('/staff-apps')
@login_required 
@role_required ('mod')
def staff_apps_page ():
    return render_template ('staff_apps.html',role =session .get ('role'),username =session .get ('username'))

@app .route ('/api/staff-apps')
@login_required 
@role_required ('mod')
def api_staff_apps ():
    apps_file ='data/staff_apps.json'
    if not os .path .exists (apps_file ):
        return jsonify ([])
    with open (apps_file ,'r',encoding ='utf-8')as f :
        data =json .load (f )
    # Заявки показываем ТОЛЬКО с основного сервера (бот может состоять в
    # нескольких) — иначе в панель нового сервера попадают чужие заявки.
    apps =[a for a in data .values ()if _record_on_main_guild (a )]
    apps .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
    return jsonify (apps )

@app .route ('/api/staff-apps/<app_id>/review',methods =['POST'])
@login_required 
@role_required ('mod')
def api_review_staff_app (app_id ):
    apps_file ='data/staff_apps.json'
    if not os .path .exists (apps_file ):
        # Честный 404: заявки нет вовсе, а не «запрос прошёл, но ничего не вышло»
        return jsonify ({'error':'Файл заявок отсутствует'}),404
    with open (apps_file ,'r',encoding ='utf-8')as f :
        data =json .load (f )
    if app_id not in data :
        return jsonify ({'error':'Заявка не найдена'}),404
    if not _record_on_main_guild (data [app_id ]):
        return jsonify ({'error':'Эта заявка с другого сервера — здесь её рассматривать нельзя.'}),404
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
    dm_info ={'sent':None }
    if bot_instance :
        app_data =data [app_id ]
        async def send_dm ():
            try :
                if action =='approve':
                    # Роль по ДОЛЖНОСТИ заявки: Хелпер или Модератор
                    # (.env → data/staff_roles.json → имя роли на сервере)
                    try :
                        from services .staff_roles import grant_staff_role ,role_hint
                        gid =str (app_data .get ('guild_id')or MAIN_GUILD_ID or '')
                        guild =bot_instance .get_guild (int (gid ))if gid .isdigit ()else None
                        if not guild and bot_instance .guilds :guild =bot_instance .guilds [0 ]
                        res =await grant_staff_role (guild ,app_data .get ('user_id'),app_data .get ('role'))
                        role_info ['assigned']=res .get ('role_name')
                        role_info ['kind']=res .get ('kind')
                        if not res .get ('role_name'):
                            role_info ['error']=res .get ('reason')
                            role_info ['hint']=role_hint (res )
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
                        embed .add_field (name =" Заметка",value =note ,inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Hakumo Panel • Система заявок",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime.now(timezone.utc)
                else :
                    embed =discord .Embed (
                    title =" Заявка отклонена",
                    description ="К сожалению, ваша заявка в администрацию на этот раз не принята.\nВы можете подать её снова позже.",
                    color =0xe74c3c 
                    )
                    embed .add_field (name =" Рассмотрел",value =session .get ('username','?'),inline =True )
                    embed .add_field (name =" Заявка ID",value =f"`{app_id}`",inline =True )
                    embed .add_field (name =" Причина отказа",value =note if note else "Не указана",inline =False )
                    embed .set_thumbnail (url =bot_instance .user .display_avatar .url )
                    embed .set_footer (text ="Hakumo Panel • Система заявок",icon_url =bot_instance .user .display_avatar .url )
                    embed .timestamp =datetime.now(timezone.utc)
                await user .send (embed =embed )
                dm_info ['sent']=True
            except Exception as e :
                dm_info ['sent']=False
                print (f"DM отправка: {e}")
            # Отметить решение на сообщении заявки в Discord (снять кнопки)
            try :
                mid =app_data .get ('message_id')
                if mid :
                    from cogs .staff_apply import APPLY_CHANNEL_ID as _APPLY_CH
                    _gid =str (app_data .get ('guild_id')or MAIN_GUILD_ID or '')
                    _g2 =bot_instance .get_guild (int (_gid ))if _gid .isdigit ()else (bot_instance .guilds [0 ]if bot_instance .guilds else None )
                    _ch2 =_g2 .get_channel (_APPLY_CH )if _g2 else None
                    if _ch2 :
                        _msg =await _ch2 .fetch_message (int (mid ))
                        if _msg and _msg .embeds :
                            _e2 =discord .Embed .from_dict (_msg .embeds [0 ].to_dict ())
                            _e2 .color =0x2ECC71 if action =='approve' else 0xE74C3C
                            _e2 .add_field (
                            name =' Решение: одобрена' if action =='approve' else ' Решение: отклонена',
                            value =f"Модератор: {session.get('username', '?')}",
                            inline =False )
                            await _msg .edit (embed =_e2 ,view =None)
            except Exception as _ee :
                print (f"Отметка решения в Discord: {_ee}")
        try :
            asyncio .run_coroutine_threadsafe (send_dm (),bot_instance .loop ).result (timeout =15 )
        except Exception as _ex:
            _log.debug("api_review_staff_app(): подавлено: %s", _ex)

    resp ={'success':True }
    if dm_info ['sent'] is not None :
        resp ['dm_sent']=dm_info ['sent']
    if action =='approve':
        resp ['role_assigned']=role_info ['assigned']
        if role_info ['error']:
            resp ['role_note']=role_info .get ('hint')or role_info ['error']
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
    except Exception as _ex:
        _log.debug("api_tunnel_url(): подавлено: %s", _ex)
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
    tokens [existing ]={'username':username ,'role':roles ,'created_at':datetime.now(timezone.utc).isoformat ()}
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
    """Expose the visible sidebar menu for the current panel role.

    Также пробрасывает состояние режима модулей (cogs_policy):
    panel_mod_only — включён ли «MOD_ONLY», panel_off_paths — страницы,
    чьи коги выключены (приглушаются в меню с чипом «выкл»).
    """
    from services .panel_menu import (panel_groups_for, module_mode_active,
    module_off_paths)
    role =session .get ('role','uye')
    menu =panel_groups_for (role )if ROLES .get (role ,-1 )>=ROLES ['mod']else []
    off_paths =module_off_paths ()
    # бейджи пунктов меню: красный счётчик «Апелляции ждут решения»
    nav_badges ={}
    if ROLES .get (role ,-1 )>=ROLES ['mod']:
        try :
            from db import GuildData
            _gid =str (session .get ('selected_guild')or MAIN_GUILD_ID or '')
            _st =GuildData ('appeals').get (_gid ,'state',None )if _gid else None
            _n =sum (1 for i in (_st or {}).get ('items',[])
                    if i .get ('status')=='pending')
            if _n :
                nav_badges ['/appeals']=_n
        except Exception as _ex:
            _log.debug('inject_panel_menu badges: %s', _ex)
    return {'panel_menu':menu ,'panel_role':role ,
            'panel_mod_only':module_mode_active (),
            'panel_off_paths':off_paths,
            'nav_badges':nav_badges}

@app .route ('/api/panel/sidebar')
@login_required 
def api_panel_sidebar ():
    """Живой сайдбар: HTML меню для ЛЮБОЙ открытой страницы.

    Владелец поменял «Доступ»/видимость категорий — сайдбар на всех
    открытых страницах обновляется сам за 1.5с (base.html свапает
    фрагмент и переподвязывает поведение). path — реальная страница,
    чтобы подсветка активного пункта не съезжала."""
    from flask import render_template as _rt 
    active =request .args .get ('path')or request .path 
    return _rt ('_sidebar_nav.html',active_path =active )


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
            # Читаем всю запись и меняем только пароль — прочие поля записи
            # владельца остаются нетронутыми.
            rec =_read_owner_record ()
            rec ['user']=target 
            rec ['password_hash']=USERS [target ]['password_hash']
            _store .atomic_write_json (_OWNER_CRED_PATH ,rec )
            _store .invalidate_path (_OWNER_CRED_PATH )
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

def _resolve_guild_member (guild ,user_id ):
    """Участник сервера по ID: кэш, затем fetch_member (работает и без intents.members).

    get_member смотрит только в кэше; если у бота не включён intents.members,
    кэш почти пуст и реальный участник «не находится». Поэтому при промахе
    дотягиваем участника прямым API-запросом через loop бота.
    """
    uid =int (user_id )
    member =guild .get_member (uid )
    if member is not None :
        return member 
    try :
        future =asyncio .run_coroutine_threadsafe (guild .fetch_member (uid ),bot_instance .loop )
        member =future .result (timeout =10 )
    except Exception as _ex :
        _log.debug('_resolve_guild_member(%s): подавлено: %s', uid, _ex)
        member =None 
    return member 

async def _resolve_guild_member_async (guild ,user_id ):
    """Аналог _resolve_guild_member для вызова ВНУТРИ loop бота (прямой await).

    execute() крутится в loop: run_coroutine_threadsafe из него привёл бы к
    дедлоку, поэтому здесь обычный await fetch_member.
    """
    uid =int (user_id )
    member =guild .get_member (uid )
    if member is not None :
        return member 
    try :
        member =await guild .fetch_member (uid )
    except Exception as _ex :
        _log.debug('_resolve_guild_member_async(%s): подавлено: %s', uid, _ex)
        member =None 
    return member 

@app .route ('/apply')
def public_apply ():
    return render_template ('public_apply.html')

@app .route ('/api/public/check-member',methods =['POST'])
def api_check_member ():
    if not bot_instance :
    # Frontend'in 503 с kыrыlmamasы для 200 dёn.
    # Bot hazыr olana userya anlaшыlыr bir message показ.
        if _demo_mode ():
            # демо-предпросмотр без бота: принимаем любой валидный ID,
            # чтобы форму заявки можно было проверить целиком
            data =request .get_json (silent =True )or {}
            uid =str (data .get ('user_id','')).strip ()
            if not uid .isdigit ()or not (17 <=len (uid )<=20 ):
                return jsonify ({'found':False ,'error':'Введи корректный Discord ID (17–20 цифр).'})
            from web .routes ._common import DEMO_MEMBERS
            dm =next ((m for m in DEMO_MEMBERS if str (m .get ('id'))==uid ),None )
            name =str (dm .get ('display_name')or dm .get ('name')or f'Участник {uid }')if dm else f'Участник {uid }'
            return jsonify ({'found':True ,'id':uid ,'name':name ,'display_name':name ,'avatar':'/static/brand/emblem-dragon.png','joined_at':None })
        return jsonify ({
        'found':False ,
        'error':'Бот ещё не готов, повторите попытку через несколько секунд.'
        })
    data =request .get_json (silent =True )or {}
    guild_id =str (data .get ('guild_id',''))
    user_id =str (data .get ('user_id',''))
    if not guild_id or not user_id :
        return jsonify ({'error':'Недостаточно параметров'}),400 
    if not user_id .isdigit ()or not (17 <=len (user_id )<=20 ):
        return jsonify ({'found':False ,'error':'Введи корректный Discord ID (17–20 цифр).'})
    try :
        guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
        member =_resolve_guild_member (guild ,user_id )
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
        # демо: сервер для публичной анкеты (иначе «Сервер не найден»)
        if _demo_mode ():
            return jsonify ([{'id':str (MAIN_GUILD_ID or '777'),'name':'Главный сервер','icon':None ,'members':_demo_counts ()[0] }])
        return jsonify ([])
    guilds =[{'id':str (g .id ),'name':g .name ,
    'icon':str (g .icon .url )if g .icon else None ,
    'members':g .member_count }
    for g in bot_instance .guilds ]
    return jsonify (guilds )

@app .route ('/api/public/apply',methods =['POST'])
def api_public_apply ():
    data =request .get_json (silent =True )or {}
    # Принимаем ключи формы обеих версий: 'почему'/'why', 'активен'/'activity'
    if 'почему'not in data and data .get ('why'):
        data ['почему']=data ['why']
    if 'активен'not in data and data .get ('activity'):
        data ['активен']=data ['activity']
    data ['role']=str (data .get ('role')or 'Модератор').strip ()[:40 ]
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

    app_id =str (int (datetime.now(timezone.utc).timestamp ()))
    guild_id =str (data ['guild_id'])

    app_entry ={
    'app_id':app_id ,
    'user_id':uid ,
    'user_name':data ['discord_name'],
    'display_name':data ['discord_name'],
    'avatar':f"https://cdn.discordapp.com/embed/avatars/{int(uid) % 6}.png",
    'guild_id':guild_id ,
    'guild_name':data .get ('guild_name',''),
    'timestamp':datetime.now(timezone.utc).isoformat (),
    'status':'pending',
    'source':'web',
    'role':data ['role'],
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
                from cogs .staff_apply import apply_target ,StaffReviewView 
                guild =discord .utils .get (bot_instance .guilds ,id =int (guild_id ))
                if not guild :
                    return 
                channel ,ping =apply_target (data .get ('role'),guild )
                if not channel :
                    return 
                embed =discord .Embed (
                title =" НОВАЯ ЗАЯВКА В ПЕРСОНАЛ • Web",
                color =0xC8922A ,
                timestamp =datetime.now(timezone.utc)
                )
                embed .add_field (name =" Пользователь",value =f"`{data['discord_name']}` (ID: `{uid}`)",inline =True )
                embed .add_field (name =" Должность",value =data ['role'],inline =True )
                embed .add_field (name =" Возраст",value =data ['yas'],inline =True )
                embed .add_field (name =" Активность",value =data ['активен'],inline =True )
                embed .add_field (name =" Опыт",value =f"```{data['tecrube']}```",inline =False )
                embed .add_field (name =" Почему именно мы?",value =f"```{data['почему']}```",inline =False )
                if data .get ('ekstra'):
                    embed .add_field (name =" Дополнительно",value =f"```{data['ekstra']}```",inline =False )
                embed .set_footer (text =f"Заявка ID: {app_id} • {guild.name}")
                view =StaffReviewView ()
                msg =await channel .send (content =ping or None ,embed =embed ,view =view )
                apps [app_id ]['message_id']=str (msg .id )
                with open (apps_file ,'w',encoding ='utf-8')as f :
                    json .dump (apps ,f ,indent =2 ,ensure_ascii =False )
            except Exception as e :
                print (f"Ошибка отправки сообщения в Discord: {e}")
        import asyncio 
        asyncio .run_coroutine_threadsafe (send_to_discord (),bot_instance .loop )

    return jsonify ({'success':True ,'app_id':app_id ,
    'hint':'Решение придёт в личные сообщения бота. На сервере статус виден командой /my-application'})

from web .routes_extra import register_extra_routes 
register_extra_routes (app ,ROLES ,login_required ,role_required ,MAIN_GUILD_ID )

# Роли Map API
# Раздел «Доступ» опрашивается SSE-страницей постоянно: готовый ответ
# держим за короткий TTL и отдаём по ETag (304 без тела), а состав ролей
# кэшируем отдельно — на крупном сервере подсчёт r.members на каждую роль
# не повторяется на каждый опрос.
import threading as _threading_rm
import hashlib as _hashlib_rm
_ROLE_MAP_LOCK = _threading_rm.Lock()
_ROLE_MAP_CACHE = {'ts': 0.0, 'raw': None, 'etag': None}
_ROLE_MAP_ROLES = {'ts': 0.0, 'roles': None}
_ROLE_MAP_TTL = 5.0
_ROLE_MAP_ROLES_TTL = 30.0


def _role_map_guild_roles():
    """Список ролей сервера для маппинга (TTL-кэш, без вложенных блокировок)."""
    import time as _time
    now = _time.time()
    with _ROLE_MAP_LOCK:
        hit = _ROLE_MAP_ROLES
        if hit['roles'] is not None and now - hit['ts'] < _ROLE_MAP_ROLES_TTL:
            return list(hit['roles'])
    # промах кэша — собираем БЕЗ удержания лока (без вложенных блокировок)
    guild_roles = []
    if bot_instance:
        gid = MAIN_GUILD_ID or (str(bot_instance.guilds[0].id)
                                if bot_instance.guilds else None)
        if gid:
            guild = bot_instance.get_guild(int(gid))
            if guild:
                _rm_counts = role_member_counts(guild)
                for r in sorted(guild.roles, key=lambda x: x.position,
                                reverse=True):
                    if r.name == '@everyone':
                        continue
                    guild_roles.append({
                        'id': str(r.id),
                        'name': r.name,
                        'color': str(r.color),
                        'position': r.position,
                        # тем же одним проходом — см. role_member_counts
                        'members': _rm_counts.get(r.id, 0),
                    })
    elif _demo_mode():
        # демо-превью без бота: роли сервера из демо-набора —
        # страница «Панели и роли» живая и показывает маппинг,
        # включая роль Куратора (9013 → curator).
        try:
            from web.routes.guild_admin import _demo_roles_seed
            for r in _demo_roles_seed():
                guild_roles.append({
                    'id': str(r['id']),
                    'name': r['name'],
                    'color': r['color'],
                    'position': int(r['id']) if str(r['id']).isdigit() else 0,
                    'members': int(r.get('members') or 0),
                })
        except Exception as _ex:
            _log.debug("api_get_role_map(): демо: %s", _ex)
    with _ROLE_MAP_LOCK:
        _ROLE_MAP_ROLES['ts'] = now
        _ROLE_MAP_ROLES['roles'] = list(guild_roles)
    return guild_roles


def _role_map_payload():
    """Собрать {role_map, guild_roles}; роли — с TTL-кэшем."""
    guild_roles = _role_map_guild_roles()
    role_map = dict(DISCORD_ROLE_MAP)
    if _demo_mode() and not role_map:
        # дефолтный демо-маппинг, пока владелец не поменял через панель
        role_map = {'9001': 'owner', '9002': 'admin', '9003': 'mod', '9013': 'curator'}
    return {'role_map': role_map, 'guild_roles': guild_roles}


def _role_map_invalidate():
    with _ROLE_MAP_LOCK:
        _ROLE_MAP_CACHE.update({'ts': 0.0, 'raw': None, 'etag': None})
        _ROLE_MAP_ROLES.update({'ts': 0.0, 'roles': None})
    try:
        from services.live_bus import publish_global
        publish_global('role_map')
    except Exception as _ex:
        _log.debug("role_map SSE: %s", _ex)


@app.route('/api/role-map')
@login_required
@role_required('admin')
def api_get_role_map():
    """Получить сопоставление ролей + список ролей сервера."""
    import time as _time
    now = _time.time()
    with _ROLE_MAP_LOCK:
        hit = _ROLE_MAP_CACHE
        fresh = hit['raw'] is not None and now - hit['ts'] < _ROLE_MAP_TTL
    if fresh:
        raw, etag = hit['raw'], hit['etag']
    else:
        raw = json.dumps(_role_map_payload(), ensure_ascii=False,
                         separators=(',', ':'))
        etag = '"' + _hashlib_rm.md5(raw.encode('utf-8')).hexdigest() + '"'
        with _ROLE_MAP_LOCK:
            _ROLE_MAP_CACHE.update({'ts': now, 'raw': raw, 'etag': etag})
    if etag in request.headers.get('If-None-Match', ''):
        return Response(status=304,
                        headers={'ETag': etag, 'Cache-Control': 'no-cache'})
    return Response(raw, mimetype='application/json',
                    headers={'ETag': etag, 'Cache-Control': 'no-cache'})

def _role_map_notify ():
    """Пнуть открытые страницы по SSE после правки карты ролей.

    «Панели и роли» и «Права команд» подписаны на топик role_map, но его
    никто не публиковал — правка доезжала до соседней вкладки только по
    страховочному таймеру (30 с).
    """
    try :
        from services .live_bus import publish_global
        publish_global ('role_map')
    except Exception as _ex :
        _log .debug ("role_map SSE-сигнал не отправлен: %s",_ex )


@app .route ('/api/role-map',methods =['POST'])
@login_required 
@role_required ('admin')
def api_set_role_map ():
    """Добавить/изменить сопоставление роли.
    panel_role: 'uye' | 'mod' | 'curator' | 'admin' | 'owner'  (uye = снять сопоставление, авто-определение)
    """
    data =request .get_json (silent =True )or {}
    role_id =str (data .get ('role_id','')).strip ()
    panel_role =data .get ('panel_role','').strip ()
    if not role_id or panel_role not in ('mod','curator','admin','owner','uye'):
        return jsonify ({'error':'Неверные данные'}),400 
    if panel_role =='uye':
        DISCORD_ROLE_MAP .pop (role_id ,None )
    else :
        DISCORD_ROLE_MAP [role_id ]=panel_role
    _save_role_map ()
    _role_map_invalidate ()
    _role_map_notify ()
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
        _role_map_invalidate ()
        _role_map_notify ()
        _log_panel_action ('ROLE_MAP_DELETE',role_id )
    return jsonify ({'success':True })

# ── Panel menu visibility (sidebar categories & rooms per panel) ──
# ── Версия сборки панели ────────────────────────────────────────────────
# Заказ владельца: после обновления непонятно, применилось ли оно —
# ошибки из старой версии выглядели как «не починили». Номер коммита виден
# в сайдбаре и отдаётся здесь, чтобы сверять с ремоутом.
@app .route ('/api/build-info')
@login_required 
def api_build_info ():
    sha =_BUILD_INFO .get ('sha')or ''
    return jsonify ({'success':True ,'sha':sha ,'short':sha [:7 ],
                    'branch':_BUILD_INFO .get ('branch')or ''})


@app .route ('/api/panel-menu')
@login_required
@role_required ('owner')
def api_panel_menu_get ():
    """Return the full MENU + current visibility config for mod/admin panels."""
    from services .panel_menu import MENU ,get_config ,CONFIGURABLE ,layout_view
    cfg =get_config ()
    return jsonify ({
    'success':True ,
    'menu':MENU ,
    'config':cfg ,
    'configurable':list (CONFIGURABLE ),
    'layout':layout_view (),
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

@app .route ('/api/panel-menu/layout',methods =['POST'])
@login_required
@role_required ('owner')
def api_panel_menu_layout ():
    """Глобальный лэйаут меню: скрытые страницы + свой порядок внутри разделов.

    {hidden_pages: [...], order: {group_key: [path, ...]}} — применяется
    ко всем панелям (и к владельцу). /panel-menu скрыть нельзя.
    """
    from services .panel_menu import save_layout
    data =request .get_json (silent =True )or {}
    hp =data .get ('hidden_pages',[])
    od =data .get ('order',{})
    go =data .get ('group_order',[])
    if not isinstance (hp ,list )or not isinstance (od ,dict )or not isinstance (go ,list ):
        return jsonify ({'success':False ,'error':'Неверный формат'}),400
    view =save_layout (hp ,od ,go )
    _log_panel_action ('PANEL_MENU_LAYOUT',f'скрыто {len(view["hidden_pages"])}, порядок в {len(view["order"])} разделах')
    return jsonify ({'success':True ,'layout':view })

    # Discord PIN Login API 
_login_pins ={}

@app .route ('/api/login/suggest',methods =['GET','POST'])
def api_login_suggest ():
    query =(request .args .get ('q')or (request .get_json (silent =True )or {}).get ('q','')or '').strip ()
    query_clean =query .lstrip ('@').lower ()

    suggestions =[]
    seen_ids =set ()

    # 1. Участники ТОЛЬКО основного сервера панели (MAIN_GUILD_ID).
    # Раньше перебирались все сервера бота — в подсказках входа появлялись
    # люди с других серверов, где состоит бот (заказ: «убери их»).
    panel_guild =_panel_guild ()
    if panel_guild is not None :
        for m in panel_guild .members :
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

            # 2. Offline / supplemental check from members.json
    # 2. Офлайн-добор из members.json — но лишь тех, кто реально на главном
    # сервере (живой кэш бота), чтобы не подсказывать посторонних.
    if len (suggestions )<12 and os .path .exists ('data/members.json')and panel_guild is not None :
        try :
            with open ('data/members.json','r',encoding ='utf-8')as f :
                mdata =json .load (f )
            live_ids ={str (mm .id )for mm in panel_guild .members }
            for uid_str ,minfo in mdata .items ():
                if uid_str in seen_ids :continue
                if str (uid_str )not in live_ids :continue   # не на главном сервере — не показываем
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
        except Exception as _ex:
            _log.debug("api_login_suggest(): подавлено: %s", _ex)

            # 3. Демо-состав — ТОЛЬКО в режиме предпросмотра (DEMO_MODE=1 без
    # бота). В бою чужих людей в подсказках быть не может: нет данных —
    # выпадашка честно пустая (заказ владельца: «данные, которых я не добавлял»).
    if not suggestions and _demo_mode ():
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
    # Ищем СТРОГО на основном сервере панели. Люди с других серверов бота
    # в панель попасть не должны (заказ: «в войти появляются люди не с
    # основного сервера — убери их»).
    panel_guild =_panel_guild ()
    try :
        if query .isdigit ()and 17 <=len (query )<=19 :
            discord_id =query 
            if panel_guild is not None :
                try :
                    user =_resolve_guild_member (panel_guild ,discord_id )
                except Exception as _ex:
                    _log.debug("api_discord_check(): подавлено: %s", _ex)
                    user =None
            # Владелец бота (OWNER_ID) может ещё не состоять на сервере на
            # этапе настройки — ему вход разрешён: тянем профиль напрямую.
            if user is None and _is_bot_owner (discord_id ):
                try :
                    user =asyncio .run_coroutine_threadsafe (
                    bot_instance .fetch_user (int (discord_id )),bot_instance .loop ).result (timeout =10 )
                except Exception as _ex:
                    _log.debug("api_discord_check owner fetch: %s", _ex)
        else :
            uname =query .lstrip ('@').lower ()
            if panel_guild is not None :
                for m in panel_guild .members :
                    if m .name .lower ()==uname or m .display_name .lower ()==uname :
                        user =m 
                        discord_id =str (m .id )
                        break
        if not user or not discord_id :
            tests .append ({'name':'Поиск пользователя','status':'fail','detail':'Не найден на сервере'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Пользователь не найден на основном сервере. Вход в панель доступен только участникам этого сервера.'})
        member_info ={'display_name':getattr (user ,'display_name',str (user )),'name':str (user ),'avatar':str (user .display_avatar .url )if hasattr (user ,'display_avatar')else ''}
        tests .append ({'name':'Поиск пользователя','status':'ok','detail':member_info ['display_name']})
    except Exception as e :
        tests .append ({'name':'Поиск пользователя','status':'fail','detail':str (e )})
        return jsonify ({'success':False ,'tests':tests ,'error':str (e )})
    # Жёсткая проверка членства: пользователь должен быть участником
    # основного сервера. Единственное исключение — владелец бота (OWNER_ID),
    # он управляет панелью даже не находясь на сервере.
    try :
        in_guild =(panel_guild is not None and _resolve_guild_member (panel_guild ,int (discord_id ))is not None )
        is_owner =_is_bot_owner (discord_id )
        if in_guild :
            tests .append ({'name':'Участник сервера','status':'ok','detail':getattr (panel_guild ,'name','')})
        elif is_owner :
            tests .append ({'name':'Участник сервера','status':'ok','detail':'Владелец бота'})
        else :
            tests .append ({'name':'Участник сервера','status':'fail','detail':'Нет на основном сервере'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Вы не состоите на основном сервере панели. Доступ только для его участников.'})
    except Exception as _ex:
        _log.debug("api_discord_check membership: %s", _ex)
        tests .append ({'name':'Участник сервера','status':'fail','detail':'Ошибка проверки'})
        return jsonify ({'success':False ,'tests':tests ,'error':'Не удалось проверить членство на сервере. Попробуйте позже.'})
    try :
        is_bot =getattr (user ,'bot',False )
        if is_bot :
            tests .append ({'name':'Проверка на бота','status':'fail','detail':'Аккаунт бота'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Боты не могут авторизоваться.'})
        else :
            tests .append ({'name':'Проверка на бота','status':'ok','detail':'Пользователь'})
    except Exception:
        tests .append ({'name':'Проверка на бота','status':'warn','detail':'Ошибка проверки'})
    try :
        created =discord .utils .snowflake_time (int (discord_id ))
        age_days =(datetime.now(timezone.utc).replace(tzinfo=None)-created ).days 
        if age_days <7 :
            tests .append ({'name':'Возраст аккаунта','status':'fail','detail':f'{age_days} дн. (слишком новый)'})
            return jsonify ({'success':False ,'tests':tests ,'error':'Вход запрещен: аккаунт зарегистрирован менее 7 дней назад.'})
        else :
            tests .append ({'name':'Возраст аккаунта','status':'ok','detail':f'{age_days} дн.'})
    except Exception:
        tests .append ({'name':'Возраст аккаунта','status':'warn','detail':'Неизвестно'})
    try :
        code =''.join (random .choices (string .digits ,k =6 ))
        import time as _t 
        _login_pins [discord_id ]={'code':code ,'expires':_t .time ()+300 ,'member_info':member_info }
        async def send_pin ():
            u =await bot_instance .fetch_user (int (discord_id ))
            embed =discord .Embed (title ='Hakumo — Код авторизации',color =0xc8922a ,timestamp =datetime.now(timezone.utc))
            embed .description =f"Здравствуйте, **{member_info['display_name']}**!\n\nВаш PIN-код для входа в панель:\n\n```fix\n{code}\n```\nДействителен в течение 5 минут."
            embed .set_footer (text ="Hakumo Panel")
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
        members [discord_id ]={'display_name':member_info ['display_name'],'name':member_info ['name'],'avatar':member_info ['avatar'],'role':live_role ,'password':'','registered_at':datetime.now(timezone.utc).isoformat ()}
        with open (members_file ,'w',encoding ='utf-8')as f :
            json .dump (members ,f ,indent =2 ,ensure_ascii =False )
    # БЕЗОПАСНОСТЬ: роль берём ТОЛЬКО живьём из Discord. Раньше
    # сохранённое role=='owner' в members.json отменяло проверку — и
    # любой, кого однажды записали владельцем, входил по PIN, даже если
    # его давно нет на сервере и ролей у него нет.
    live_role =_get_role_from_discord (discord_id )
    if live_role =='uye':
        return jsonify ({'success':False ,'error':'PIN верный, но доступа к панели нет: нужна роль модератора на сервере.'})
    members [discord_id ]['role']=live_role 
    with open (members_file ,'w',encoding ='utf-8')as f :
        json .dump (members ,f ,indent =2 ,ensure_ascii =False )
    session .permanent =True 
    session ['logged_in']=True 
    session ['username']=member_info ['display_name']
    session ['role']=live_role 
    session ['discord_id']=discord_id 
    session .modified =True 
    _save_login_token (discord_id ,live_role )
    _log_login (member_info ['display_name'],live_role ,member_info ['avatar'],discord_id )
    return jsonify ({'success':True ,'redirect':'/'})


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
        except Exception:color =discord .Color (0xdc143c )
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
        if _demo_mode ():
            _log_panel_action ('BOT_RESTART',session .get ('username'))
            return jsonify ({'success':True ,'demo':True })
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
            except Exception as _ex:
                _log.debug("api_bot_diagnose(): подавлено: %s", _ex)
                # Latency check
            try :
                if bot_instance.latency is not None and math.isfinite(bot_instance.latency):
                    lat = bot_instance.latency * 1000 
                    if lat > 800:
                        issues.append(f'Высокий Discord latency: {round(lat, 0)}ms')
            except Exception as _ex:
                _log.debug("api_bot_diagnose(): подавлено: %s", _ex)
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

@app .route ('/api/bot/memory-profile',methods =['POST'])
@login_required
@role_required ('owner')
def api_bot_memory_profile ():
    """Профиль памяти: КУДА уходит RAM — кэш Discord или Python-объекты.

    Жалоба 30.08.2026: RSS 1649,8 МБ на «Статистике бота» при пороге
    критичности 900 МБ. Чтобы не гадать, считаем по полочкам: сколько
    участников/каналов/ролей держит шлюз, сколько живых объектов Python
    и какие типы их больше всего. GC до замера отделяет мусор от живого.
    """
    import gc
    from collections import Counter
    if not bot_instance and _demo_mode ():
        return jsonify ({
        'success':True ,'demo':True ,
        'rss_mb':412.6 ,'rss_after_gc_mb':401.8 ,'threads':18 ,
        'guilds':1 ,'members_cached':_demo_counts ()[0] ,'channels_cached':14 ,
        'roles_cached':9 ,'voice_clients':0 ,'cogs':24 ,'extensions':24 ,
        'objects_total':486311 ,
        'top_types':[['builtins.dict',94210],['builtins.instance_method',61884],
                     ['builtins.str',58472],['builtins.function',24106],
                     ['discord.user.User',8312],['builtins.set',6128],
                     ['builtins.list',5904],['builtins.tuple',5231],
                     ['builtins.type',2140],['builtins.weakref',1987]],
        'per_guild':[{'name':'Демо-сервер Hakumo','members':_demo_counts ()[0]}],
        'gc_generations':[{'collections':214,'collected':1894,'uncollectable':0},
                          {'collections':37,'collected':5421,'uncollectable':0},
                          {'collections':9,'collected':12837,'uncollectable':0}]
        })
    rss_before =0.0
    threads =0
    try :
        import psutil as _ps ,os as _os
        _proc =_ps .Process (_os .getpid ())
        rss_before =_proc .memory_info ().rss /1024 /1024
        threads =_proc .num_threads ()
    except Exception as _ex:
        _log .debug ("api_bot_memory_profile(): psutil: %s",_ex)
    gc .collect ()
    rss_after =rss_before
    try :
        import psutil as _ps ,os as _os
        rss_after =_ps .Process (_os .getpid ()).memory_info ().rss /1024 /1024
    except Exception as _ex:
        _log .debug ("api_bot_memory_profile(): повторный замер: %s",_ex)
    guilds =0 ;members =0 ;channels =0 ;roles =0 ;voice =0
    per_guild =[]
    cogs =0 ;extensions =0
    if bot_instance :
        try :
            guilds =len (bot_instance .guilds )
            for g in bot_instance .guilds :
                _m =len (getattr (g ,'members',None )or [])
                members +=_m
                channels +=len (getattr (g ,'channels',None )or [])
                roles +=len (getattr (g ,'roles',None )or [])
                per_guild .append ({'name':str (getattr (g ,'name','?'))[:40],'members':_m })
            per_guild =sorted (per_guild ,key =lambda x :-x ['members'])[:5]
            voice =len (getattr (bot_instance ,'voice_clients',None )or [])
            cogs =len (getattr (bot_instance ,'cogs',{})or {})
            extensions =len (getattr (bot_instance ,'extensions',{})or {})
        except Exception as _ex:
            _log .debug ("api_bot_memory_profile(): кэш Discord: %s",_ex)
    objects_total =0
    top_types =[]
    try :
        _objs =gc .get_objects ()
        objects_total =len (_objs )
        _cnt =Counter ()
        for _o in _objs :
            _t =type (_o )
            _cnt [f'{_t .__module__ }.{_t .__name__ }']+=1
        top_types =[[k ,v ]for k ,v in _cnt .most_common (15 )]
        del _objs ,_cnt
    except Exception as _ex:
        _log .debug ("api_bot_memory_profile(): подсчёт объектов: %s",_ex)
    return jsonify ({
    'success':True ,
    'rss_mb':round (rss_before ,1 ),
    'rss_after_gc_mb':round (rss_after ,1 ),
    'threads':threads ,
    'guilds':guilds ,'members_cached':members ,
    'channels_cached':channels ,'roles_cached':roles ,
    'voice_clients':voice ,'cogs':cogs ,'extensions':extensions ,
    'objects_total':objects_total ,'top_types':top_types ,
    'per_guild':per_guild ,
    'gc_generations':[dict (g )for g in gc .get_stats ()]
    })


@app .route ('/api/bot/sync',methods =['POST'])
@login_required 
@role_required ('admin')
def api_bot_sync ():
    if not bot_instance :
        if _demo_mode ():
            # витрина без живого бота: команда «сработала», страница живая
            _log_panel_action ('BOT_SYNC',session .get ('username'))
            return jsonify ({'success':True ,'demo':True ,'synced_guilds':['Hakumo Demo']})
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
    async def do ():
    # ЕДИНСТВЕННО правильный синк — full_sync: гильдовые копии (мгновенно)
    # + чистка глобальных (и слэшей, и контекстных меню) — без дублей.
        from services.sync_filtered import full_sync as _full_sync
        try :
            await _full_sync (bot_instance )
        except Exception as _ex:
            _log .warning ('bot sync (кнопка): %s',_ex )
    try :
        # НЕ ждём результат (раньше run_coroutine_threadsafe(...).result(60)
        # вешал Flask на минуту — панель «умирала» именно от этого, а
        # повторный клик плодил параллельные синки). Запускаем фоном:
        # сам full_sync защищён локом от повторного входа.
        asyncio .run_coroutine_threadsafe (do (),bot_instance .loop )
        _log_panel_action ('BOT_SYNC',session .get ('username'))
        return jsonify ({'success':True ,'started':True })
    except Exception as e :
        return jsonify ({'error':str (e )})

        # Рентген команд: что сейчас РЕАЛЬНО зарегистрировано в Discord
        # (глобально и по каждому серверу) — по этому видно дубли.
@app .route ('/api/bot/commands-audit')
@login_required
@role_required ('admin')
def api_bot_commands_audit ():
    if not bot_instance :
        if _demo_mode ():
            return jsonify ({'demo':True ,'global':['апелляция'],
                             'guilds':{'Hakumo Demo (777)':['help','modpanel','warn']},
                             'duplicates':[]})
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
    async def do ():
        out ={'global':[],'guilds':{},'duplicates':[]}
        import discord as _d
        # Цели синка из конфигурации + метка последнего полного синка —
        # по ним сразу видно, пробежал ли вообще новый full_sync.
        try :
            from config import Config as _Cfg
            out ['targets_conf']=[o .id for o in _Cfg .guild_objects ()]
        except Exception as _ex:
            out ['targets_conf_error']=str (_ex )
        try :
            import json as _json ,os as _os
            with open (_os .path .join ('data','sync_last.json'),encoding ='utf-8')as f :
                out ['last_sync']=_json .load (f )
        except Exception :
            out ['last_sync']=None
        try :
            out ['global']=sorted (c .name for c in await bot_instance .tree .fetch_commands ())
        except Exception as _ex:
            out ['global_error']=str (_ex )
        glob =set (out ['global'])
        for g in list (bot_instance .guilds ):
            try :
                names =sorted (c .name for c in await bot_instance .tree .fetch_commands (guild =_d .Object (id =g .id )))
                key =f'{g .name } ({g .id })'
                out ['guilds'][key ]=names
                dup =sorted (glob &set (names ))
                if dup :
                    out ['duplicates'].append ({'guild':key ,'names':dup })
            except Exception as _ex:
                out ['guilds'][f'{g .name } ({g .id })']=f'ошибка: {_ex }'
        return out
    coro =do ()
    try :
        _loop =getattr (bot_instance ,'loop ',None )
        if _loop is None :
            # Фейковый бот без работающего event loop (тесты/демо) — корутину
            # нельзя планировать, закрываем её сами, иначе RuntimeWarning.
            coro .close ()
            return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'})
        result =asyncio .run_coroutine_threadsafe (coro ,_loop ).result (timeout =60 )
        return jsonify (result )
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

    # Участники — только основного сервера панели (не всех серверов бота).
    _search_guild =_panel_guild ()
    if _search_guild is not None :
        for member in _search_guild .members :
            if q in member .display_name .lower ()or q in str (member .id ):
                results .append ({
                'type':'member',
                'icon':'',
                'title':member .display_name ,
                'subtitle':f'{_search_guild.name} • ID: {member.id}',
                'url':f'/users?search={member.id}'
                })
                if len (results )>=5 :
                    break

                        # Предупреждения
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
            if MAIN_GUILD_ID and str (guild_id )!=str (MAIN_GUILD_ID ):
                continue 
            for ev in reversed (events [-200 :]):
                _act_h =human_action (ev .get ('action',''))
                if (q in ev .get ('action','').lower ()or 
                q in _act_h .lower ()or 
                q in ev .get ('user_name','').lower ()or 
                q in ev .get ('reason','').lower ()):
                    results .append ({
                    'type':'log',
                    'icon':'',
                    'title':f'{_act_h} — {ev.get("user_name", "?")}',
                    'subtitle':ev .get ('reason',''),
                    'url':'/logs'
                    })
                    if len (results )>=15 :
                        break 

    return jsonify (results [:15 ])

    # Голос Команда Endpoint (voice_listener.py для) 
VOICE_SECRET =os .getenv ('VOICE_SECRET','Hakumo-voice-2024')

@app .route ('/api/voice-command',methods =['POST'])
def api_voice_command ():
    """Обработать голосовые команды от voice_listener.py"""
    data =request .get_json (silent =True )or {}
    if not data or data .get ('secret')!=VOICE_SECRET :
        return jsonify ({'error':'Не авторизован'}),401 
    command =data .get ('command','').strip ()
    if not command :
        return jsonify ({'error':'Команда пусто'}),400 

    if not bot_instance :
        return jsonify ({'error':'Бот Discord сейчас не в сети или не подключен.'}),503 

    from config import clean_number
    OWNER_ID_INT = clean_number(os.getenv('OWNER_ID')) or 987430047889637426

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
            # Если истории сообщений нет — шлём сразу в ЛС
        await dm .send (command )
        return 'OK (DM sent)'

    try :
        result =asyncio .run_coroutine_threadsafe (dispatch (),bot_instance .loop ).result (timeout =15 )
        return jsonify ({'success':True ,'result':result })
    except Exception as e :
        return jsonify ({'error':str (e )}),500 



# Восстановление пароля: коды для страницы входа
import random as _random 
_reset_codes ={}# {discord_id: {code, expires}}

@app .route ('/api/forgot-password',methods =['POST'])
def api_forgot_password ():
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    if not discord_id :
        return jsonify ({'error':'Требуется Discord ID'})

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
        return jsonify ({'error':f'DM не отправлено: {e}'})


@app .route ('/api/reset-password',methods =['POST'])
def api_reset_password ():
    import time as _time 
    data =request .get_json (silent =True )or {}
    discord_id =str (data .get ('discord_id','')).strip ()
    code =str (data .get ('code','')).strip ()
    new_pass =str (data .get ('new_password','')).strip ()

    if not discord_id or not code or not new_pass :
        return jsonify ({'error':'Недостаточно информации'})
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
    if not _vis_allowed ('notifications_min_role'):
        return jsonify ({'notifications':[],'unread':0 ,'ts':int (_time .time ()*1000 )})
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
    except Exception as _ex:
        _log.debug("api_notifications_poll(): подавлено: %s", _ex)
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
    except Exception as _ex:
        _log.debug("api_notifications_poll(): подавлено: %s", _ex)
    notifs .sort (key =lambda x :x .get ('ts',0 ),reverse =True )
    unread =len ([n for n in notifs if n .get ('ts',0 )>seen_ts ])+personal_unread 
    return jsonify ({'notifications':notifs [:20 ],'unread':unread ,'ts':int (_t .time ()*1000 )})


# ── Лента активности: человекочитаемые названия панель-действий ─────────────
# Сырой «POST /api/guild/…/channels-visibility» превращается в
# «Изменили видимость каналов» со ссылкой на нужный раздел.
_ACTION_MAP = (
    # специфичные пути — ПЕРЕД общими ('/schedule' перехватил бы и /mod-schedule)
    (r'/appeals/resolve', 'Решение по апелляции', 'fa-scale-balanced', '/appeals'),
    (r'/appeals/claim', 'Взяли апелляцию в работу', 'fa-hand', '/appeals'),
    (r'/appeals/settings', 'Настроили правила апелляций', 'fa-sliders', '/appeals'),
    (r'/appeals/channel', 'Выбрали канал апелляций', 'fa-hashtag', '/appeals'),
    (r'/appeals', 'Действие с апелляциями', 'fa-scale-balanced', '/appeals'),
    (r'/mod-schedule/create', 'Запланировали наказание', 'fa-calendar-plus', '/mod-schedule'),
    (r'/mod-schedule/cancel', 'Отменили отложенное действие', 'fa-calendar-xmark', '/mod-schedule'),
    (r'/ladder/cooldown', 'Настроили авто-остывание', 'fa-temperature-low', '/ladder'),
    (r'/ladder/add', 'Добавили ступень лестницы', 'fa-stairs', '/ladder'),
    (r'/ladder/remove', 'Убрали ступень лестницы', 'fa-stairs', '/ladder'),
    (r'/staff-rating/remove', 'Сняли голос за модератора', 'fa-star-half-stroke', '/staff-rating'),
    (r'/punish', 'Наказание из панели', 'fa-gavel', '/warnings'),
    (r'/roles/create', 'Дали роль', 'fa-user-plus', '/roles'),
    (r'/roles/\d+/delete', 'Удалили роль', 'fa-user-minus', '/roles'),
    (r'channels-visibility', 'Изменили видимость каналов', 'fa-eye-slash', '/channels'),
    (r'/lockdown', 'Локдаун каналов', 'fa-lock', '/lockdown'),
    (r'/schedule', 'Расписание анонсов', 'fa-calendar-days', '/schedule'),
    (r'/role-map', 'Настроили карту ролей', 'fa-map', '/role-permissions'),
    (r'/role-permissions', 'Изменили права ролей', 'fa-key', '/role-permissions'),
    (r'/warnings', 'Выдали предупреждение', 'fa-triangle-exclamation', '/warnings'),
    (r'/temp-mod', 'Временные меры', 'fa-clock', '/temp-moderation'),
    (r'/ai-mod', 'Настроили AI-модерацию', 'fa-brain', '/ai-moderation'),
    (r'/autofilter', 'Настроили автофильтр', 'fa-filter', '/autofilter'),
    (r'/antifake', 'Изменили защиту от фейков', 'fa-user-secret', '/antifake'),
    (r'/backup', 'Бэкапы', 'fa-box-archive', '/backups'),
    (r'/announcement', 'Объявления', 'fa-bullhorn', '/announcements'),
    (r'/webhook', 'Вебхуки', 'fa-link', '/webhooks'),
    (r'/ban_appeal_channel', 'Канал апелляции после бана', 'fa-user-lock', '/channel-settings'),
    (r'/proof_channel', 'Канал доказательств', 'fa-folder-open', '/channel-settings'),
    (r'/welcome_channel', 'Канал приветствий', 'fa-hand-sparkles', '/channel-settings'),
    (r'/appeals_channel', 'Канал апелляций', 'fa-scale-balanced', '/channel-settings'),
    (r'/staff_apply_channel', 'Канал заявок в команду', 'fa-file-signature', '/channel-settings'),
    (r'/welcome-channel|/welcome-card', 'Приветствие новичков', 'fa-handshake', '/welcome-editor'),
    (r'/staff-apps|staff_apps', 'Заявка в команду', 'fa-file-signature', '/staff-apps'),
    (r'/verify/', 'Настроили верификацию', 'fa-clipboard-check', '/verify'),
    (r'/pagerduty', 'Настроили PagerDuty', 'fa-tower-broadcast', '/pagerduty'),
    (r'/feature-flags', 'Флаги функций', 'fa-flag', '/feature-flags'),
    (r'/commands', 'Команды бота', 'fa-terminal', '/commands'),
    (r'/cog-manager|reload', 'Управление модулями', 'fa-cubes', '/cog-manager'),
    (r'/bot/restart', 'Перезапустили бота', 'fa-rotate', '/bot-settings'),
    (r'/bot/sync', 'Синхронизировали команды', 'fa-arrows-rotate', '/bot-settings'),
    (r'/bot/gc', 'Очистили память бота', 'fa-broom', '/bot-settings'),
    (r'/bot/diagnose', 'Диагностика бота', 'fa-stethoscope', '/bot-settings'),
    (r'/bot-settings', 'Настройки бота', 'fa-sliders-h', '/bot-settings'),
    (r'/log-settings', 'Настроили логи сервера', 'fa-list-check', '/log-settings'),
    (r'/log-cards', 'Карточки логов', 'fa-id-card', '/log-settings'),
    (r'/report', 'Настройки репортов', 'fa-flag', '/reports-queue'),
    (r'/staff-limits', 'Лимиты персонала', 'fa-shield-halved', '/guardian'),
    (r'/verify', 'Верификация', 'fa-clipboard-check', '/verify'),
    (r'/anticrash', 'Анти-краш', 'fa-life-ring', '/anticrash'),
    (r'/antiraid', 'Анти-рейд', 'fa-shield-virus', '/antiraid'),
    (r'/mod-settings|/ladder', 'Авто-наказания', 'fa-hammer', '/ladder'),
    (r'/role-settings', 'Роли за наказания', 'fa-user-tag', '/role-settings'),
    (r'/send-embed', 'Отправили эмбед', 'fa-paper-plane', '/send-command'),
    (r'/send-message', 'Отправили сообщение', 'fa-paper-plane', '/send-command'),
    (r'/ban|/kick|/mute|/punish', 'Наказание участника', 'fa-gavel', '/logs'),
)


# Сегменты путей → человеческие названия (для путей, которых нет в точечной
# карте выше). Последний содержательный сегмент превращаем в русское слово,
# чтобы в журнале/ленте не светилось сырое «api … settings».
_SEGMENT_NAMES = {
    'settings': 'настройки', 'config': 'настройки', 'save': 'сохранение',
    'log-settings': 'настройки логов', 'log-cards': 'карточки логов',
    'mod-settings': 'настройки модерации', 'role-settings': 'роли наказаний',
    'report-settings': 'настройки репортов', 'bot-settings': 'настройки бота',
    'channel-routes': 'маршруты каналов', 'channel-settings': 'настройки каналов',
    'staff-limits': 'лимиты персонала', 'guardian': 'щит сервера',
    'antiraid': 'анти-рейд', 'anticrash': 'анти-краш', 'antifake': 'антифейк',
    'autofilter': 'автофильтр', 'verify': 'верификация', 'welcome-card': 'карточка приветствия',
    'pagerduty': 'тревоги PagerDuty', 'feature-flags': 'флаги функций',
    'commands': 'команды', 'switch': 'переключатель команд', 'switches': 'переключатели команд',
    'menu-mode': 'режим меню', 'ladder': 'лестница наказаний',
    'punish': 'наказание', 'appeals': 'апелляции', 'reports': 'репорты',
    'reports-queue': 'очередь репортов', 'warnings': 'предупреждения',
    'warn-level': 'роль за уровень варнов', 'mod-schedule': 'расписание наказаний',
    'mod-control': 'контроль команды', 'mod-insights': 'аналитика рисков',
    'security-center': 'центр безопасности', 'role': 'роль', 'roles': 'роли',
    'role-map': 'карта ролей', 'role-permissions': 'права ролей',
    'members': 'участники', 'member': 'участник', 'nick': 'ник участника',
    'channels': 'каналы', 'announcements': 'объявления', 'announcement': 'объявление',
    'backups': 'бэкапы', 'backup': 'бэкап', 'webhook': 'вебхук', 'webhooks': 'вебхуки',
    'presence': 'статус бота', 'sync': 'синхронизация команд', 'restart': 'перезапуск бота',
    'diagnose': 'диагностика', 'gc': 'очистка памяти', 'memory-profile': 'профиль памяти',
    'commands-audit': 'аудит команд', 'update-source': 'обновление источника',
    'visibility': 'видимость', 'toggle': 'переключение', 'state': 'состояние',
    'status': 'статус', 'overview': 'обзор', 'summary': 'сводка', 'threshold': 'порог',
    'protect': 'защита участника', 'unprotect': 'снятие защиты', 'action': 'действие',
    'strikes': 'нарушения фейк-защиты', 'lab': 'проверка', 'test': 'тест',
    'cooldown': 'кулдаун', 'add': 'добавление', 'remove': 'удаление',
    'create': 'создание', 'delete': 'удаление', 'reset': 'сброс', 'clear': 'очистка',
    'claim': 'взято в работу', 'resolve': 'решение', 'export': 'экспорт',
    'upload': 'загрузка', 'appearance': 'оформление', 'preview': 'предпросмотр',
    'publish': 'публикация', 'rollout': 'выкатка', 'amnesty': 'амнистия',
    'reasons': 'причины', 'dossier': 'досье', 'scan': 'сканирование',
    'newaccount': 'молодые аккаунты', 'fake-score': 'оценка фейка',
    'spam-sim': 'симуляция спама', 'protection-reset': 'сброс защиты',
    'custom': 'отчёт', 'weekly': 'недельный отчёт', 'generate': 'генерация отчёта',
    'view': 'просмотр', 'records': 'записи', 'revert': 'откат', 'changes': 'журнал изменений',
    'analytics': 'аналитика', 'advanced': 'расширенная аналитика',
    'heatmap': 'тепловая карта', 'invite-leaders': 'приглашения', 'member-flow': 'приток участников',
    'mod-load': 'нагрузка модерации', 'voice-pulse': 'голосовая активность',
    'week-summary': 'итоги недели', 'channel-drill': 'разбор по каналам',
    'switch-bulk': 'массовое переключение', 'catalog': 'каталог команд',
    'leave-guild': 'выход с сервера', 'send-message': 'отправка сообщения',
    'send-embed': 'отправка эмбеда', 'execute-command': 'выполнение команды',
    'change-password': 'смена пароля', 'add-member': 'добавление участника',
    'my-token': 'токен входа', 'tunnel-url': 'адрес туннеля',
    'panel-menu': 'настройка меню панели', 'layout': 'раскладка меню',
    'voice-command': 'голосовая команда', 'forgot-password': 'сброс пароля',
    'reset-password': 'новый пароль', 'discord-login': 'вход через Discord',
    'discord-check': 'проверка Discord', 'login': 'вход', 'logout': 'выход',
    'notifications': 'уведомления', 'activity-feed': 'лента активности',
    'panel-logs': 'журнал панели', 'sidebar': 'сайдбар', 'search': 'поиск',
}


def _human_fallback_title(method, path):
    """Человеческое название для пути, которого нет в точечной карте.

    Берём последние осмысленные сегменты (отбрасываем api/guild/<id>/числа)
    и переводим словарём; глагол подбираем по методу (DELETE → «удалили»,
    POST → «изменили/создали»). Никаких сырых '/api/...' в журнале."""
    raw_segs = [s for s in str(path or '').split('/') if s]
    segs = []
    for s in raw_segs:
        if s in ('api', 'guild'):
            continue
        if s.isdigit():          # id сервера/пользователя
            continue
        segs.append(s)
    # известные составные сегменты переводим целиком (до разбиения по дефису)
    _known = {
        'ban_appeal_channel': 'канал апелляции', 'proof_channel': 'канал доказательств',
        'appeals_channel': 'канал апелляций', 'welcome_channel': 'канал приветствий',
        'staff_apply_channel': 'канал заявок', 'appeal_menu_channel': 'меню апелляций',
        'guardian_channel': 'тревоги щита', 'security_channel': 'лог авто-защиты',
        'antiraid_channel': 'алерты анти-рейда', 'anticrash_channel': 'сводки анти-краша',
        'pagerduty_channel': 'канал PagerDuty', 'log_settings': 'настройки логов',
        'role_settings': 'роли наказаний', 'mod_settings': 'настройки модерации',
        'staff_limits': 'лимиты персонала', 'bot_settings': 'настройки бота',
        'feature_flags': 'флаги функций', 'panel_menu': 'меню панели',
        'channel_routes': 'маршруты каналов', 'message_logs': 'логи сообщений',
        'send_message': 'отправка сообщения', 'send_embed': 'отправка эмбеда',
        'execute_command': 'выполнение команды', 'memory_profile': 'профиль памяти',
        'commands_audit': 'аудит команд', 'change_password': 'смена пароля',
        'forgot_password': 'запрос сброса пароля', 'reset_password': 'сброс пароля',
        'discord_login': 'вход через Discord', 'discord_check': 'проверка Discord',
        'activity_feed': 'лента активности', 'panel_logs': 'журнал панели',
        'leave_guild': 'выход с сервера', 'add_member': 'добавление участника',
        'my_token': 'токен входа', 'tunnel_url': 'адрес туннеля', 'my_applications': 'мои заявки',
        'my_notifications': 'уведомления', 'login_suggest': 'подсказки входа',
        'role_map': 'карта ролей', 'role_permissions': 'права ролей',
        'staff_apps': 'заявки в команду', 'voice_command': 'голосовая команда',
    }
    segs = [_known.get(s.lower(), s) for s in segs]
    # имя действия — последний сегмент, контекст — предыдущий (если есть)
    name = ''
    context = ''
    if segs:
        last = segs[-1].lower()
        name = _SEGMENT_NAMES.get(last, last.replace('-', ' ').replace('_', ' '))
        if len(segs) >= 2:
            prev = segs[-2].lower()
            context = _SEGMENT_NAMES.get(prev, prev.replace('-', ' ').replace('_', ' '))
    verb = {'DELETE': 'Удалили', 'POST': 'Изменили', 'PUT': 'Изменили',
            'PATCH': 'Изменили', 'GET': 'Открыли'}.get(str(method or '').upper(), 'Действие')
    if context and name and name != context:
        title = f'{verb}: {context} — {name}'
    elif name:
        title = f'{verb}: {name}'
    else:
        title = 'Действие в панели'
    return title


def _human_panel_action(action):
    """«POST /api/guild/123/roles/create» → ('Дали роль', 'fa-user-plus', '/roles').

    Сначала точечная карта известных действий; если пути там нет — собираем
    понятное название из сегментов (без сырого '/api/...')."""
    a = str(action or '').strip()
    method = a.split(' ', 1)[0] if ' ' in a else ''
    path = a.split(' ', 1)[1] if ' ' in a else a
    for pat, title, icon, link in _ACTION_MAP:
        if _re.search(pat, path):
            return title, icon, link
    title = _human_fallback_title(method, path)
    return title, 'fa-sliders', '/panel-logs'


@app .route ('/api/activity-feed')
@login_required
def api_activity_feed ():
    if not _vis_allowed ('activity_min_role'):
        return jsonify ([])
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
                        ts = _epoch_from_ts (e .get ('timestamp'))
                    except Exception:
                        ts = 0
                push('fa-lock', 'Вход в панель', e.get('username'), f"Роль: {e.get('role','?')}", ts, 'auth', link='/logs')
    except Exception as _ex:
        _log.debug("api_activity_feed(): подавлено: %s", _ex)

    # 2) Действия модерации (audit + mod_data)
    try:
        f = 'data/audit_log.json'
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            for gid, events in data.items():
                if MAIN_GUILD_ID and str (gid )!=str (MAIN_GUILD_ID ):
                    continue
                for ev in events[-15:]:
                    ts = 0
                    try:
                        ts = _epoch_from_ts (ev .get ('timestamp'))
                    except Exception:
                        ts = 0
                    act = human_action (ev.get('action')).lower()
                    icon = 'fa-shield-halved'
                    evtype = 'mod'
                    if 'бан' in act or 'ban' in act: icon = 'fa-gavel'
                    elif 'мут' in act or 'mute' in act: icon = 'fa-comment-slash'
                    elif 'кик' in act or 'kick' in act: icon = 'fa-door-open'
                    elif 'роль' in act: icon = 'fa-masks-theater'
                    elif 'канал' in act: icon = 'fa-folder-open'
                    elif 'сообщ' in act or 'message' in act: icon = 'fa-comment'
                    elif 'голос' in act or 'voice' in act: icon = 'fa-microphone'
                    push(icon, human_action (ev.get('action','Действие')), ev.get('user_name') or ev.get('mod_name'),
                         ev.get('reason',''), ts, evtype, link='/logs')
    except Exception as _ex:
        _log.debug("api_activity_feed(): подавлено: %s", _ex)

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
                            ts = _epoch_from_ts (w .get ('timestamp'))
                        except Exception:
                            ts = 0
                        push('fa-triangle-exclamation', 'Предупреждение', w.get('moderator') or w.get('mod') or uid,
                             w.get('reason',''), ts, 'warn', link='/warnings')
    except Exception as _ex:
        _log.debug("api_activity_feed(): подавлено: %s", _ex)

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
                ts = e.get('ts', 0)
                if isinstance(ts, str) and not str(ts).isdigit():
                    try:
                        ts = _epoch_from_ts (ts )
                    except Exception:
                        ts = 0
                _title, _icon, _link = _human_panel_action(e.get('action', ''))
                push(_icon, _title, e.get('username'), e.get('detail', ''), ts, 'panel', link=_link)
    except Exception as _ex:
        _log.debug("api_activity_feed(): подавлено: %s", _ex)

    # 6) События диспетчера уведомлений (история с иконками и ссылками)
    try:
        f = 'data/notification_history.json'
        _ev_type = {'warn':'warn', 'mod_action':'mod', 'staff_apply':'panel',
                    'test':'system'}
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fp:
                hist = json.load(fp)
            for h in hist[-30:]:
                ts = 0
                try:
                    ts = _epoch_from_ts (h .get ('created_at'))
                except Exception:
                    ts = 0
                push(h.get('icon','🔔'), h.get('title','Уведомление'), 'Система',
                     h.get('body',''), ts, _ev_type.get(h.get('event',''),'system'),
                     link=h.get('link',''))
    except Exception as _ex:
        _log.debug("api_activity_feed(): подавлено: %s", _ex)

    # Сортировка — новые сверху
    items.sort(key=lambda x: x.get('ts') or 0, reverse=True)
    return jsonify({'items': items[:80]})


    # WebSocket Server Initialization 
if WEBSOCKET_ENABLED :
    try :
    # Запуск WebSocket сервера в отдельном потоке (адрес/порт из .env;
    # при запуске ботом через main.py повторный вызов — no-op)
        _ws_host =(os .environ .get ('WS_HOST','')or '').strip ()or 'localhost'
        _ws_port =int (os .environ .get ('WS_PORT','')or 0 )or 8765
        ws_thread =start_websocket_thread (host =_ws_host ,port =_ws_port )
        print ('[WebSocket] Сервер инициализирован')
    except Exception as e :
        print (f'[WebSocket] Ошибка инициализации: {e}')
        WEBSOCKET_ENABLED =False 



# Запуск панели отдельным процессом — ОБЯЗАТЕЛЬНО в самом конце файла.
# Раньше этот блок стоял в середине, app.run() блокировал импорт, и все
# маршруты ниже (/api/forgot-password, /api/reset-password,
# /api/notifications/poll, /api/activity-feed) не регистрировались:
# «python web/app.py» отвечал на них 404. Через main.py (бот поднимает
# панель сам) __name__ != "__main__", поэтому там они работали.
if __name__ =='__main__':
    # Панель отдельным процессом (python web/app.py) — без бота; для
    # «панель видит бота» запускай main.py (встроенный сервер).
    _p_port =int (os .environ .get ('PANEL_PORT','')or 0 )
    if not _p_port:
        try :
            from config import Config
            _p_port =int (getattr (Config ,'PORT',0 )or 0 )
        except Exception :
            _p_port =0
    app .run (host ='0.0.0.0',port =(_p_port or 5000 ),debug =False ,threaded =True )
