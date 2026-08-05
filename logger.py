"""
Централизованная система логирования
Файл + консоль, ротация, форматирование
+ живой буфер для веб-консоли панели (/konsol)
"""
import logging
import os
import sys
import time
import itertools
from collections import deque
from logging.handlers import RotatingFileHandler
from datetime import datetime


_initialized = False

# ── Живой буфер для веб-консоли (последние 300 строк, только в памяти) ──
_live_buffer = deque(maxlen=300)
_live_counter = itertools.count(1)


class _LiveLogHandler(logging.Handler):
    """Складывает записи логов в кольцевой буфер для панели."""

    def emit(self, record: logging.LogRecord):
        try:
            _live_buffer.append({
                'id': next(_live_counter),
                'ts': time.time(),
                'level': record.levelname,
                'name': record.name,
                'msg': str(record.getMessage())[:500],
            })
        except Exception:
            pass


def get_live_logs(after_id: int = 0, limit: int = 200) -> list:
    """Записи живого буфера с id > after_id (максимум limit, по порядку)."""
    try:
        after_id = int(after_id)
    except Exception:
        after_id = 0
    items = [r for r in _live_buffer if r['id'] > after_id]
    return items[-limit:]


def setup_logger(name: str = "bot", log_file: str = None, level: str = None) -> logging.Logger:
    """
    Настроить и вернуть логгер.
    
    Args:
        name: Имя логгера
        log_file: Путь к файлу логов (по умолчанию logs/bot.log)
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global _initialized
    
    if log_file is None:
        log_file = "logs/bot.log"
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    
    # Создать директорию
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    
    # Если логгер уже настроен — не дублировать
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Формат
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Консольный хендлер
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)
    
    # Файловый хендлер с ротацией
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    
    # Отдельный файл для ошибок
    error_file = log_file.replace(".log", "_errors.log")
    error_handler = RotatingFileHandler(
        error_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    logger.addHandler(error_handler)

    # Живой буфер для веб-консоли (один хендлер на логгер, чтобы не было дублей)
    if not any(isinstance(h, _LiveLogHandler) for h in logger.handlers):
        live = _LiveLogHandler()
        live.setLevel(logging.DEBUG)
        logger.addHandler(live)

    _initialized = True
    return logger


def get_logger(name: str = "bot") -> logging.Logger:
    """Получить существующий логгер или создать новый"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Быстрый доступ
log = get_logger("bot")
