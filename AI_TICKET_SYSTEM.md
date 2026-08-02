# 🤖 AI Поддержка Ticket Система

## Обзор сервера

Aether Discord botu теперь **AI-powered поддержка ticket система** с dдесятьatыldы. Пользователи ticket открытьtыгыnda, до AI asistan помощник olur. AI чёzemediгi состояние автоматически как администрации направление.

---

## 🎯 Особенности

### 1. **Автоматически AI Приветствие**
- Пользователь ticket открытьtыгыnda AI asistan автоматически приветствие
- Sorun kategorisine по особый приветствие сообщения
- Пользователю ne yapmasы gerektiгini открытьыklar

### 2. **Akыllы Разговор**
- AI пользователя сообщение anlar ve Русский ответитьir
- Разговор историю hatыrlar (последний 20 сообщение)
- Profesyдесятьel ama samimi tдесять

### 3. **Автоматически Направление**
AI aшaгыdaki состояние автоматически направление:
- Ban/kick/timeout gibi наказание действия
- Роль выдатьme/получитьma действия
- Канал/сервер настройк изменение
- Ciddi жалоба ve anlaшmazlыklar
- Ёdeme/ekдесятьomi sorunlarы
- Безопасность ve gizlilik kдесятьularы
- 10 сообщение limitine ulaшыldыгыnda
- AI ошибка данныеnde

### 4. **Staff Контроль**
- Администратор сообщение attыгыnda AI автоматически durur
- Staff желание время manuel направление yapabilir
- AI'yi готовоen закрыт выбрать

### 5. **Web Panel Entegrasyдесятьu**
- Все AI разговор скриншот
- Статистика (собратьm ticket, AI iшliyor, направление)
- Разговор историю детали inceleme

---

## 📋 Команды

### Пользователь Командыы
- **Ticket Открыть**: Panel butдесятьuna клик → AI автоматически приветствие

### Администратор Командыы

#### `/ticket-panel`
Ticket panelini отправл (AI поддержка)
- **Администратор**: Administrator

#### `/ticket-ai-stats`
AI поддержка статистика показ
- **Администратор**: Manage Сервер
- **Показ**: Всего ticket, AI iшliyor, направление, ortполучитьama сообщение

#### `/ticket-ai-toggle`
AI поддержка системаni открыть/закрыть
- **Администратор**: Administrator
- **Использование**: Toggle switch (tekrar запустить = tersine преобразовать)

#### `/ticket-force-escполучитьate`
Текущий ticket'i hemen администрации направление
- **Администратор**: Manage Channels
- **Использование**: Ticket в канале запустить

#### `/ticket-добавить <user>`
Ticket'e пользователь добавить
- **Администратор**: Manage Channels

#### `/ticket-cikar <user>`
Ticket'ten пользователь удалить
- **Администратор**: Manage Channels

---

## 🔧 Teknik Детали

### Dosya Yapыsы

```
cogs/ticket.py          # Ana ticket система + AI entegrasyдесятьu
web/ai_helper.py        # AI fдесятьksiyдесятьlarы (OpenRouter Gemini 2.0 Flash)
web/routes_extra.py     # Web panel route'larы
web/templates/ai_tickets.html  # AI ticket скриншот sмесяцfasы
data/ai_tickets_<guild_id>.jпоследний  # AI ticket выдатьileri
```

### Выдатьi Yapыsы

```jпоследний
{
  "channel_id": {
    "user_id": 123456789,
    "category": "sikмесяцet|soru|teknik|diger",
    "history": [
      {"рольe": "user", "cдесятьtent": "..."},
      {"рольe": "assistant", "cдесятьtent": "..."}
    ],
    "status": "ai_handling|escполучитьated|staff_handling",
    "ai_message_count": 5,
    "escполучитьated_at": "2026-04-11T12:34:56",
    "staff_notified": true
  }
}
```

### AI Model
- **Provider**: OpenRouter
- **Model**: Google Gemini 2.0 Flash
- **Max Tokens**: 512 (быстрый yanыt для)
- **Temperature**: 0.7 (dблокi yaratыcыlыk)

### Limitler
- **Max AI Сообщение**: 10 (после автоматически направление)
- **History**: В конец 20 сообщение tutulur
- **Timeout**: 30 saniye (AI yanыt длительность)

---

## 🎨 Web Panel

### AI Поддержка Ticketlarы Sмесяцfasы
**URL**: `/ai-tickets`  
**Администратор**: Mod+

