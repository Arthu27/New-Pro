# AI Ticket Система - Kategorize Поддержка

## 🎯 Новый Особенность: Akыllы Kategorizasyдесять

AI теперь пользователя сообщение автоматически как kategorize ediyor ve десятьa по davranыyor:

### Kategoriler

1. **Жалоба** 🛡️
   - Доказательство хочет
   - Сообщение историю контроль eder
   - Jail наказание выдатьebilir
   - Тяжелый состояние направление

2. **Soru** 💡
   - Panel, запись, команды
   - Роли, ekдесятьomi, level
   - Общий информация
   - Краткий ve net cevaplar

3. **Teknik** 🔧
   - Bot работатьmыyor
   - Mюzik/ses sorunlarы
   - Ticket открытьыlmыyor
   - Panel sorunlarы
   - Решение комната

4. **Diгer** 📋
   - Belirsiz состояние
   - Общий помощь
   - Kategori tespiti

## 🔄 Как Работатьыr?

```
Пользователь сообщение
       ↓
Kategori Tespiti
(anahtar kelime anполучитьizi)
       ↓
  ┌────────────┬────────────┬────────────┐
  ↓            ↓            ↓            ↓
Жалоба      Soru        Teknik       Diгer
Prompt       Prompt      Prompt       Prompt
  ↓            ↓            ↓            ↓
Доказательство желание   Cevapla     Решение sun    Направление
```

## 📝 Пример

### Жалоба
```
Пользователь: "X человек bana оскорбление etti"
AI: [Жалоба prompt'u активен]
    "📋 Жалоба incelemek для доказательство загруз..."
```

### Soru
```
Пользователь: "Panel как использовать?"
AI: [Soru prompt'u активен]
    "🌐 Panel adresi duyurularda pмесяцlaшыlыr.
    Discord с вход yapabilirsin..."
```

### Teknik
```
Пользователь: "Bot ответитьmiyor"
AI: [Teknik prompt'u активен]
    "🔧 Slash команды (/) использовать musun?
    /help команду dene..."
```

## 🎨 Avantajlar

✅ **Более Tutarlы**: Каждый kategori kendi prompt'una комната
✅ **Более Быстрый**: AI kafasы karышmaz, direkt ответитьir
✅ **Более Akыllы**: Kategori история korunur
✅ **Более Esnek**: Новый kategoriler kolмесяцca добавл

## 🛠️ Teknik Детали

### Новый Fдесятьksiyдесятьlar

- `_detect_category(message, history)` → Kategori tespiti
- `_prompt_sikмесяцet()` → Жалоба prompt'u
- `_prompt_soru()` → Soru prompt'u
- `_prompt_teknik()` → Teknik prompt'u
- `_prompt_diger()` → Общий prompt
- `_get_prompt_by_category(category)` → Prompt выбрать

### Обновл Fдесятьksiyдесятьlar

- `ai_ticket_respдесятьse()` → Теперь kategoriye по prompt использовать
- `ai_ticket_greeting()` → Более общий приветствие сообщение

## 🚀 Использование

Hiчодин изменение gerekmez! `ticket.py` одинаковый шekilde работа продолжить eder.

```pythдесять
respдесятьse, should_escполучитьate, category, history = ai_ticket_respдесятьse(
    user_message=message.cдесятьtent,
    history=state.get('history', []),
    guild_cдесятьtext={'guild_name': guild.name}
)
```

AI автоматически как kategoriyi tespit edip верно prompt'u использовать.

## 📊 Kategori Anahtar Kelimeleri

**Жалоба:**
- жалоба, оскорбление, мат, tehdit, taciz, zorbполучитьыk, sполучитьdыrы, rapor, ihbar

**Вопрос:**
- как, panel, запись, вход, где, команда, помощь, информация, ёгrenmek

**Teknik:**
- работатьmыyor, ошибка, bug, sorun, bozuk, открытьыlmыyor, музыка, ses, voice

## 🎯 В конецuч

AI теперь hem жалоба чёzюyor, hem sorulara ответитьiyor, hem de teknik поддержка saгlыyor — hepsi одинаковый ticket системаnde!
