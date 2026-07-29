# AI Ticket Система - Kategorize Поддержка

## 🎯 Новый Особенность: Akıllı Kategorizasyon

AI теперь пользователя сообщение автоматически как kategorize ediyor ve ona по davranıyor:

### Kategoriler

1. **Жалоба** 🛡️
   - Доказательство хочет
   - Сообщение историю контроль eder
   - Jail наказание verebilir
   - Тяжелый состояние направление

2. **Soru** 💡
   - Panel, запись, команды
   - Роли, ekonomi, level
   - Общий информация
   - Краткий ve net cevaplar

3. **Teknik** 🔧
   - Bot çalışmıyor
   - Müzik/ses sorunları
   - Ticket açılmıyor
   - Panel sorunları
   - Решение комната

4. **Diğer** 📋
   - Belirsiz состояние
   - Общий помощь
   - Kategori tespiti

## 🔄 Как Çalışır?

```
Пользователь сообщение
       ↓
Kategori Tespiti
(anahtar kelime analizi)
       ↓
  ┌────────────┬────────────┬────────────┐
  ↓            ↓            ↓            ↓
Жалоба      Soru        Teknik       Diğer
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
    "🌐 Panel adresi duyurularda paylaşılır.
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

✅ **Более Tutarlı**: Каждый kategori kendi prompt'una комната
✅ **Более Быстрый**: AI kafası karışmaz, direkt ответитьir
✅ **Более Akıllı**: Kategori история korunur
✅ **Более Esnek**: Новый kategoriler kolayca добавл

## 🛠️ Teknik Детали

### Новый Fonksiyonlar

- `_detect_category(message, history)` → Kategori tespiti
- `_prompt_sikayet()` → Жалоба prompt'u
- `_prompt_soru()` → Soru prompt'u
- `_prompt_teknik()` → Teknik prompt'u
- `_prompt_diger()` → Общий prompt
- `_get_prompt_by_category(category)` → Prompt выбрать

### Обновл Fonksiyonlar

- `ai_ticket_response()` → Теперь kategoriye по prompt использовать
- `ai_ticket_greeting()` → Более общий приветствие сообщение

## 🚀 Использование

Hiçbir изменение gerekmez! `ticket.py` одинаковый şekilde работа devam eder.

```python
response, should_escalate, category, history = ai_ticket_response(
    user_message=message.content,
    history=state.get('history', []),
    guild_context={'guild_name': guild.name}
)
```

AI автоматически как kategoriyi tespit edip верно prompt'u использовать.

## 📊 Kategori Anahtar Kelimeleri

**Жалоба:**
- жалоба, оскорбление, мат, tehdit, taciz, zorbalık, saldırı, rapor, ihbar

**Вопрос:**
- как, panel, запись, вход, где, команда, помощь, информация, öğrenmek

**Teknik:**
- çalışmıyor, ошибка, bug, sorun, bozuk, açılmıyor, музыка, ses, voice

## 🎯 В конецuç

AI теперь hem жалоба çözüyor, hem sorulara ответитьiyor, hem de teknik поддержка sağlıyor — hepsi одинаковый ticket sisteminde!
