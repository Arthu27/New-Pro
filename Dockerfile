# ============================================================
#   HAKUMO BOT — Production Dockerfile
# ============================================================
FROM python:3.11-slim

# Системные зависимости
# ffmpeg убран из образа: система музыки /play снесена (2026-09-01),
# оставшиеся голосовые функции (PCM-тишина, voice-recv) ffmpeg не используют.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Зависимости Python (кэш слоёв)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём необходимые директории
RUN mkdir -p data logs backups plugins

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DISABLE_TUNNEL=1

# Веб-панель снята — порт 5001 не слушаем (docs/PANEL-REMOVED.md)

# Healthcheck: PID 1 (процесс бота) жив
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import os; os.kill(1, 0)" || exit 1

# Запуск
CMD ["python", "main.py"]
