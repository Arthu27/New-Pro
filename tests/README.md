# tests/ — регрессионный полигон

Каждый файл `test_*.py` — самостоятельный скрипт **без токена Discord**,
печатающий `PASS:`/`FAIL:` по каждой проверке и финальную строку
`=== PASS N / FAIL M ===`. Код выхода: 0 — зелёно, 1 — есть падения.

## Запуск

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python scripts/run_tests.py        # вся регрессия + сводка
.venv/bin/python scripts/run_tests.py -v     # + вывод упавших наборов
.venv/bin/python tests/test_voice_stats.py   # один набор
```

## Контракт нового теста

```python
import os, sys, tempfile
_TMP = tempfile.mkdtemp(prefix='aether_x_test_')
os.chdir(_TMP)                                   # ИЗОЛЯЦИЯ: чужие data/ не трогаем
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')  # до импорта db!
```

- `check(ok, msg)` — счётчик PASS/FAIL, финал `=== PASS N / FAIL M ===`
  и `sys.exit(1 if FAIL else 0)`.
- Тестируем **чистые функции** когов (парсинг/решения/формат) — Discord
  не нужен. Flask-страницы — через `app.test_client()` +
  `client.session_transaction()` (фейковый логин `role: 'owner'`).
- Финалом — `shutil.rmtree(_TMP, ignore_errors=True)`.

## Сторожа качества (уже стоят на карауле)

| Тест | Что караулит |
| --- | --- |
| `test_housekeeping.py` | утечки sqlite, молчаливые except, покрытие `.env.example`, чистый корень |
| `test_log_timestamps.py` | aware-UTC метки, запрет `utcnow()`, naive-isoformat |
| `test_cogs_policy.py` | классификация когов (MOD_ONLY/CORE/MODERATION) консистентна |
| `test_panel_module_mode.py` | гашение пунктов меню в MOD_ONLY, эмодзи-сторож шаблонов |
| `test_voice_stats.py` | единый источник голосовой статистики, RU-единицы |
| `test_routes_layout.py` | фасад роутов худой, доменные модули на месте |
| `test_link_audit.py` | связи: fetch-URL vs роуты, inline-хендлеры vs функции, href/form/id |
| `test_pages_http.py` | все страницы меню → 200 владельцу, GET-API не 500, чистота от undefined |
| `test_css_audit.py` | CSS-баланс, переменные, @keyframes, палитра, чёрная гостевая зона |
| `test_contract_audit.py` | контракты GET-API (поля фронта), POST-smoke, целостность data/ |
| `test_a11y_audit.py` | доступность (alt/labels/имена кнопок), rel=noopener, баланс тегов рендера |
| `test_web_hygiene.py` | CSP без CDN, защитные заголовки, локальный sw.js, бюджеты ассетов |
| `test_ws_health.py` | живой WebSocket: handshake, ping/pong, 1008, broadcast |
| `test_icon_audit.py` | битые иконки FA, эмодзи-сторож, префиксы стилей, иконки меню |
| `test_http_semantics.py` | HEAD/405/404, MIME-типы, фазз query, битый JSON, бюджет рендера |
| `test_menu_audit.py` | меню→роуты Flask, уникальность путей, мёртвые шаблоны, конкурентность |
| `test_py_compile.py` | compileall всех .py, скан секретов/токенов, мёртвые route-модули |
| `test_state_roundtrip.py` | переходы состояния: создать→увидеть→изменить→удалить (роли/расписание/leveling) |
| `test_final_audit.py` | дубли роутов, детерминизм рендера, кодировки/BOM/мохибаке, трейлинг-слэш |
| `scripts/audit_to_letter.py` | аудит «до буквы»: кодировки/кракозябры/эмодзи/сущности, FA-иконки vs вендор, классы-сироты, мёртвые href, опечатки, баланс тегов/Jinja, дубли id, title, двойные пробелы в заголовках |
| `test_mod_rules_pro.py` | профи-фичи: правила с линками/картинками/миниатюрами (нормализация, валидация URL, публикация без двойной обёртки), статистика модераторов (действия/сроки/сообщения/голос, KPI), счётчик сообщений mod_activity |

Любая новая фича = логика-ядро чистое + тест по контракту выше.