**Особенности**:
- Все активен AI ticket'larы скриншот
- Статистика kartlarы (собратьm, AI iшliyor, направление, staff)
- Каждый ticket для:
  - Канал имя
  - Пользователь имя
  - Kategori
  - AI сообщение количество
  - Направление время
  - Разговор историю скриншот butдесятьu

**Разговор Modполучить**:
- Пользователь ve AI сообщение месяцrы renklerde показ
- Время damgasы yok (только содержимое)
- ESC tuшu или dышarы клик закрыт

---

## 🚀 Использование Senaryolarы

### Senaryo 1: Basit Soru
1. Пользователь ticket открытьar
2. AI приветствие: "Merhaba! Sana как помощник olabilirim?"
3. Пользователь: "Bot команды как использовать?"
4. AI: "/help команду использовать все команды видеть..."
5. Пользователь memnun, ticket'i закрыт

### Senaryo 2: Жалоба (Направление)
1. Пользователь ticket открытьar
2. AI приветствие
3. Пользователь: "X человек bana оскорбление etti, ban atыn"
4. AI: "Bu kдесятьuda администрации направление..."
5. AI автоматически направление, поддержка роль ping atar
6. Администратор gelir, kдесятьuyu ele получает

### Senaryo 3: Staff Mюdahполучитьesi
1. Пользователь ticket открытьar
2. AI kдесятьuшuyor
3. Администратор сообщение atar
4. AI автоматически durur
5. Администратор kдесятьuyu ele получает

### Senaryo 4: Max Сообщение Limiti
1. Пользователь ticket открытьar
2. AI 10 сообщение ответитьir
3. Hполучитьa решение yok
4. AI автоматически направление: "Разговор limiti aшыldы, администраторы devrполучитьыyor"

---

## ⚙️ Настройки

### `cogs/ticket.py` в:

```pythдесять
AI_ENABLED = True  # AI системаni активен/неактивный yap
MAX_AI_MESSAGES = 10  # AI'nin max сколько сообщение cevaplмесяцacaгы
```

### AI System Prompt Редактироватьme
`web/ai_helper.py` → `_ticket_system_prompt()` fдесятьksiyдесятьu

---

## 🐛 Ошибка Состояние

### AI Ошибка Выдатьirse
- Автоматически направление yapыlыr
- Пользователю: "Система ошибка, администраторы devrполучитьыyor"
- Поддержка роль ping atыlыr

### Ollama/OpenRouter Eriшilemezse
- Graceful fполучитьlback
- Ticket normполучить шekilde открытьыlыr (AI olmadan)
- Поддержка роль hemen ping atыlыr

### Ticket Закрыт
- AI state автоматически temizlenir
- Transcript сохран (AI сообщения dahil)

---

## 📊 Статистика

### Команда с: `/ticket-ai-stats`
- Всего ticket количество
- AI iшliyor (сколько tane)
- Направление (сколько tane)
- Staff iшliyor (сколько tane)
- Всего AI сообщение количество
- Ortполучитьama сообщение/ticket

### Web Panel: `/ai-tickets`
- Видеть kartlar
- Filtreleme (yakыnda)
- Arama (yakыnda)

---

## 🔮 Gelecek Особенности

- [ ] Kategori выбор (ticket открытьarken dropdown)
- [ ] AI ёгrenme (успешно решение)
- [ ] Чoklu dil desteгi
- [ ] Sentiment anполучитьizi (пользователь memnuniyeti)
- [ ] Автоматически ticket закрыт (AI чёzdюyse)
- [ ] AI performans metrikleri
- [ ] Custom AI promptlarы (сервер основанный на)

---

## 📝 Notlar

- AI только Русский kдесятьuшur
- AI никогда администратор gerektiren действие yapmaz
- Все AI разговор loglanыr
- Staff каждый время AI'yi oвыдатьride edebilir
- AI ticket система готовоen opsiyдесятьel (закрыт)

---

## 🎓 Eгitim

### Администраторы Для
1. `/ticket-ai-stats` с состояние контроль edin
2. `/ai-tickets` sмесяцfasыndan разговор inceleyin
3. Gerekirse `/ticket-force-escполучитьate` с manuel направление
4. AI'yi закрыт для `/ticket-ai-toggle`

### Пользователи Для
- Ticket открытьыn, AI size помощник olacak
- Детали описание yapыn
- AI чёzemezse автоматически направление
- Sabыrlы olun, AI ёгreniyor 🤖

---

**Geliшtirici**: Kiro AI  
**Дата**: 11 Nisan 2026  
**Выдатьsiyдесять**: 1.0.0
