"""
Централизованная система логирования
Файл + консоль, ротация, форматирование
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime


_initialized = False


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
