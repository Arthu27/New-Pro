"""
Централизованная конфигурация бота
Все настройки в одном месте
"""
import os
import logging
from dotenv import load_dotenv

# python-dotenv может печатать предупреждения о строках-комментариях (русские, с длинным тире и т.п.).
# Они безвредны — скрываем предупреждения, но продолжаем читать значения.
logging.getLogger("dotenv").setLevel(logging.ERROR)

# Загружаем .env из каталога этого файла (надёжно, независимо от рабочей директории)
# и с override=True, чтобы значение из .env всегда применялось.
# DOTENV_PATH — другой dotenv-файл (демо-превью панели стартует с
# config/panel_preview.env, чтобы боевой .env не смешивался с витриной).
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_env_path = os.environ.get("DOTENV_PATH") or os.path.join(_BASE_DIR, ".env")
if not os.path.isabs(_env_path):
    _env_path = os.path.join(_BASE_DIR, _env_path)
load_dotenv(_env_path, override=True)


def _get_token():
    """Токен из .env. Учитывает и ошибочный вариант с кириллической буквой
    (TОКEN), если он остался в файле от старого шаблона."""
    t = os.getenv("TOKEN", "") or os.getenv("TОКEN", "")
    return t.strip()


def clean_number(value):
    """Почистить строковое значение числа из .env от частых опечаток.

    Убирает пробелы, комментарий вплотную (2 # воркера), лишнюю запятую или
    точку с запятой на конце (2,). Возвращает None, если число не читается.
    """
    if value is None:
        return None
    s = str(value).strip().split("#", 1)[0].strip().rstrip(",;").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))  # допускает "2.0"
        except ValueError:
            return None


def _env_int(name: str, default: int) -> int:
    """Целое число из .env, устойчивое к опечаткам. При неудаче — default
    и предупреждение в предстартовый вывод."""
    parsed = clean_number(os.getenv(name))
    if parsed is None:
        raw = os.getenv(name)
        if raw not in (None, ""):
            logging.getLogger("hakumo.config").warning(
                "Config: значение %s=%r не является числом — используется %s",
                name, raw, default,
            )
        return default
    return parsed


def _env_int_list(name: str) -> list:
    """Список целых через запятую; битые элементы пропускаются с предупреждением."""
    out = []
    for part in (os.getenv(name, "") or "").split(","):
        parsed = clean_number(part)
        if parsed is not None:
            out.append(parsed)
        elif part.strip():
            logging.getLogger("hakumo.config").warning(
                "Config: элемент %r в %s не является числом — пропущен", part, name,
            )
    return out


