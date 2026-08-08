"""
Конфигурация Gunicorn.
Переменные окружения (все опциональны):
  WEB_WORKERS      : количество воркеров (по умолчанию: 2 или число CPU)
  WEB_TIMEOUT      : таймаут запроса (по умолчанию: 60)
  WEB_GRACEFUL     : graceful-таймаут (по умолчанию: 30)
  WEB_BIND         : bind (по умолчанию: 0.0.0.0:5001)
  WEB_LOG_LEVEL    : уровень логов (по умолчанию: warning)
  WEB_PRELOAD      : 1 — preload_app, по умолчанию: 1
  WEB_KEEPALIVE    : keep-alive, сек (по умолчанию: 5)
"""
import os 
import multiprocessing 

_workers =int (os .getenv ('WEB_WORKERS','0'))or min (4 ,multiprocessing .cpu_count ())
_bind =os .getenv ('WEB_BIND','0.0.0.0:5001')
_timeout =int (os .getenv ('WEB_TIMEOUT','60'))
_graceful =int (os .getenv ('WEB_GRACEFUL','30'))
_loglevel =os .getenv ('WEB_LOG_LEVEL','warning')
_preload =os .getenv ('WEB_PRELOAD','1')=='1'
_keepalive =int (os .getenv ('WEB_KEEPALIVE','5'))

# Gunicorn приватный degiskenleri (config dosyasi olarak okunur)
bind =_bind 
workers =_workers 
worker_class ='sync'
timeout =_timeout 
graceful_timeout =_graceful 
keepalive =_keepalive 
loglevel =_loglevel 
preload_app =_preload 
accesslog =os .getenv ('WEB_ACCESS_LOG','-')# stdout
errorlog =os .getenv ('WEB_ERROR_LOG','-')# stdout
# Gunicorn 26+ ile uyumlu, basit access лог formati
access_log_format ='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Имена процессов (видно в ps/top)
proc_name ='moebius-web'

# Перезапуск воркера после максимального числа запросов (защита от утечек памяти)
max_requests =int (os .getenv ('WEB_MAX_REQUESTS','1000'))
max_requests_jitter =int (os .getenv ('WEB_MAX_REQUESTS_JITTER','100'))

# Класс воркера: sync (по умолчанию) или gevent (для I/O с большим числом соединений).
# Flask + flask_session (filesystem) ile 'sync' yeterli; высокий RPS isteniyorsa
# 'gevent' secilebilir (gevent kurulu olmali).
_worker_class_env =os .getenv ('WEB_WORKER_CLASS','sync').lower ()
if _worker_class_env =='gevent':
    try :
        import gevent # noqa: F401
        worker_class ='gevent'
        # с gevent нет потока на каждое соединение, поэтому один worker обслуживает больше
        # fazla eszamanli istek kaldirir.
        if int (os .getenv ('WEB_WORKERS','0')or 0 )<=1 :
            workers =int (os .getenv ('WEB_THREADS','2'))# threads yerine worker
    except ImportError :
        worker_class ='sync'
