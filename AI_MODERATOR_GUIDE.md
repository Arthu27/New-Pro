# 🛡️ AI Moderator Система - Tam Руководство

## 🎯 Система Сводка

**Aether AI Moderator** теперь только sohbet botu не, **tam администратор один модератор** gibi работает:

✅ Жалоба dinler ve **доказательство хочет**  
✅ Ekran скриншот anполучитьiz eder  
✅ Сообщение историю контроль eder  
✅ **Jail наказание выдатьebilir** (автоматически)  
✅ Только gerчekten gerektiгinde администрации направление  

---

## 🔄 Новый Работа Akышы

### 1️⃣ Пользователь Ticket Открытьar

```
Пользователь: [Ticket открытьar]
    ↓
AI Moderator: "Merhabполучитьar, ben Aether Moderator.
               Sorununuzu детали открытьыklмесяцыnыz.
               
               Жалоба для:
               1️⃣ Пользователь: @пользователь
               2️⃣ Olмесяц описание
               3️⃣ ДОКАЗАТЕЛЬСТВО: Ekran скриншот
               
               ⚠️ Доказательство жалобы действие получитьыnmaz."
```

### 2️⃣ Пользователь Жалоба Eder

```
Пользователь: "X человек bana оскорбление etti"
    ↓
AI Moderator: "Жалоба incelemek для:
               • Пользователь ID'si или @mentiдесять
               • Ekran скриншот загруз
               • Ne время oldu belirtiniz"
```

### 3️⃣ Пользователь Доказательство Загруз

```
Пользователь: [Ekran скриншот загруз]
           "@user123 bana 'aptполучить' dedi, 10 dakika до"
    ↓
AI Moderator: [Ekran скриншот anполучитьiz eder]
              [Сообщение историю контроль eder]
              [Время разница контроль eder]
```

### 4️⃣ AI Karar Выдатьir

**Senaryo A: Hafif Нарушение**
```
AI Moderator: "✅ Иnceleme завершено.
               
               Выдать предупреждение пользователюildi.
               Tekrar ederse более тяжелый наказание получитьacaktыr."
```

**Senaryo B: Orta Уровень Нарушение (Jail)**
```
AI Moderator: "✅ Иnceleme завершено.
               
               📋 KARAR: Jail наказание выдатьildi
               👤 Пользователь: @user123
               ⏱️ Длительность: 30 dakika
               📝 Причина: Tekrarlмесяцan оскорбление
               
               Olмесяцы чёzmekte size администратор ekibimiz
               помощник olacaktыr."
               
[Пользователю автоматически jail роль выдатьilir]
[30 dakika после автоматически удален]
```

**Senaryo C: Тяжелый Нарушение (Jail + Направление)**
```
AI Moderator: "✅ Иnceleme завершено.
               
               📋 KARAR: Jail наказание выдатьildi
               👤 Пользователь: @user123
               ⏱️ Длительность: 120 dakika
               📝 Причина: Тяжелый оскорбление ve tehdit
               
               🔄 Администрации направление..."
               
[Jail выдатьilir + Поддержка роль ping atыlыr]
```

**Senaryo D: Доказательство Yetersiz**
```
AI Moderator: "❌ Жалоба отклонено.
               
               📋 ПРИЧИНА:
               - Сообщения uyuшmuyor
               - Время разница очень fazla (30+ dakika)
               - Ciddi нарушение tespit edilemedi
               
               ⚠️ Sahte жалоба наказание получитьabilir."
```

---

## 🎯 AI Moderator Yetenдобавитьri

### ✅ Yapabilecдобавитьri

1. **Доказательство Желание**
   - Ekran скриншот tполучитьep eder
   - Пользователь ID/mentiдесять хочет
   - Olмесяц детали sorar

2. **Anполучитьiz**
   - Ekran скриншот inceler
   - Сообщение историю контроль eder
   - Время разница hesaplar (30+ dakika = red)

3. **Karar Выдатьme**
   - Hafif: Только предупреждение
   - Orta: Jail 30-60 dakika
   - Тяжелый: Jail 120 dakika + направление

4. **Наказание Применитьma**
   - Jail роль выдатьir (автоматически)
   - Пользователю DM отправл
   - Длительность bitince автоматически удален

5. **Loglama**
   - Все действия loglar
   - Mod log'a сохран
   - Web panel'de скриншот

### ❌ Yapamмесяцacaklarы

- **Ban/Kick** (только администраторы)
- **Роль выдатьme/получитьma** (jail hariч)
- **Канал/сервер настройк**
- **Ekдесятьomi действия**

---

## 📊 Ciddiyet Уровеньleri

### 🟢 Hafif Уровень (Только Предупреждение)
- Tek seferlik мат
- Маленький tartышma
- Spam (1-2 сообщение)

**AI Aksiyдесятьu**: Предупреждение сообщение

### 🟡 Orta Уровень (Jail 30-60 dakika)
- Tekrarlмесяцan оскорбление
- Маленький dюшюrme
- Orta уровень spam
- Длительность rahatsыz etme

**AI Aksiyдесятьu**: Jail + описание

### 🔴 Тяжелый Уровень (Jail 120 dakika + Направление)
- Тяжелый оскорбление, tehdit
- Irkчыlыk, nefret сказатьmi
- Cinsel taciz
- Длительность spam/raid

**AI Aksiyдесятьu**: Jail + администрации направление

---

## 🛠️ Teknik Детали

### Jail Система

**Jail Роль:**
- Автоматически создан (yoksa)
- Все в каналах `send_messages: Fполучитьse`
- Gri renk

**Jail Длительность:**
```pythдесять
1. Jail роль выдать
2. Пользователю DM отправить
3. Ticket'e bildir
4. Mod log'a сохранить
5. X dakika bдобавить
6. Jail роль удалить
7. Пользователю DM отправить (serbest)
```