class Config:
    """Основной класс конфигурации"""
    
    # === Discord ===
    TOKEN: str = _get_token()
    OWNER_ID: int = _env_int("OWNER_ID", 0)
    # Дополнительные владельцы бота: OWNER_IDS=123456,789012 (через запятую)
    OWNER_IDS: list = _env_int_list("OWNER_IDS")

    @classmethod
    def all_owner_ids(cls) -> set:
        """Все владельцы бота: OWNER_ID + OWNER_IDS (живое чтение .env)."""
        ids = set(_env_int_list("OWNER_IDS"))
        main = clean_number(os.getenv("OWNER_ID"))
        if main:
            ids.add(main)
        return ids
    MAIN_GUILD_ID: int = _env_int("MAIN_GUILD_ID", 0)
    COMMAND_PREFIX: str = "!"

    # Источник самообновления (/update): репозиторий и ветка на GitHub.
    UPDATE_REPO: str = os.getenv("UPDATE_REPO", "Arthu27/New-Pro")
    UPDATE_BRANCH: str = os.getenv("UPDATE_BRANCH", "main")

    # Дополнительные серверы для slash-команд (через запятую в .env: EXTRA_GUILD_IDS=111,222)
    EXTRA_GUILD_IDS: list = _env_int_list("EXTRA_GUILD_IDS")

    @classmethod
    def guild_objects(cls):
        """Список discord.Object серверов для регистрации guild-команд.

        Только сервер(ы) из .env: MAIN_GUILD_ID + EXTRA_GUILD_IDS.
        Если MAIN_GUILD_ID не задан — команды регистрируются глобально (любой сервер).
        """
        import discord
        ids = []
        if cls.MAIN_GUILD_ID:
            ids.append(cls.MAIN_GUILD_ID)
        ids.extend(cls.EXTRA_GUILD_IDS)
        if not ids:
            # .env пуст — глобальная регистрация (работает на любом сервере)
            return []
        return [discord.Object(id=g) for g in ids]
    
    # === Web Panel ===
    PORT: int = _env_int("PORT", 5001)
    # Хардкод-дефолт убран: зная ключ из исходников, любой мог подделать
    # cookie сессии панели. Если в .env пусто, web/app.py сам сгенерирует
    # случайный ключ и сохранит его в data/flask_secret.key
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    DISABLE_TUNNEL: bool = os.getenv("DISABLE_TUNNEL", "0") == "1"
    
    # === AI ===
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    AI_MODEL: str = os.getenv("AI_MODEL", "qwen2.5:3b")
    
    # === Database ===
    DB_PATH: str = os.path.join(_BASE_DIR, os.getenv("DB_PATH", "data/bot.db"))
    
    # === Logging ===
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")
    LOG_MAX_BYTES: int = _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)  # 10MB
    LOG_BACKUP_COUNT: int = _env_int("LOG_BACKUP_COUNT", 5)
    
    # === Gunicorn ===
    WEB_WORKERS: int = _env_int("WEB_WORKERS", 0)
    WEB_BIND: str = os.getenv("WEB_BIND", f"0.0.0.0:{PORT}")
    WEB_TIMEOUT: int = _env_int("WEB_TIMEOUT", 60)
    WEB_LOG_LEVEL: str = os.getenv("WEB_LOG_LEVEL", "warning")
    WEB_KEEPALIVE: int = _env_int("WEB_KEEPALIVE", 5)
    WEB_MAX_REQUESTS: int = _env_int("WEB_MAX_REQUESTS", 1000)
    
    # === Paths ===
    DATA_DIR: str = os.path.join(_BASE_DIR, "data")
    LOGS_DIR: str = os.path.join(_BASE_DIR, "logs")
    BACKUPS_DIR: str = os.path.join(_BASE_DIR, "backups")
    PLUGINS_DIR: str = os.path.join(_BASE_DIR, "plugins")
    
    # === Bot Settings ===
    BOT_STATUS: str = "online"  # online, idle, dnd, invisible
    BOT_ACTIVITY_TYPE: str = "watching"  # listening, playing, watching, competing
    BOT_ACTIVITY_TEXT: str = "Hakumo"
    
    # === Ticket Settings ===
    TICKET_CATEGORY_ID: int = _env_int("TICKET_CATEGORY_ID", 0)
    TICKET_SUPPORT_ROLE_ID: int = _env_int("TICKET_SUPPORT_ROLE_ID", 0)
    TICKET_TRANSCRIPT_CHANNEL_ID: int = _env_int("TICKET_TRANSCRIPT_CHANNEL_ID", 0)
    TICKET_MAX_OPEN: int = _env_int("TICKET_MAX_OPEN", 3)
    
    # === Moderation ===
    MOD_LOG_CHANNEL_ID: int = _env_int("MOD_LOG_CHANNEL_ID", 0)
    
    # === Limits ===
    MAX_WARNINGS_BEFORE_BAN: int = 5
    MAX_WARNINGS_BEFORE_MUTE: int = 3
    AUTO_CLOSE_HOURS: int = 48  # Ticket auto-close after hours


    # === Hardcoded IDs (from cogs) ===
    LOG_CHANNEL_ID: int = _env_int('LOG_CHANNEL_ID', 1491145640900558979)
    COMPANION_USER_ID: int = _env_int('COMPANION_USER_ID', 1353157554967937153)
    REQUIRED_ROLE_ID: int = _env_int('REQUIRED_ROLE_ID', 1474866958758576309)
    APPLY_CHANNEL_ID: int = _env_int('APPLY_CHANNEL_ID', 1484308081302306846)
    # Роли, выдаваемые после одобрения заявки в команду (0 = искать по имени)
    STAFF_HELPER_ROLE_ID: int = _env_int('STAFF_HELPER_ROLE_ID', 0)
    STAFF_MODERATOR_ROLE_ID: int = _env_int('STAFF_MODERATOR_ROLE_ID', 0)
    # Ветки заявок: куда отправлять «новую заявку» по должности
    # (0 = общий канал APPLY_CHANNEL_ID)
    STAFF_HELPER_CHANNEL_ID: int = _env_int('STAFF_HELPER_CHANNEL_ID', 0)
    STAFF_MODERATOR_CHANNEL_ID: int = _env_int('STAFF_MODERATOR_CHANNEL_ID', 0)
    # Кураторы: кого пинговать в ветке (0 = не пинговать)
    # Куратор заявок один на обе ветки; старые раздельные переменные
    # работают как запасное значение (если новая не задана)
    STAFF_CURATOR_ROLE_ID: int = _env_int('STAFF_CURATOR_ROLE_ID', 0)
    STAFF_HELPER_CURATOR_ROLE_ID: int = _env_int('STAFF_HELPER_CURATOR_ROLE_ID', 0)
    STAFF_MODERATOR_CURATOR_ROLE_ID: int = _env_int('STAFF_MODERATOR_CURATOR_ROLE_ID', 0)

    @classmethod
    def data_path(cls, *parts: str) -> str:
        """Абсолютный путь к файлу в data/ независимо от рабочей директории.

        Коги часто пишут в относительный 'data/...', что ломается, если бот
        запущен из другого каталога (cwd). Эта функция всегда резолвит путь
        к единому data-каталогу.
        """
        return os.path.join(cls.DATA_DIR, *parts)

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
