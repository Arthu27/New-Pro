#!/usr/bin/env bash
# Запуск веб-панели Hakumo.
#   ./start_panel.sh          — БОЕВОЙ режим: токен, сервер и пароль из .env
#   ./start_panel.sh --demo   — демо-превью без бота (все данные выдуманные,
#                               настройки из config/panel_preview.env)
set -e
cd "$(dirname "$0")"

DEMO=0
if [ "${1:-}" = "--demo" ]; then
  DEMO=1
fi

echo "============================================================"
if [ "$DEMO" = "1" ]; then
  echo "  HAKUMO - ВЕБ-ПАНЕЛЬ (ДЕМО-превью: данные выдуманные!)"
else
  echo "  HAKUMO - ВЕБ-ПАНЕЛЬ (боевой режим, настройки из .env)"
fi
echo "============================================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ОШИБКА] Python 3 не найден. Установи: https://python.org"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "[1/4] Создаю виртуальное окружение..."
  python3 -m venv .venv
fi

echo "[2/4] Устанавливаю зависимости (только для панели)..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements-panel.txt --quiet

if [ "$DEMO" = "1" ]; then
  echo "[3/4] Готовлю демо-данные (выдуманный сервер, участники, логи)..."
  export DEMO_MODE=1
  .venv/bin/python scripts/seed_demo_panel.py
  # Панель читает пресет превью вместо боевого .env (см. config.py: DOTENV_PATH)
  export DOTENV_PATH=config/panel_preview.env
else
  echo "[3/4] Демо-посев пропущен (боевой режим — только реальные данные)."
  if [ ! -f .env ]; then
    echo
    echo "[ВНИМАНИЕ] .env не найден — панель не знает ни токена, ни твоего сервера."
    echo "           1) Скопируй шаблон:  cp .env.example .env"
    echo "           2) Заполни TOKEN и MAIN_GUILD_ID (ID твоего сервера)."
    echo "           Просто посмотреть витрину:  ./start_panel.sh --demo"
    echo
  fi
fi

PORT="${PANEL_PORT:-5001}"
echo "[4/4] Запускаю панель..."
echo "    Адрес:  http://localhost:${PORT}"
if [ "$DEMO" = "1" ]; then
  echo "    Логин:  owner"
  echo "    Пароль: preview123"
else
  echo "    Логин/пароль: из .env (PANEL_USER / PANEL_PASSWORD)"
fi
echo "    Остановить: Ctrl+C"
echo

exec .venv/bin/python -m flask --app web.wsgi run --host 0.0.0.0 --port "$PORT"
