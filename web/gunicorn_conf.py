"""
Конфигурация Gunicorn.
Переменные окружения (все опциональны):
  WEB_WORKERS      : количество воркеров (по умолчанию: до 4 или число CPU)
  WEB_TIMEOUT      : таймаут запроса (по умолчанию: 60)
  WEB_GRACEFUL     : graceful-таймаут (по умолчанию: 30)
  WEB_BIND         : bind (по умолчанию: 0.0.0.0:5001)
  WEB_LOG_LEVEL    : уровень логов (по умолчанию: warning)
  WEB_PRELOAD      : 1 — preload_app, по умолчанию: 1
  WEB_KEEPALIVE    : keep-alive, сек (по умолчанию: 5)
"""
import os
import multiprocessing


def _num(name: str, default: int) -> int:
    """Целое число из окружения, устойчивое к опечаткам.

    Лечит частые ошибки: пробелы, комментарий вплотную (2 # воркера),
    лишняя запятая или точка с запятой на конце (2,). При неудаче — default.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    s = str(raw).strip().split('#', 1)[0].strip().rstrip(',;').strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            print(f"[gunicorn_conf] {name}={raw!r} не является числом — используется {default}")
            return default


_workers = _num('WEB_WORKERS', 0) or min(4, multiprocessing.cpu_count())
_bind = os.getenv('WEB_BIND', '0.0.0.0:5001')
_timeout = _num('WEB_TIMEOUT', 60)
_graceful = _num('WEB_GRACEFUL', 30)
_loglevel = os.getenv('WEB_LOG_LEVEL', 'warning')
_preload = os.getenv('WEB_PRELOAD', '1') == '1'
_keepalive = _num('WEB_KEEPALIVE', 5)

# Приватные переменные Gunicorn (этот файл читается как конфиг-файл)
bind = _bind
workers = _workers
worker_class = 'sync'
timeout = _timeout
graceful_timeout = _graceful
keepalive = _keepalive
loglevel = _loglevel
preload_app = _preload
accesslog = os.getenv('WEB_ACCESS_LOG', '-')  # stdout
errorlog = os.getenv('WEB_ERROR_LOG', '-')    # stdout
# Простой формат access-лога, совместимый с Gunicorn 26+
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Имя процессов (видно в ps/top)
proc_name = 'moebius-web'

# Перезапуск воркера после максимального числа запросов (защита от утечек памяти)
max_requests = _num('WEB_MAX_REQUESTS', 1000)
max_requests_jitter = _num('WEB_MAX_REQUESTS_JITTER', 100)

# Класс воркера: sync (по умолчанию) или gevent (для I/O с большим числом соединений).
# Для Flask + flask_session (filesystem) достаточно sync; при высоком RPS можно
# выбрать gevent (пакет gevent должен быть установлен).
_worker_class_env = os.getenv('WEB_WORKER_CLASS', 'sync').lower()
if _worker_class_env == 'gevent':
    try:
        import gevent  # noqa: F401
        worker_class = 'gevent'
        # с gevent один воркер обслуживает больше одновременных запросов
        if _num('WEB_WORKERS', 0) <= 1:
            workers = _num('WEB_THREADS', 2)
    except ImportError:
        worker_class = 'sync'
