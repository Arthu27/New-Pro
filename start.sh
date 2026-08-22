#!/bin/bash

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       ЗАПУСК БОТА MOEBIUS        ║"
echo "  ╚═══════════════════════════════════╝"
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "  [ОШИБКА] Python3 не найден!"
    echo "  Пожалуйста Python 3.8+ установите."
    echo ""
    exit 1
fi

echo "  [ОК] Python найден: $(python3 --version)"
echo ""

# ── Авто-установка зависимостей в виртуальное окружение ──
if [ ! -d ".venv" ]; then
    echo "  [1/3] Создаю виртуальное окружение (.venv)..."
    python3 -m venv .venv || {
        echo "  [ОШИБКА] Не удалось создать .venv (нужен пакет python3-venv)."
        exit 1
    }
fi

echo "  [2/3] Устанавливаю зависимости (все, что нужно боту)..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet
echo "  [ОК] Зависимости установлены"
echo ""

# .env
if [ ! -f .env ]; then
    echo "  [ПРЕДУПРЕЖДЕНИЕ] .env файл не найден!"
    echo "  Пожалуйста создайте .env файл и добавьте TOKEN."
    echo "  (Шаблон: .env.example)"
    echo ""
fi

# Gunicorn (production) установлен ли?
if .venv/bin/python -c "import gunicorn" 2>/dev/null; then
    echo "  [ОК] Gunicorn найден (production WSGI)."
else
    echo "  [ИНФО] Gunicorn нет — будет использован fallback Werkzeug."
fi
echo ""
echo "  [3/3] Bot запускается..."
echo ""
.venv/bin/python main.py
