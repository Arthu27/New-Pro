# cogs/ — модули бота

Каждый файл — модуль Discord-бота (cog), загружаемый при старте из `main.py`.
Каталог всех модулей с описаниями: [`docs/MODULES.md`](../docs/MODULES.md).

## Как устроен модуль

```python
# -*- coding: utf-8 -*-
"""Название (Name Cog)
=====================
Одна строка — что делает. Команды списком ниже.
"""
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

Полный каталог правил и готовый пример — любой свежий модуль
(`reminders.py`, `anti_alt.py`, `night_mode.py`).

## Железные конвенции (сторожит регрессия)

1. **Метки времени — только aware UTC**: `datetime.now(timezone.utc)`.
   `utcnow()` и naive `isoformat()` запрещены (ломали панель и возраст
   аккаунтов) — `tests/test_log_timestamps.py` роняет сборку за это.
2. **Хранилище — SQLite через `GuildData('<неймспейс>')`** (см. `db.py`),
   не JSON-файлы. Ключ `'settings'` — настройки сервера (их редактирует
   панель «Автоматика»).
3. **Ни одного молчаливого `except: pass/continue`** — каждое подавление
   подписано `log.debug(...)`. Сторож: `tests/test_housekeeping.py`.
4. **Никаких турецких единиц времени** (`dk/sa/sn`) — только русские
   ч/мин/сек. Сторож: `tests/test_voice_stats.py`.
5. **Декоративных эмодзи в сообщениях нет** — текст и типографика.
6. **Чистые функции выносим наверх модуля** (парсинг, форматирование,
   решения) — они тестируются без Discord-клиента, без токена.
7. Команды — `hybrid_command` (слэш + префикс сразу), модерские — под
   `@commands.has_permissions(...)`.
8. **Слеш-меню лимитировано (100 глобальных команд Discord)** — после
   загрузки каждого модуля `slash_budget.py` оставляет в меню только
   `KEEP_SLASH`, остальные команды живут на префиксе. Новая команда в
   слеш-меню попадает явно: именем из декоратора в `KEEP_SLASH`.
   Сторож: `tests/test_slash_budget.py` (реально грузит все коги).

## Режимы загрузки (cogs_policy.py)

- `MOD_ONLY=1` — грузятся только модерация и ядро (списки в
  `cogs_policy.py`: `CORE_COGS`, `MODERATION_COGS`).
- `DISABLED_COGS=a,b` — выключить точечно.
- `EXTRA_COGS=a,b` — вернуть поверх MOD_ONLY.

Новый модуль обязан быть классифицирован: если он модераторский —
впишите файл в `MODERATION_COGS`, иначе он автоматически попадёт в
«комьюнити» и будет спать в MOD_ONLY. Сторож классификации:
`tests/test_cogs_policy.py`.

Хелперы (`_card_style.py`, `embed_utils.py`, `icons.py`,
`leveling_engagement.py`) — не коги, импортируются другими модулями.

## Общие сервисы для когов

`services/text_format.py` — русские склонения, длительности
(`fmt_seconds`, `parse_duration`, `parse_deadline`, `rel_time`). Не
изобретайте свои «ч/мин» — берите отсюда.
