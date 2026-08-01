# 🤖 AI Поддержка Ticket Система - Быстрый Сводка

## Ne Yaptыk?

Aether botuna **AI-powered поддержка система** добавить. Теперь пользователи ticket открытьtыгыnda:

1. **AI автоматически приветствие** ve помощник olmмесяцa работатьыr
2. **Basit вопросы чёzer** (bot команды, общий информация)
3. **Чёzemediгi состояние администрации направление** (жалоба, ban tполучитьebi, vb.)

---

## Как Работает?

### Пользователь Tarafы
```
Пользователь ticket открытьar
    ↓
AI: "Merhaba! Sana как помощник olabilirim?"
    ↓
Пользователь sorusunu sorar
    ↓
AI ответитьir ИЛИ администрации направление
```

### Направление Состояние
AI шunlarda автоматически направление:
- ❌ Ban/kick/timeout tполучитьepleri
- ❌ Роль выдатьme/получитьma
- ❌ Сервер настройк
- ❌ Ciddi жалобы
- ❌ 10 сообщение limitine ulaшыldыгыnda
- ❌ AI ошибка данныеnde

---

## Новый Команды

### `/ticket-ai-stats`
AI статистика показ (сколько ticket, сколько направление, vb.)

### `/ticket-ai-toggle`
AI системаni открыть/закрыть

### `/ticket-force-escполучитьate`
Текущий ticket'i hemen администрации направление

---

## Web Panel

**Новый Sмесяцfa**: `/ai-tickets`

- Все AI разговор скриншот
- Статистика (собратьm, AI iшliyor, направление)
- Каждый ticket'in разговор историю incele

**Menюde**: Статистика → 🤖 AI Поддержка Ticketlarы

---

## Настройки

`cogs/ticket.py` dosyasыnda:

```pythдесять
AI_ENABLED = True  # AI'yi закрыть/открыть
MAX_AI_MESSAGES = 10  # AI max сколько сообщение cevaplasыn
```

---

## Пример Использование

### ✅ AI Чёzebilir
**Пользователь**: "Bot команды как использовать?"  
**AI**: "/help команду использовать все команды видеть..."

### 🔄 AI Направление
**Пользователь**: "X человек bana оскорбление etti, ban atыn"  
**AI**: "Bu kдесятьuda администрации направление..."  
*[Поддержка роль ping atыlыr]*

---

## Teknik Детали

- **AI Model**: OpenRouter Gemini 2.0 Flash
- **Dil**: Только Русский
- **Выдатьi**: `data/ai_tickets_<guild_id>.jпоследний`
- **Max Сообщение**: 10 (после автоматически направление)
- **History**: В конец 20 сообщение tutulur

---

## Ёnemli Notlar

✅ AI никогда администратор gerektiren действие yapmaz  
✅ Staff сообщение attыгыnda AI автоматически durur  
✅ Все разговор loglanыr  
✅ AI закрыт (`/ticket-ai-toggle`)  
✅ Staff каждый время manuel направление yapabilir  

---

## Тест Etmek Для

1. Ticket открыть (panel butдесятьu)
2. AI'nin приветствие сообщение видеть
3. Basit один soru sor (напр.: "bot команды nedir?")
4. AI'nin cevabыnы видеть
5. Сейчас жалоба et (напр.: "X человек spam yapыyor")
6. AI'nin направление yaptыгыnы видеть

---

**Готов! 🚀**

Теперь botun AI поддержка ticket система var. Пользователи более быстрый помощь получитьacak, администраторы более az basit soruyla uгraшacak.
