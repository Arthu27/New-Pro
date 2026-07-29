# 🤖 AI Поддержка Ticket Система

## Обзор сервера

Aether Discord botu теперь **AI-powered поддержка ticket система** с donatıldı. Пользователи ticket açtığında, до AI asistan помощник olur. AI çözemediği состояние автоматически как администрации направление.

---

## 🎯 Особенности

### 1. **Автоматически AI Приветствие**
- Пользователь ticket açtığında AI asistan автоматически приветствие
- Sorun kategorisine по особый приветствие сообщения
- Пользователю ne yapması gerektiğini açıklar

### 2. **Akıllı Разговор**
- AI пользователя сообщение anlar ve Русский ответитьir
- Разговор историю hatırlar (son 20 сообщение)
- Profesyonel ama samimi ton

### 3. **Автоматически Направление**
AI aşağıdaki состояние автоматически направление:
- Ban/kick/timeout gibi наказание действия
- Роль verme/alma действия
- Канал/сервер настройк изменение
- Ciddi жалоба ve anlaşmazlıklar
- Ödeme/ekonomi sorunları
- Безопасность ve gizlilik konuları
- 10 сообщение limitine ulaşıldığında
- AI ошибка данныеnde

### 4. **Staff Контроль**
- Администратор сообщение attığında AI автоматически durur
- Staff желание время manuel направление yapabilir
- AI'yi tamamen закрыт выбрать

### 5. **Web Panel Entegrasyonu**
- Все AI разговор скриншот
- Статистика (собратьm ticket, AI işliyor, направление)
- Разговор историю детали inceleme

---

## 📋 Команды

### Пользователь Командыı
- **Ticket Aç**: Panel butonuna клик → AI автоматически приветствие

### Администратор Командыı

#### `/ticket-panel`
Ticket panelini отправл (AI поддержка)
- **Администратор**: Administrator

#### `/ticket-ai-stats`
AI поддержка статистика показ
- **Администратор**: Manage Сервер
- **Показ**: Всего ticket, AI işliyor, направление, ortalama сообщение

#### `/ticket-ai-toggle`
AI поддержка sistemini aç/закрыть
- **Администратор**: Administrator
- **Использование**: Toggle switch (tekrar çalıştır = tersine преобразовать)

#### `/ticket-force-escalate`
Текущий ticket'i hemen администрации направление
- **Администратор**: Manage Channels
- **Использование**: Ticket в канале çalıştır

#### `/ticket-добавить <user>`
Ticket'e пользователь добавить
- **Администратор**: Manage Channels

#### `/ticket-cikar <user>`
Ticket'ten пользователь удалить
- **Администратор**: Manage Channels

---

## 🔧 Teknik Детали

### Dosya Yapısı

```
cogs/ticket.py          # Ana ticket система + AI entegrasyonu
web/ai_helper.py        # AI fonksiyonları (OpenRouter Gemini 2.0 Flash)
web/routes_extra.py     # Web panel route'ları
web/templates/ai_tickets.html  # AI ticket скриншот sayfası
data/ai_tickets_<guild_id>.json  # AI ticket verileri
```

### Veri Yapısı

```json
{
  "channel_id": {
    "user_id": 123456789,
    "category": "sikayet|soru|teknik|diger",
    "history": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "status": "ai_handling|escalated|staff_handling",
    "ai_message_count": 5,
    "escalated_at": "2026-04-11T12:34:56",
    "staff_notified": true
  }
}
```

### AI Model
- **Provider**: OpenRouter
- **Model**: Google Gemini 2.0 Flash
- **Max Tokens**: 512 (быстрый yanıt для)
- **Temperature**: 0.7 (dengeli yaratıcılık)

### Limitler
- **Max AI Сообщение**: 10 (после автоматически направление)
- **History**: В конец 20 сообщение tutulur
- **Timeout**: 30 saniye (AI yanıt длительность)

---

## 🎨 Web Panel

### AI Поддержка Ticketları Sayfası
**URL**: `/ai-tickets`  
**Администратор**: Mod+

