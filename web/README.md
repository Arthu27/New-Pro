# web/ — веб-панель управления

Flask-панель «Aether Panel»: аналитика, логи, демки (mod-proof), тикеты,
роли/каналы, анти-рейд, экономика, настройки бота, **автоматика** и т.д.
Панель работает и рядом с ботом, и автономно (демо-режим:
`scripts/demo_panel.py`).

## Структура

```
web/
├── app.py              # приложение, логин, /api/guilds, инъекция panel_menu
├── wsgi.py             # точка входа для gunicorn
├── gunicorn_conf.py    # прод-сервер
├── websocket_server.py # realtime-канал панели
├── ai_*.py, complaint_analyzer.py, ...  # AI-слой панели
├── routes/
│   ├── _common.py      # импорты-контракт: Ctx, хелперы нормализации...
│   ├── <домен>.py      # register(ctx) — доменные маршруты
│   └── automation.py   # страница «Автоматика» + API настроек новых когов
├── routes_extra.py     # тонкий фасад: register_extra_routes(...) дёргает
│                       # register(ctx) всех доменов по порядку
├── templates/          # Jinja-шаблоны (base.html — каркас и сайдбар)
└── static/             # css/js/иконки (style.css — дизайн-система, app.js — клиентский кит)
```

## Как добавить страницу

1. `web/routes/<домен>.py` с `def register(ctx):` — внутри обычные
   `@app.route`, права через `ctx.login_required` / `ctx.role_required('admin')`.
2. Вписать домен в `web/routes_extra.py` (импорт + `_MODULES`).
3. Шаблон в `templates/`, пункт меню — в `services/panel_menu.py` (`MENU`),
   и если страница обслуживается когом — в `PAGE_COGS` (для гашения в
   MOD_ONLY).
4. Тест: `tests/test_automation_page.py` — эталон (рендер, API, валидация,
   линт).

## Железные правила

- **Эмодзи в шаблонах нет** — Font Awesome иконки. Сторож:
  `tests/test_panel_module_mode.py` + banned-список глобально.
- Данные из кода панели идут в `data/` только через те же неймспейсы
  `GuildData`, что читают коги (сквозное соглашение — см. `automation.py`).
- Метки времени — aware UTC (`_ts_to_utc_iso` нормализует вход).
- Харды брендов (Hakumo и т.п.) запрещены — имя сервера из API.
