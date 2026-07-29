# 🛡️ AI Moderator Система - Tam Руководство

## 🎯 Система Сводка

**Aether AI Moderator** теперь только sohbet botu не, **tam администратор bir модератор** gibi работает:

✅ Жалоба dinler ve **доказательство хочет**  
✅ Ekran скриншот analiz eder  
✅ Сообщение историю контроль eder  
✅ **Jail наказание verebilir** (автоматически)  
✅ Только gerçekten gerektiğinde администрации направление  

---

## 🔄 Новый Работа Akışı

### 1️⃣ Пользователь Ticket Açar

```
Пользователь: [Ticket açar]
    ↓
AI Moderator: "Merhabalar, ben Aether Moderator.
               Sorununuzu детали açıklayınız.
               
               Жалоба для:
               1️⃣ Пользователь: @пользователь
               2️⃣ Olay описание
               3️⃣ ДОКАЗАТЕЛЬСТВО: Ekran скриншот
               
               ⚠️ Доказательство жалобы действие alınmaz."
```

### 2️⃣ Пользователь Жалоба Eder

```
Пользователь: "X человек bana оскорбление etti"
    ↓
AI Moderator: "Жалоба incelemek для:
               • Пользователь ID'si или @mention
               • Ekran скриншот загруз
               • Ne время oldu belirtiniz"
```

### 3️⃣ Пользователь Доказательство Загруз

```
Пользователь: [Ekran скриншот загруз]
           "@user123 bana 'aptal' dedi, 10 dakika до"
    ↓
AI Moderator: [Ekran скриншот analiz eder]
              [Сообщение историю контроль eder]
              [Время разница контроль eder]
```

### 4️⃣ AI Karar Verir

**Senaryo A: Hafif Нарушение**
```
AI Moderator: "✅ İnceleme завершено.
               
               Выдать предупреждение пользователюildi.
               Tekrar ederse более тяжелый наказание alacaktır."
```

**Senaryo B: Orta Seviye Нарушение (Jail)**
```
AI Moderator: "✅ İnceleme завершено.
               
               📋 KARAR: Jail наказание verildi
               👤 Пользователь: @user123
               ⏱️ Длительность: 30 dakika
               📝 Причина: Tekrarlayan оскорбление
               
               Olayı çözmekte size администратор ekibimiz
               помощник olacaktır."
               
[Пользователю автоматически jail роль verilir]
[30 dakika после автоматически удален]
```

**Senaryo C: Тяжелый Нарушение (Jail + Направление)**
```
AI Moderator: "✅ İnceleme завершено.
               
               📋 KARAR: Jail наказание verildi
               👤 Пользователь: @user123
               ⏱️ Длительность: 120 dakika
               📝 Причина: Тяжелый оскорбление ve tehdit
               
               🔄 Администрации направление..."
               
[Jail verilir + Поддержка роль ping atılır]
```

**Senaryo D: Доказательство Yetersiz**
```
AI Moderator: "❌ Жалоба reddedildi.
               
               📋 ПРИЧИНА:
               - Сообщения uyuşmuyor
               - Время разница очень fazla (30+ dakika)
               - Ciddi нарушение tespit edilemedi
               
               ⚠️ Sahte жалоба наказание alabilir."
```

---

## 🎯 AI Moderator Yetenekleri

### ✅ Yapabilecekleri

1. **Доказательство Желание**
   - Ekran скриншот talep eder
   - Пользователь ID/mention хочет
   - Olay детали sorar

2. **Analiz**
   - Ekran скриншот inceler
   - Сообщение историю контроль eder
   - Время разница hesaplar (30+ dakika = red)

3. **Karar Verme**
   - Hafif: Только предупреждение
   - Orta: Jail 30-60 dakika
   - Тяжелый: Jail 120 dakika + направление

4. **Наказание Применитьma**
   - Jail роль verir (автоматически)
   - Пользователю DM отправл
   - Длительность bitince автоматически удален

5. **Loglama**
   - Все действия loglar
   - Mod log'a сохран
   - Web panel'de скриншот

### ❌ Yapamayacakları

- **Ban/Kick** (только администраторы)
- **Роль verme/alma** (jail hariç)
- **Канал/сервер настройк**
- **Ekonomi действия**

---

## 📊 Ciddiyet Seviyeleri

### 🟢 Hafif Seviye (Только Предупреждение)
- Tek seferlik мат
- Маленький tartışma
- Spam (1-2 сообщение)

**AI Aksiyonu**: Предупреждение сообщение

### 🟡 Orta Seviye (Jail 30-60 dakika)
- Tekrarlayan оскорбление
- Маленький düşürme
- Orta seviye spam
- Длительность rahatsız etme

**AI Aksiyonu**: Jail + описание

### 🔴 Тяжелый Seviye (Jail 120 dakika + Направление)
- Тяжелый оскорбление, tehdit
- Irkçılık, nefret сказатьmi
- Cinsel taciz
- Длительность spam/raid

**AI Aksiyonu**: Jail + администрации направление

---

## 🛠️ Teknik Детали

### Jail Система

**Jail Роль:**
- Автоматически создан (yoksa)
- Все в каналах `send_messages: False`
- Gri renk