**Особенности**:
- Все активен AI ticket'ları скриншот
- Статистика kartları (собратьm, AI işliyor, направление, staff)
- Каждый ticket для:
  - Канал имя
  - Пользователь имя
  - Kategori
  - AI сообщение количество
  - Направление время
  - Разговор историю скриншот butonu

**Разговор Modal**:
- Пользователь ve AI сообщение ayrı renklerde показ
- Время damgası yok (только содержимое)
- ESC tuşu или dışarı клик закрыт

---

## 🚀 Использование Senaryoları

### Senaryo 1: Basit Soru
1. Пользователь ticket açar
2. AI приветствие: "Merhaba! Sana как помощник olabilirim?"
3. Пользователь: "Bot команды как использовать?"
4. AI: "/help команду использовать все команды видеть..."
5. Пользователь memnun, ticket'i закрыт

### Senaryo 2: Жалоба (Направление)
1. Пользователь ticket açar
2. AI приветствие
3. Пользователь: "X человек bana оскорбление etti, ban atın"
4. AI: "Bu konuda администрации направление..."
5. AI автоматически направление, поддержка роль ping atar
6. Администратор gelir, konuyu ele получает

### Senaryo 3: Staff Müdahalesi
1. Пользователь ticket açar
2. AI konuşuyor
3. Администратор сообщение atar
4. AI автоматически durur
5. Администратор konuyu ele получает

### Senaryo 4: Max Сообщение Limiti
1. Пользователь ticket açar
2. AI 10 сообщение ответитьir
3. Hala решение yok
4. AI автоматически направление: "Разговор limiti aşıldı, администраторы devralıyor"

---

## ⚙️ Настройки

### `cogs/ticket.py` в:

```python
AI_ENABLED = True  # AI sistemini активен/pasif yap
MAX_AI_MESSAGES = 10  # AI'nin max сколько сообщение cevaplayacağı
```

### AI System Prompt Редактироватьme
`web/ai_helper.py` → `_ticket_system_prompt()` fonksiyonu

---

## 🐛 Ошибка Состояние

### AI Ошибка Verirse
- Автоматически направление yapılır
- Пользователю: "Система ошибка, администраторы devralıyor"
- Поддержка роль ping atılır

### Ollama/OpenRouter Erişilemezse
- Graceful fallback
- Ticket normal şekilde açılır (AI olmadan)
- Поддержка роль hemen ping atılır

### Ticket Закрыт
- AI state автоматически temizlenir
- Transcript сохран (AI сообщения dahil)

---

## 📊 Статистика

### Команда с: `/ticket-ai-stats`
- Всего ticket количество
- AI işliyor (сколько tane)
- Направление (сколько tane)
- Staff işliyor (сколько tane)
- Всего AI сообщение количество
- Ortalama сообщение/ticket

### Web Panel: `/ai-tickets`
- Видеть kartlar
- Filtreleme (yakında)
- Arama (yakında)

---

## 🔮 Gelecek Особенности

- [ ] Kategori выбор (ticket açarken dropdown)
- [ ] AI öğrenme (успешно решение)
- [ ] Çoklu dil desteği
- [ ] Sentiment analizi (пользователь memnuniyeti)
- [ ] Автоматически ticket закрыт (AI çözdüyse)
- [ ] AI performans metrikleri
- [ ] Custom AI promptları (сервер основанный на)

---

## 📝 Notlar

- AI только Русский konuşur
- AI никогда администратор gerektiren действие yapmaz
- Все AI разговор loglanır
- Staff каждый время AI'yi override edebilir
- AI ticket система tamamen opsiyonel (закрыт)

---

## 🎓 Eğitim

### Администраторы Для
1. `/ticket-ai-stats` с состояние контроль edin
2. `/ai-tickets` sayfasından разговор inceleyin
3. Gerekirse `/ticket-force-escalate` с manuel направление
4. AI'yi закрыт для `/ticket-ai-toggle`

### Пользователи Для
- Ticket açın, AI size помощник olacak
- Детали описание yapın
- AI çözemezse автоматически направление
- Sabırlı olun, AI öğreniyor 🤖

---

**Geliştirici**: Kiro AI  
**Дата**: 11 Nisan 2026  
**Versiyon**: 1.0.0
