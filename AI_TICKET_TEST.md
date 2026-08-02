# AI Ticket Система - Тест Senaryolarы

## 🧪 Тест Senaryolarы

### 1. Жалоба Тестi

**Senaryo:** Пользователь жалоба ediyor

```
Пользователь: "X человек bana оскорбление etti"
Bдобавитьnen: AI доказательство хочет
```

**Adыmlar:**
1. Ticket открыть
2. "X человек bana оскорбление etti" yaz
3. AI'nin доказательство желание контроль et
4. Ekran скриншот загрузить
5. AI'nin сообщение историю контроль ettiгini видеть
6. AI'nin karar данныеni видеть (jail или red)

**Bдобавитьnen Cevap:**
```
📋 Жалоба incelemek для:

1️⃣ Жалоба ettiгiniz пользователь: @пользователь или ID
2️⃣ Olмесяц описание: Ne oldu, ne время
3️⃣ ДОКАЗАТЕЛЬСТВО: Ekran скриншот загруз

⚠️ Доказательство жалобы действие получитьыnmaz.
```

---

### 2. Soru Тестi

**Senaryo:** Пользователь panel о soru soruyor

```
Пользователь: "Panel как использовать?"
Bдобавитьnen: AI ответитьir
```

**Adыmlar:**
1. Ticket открыть
2. "Panel как использовать?" yaz
3. AI'nin direkt cevap данныеni контроль et

**Bдобавитьnen Cevap:**
```
🌐 Panel adresi сервер duyurularыnda pмесяцlaшыlыr.

Запись olmak для:
• Panel'e git → "Запись Ol"
• Discord с вход yap
• Администратор deгilsen "Участник" paneline eriшirsin

💡 Baшka sorun var mы?
```

---

### 3. Teknik Sorun Тестi

**Senaryo:** Пользователь bot работатьmыyor diyor

```
Пользователь: "Bot ответитьmiyor"
Bдобавитьnen: AI решение sunar
```

**Adыmlar:**
1. Ticket открыть
2. "Bot ответитьmiyor" yaz
3. AI'nin решение ёnerdiгini контроль et

**Bдобавитьnen Cevap:**
```
🔧 Bot ответитьmiyorsa:

• Slash команды (/) использовать musun?
• Botun администратор var mы?
• Верно канал mыsыn?

Решение: /help команду dene
Hполучитьa работа администрации bildireceгim.
```

---

### 4. Karышыk Soru Тестi

**Senaryo:** Пользователь belirsiz сообщение отправл

```
Пользователь: "Помощь lazыm"
Bдобавитьnen: AI kategori sorar
```

**Adыmlar:**
1. Ticket открыть
2. "Помощь lazыm" yaz
3. AI'nin ne tюr помощь желание sorduгunu контроль et

**Bдобавитьnen Cevap:**
```
💡 Tabii, size помощник olмесяцыm!

Ne kдесятьuda помощь желание?
• Жалоба mi var?
• Soru mu sormak istiyorsunuz?
• Teknik sorun mu yaшыyorsunuz?

Пожалуйста детали открытьыklмесяцыnыz.
```

---

### 5. Kategori Geчiш Тестi

**Senaryo:** Пользователь до soru soruyor, после жалоба ediyor

```
Пользователь: "Panel как использовать?"
AI: [Cevap выдатьir]
Пользователь: "Месяцrыca X человек bana оскорбление etti"
Bдобавитьnen: AI kategoriyi deгiшtirir, доказательство хочет
```

**Adыmlar:**
1. Ticket открыть
2. "Panel как использовать?" yaz
3. AI ответитьsin
4. "Месяцrыca X человек bana оскорбление etti" yaz
5. AI'nin доказательство желание контроль et

---

## 🎯 Успешно Kriterleri

✅ AI верно kategoriyi tespit ediyor
✅ Каждый kategoride uygun ответитьiyor
✅ Жалоба доказательство istiyor
✅ Sorularda direkt ответитьiyor
✅ Teknik sorunlarda решение sunuyor
✅ Kategori geчiшlerinde uyum saгlыyor
✅ Gerektiгinde направление

---

## 🐛 Ошибка Senaryolarы

### Senaryo 1: AI неверно kategori выбрать
**Решение:** `_detect_category()` fдесятьksiyдесятьuna anahtar kelime добавить

### Senaryo 2: AI доказательство желание
**Решение:** `_prompt_sikмесяцet()` prompt'unu контроль et

### Senaryo 3: AI очень uzun ответитьiyor
**Решение:** `max_tokens` деньгиmetresini azполучитьt (шu an 512)

### Senaryo 4: AI Русский kдесятьuшmuyor
**Решение:** Каждый prompt'ta "Русский kдесятьuш" правило var, API key'i контроль et

---

## 📊 Тест В конецuчlarы

| Тест | Состояние | Not |
|------|-------|-----|
| Жалоба | ⏳ | Ожидает |
| Soru | ⏳ | Ожидает |
| Teknik | ⏳ | Ожидает |
| Karышыk | ⏳ | Ожидает |
| Geчiш | ⏳ | Ожидает |

**Состояние Kodlarы:**
- ⏳ Ожидает
- ✅ Успешно
- ❌ Неудачно
- ⚠️ Kыsmi Успешно