**Jail Длительность:**
```python
1. Jail роль ver
2. Пользователю DM отправить
3. Ticket'e bildir
4. Mod log'a сохранить
5. X dakika bekle
6. Jail роль удалить
7. Пользователю DM отправить (serbest)
```

### Сообщение История Контроль

```python
1. В конец 50 сообщение al
2. Bot сообщение filtrele
3. Время damgalarını контроль et
4. Жалоба edilen пользователя сообщение bul
5. Ekran скриншот с приветствие
6. Время разница 30+ dakika ise → RED
```

### AI Action Parsing

AI cevabında особый tag'ler:

```
[JAIL]
user_id: 123456789
duration: 30
reason: Tekrarlayan оскорбление
```

```
[CHECK_HISTORY]
→ Сообщение историю контроль et
```

```
[ANALYZE_IMAGE]
→ Ekran скриншот analiz et
```

```
[ESCALATE]
Kategori: agir_ihlal
Aciklama: Tehdit içeren сообщения
```

---

## 🎮 Новый Команды

### Пользователь Для
- Ticket aç → AI Moderator автоматически приветствие
- Доказательство загрузить → AI analiz eder
- Апелляция et → Администрации направление

### Администратор Для

#### `/ticket-ai-stats`
AI moderator статистика показ
- Всего jail количество
- Reddedilen жалобы
- Ortalama решение длительность

#### `/ticket-ai-toggle`
AI moderator sistemini aç/закрыть

#### `/ticket-force-escalate`
Текущий ticket'i hemen администрации направление

---

## 📋 Пример Senaryolar

### Senaryo 1: Успешно Jail

```
👤 Пользователь: "X человек bana оскорбление etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "@user123 bana aptal dedi"
🤖 AI: [Analiz ediyor...]
       [Сообщение историю контроль ediyor...]
       ✅ "Jail наказание verildi: 30 dakika"
[user123'e jail роль verilir]
[30 dakika после автоматически удален]
```

### Senaryo 2: Reddedilen Жалоба

```
👤 Пользователь: "X человек bana оскорбление etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "2 saat до böyle dedi"
🤖 AI: [Analiz ediyor...]
       [Сообщение историю контроль ediyor...]
       ❌ "Жалоба reddedildi: Время разница очень fazla"
```

### Senaryo 3: Тяжелый Нарушение

```
👤 Пользователь: "X человек bana ölümle tehdit etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "Seni öldüreceğim dedi"
🤖 AI: [Analiz ediyor...]
       ✅ "Jail наказание verildi: 120 dakika"
       🔄 "Администрации направление..."
[Jail verilir + Поддержка роль ping atılır]
```

---

## ⚙️ Настройки

### `cogs/ticket.py`

```python
AI_ENABLED = True  # AI moderator активен/pasif
MAX_AI_MESSAGES = 10  # Max сообщение количество
```

### Jail Длительность

```python
# web/ai_helper.py в AI prompt'ta tanımlı:
Hafif: Jail yok (только предупреждение)
Orta: 30-60 dakika
Тяжелый: 120 dakika
```

---

## 🔒 Безопасность Önlemleri

### Sahte Жалоба Koruması
- Сообщение история контроль
- Время разница контроль (30+ dakika = red)
- Sahte жалоба yapana предупреждение

### Jail Kötüye Использование Koruması
- Max jail длительность: 120 dakika
- Все jail'ler loglanır
- Администраторы каждый время override edebilir

### Апелляция Mekanizması
- Пользователь апелляция ederse → автоматически направление
- Администраторы jail'i manuel удален

---

## 📊 Web Panel

### AI Moderator Logları
**URL**: `/ai-tickets`

**Показ**:
- Все AI moderator kararları
- Jail наказание
- Reddedilen жалобы
- Разговор история

---

## 🚀 Test Etmek Для

### Test 1: Успешно Jail
1. Ticket aç
2. "X человек bana оскорбление etti" yaz
3. Sahte ekran скриншот загрузить
4. AI'nin jail данныеni видеть

### Test 2: Reddedilen Жалоба
1. Ticket aç
2. "2 saat до X человек böyle dedi" yaz
3. AI'nin reddettiğini видеть

### Test 3: Направление
1. Ticket aç
2. "X человек bana ölümle tehdit etti" yaz
3. AI'nin jail verip направление видеть

---

## ✅ Avantajlar

**Пользователи Для:**
- ⚡ Anında moderasyon
- 🤖 7/24 активен
- 📋 Adil ve tutarlı kararlar

**Администраторы Для:**
- 🎯 Только ciddi состояние ilgilenirler
- 📊 Все действия loglanır
- 🔄 Желание время override edebilirler

**Сервер Для:**
- 🛡️ Более быстрый moderasyon
- 📉 Более az toksik ortam
- 📈 Более fazla пользователь memnuniyeti

---

## 🎓 Önemli Notlar

⚠️ **AI Moderator**:
- Только jail verebilir (ban/kick не)
- Доказательство olmadan наказание vermez
- Время разница контроль eder
- Тяжелый состояние администрации направление

✅ **Администраторы**:
- Каждый время AI'yi override edebilir
- Jail'i manuel удален
- AI'yi tamamen закрыт

---

**Система Hazır! 🛡️**

Теперь AI Moderator tam администратор gibi работает. Жалоба dinliyor, доказательство istiyor, analiz ediyor ve jail наказание verebiliyor!
