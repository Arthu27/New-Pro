# 📚 Devnotes — архив заметок разработки

Сюда снесены исторические заметки и черновики фич, которые годами копились
в корне репозитория (аудит 2026-08: 19 файлов `.txt`/`.md` смешанного
RU/TR содержания).

**Важно:** это не актуальная документация, а архив «как это делали».
Актуальное состояние проекта описывает корневой `README.md` и код.

## Содержимое

### AI тикеты
- `AI_TICKET_SYSTEM.md` — концепция AI-тикет системы
- `AI_TICKET_FLOW.txt` — потоки/сценарии
- `AI_TICKET_COMPLETE_FEATURES.md` — полный список задуманных фич
- `AI_TICKET_MULTI_PARTY_SYSTEM.md` — многосторонние тикеты
- `AI_TICKET_KATEGORIZE.md` — категоризация (TR)
- `AI_TICKET_TEST.md` — заметки по тестированию
- `AI_TICKET_OZET.md` — сводка (TR)

### AI модератор
- `AI_MODERATOR_GUIDE.md` — гайд
- `AI_MODERATOR_FLOW.txt` — потоки
- `AI_MODERATOR_OZET.md` — сводка (TR)

### Прочее
- `AETHER_FEATURES_RU.txt` — общий обзор возможностей бота
- `TODO.md` — историческая сводка завершённых модулей (списка задач там нет)
- `GUNCELLEME_RU.txt`, `GUNCELLEME_LISTESI_RU.md` — списки обновлений
- `HIZLI_BASLANGIC.md` — быстрый старт (TR)
- `MODERN_PANEL_TASARIM.md` — дизайн-заметки панели (TR)
- `RATE_LIMITING_GUIDE.md` — ограничение частоты запросов
- `TAMAMLANAN_OZELLIKLER_OZET.md` — сводка сделанных фич (TR)
- `TICKET_FIXES.md` — фиксы тикетов

Корень держит чистым линт в `tests/test_housekeeping.py`:
новые `.txt`/`.md` в корень больше не пролезут незамеченными.
