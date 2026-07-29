# AI Ticket Система - Test Senaryoları

## 🧪 Test Senaryoları

### 1. Жалоба Testi

**Senaryo:** Пользователь жалоба ediyor

```
Пользователь: "X человек bana оскорбление etti"
Beklenen: AI доказательство хочет
```

**Adımlar:**
1. Ticket aç
2. "X человек bana оскорбление etti" yaz
3. AI'nin доказательство желание контроль et
4. Ekran скриншот загрузить
5. AI'nin сообщение историю контроль ettiğini видеть
6. AI'nin karar данныеni видеть (jail или red)

**Beklenen Cevap:**
```
📋 Жалоба incelemek для:

1️⃣ Жалоба ettiğiniz пользователь: @пользователь или ID
2️⃣ Olay описание: Ne oldu, ne время
3️⃣ ДОКАЗАТЕЛЬСТВО: Ekran скриншот загруз

⚠️ Доказательство жалобы действие alınmaz.
```

---

### 2. Soru Testi

**Senaryo:** Пользователь panel о soru soruyor

```
Пользователь: "Panel как использовать?"
Beklenen: AI ответитьir
```

**Adımlar:**
1. Ticket aç
2. "Panel как использовать?" yaz
3. AI'nin direkt cevap данныеni контроль et

**Beklenen Cevap:**
```
🌐 Panel adresi сервер duyurularında paylaşılır.

Запись olmak для:
• Panel'e git → "Запись Ol"
• Discord с вход yap
• Администратор değilsen "Участник" paneline erişirsin

💡 Başka sorun var mı?
```

---

### 3. Teknik Sorun Testi

**Senaryo:** Пользователь bot çalışmıyor diyor

```
Пользователь: "Bot ответитьmiyor"
Beklenen: AI решение sunar
```

**Adımlar:**
1. Ticket aç
2. "Bot ответитьmiyor" yaz
3. AI'nin решение önerdiğini контроль et

**Beklenen Cevap:**
```
🔧 Bot ответитьmiyorsa:

• Slash команды (/) использовать musun?
• Botun администратор var mı?
• Верно канал mısın?

Решение: /help команду dene
Hala работа администрации bildireceğim.
```

---

### 4. Karışık Soru Testi

**Senaryo:** Пользователь belirsiz сообщение отправл

```
Пользователь: "Помощь lazım"
Beklenen: AI kategori sorar
```

**Adımlar:**
1. Ticket aç
2. "Помощь lazım" yaz
3. AI'nin ne tür помощь желание sorduğunu контроль et

**Beklenen Cevap:**
```
💡 Tabii, size помощник olayım!

Ne konuda помощь желание?
• Жалоба mi var?
• Soru mu sormak istiyorsunuz?
• Teknik sorun mu yaşıyorsunuz?

Пожалуйста детали açıklayınız.
```

---

### 5. Kategori Geçiş Testi

**Senaryo:** Пользователь до soru soruyor, после жалоба ediyor

```
Пользователь: "Panel как использовать?"
AI: [Cevap verir]
Пользователь: "Ayrıca X человек bana оскорбление etti"
Beklenen: AI kategoriyi değiştirir, доказательство хочет
```

**Adımlar:**
1. Ticket aç
2. "Panel как использовать?" yaz
3. AI ответитьsin
4. "Ayrıca X человек bana оскорбление etti" yaz
5. AI'nin доказательство желание контроль et

---

## 🎯 Успешно Kriterleri

✅ AI верно kategoriyi tespit ediyor
✅ Каждый kategoride uygun ответитьiyor
✅ Жалоба доказательство istiyor
✅ Sorularda direkt ответитьiyor
✅ Teknik sorunlarda решение sunuyor
✅ Kategori geçişlerinde uyum sağlıyor
✅ Gerektiğinde направление

---

## 🐛 Ошибка Senaryoları

### Senaryo 1: AI неверно kategori выбрать
**Решение:** `_detect_category()` fonksiyonuna anahtar kelime добавить

### Senaryo 2: AI доказательство желание
**Решение:** `_prompt_sikayet()` prompt'unu контроль et

### Senaryo 3: AI очень uzun ответитьiyor
**Решение:** `max_tokens` parametresini azalt (şu an 512)

### Senaryo 4: AI Русский konuşmuyor
**Решение:** Каждый prompt'ta "Русский konuş" правило var, API key'i контроль et

---

## 📊 Test В конецuçları

| Test | Состояние | Not |
|------|-------|-----|
| Жалоба | ⏳ | Bekliyor |
| Soru | ⏳ | Bekliyor |
| Teknik | ⏳ | Bekliyor |
| Karışık | ⏳ | Bekliyor |
| Geçiş | ⏳ | Bekliyor |

**Состояние Kodları:**
- ⏳ Bekliyor
- ✅ Успешно
- ❌ Неудачно
- ⚠️ Kısmi Успешно
