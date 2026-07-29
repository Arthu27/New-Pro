# 🤖 AI Поддержка Ticket Система - Быстрый Сводка

## Ne Yaptık?

Aether botuna **AI-powered поддержка система** добавить. Теперь пользователи ticket açtığında:

1. **AI автоматически приветствие** ve помощник olmaya çalışır
2. **Basit вопросы çözer** (bot команды, общий информация)
3. **Çözemediği состояние администрации направление** (жалоба, ban talebi, vb.)

---

## Как Работает?

### Пользователь Tarafı
```
Пользователь ticket açar
    ↓
AI: "Merhaba! Sana как помощник olabilirim?"
    ↓
Пользователь sorusunu sorar
    ↓
AI ответитьir ИЛИ администрации направление
```

### Направление Состояние
AI şunlarda автоматически направление:
- ❌ Ban/kick/timeout talepleri
- ❌ Роль verme/alma
- ❌ Сервер настройк
- ❌ Ciddi жалобы
- ❌ 10 сообщение limitine ulaşıldığında
- ❌ AI ошибка данныеnde

---

## Новый Команды

### `/ticket-ai-stats`
AI статистика показ (сколько ticket, сколько направление, vb.)

### `/ticket-ai-toggle`
AI sistemini aç/закрыть

### `/ticket-force-escalate`
Текущий ticket'i hemen администрации направление

---

## Web Panel

**Новый Sayfa**: `/ai-tickets`

- Все AI разговор скриншот
- Статистика (собратьm, AI işliyor, направление)
- Каждый ticket'in разговор историю incele

**Menüde**: Статистика → 🤖 AI Поддержка Ticketları

---

## Настройки

`cogs/ticket.py` dosyasında:

```python
AI_ENABLED = True  # AI'yi закрыть/aç
MAX_AI_MESSAGES = 10  # AI max сколько сообщение cevaplasın
```

---

## Пример Использование

### ✅ AI Çözebilir
**Пользователь**: "Bot команды как использовать?"  
**AI**: "/help команду использовать все команды видеть..."

### 🔄 AI Направление
**Пользователь**: "X человек bana оскорбление etti, ban atın"  
**AI**: "Bu konuda администрации направление..."  
*[Поддержка роль ping atılır]*

---

## Teknik Детали

- **AI Model**: OpenRouter Gemini 2.0 Flash
- **Dil**: Только Русский
- **Veri**: `data/ai_tickets_<guild_id>.json`
- **Max Сообщение**: 10 (после автоматически направление)
- **History**: В конец 20 сообщение tutulur

---

## Önemli Notlar

✅ AI никогда администратор gerektiren действие yapmaz  
✅ Staff сообщение attığında AI автоматически durur  
✅ Все разговор loglanır  
✅ AI закрыт (`/ticket-ai-toggle`)  
✅ Staff каждый время manuel направление yapabilir  

---

## Test Etmek Для

1. Ticket aç (panel butonu)
2. AI'nin приветствие сообщение видеть
3. Basit bir soru sor (напр.: "bot команды nedir?")
4. AI'nin cevabını видеть
5. Şimdi жалоба et (напр.: "X человек spam yapıyor")
6. AI'nin направление yaptığını видеть

---

**Hazır! 🚀**

Теперь botun AI поддержка ticket система var. Пользователи более быстрый помощь alacak, администраторы более az basit soruyla uğraşacak.
