"""
Централизованная конфигурация бота
Все настройки в одном месте
"""
import os
import logging
from dotenv import load_dotenv

# python-dotenv yorum satırlarını (Rusça, uzun çizgili vb.) uyarı olarak basabiliyor.
# Bunlar zararsızdır — uyarıları gizleyip değerleri yine de okumaya devam ediyoruz.
logging.getLogger("dotenv").setLevel(logging.ERROR)

# Загружаем .env из каталога этого файла (надёжно, независимо от рабочей директории)
# и с override=True, чтобы значение из .env всегда применялось.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)


def _get_token():
    """Токен из .env. Учитывает и ошибочный вариант с кириллической буквой
    (TОКEN), если он остался в файле от старого шаблона."""
    t = os.getenv("TOKEN", "") or os.getenv("TОКEN", "")
    return t.strip()


class Config:
    """Основной класс конфигурации"""
    
    # === Discord ===
    TOKEN: str = _get_token()
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    MAIN_GUILD_ID: int = int(os.getenv("MAIN_GUILD_ID", "0"))
    COMMAND_PREFIX: str = "!"
    
    # === Web Panel ===
    PORT: int = int(os.getenv("PORT", "5001"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "aether-super-secret-key-2026")
    DISABLE_TUNNEL: bool = os.getenv("DISABLE_TUNNEL", "0") == "1"
    
    # === AI ===
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    AI_MODEL: str = os.getenv("AI_MODEL", "qwen2.5:3b")
    
    # === Database ===
    DB_PATH: str = os.getenv("DB_PATH", "data/bot.db")
    
    # === Logging ===
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # === Gunicorn ===
    WEB_WORKERS: int = int(os.getenv("WEB_WORKERS", "0"))
    WEB_BIND: str = os.getenv("WEB_BIND", f"0.0.0.0:{PORT}")
    WEB_TIMEOUT: int = int(os.getenv("WEB_TIMEOUT", "60"))
    WEB_LOG_LEVEL: str = os.getenv("WEB_LOG_LEVEL", "warning")
    WEB_KEEPALIVE: int = int(os.getenv("WEB_KEEPALIVE", "5"))
    WEB_MAX_REQUESTS: int = int(os.getenv("WEB_MAX_REQUESTS", "1000"))
    
    # === Paths ===
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"
    BACKUPS_DIR: str = "backups"
    PLUGINS_DIR: str = "plugins"
    
    # === Bot Settings ===
    BOT_STATUS: str = "idle"  # online, idle, dnd, invisible
    BOT_ACTIVITY_TYPE: str = "listening"  # listening, playing, watching, competing
    BOT_ACTIVITY_TEXT: str = ".gg/Aether"
    
    # === Ticket Settings ===
    TICKET_CATEGORY_ID: int = int(os.getenv("TICKET_CATEGORY_ID", "0"))
    TICKET_SUPPORT_ROLE_ID: int = int(os.getenv("TICKET_SUPPORT_ROLE_ID", "0"))
    TICKET_TRANSCRIPT_CHANNEL_ID: int = int(os.getenv("TICKET_TRANSCRIPT_CHANNEL_ID", "0"))
    TICKET_MAX_OPEN: int = int(os.getenv("TICKET_MAX_OPEN", "3"))
    
    # === Moderation ===
    MOD_LOG_CHANNEL_ID: int = int(os.getenv("MOD_LOG_CHANNEL_ID", "0"))
    
    # === Limits ===
    MAX_WARNINGS_BEFORE_BAN: int = 5
    MAX_WARNINGS_BEFORE_MUTE: int = 3
    AUTO_CLOSE_HOURS: int = 48  # Ticket auto-close after hours


    # === Hardcoded IDs (from cogs) ===
    LOG_CHANNEL_ID: int = int(os.getenv('LOG_CHANNEL_ID', '1491145640900558979'))
    COMPANION_USER_ID: int = int(os.getenv('COMPANION_USER_ID', '1353157554967937153'))
    REQUIRED_ROLE_ID: int = int(os.getenv('REQUIRED_ROLE_ID', '1474866958758576309'))
    APPLY_CHANNEL_ID: int = int(os.getenv('APPLY_CHANNEL_ID', '1484308081302306846'))

    @classmethod
    def ensure_dirs(cls):
        """Создать необходимые директории"""
        for d in [cls.DATA_DIR, cls.LOGS_DIR, cls.BACKUPS_DIR, cls.PLUGINS_DIR]:
            os.makedirs(d, exist_ok=True)

    @classmethod
    def validate(cls) -> list:
        """Проверить критические настройки, вернуть список ошибок"""
        errors = []
        if not cls.TOKEN:
            errors.append("TOKEN не указан в .env")
        if cls.OWNER_ID == 0:
            errors.append("OWNER_ID не указан в .env")
        return errors


# Создаём синглтон
config = Config()