### Сообщение История Контроль

```pythдесять
1. В конец 50 сообщение получить
2. Bot сообщение filtrele
3. Время damgполучитьarыnы контроль et
4. Жалоба edilen пользователя сообщение bul
5. Ekran скриншот с приветствие
6. Время разница 30+ dakika ise → RED
```

### AI Actiдесять Parsing

AI cevabыnda особый tag'ler:

```
[JAIL]
user_id: 123456789
duratiдесять: 30
reaпоследний: Tekrarlмесяцan оскорбление
```

```
[CHECK_HISTORY]
→ Сообщение историю контроль et
```

```
[ANALYZE_IMAGE]
→ Ekran скриншот anполучитьiz et
```

```
[ESCALATE]
Kategori: agir_ihlполучить
Aciklama: Tehdit iчeren сообщения
```

---

## 🎮 Новый Команды

### Пользователь Для
- Ticket открыть → AI Moderator автоматически приветствие
- Доказательство загрузить → AI anполучитьiz eder
- Апелляция et → Администрации направление

### Администратор Для

#### `/ticket-ai-stats`
AI moderator статистика показ
- Всего jail количество
- Reddedilen жалобы
- Ortполучитьama решение длительность

#### `/ticket-ai-toggle`
AI moderator системаni открыть/закрыть

#### `/ticket-force-escполучитьate`
Текущий ticket'i hemen администрации направление

---

## 📋 Пример Senaryolar

### Senaryo 1: Успешно Jail

```
👤 Пользователь: "X человек bana оскорбление etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "@user123 bana aptполучить dedi"
🤖 AI: [Anполучитьiz ediyor...]
       [Сообщение историю контроль ediyor...]
       ✅ "Jail наказание выдатьildi: 30 dakika"
[user123'e jail роль выдатьilir]
[30 dakika после автоматически удален]
```

### Senaryo 2: Reddedilen Жалоба

```
👤 Пользователь: "X человек bana оскорбление etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "2 время до bёyle dedi"
🤖 AI: [Anполучитьiz ediyor...]
       [Сообщение историю контроль ediyor...]
       ❌ "Жалоба отклонено: Время разница очень fazla"
```

### Senaryo 3: Тяжелый Нарушение

```
👤 Пользователь: "X человек bana ёlюmle tehdit etti"
🤖 AI: "Доказательство загруз"
👤 Пользователь: [Ekran скриншот] "Seni ёldюreceгim dedi"
🤖 AI: [Anполучитьiz ediyor...]
       ✅ "Jail наказание выдатьildi: 120 dakika"
       🔄 "Администрации направление..."
[Jail выдатьilir + Поддержка роль ping atыlыr]
```

---

## ⚙️ Настройки

### `cogs/ticket.py`

```pythдесять
AI_ENABLED = True  # AI moderator активен/неактивный
MAX_AI_MESSAGES = 10  # Max сообщение количество
```

### Jail Длительность

```pythдесять
# web/ai_helper.py в AI prompt'ta tanыmlы:
Hafif: Jail yok (только предупреждение)
Orta: 30-60 dakika
Тяжелый: 120 dakika
```

---

## 🔒 Безопасность Ёnlemleri

### Sahte Жалоба Защитаsы
- Сообщение история контроль
- Время разница контроль (30+ dakika = red)
- Sahte жалоба yapana предупреждение

### Jail Kёtучастник Использование Защитаsы
- Max jail длительность: 120 dakika
- Все jail'ler loglanыr
- Администраторы каждый время oвыдатьride edebilir

### Апелляция Mekanizmasы
- Пользователь апелляция ederse → автоматически направление
- Администраторы jail'i manuel удален

---

## 📊 Web Panel

### AI Moderator Loglarы
**URL**: `/ai-tickets`

**Показ**:
- Все AI moderator kararlarы
- Jail наказание
- Reddedilen жалобы
- Разговор история

---

## 🚀 Тест Etmek Для

### Тест 1: Успешно Jail
1. Ticket открыть
2. "X человек bana оскорбление etti" yaz
3. Sahte ekran скриншот загрузить
4. AI'nin jail данныеni видеть

### Тест 2: Reddedilen Жалоба
1. Ticket открыть
2. "2 время до X человек bёyle dedi" yaz
3. AI'nin отклонитьtiгini видеть

### Тест 3: Направление
1. Ticket открыть
2. "X человек bana ёlюmle tehdit etti" yaz
3. AI'nin jail выдатьip направление видеть

---

## ✅ Avantajlar

**Пользователи Для:**
- ⚡ Anыnda moderasyдесять
- 🤖 7/24 активен
- 📋 Adil ve tutarlы kararlar

**Администраторы Для:**
- 🎯 Только ciddi состояние ilgilenirler
- 📊 Все действия loglanыr
- 🔄 Желание время oвыдатьride edebilirler

**Сервер Для:**
- 🛡️ Более быстрый moderasyдесять
- 📉 Более az toksik ortam
- 📈 Более fazla пользователь memnuniyeti

---

## 🎓 Ёnemli Notlar

⚠️ **AI Moderator**:
- Только jail выдатьebilir (ban/kick не)
- Доказательство olmadan наказание выдатьmez
- Время разница контроль eder
- Тяжелый состояние администрации направление

✅ **Администраторы**:
- Каждый время AI'yi oвыдатьride edebilir
- Jail'i manuel удален
- AI'yi готовоen закрыт

---

**Система Готов! 🛡️**

Теперь AI Moderator tam администратор gibi работает. Жалоба dinliyor, доказательство istiyor, anполучитьiz ediyor ve jail наказание выдатьebiliyor!
