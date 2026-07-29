# 🛡️ AI Moderator - Быстрый Сводка

## Ne Изменено?

AI теперь **только sohbet botu не**, **tam администратор модератор** gibi работает:

### Назад Система ❌
```
Пользователь: "X человек bana оскорбление etti"
AI: "Администрации направление..."
[Поддержка роль ping atılır]
```

### Новый Система ✅
```
Пользователь: "X человек bana оскорбление etti"
AI: "Доказательство загруз (ekran скриншот)"
Пользователь: [Ekran скриншот загруз]
AI: [Analiz eder, сообщение историю контроль eder]
AI: "✅ Jail наказание verildi: 30 dakika"
[Автоматически jail роль verilir]
[30 dakika после автоматически удален]
```

---

## 🎯 Новый Yetenekler

### 1. Доказательство Желание
- Ekran скриншот talep eder
- Пользователь ID хочет
- Olay детали sorar

### 2. Analiz
- Ekran скриншот inceler
- Сообщение историю контроль eder
- Время разница hesaplar

### 3. Karar Verme
- **Hafif**: Только предупреждение
- **Orta**: Jail 30-60 dakika
- **Тяжелый**: Jail 120 dakika + направление

### 4. Наказание Применитьma
- Jail роль verir (автоматически)
- Пользователю DM отправл
- Длительность bitince автоматически удален

---

## 📋 Работа Akışı

```
1. Пользователь жалоба eder
   ↓
2. AI доказательство хочет
   ↓
3. Пользователь ekran скриншот загруз
   ↓
4. AI analiz eder:
   • Ekran скриншот gerçek mi?
   • Сообщение история uyuşuyor mu?
   • Время разница 30 dakikadan az mı?
   ↓
5. AI karar verir:
   ├─ Hafif → Предупреждение
   ├─ Orta → Jail 30-60 dk
   └─ Тяжелый → Jail 120 dk + Направление
   ↓
6. Наказание примен (автоматически)
```

---

## 🛡️ Безопасность Önlemleri

### Sahte Жалоба Koruması
✅ Сообщение история контроль  
✅ Время разница контроль (30+ dakika = red)  
✅ Sahte жалоба yapana предупреждение  

### Jail Koruması
✅ Max jail: 120 dakika  
✅ Все действия loglanır  
✅ Администраторы override edebilir  

---

## 🎮 Пример Senaryo

### Успешно Jail

```
👤 Пользователь: "X человек bana оскорбление etti"

🤖 AI: "Жалоба incelemek для:
       1️⃣ Пользователь ID
       2️⃣ Olay описание
       3️⃣ ДОКАЗАТЕЛЬСТВО: Ekran скриншот"

👤 Пользователь: [Ekran скриншот загруз]
              "@user123 bana 'aptal' dedi, 5 dakika до"

🤖 AI: [Analiz ediyor...]
       [Сообщение историю контроль ediyor...]
       
       ✅ İnceleme завершено.
       
       📋 KARAR: Jail наказание verildi
       👤 Пользователь: @user123
       ⏱️ Длительность: 30 dakika
       📝 Причина: Tekrarlayan оскорбление
       
       Olayı çözmekte size администратор ekibimiz
       помощник olacaktır.

[user123'e автоматически jail роль verilir]
[30 dakika после автоматически удален]
```

---

## ⚙️ Настройки

```python
# cogs/ticket.py
AI_ENABLED = True  # AI moderator активен/pasif
MAX_AI_MESSAGES = 10  # Max сообщение количество
```

---

## 📊 Ciddiyet Seviyeleri

| Seviye | Пример | AI Aksiyonu |
|--------|----------|-------------|
| 🟢 Hafif | Tek мат, маленький tartışma | Только предупреждение |
| 🟡 Orta | Tekrarlayan оскорбление, spam | Jail 30-60 dk |
| 🔴 Тяжелый | Tehdit, nefret сказатьmi | Jail 120 dk + Направление |

---

## ✅ Avantajlar

**Пользователи:**
- ⚡ Anında moderasyon (7/24)
- 📋 Adil ve tutarlı kararlar

**Администраторы:**
- 🎯 Только ciddi состояние ilgilenirler
- 📊 Все действия loglanır

**Сервер:**
- 🛡️ Более быстрый moderasyon
- 📉 Более az toksik ortam

---

## 🚀 Test Et

1. Ticket aç
2. "X человек bana оскорбление etti" yaz
3. Sahte ekran скриншот загрузить
4. AI'nin jail данныеni видеть

---

**Система Hazır! 🛡️**

AI теперь tam администратор модератор gibi работает!
