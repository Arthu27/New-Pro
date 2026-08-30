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

# ── Авто-поднятие: VDS ─────────────────────────────────────────────
# Процесс бота может умереть (нехватка памяти на маленьком VDS, краш,
# перезагрузка сервера). Этот цикл поднимает его снова через 5 секунд.
# Внутри main.py свой цикл переподключения к Discord — сюда попадаем
# только если упал сам процесс. Код 7 = неверный токен (чинить .env).
# Для настоящей надёжности поставь systemd-службу: deploy/VDS-SETUP.md
while true; do
    .venv/bin/python main.py
    CODE=$?
    if [ "$CODE" -eq 7 ]; then
        echo "  [СТОП] Токен Discord неверный. Исправь TOKEN в .env и запусти снова."
        exit 7
    fi
    # ВАЖНО: каждый выход процесса — в журнал (код + время). Раньше бот
    # «сидел 14 часов и сам перезапустился» без следов: причина (краш/OOM/
    # сигнал) теперь видна в logs/bot_restarts.log и data/run_log.json.
    mkdir -p logs
    {
        echo "[$(date '+%F %T')] Бот завершился: код $CODE (аптайм см. data/run_log.json)"
    } >> logs/bot_restarts.log
    echo "  [ПЕРЕЗАПУСК] Бот завершился (код $CODE). Поднимаю через 5 сек..."
    echo "  (причина: logs/bot_restarts.log, история: data/run_log.json)"
    echo "  (остановить полностью: Ctrl+C во время паузы или закрыть окно)"
    sleep 5
done
