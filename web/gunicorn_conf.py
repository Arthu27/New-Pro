"""
Gunicorn konfigurasyonu.
Env degiskenleri (hepsi opsiyonel):
  WEB_WORKERS      : worker sayisi (default: 2 veya CPU sayisi)
  WEB_TIMEOUT      : request timeout (default: 60)
  WEB_GRACEFUL     : graceful timeout (default: 30)
  WEB_BIND         : bind (default: 0.0.0.0:5001)
  WEB_LOG_LEVEL    : log seviyesi (default: warning)
  WEB_PRELOAD      : 1 ise preload_app, default: 1
  WEB_KEEPALIVE    : keep-alive sn (default: 5)
"""
import os
import multiprocessing

_workers = int(os.getenv('WEB_WORKERS', '0')) or min(4, multiprocessing.cpu_count())
_bind = os.getenv('WEB_BIND', '0.0.0.0:5001')
_timeout = int(os.getenv('WEB_TIMEOUT', '60'))
_graceful = int(os.getenv('WEB_GRACEFUL', '30'))
_loglevel = os.getenv('WEB_LOG_LEVEL', 'warning')
_preload = os.getenv('WEB_PRELOAD', '1') == '1'
_keepalive = int(os.getenv('WEB_KEEPALIVE', '5'))

# Gunicorn ozel degiskenleri (config dosyasi olarak okunur)
bind = _bind
workers = _workers
worker_class = 'sync'
timeout = _timeout
graceful_timeout = _graceful
keepalive = _keepalive
loglevel = _loglevel
preload_app = _preload
accesslog = os.getenv('WEB_ACCESS_LOG', '-')   # stdout
errorlog = os.getenv('WEB_ERROR_LOG', '-')     # stdout
# Gunicorn 26+ ile uyumlu, basit access log formati
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process isimleri (ps/top'ta gorunur)
proc_name = 'moebius-web'

# Maksimum istek sayisi sonrasi worker'i yenile (memory leak korunmasi)
max_requests = int(os.getenv('WEB_MAX_REQUESTS', '1000'))
max_requests_jitter = int(os.getenv('WEB_MAX_REQUESTS_JITTER', '100'))

# Worker sinifi: sync (default) veya gevent (cok baglantili I/O icin).
# Flask + flask_session (filesystem) ile 'sync' yeterli; yuksek RPS isteniyorsa
# 'gevent' secilebilir (gevent kurulu olmali).
_worker_class_env = os.getenv('WEB_WORKER_CLASS', 'sync').lower()
if _worker_class_env == 'gevent':
    try:
        import gevent  # noqa: F401
        worker_class = 'gevent'
        # gevent ile connection basina thread olmadigindan worker basina daha
        # fazla eszamanli istek kaldirir.
        if int(os.getenv('WEB_WORKERS', '0') or 0) <= 1:
            workers = int(os.getenv('WEB_THREADS', '2'))  # threads yerine worker
    except ImportError:
        worker_class = 'sync'
