#!/usr/bin/env bash
# Запуск веб-панели Aether в демо-режиме (бот-токен не нужен).
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  AETHER - ВЕБ-ПАНЕЛЬ (демо-режим, без токена бота)"
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

echo "[3/4] Готовлю демо-данные..."
.venv/bin/python scripts/seed_demo_panel.py

echo
echo "[4/4] Запускаю панель..."
echo "    Адрес:  http://localhost:5001"
echo "    Логин:  owner"
echo "    Пароль: preview123"
echo "    Остановить: Ctrl+C"
echo

export DEMO_MODE=1
export SECRET_KEY=local-preview-secret
export PANEL_USER=owner
export PANEL_PASSWORD=preview123
export MAIN_GUILD_ID=987654321098765432
exec .venv/bin/python -m flask --app web.wsgi run --host 0.0.0.0 --port 5001
