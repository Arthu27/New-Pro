#!/bin/bash

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       ЗАПУСК БОТА MOEBIUS        ║"
echo "  ╚═══════════════════════════════════════╝"
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

# .env dosyası kontrolü
if [ ! -f .env ]; then
    echo "  [ПРЕДУПРЕЖДЕНИЕ] .env файл не найден!"
    echo "  Пожалуйста создайте .env файл и добавьте TOKEN."
    echo ""
fi

# Gunicorn (production) установлен ли?
if python3 -c "import gunicorn" 2>/dev/null; then
    echo "  [ОК] Gunicorn найден (production WSGI)."
else
    echo "  [ИНФО] Gunicorn нет — pip install gunicorn можете установить через."
    echo "         (Иначе будет использован fallback Werkzeug)"
fi
echo ""
echo "  [ИНФО] Bot запускается..."
echo ""
python3 main.py
