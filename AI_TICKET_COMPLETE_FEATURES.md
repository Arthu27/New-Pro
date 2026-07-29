# AI Ticket Система - Все Особенности Dokümantasyonu

## 🎯 Обзор сервера

Aether Discord botunun AI ticket moderasyon система теперь **tam автоматически, adil ve akıllı** bir moderasyon platformu. Все Tier 1, Tier 2 ve bazı Tier 3 особенности добавлено.

---

## ✅ Добавл Особенности

### 🔥 **Tier 1: Kritik Особенности** (ЗАВЕРШЕНО)

#### 1. ✅ **Взаимный Нарушение Tespiti**
- AI теперь **каждый iki сканироватьfı da** analiz ediyor
- Взаимный мат → **ikisine de наказание**
- Tek сканироватьflı нарушение → только suçluya наказание
- Sahte жалоба → жалоба наказание

**Kod:**
```python
if 'KARŞILIKLI_IHLAL' in verdict_upper:
    # Каждый iki сканироватьfa da mute at
    await target.timeout(...)
    await complainant.timeout(...)
```

---

#### 2. ✅ **Удален Сообщение Analizi**
- `_msg_cache` через удален сообщения inceliyor
- Удален сообщения `🗑️ УДАЛЕН СООБЩЕНИЕ` etiketi с показ
- Пользователи доказательство karartamıyor

**Kod:**
```python
# Удален сообщения cache'den тянуть
from cogs.logs import _msg_cache as _lc
for msg_id, cached_msg in list(_lc.items()):
    if cached_msg.get('channel_id') != channel_id:
        continue
    deleted_msgs.append(f"🗑️ УДАЛЕН СООБЩЕНИЕ: {cached_msg['content']}")
```

---

#### 3. ✅ **Апелляция Система**
- Пользователи AI kararına **1 kez апелляция** edebilir
- AI апелляция yeniden значение
- Апелляция kabul edilirse → администрации escalate
- Апелляция reddedilirse → наказание geçerli kполучает

**Использование:**
```
Пользователь: "апелляция ediyorum, bu haksızlık"
Bot: "📝 Апелляция alındı! Yeniden значение..."
```

**Kod:**
```python
async def _handle_appeal(self, channel, state, guild_id, channel_id, penalty):
    # AI'ya апелляция отправить
    verdict = _call_text([...], prompt)
    
    if 'KABUL' in verdict:
        await channel.send("✅ Апелляция kabul edildi!")
        await self._escalate_ticket(...)
```

---

#### 4. ✅ **Наказание Gradasyonu (Tekrarlayan Нарушения)**
- **В начало нарушение:** 15-30 dakika (base duration)
- **İkinci нарушение (7 день в):** 2x (30-60 dakika)
- **Üçüncü нарушение:** 4x (60-120 dakika)
- **Dördüncü+ нарушение:** 8x (max 24 saat)

**Kod:**
```python
def _calculate_penalty_duration(self, guild_id, user_id, base_duration):
    history = self._get_penalty_history(guild_id, user_id, days=7)
    multiplier = 2 ** min(len(history), 3)
    return min(base_duration * multiplier, 1440)  # max 24 saat
```

**Пример:**
```
В начало мат: 30 dakika mute
İkinci мат (3 день после): 60 dakika mute
Üçüncü мат (5 день после): 120 dakika mute
```

---

#### 5. ✅ **Доказательство Добавить Система**
- AI "нарушение yok" dediğinde → ek доказательство teklif ediyor
- Пользователь screenshot/ek сообщение добавить
- AI yeniden analiz eder

**Использование:**
```
Bot: "Нарушение tespit edemedim. Ek доказательство добавить хочет misin? (evet/hayır)"
Пользователь: "evet"
Bot: "📎 Ek доказательство добавить modu активен! Screenshot или сообщения отправить."
Пользователь: [screenshot загруз]
Пользователь: "tamam"
Bot: "✅ Дополнительные доказательства получены. Повторный анализ..."
```

**Kod:**
```python
if state.get('adding_evidence'):
    if content == 'tamam':
        # Yeniden analiz et
        await self._analyze_complaint(...)
    else:
        # Доказательство добавить
        state['additional_evidence'].append(message.content)
```

---

#### 6. ✅ **AI Доверие Skoru**
- Каждый karar для AI'nın доверие seviyesi hesaplanıyor (%0-100)
- **Низкий доверие (<60%)** → автоматически администрации escalate
- **Высокий доверие (>80%)** → наказание примен

**Kod:**
```python
def _get_ai_confidence(self, verdict: str) -> int:
    confidence = 50
    if 'открыт' in verdict or 'kesin' in verdict:
        confidence += 30
    if 'belirsiz' in verdict:
        confidence -= 30
    return max(0, min(100, confidence))

# Использование
confidence = self._get_ai_confidence(verdict)
if confidence < 60:
    await self._escalate_ticket(channel, state, 'low_confidence')
```

**Пример:**
```
🔍 AI Analizi (Доверие: %85):
"Жалоба edilen человек açıkça мат etmiş, жалоба eden temiz."

🔍 AI Analizi (Доверие: %45):
"Bağlam belirsiz, администрации iletiyorum."
```

---

### ⚡ **Tier 2: Önemli Особенности** (ЗАВЕРШЕНО)

#### 7. ✅ **Детали Статистика & Dashboard**
- Web panelinde `/ai_ticket_stats` sayfası
- Всего ticket, наказание, взаимный нарушение, sahte жалоба число
- En очень наказание alan пользователи
- Наказание причина dağılımı
- AI performans metrikleri

**Особенности:**
- 📊 Karar dağılımı (tek сканироватьflı, взаимный, sahte, нарушение yok)
- ⚖️ AI performansı (ortalama доверие, апелляция oranı)
- 👥 En очень наказание alan пользователи (top 10)
- 📋 Наказание причина (мат, tehdit, zorbalık, vb.)

**Erişim:**
```
Web Panel → /ai_ticket_stats
Администратор: Модератор+
```

---

### 🎯 **Tier 3: Gelişmiş Особенности** (KISMİ)

#### 8. ⚠️ **Proaktif Предупреждение Система** (PLANLANDI)
- Automod с entegrasyon
- В начало мат → предупреждение + сообщение удалить
- İkinci мат → автоматически mute

#### 9. ⚠️ **Автоматически Özür Система** (PLANLANDI)
- Наказание alan пользователю özür dileme teklifi
- Özür dilerse → наказание %50 azполучает

#### 10. ⚠️ **Sentiment Analizi** (PLANLANDI)
- Сообщение tonunu analiz et (agresif, şakacı, savunmacı)
- Tona по наказание тяжелый настройк

---

## 📊 Veri Yapıları

### 1. **Penalty Dosyası** (`data/ticket_penalties.json`)
```json
{
  "guild_id": {
    "user_id": [
      {
        "name": "Пользователь Имя",
        "reason": "взаимный мат/оскорбление",
        "date": "2026-04-17T12:30:00",
        "duration": 30
      },
      {
        "name": "Пользователь Имя",
        "reason": "оскорбление",
        "date": "2026-04-19T15:45:00",
        "duration": 60
      }
    ]
  }
}
```

### 2. **Ticket State** (`data/ai_tickets_{guild_id}.json`)
```json
{
  "channel_id": {
    "user_id": 123456789,
    "category": "sikayet",
    "status": "ai_handling",
    "ai_message_count": 5,
    "appeal_used": false,
    "waiting_for_evidence": false,
    "adding_evidence": false,
    "additional_evidence": [],
    "complaint": {
      "active": true,
      "step": "analyze",
      "type": "kufur",
      "accused_id": "987654321",
      "messages": ["..."],
      "messages_verified": true
    }
  }
}
```

---

## 🔄 İş Akışları

### **Akış 1: Взаимный Мат**
```
1. Пользователь A ticket açar
2. "Жалоба" kategorisi выбрать
3. Olayı anlatır: "B bana мат etti"
4. Жалоба türü: Мат/Hakaret
5. Жалоба edilen ID: B'nin ID'si
6. Канал ID: Olayın gerçekleştiği канал
7. AI сообщения сканироватьr (удален сообщения dahil)
8. AI analiz eder:
   - A'nın сообщения: "sen salaksın"
   - B'nin сообщения: "sen более salaksın"
9. AI kararı: KARŞILIKLI_IHLAL
10. Каждый ikisine de 30 dakika mute
11. История наказание контроль:
    - A: В начало нарушение → 30 dakika
    - B: İkinci нарушение → 60 dakika
```

### **Akış 2: Апелляция**
```
1. Пользователь наказание получает
2. Ticket'ta "апелляция ediyorum" yazar
3. AI апелляция получает
4. Апелляция hakkı контроль (max 1)
5. AI апелляция значение
6. Karar:
   - KABUL → Администрации escalate
   - RED → Наказание geçerli
   - BELIRSIZ → Администрации escalate
```

### **Akış 3: Ek Доказательство**
```
1. AI "нарушение yok" der
2. "Ek доказательство добавить хочет misin?" sorar
3. Пользователь "evet" der
4. Ek доказательство добавить modu активен
5. Пользователь screenshot/сообщение отправл
6. "tamam" напишите AI yeniden analiz eder
7. Новый karar verilir
```

---

## 🎮 Команды

### Discord Командыı
```
/ticket-panel              → Ticket panelini отправл
/ticket-добавить @user         → Ticket'a пользователь добавить
/ticket-cikar @user        → Ticket'tan пользователь удаляет
/ticket-ai-stats           → AI статистика показ
/ticket-ai-toggle          → AI sistemini aç/закрыть
/ticket-force-escalate     → Ticket'i администрации направление
```

### Web Panel
```
/ai_ticket_stats           → Детали AI статистика
```

---

## 📈 Статистика Metrikleri

### Hesaplanan Metrikler
1. **Всего Ticket Количество**
2. **Всего Наказание Количество**
3. **Взаимный Нарушение Oranı** (%)
4. **Sahte Жалоба Oranı** (%)
5. **Tek Taraflı Нарушение Oranı** (%)
6. **Нарушение Yok Oranı** (%)
7. **Ortalama AI Доверие Skoru** (%)
8. **Высокий Доверие Karar Количество**
9. **Низкий Доверие (Escalate) Количество**
10. **Апелляция Oranı** (%)
11. **Апелляция Kabul Oranı** (%)
12. **En Очень Наказание Alan Пользователи** (top 10)
13. **Наказание Причина Dağılımı**

---

## 🔧 Teknik Детали

### Новый Fonksiyonlar

#### `_record_penalty(guild_id, user_id, user_name, reason, duration)`
Наказание kaydını JSON dosyasına yazar (liste formatında, история наказания для).

#### `_get_penalty_history(guild_id, user_id, days=7)`
В конец X день в наказание историю döner.

#### `_calculate_penalty_duration(guild_id, user_id, base_duration)`
История наказание по gradation примен (2^n multiplier).

#### `_get_ai_confidence(verdict)`
AI kararının доверие skorunu hesaplar (0-100).

#### `_handle_appeal(channel, state, guild_id, channel_id, penalty)`
Апелляция AI с значение.

#### `calculate_ai_ticket_stats(guild_id)`
Web paneli для статистика hesaplar.

---

## 🚀 Использование Пример

### Пример 1: В начало Нарушение
```
Пользователь: "X bana мат etti"
AI: [Analiz eder]
AI: "✅ X 30 dakika mute aldı (ilk нарушение)"
```

### Пример 2: Tekrarlayan Нарушение
```
Пользователь: "Y yine мат etti"
AI: [История наказание контроль eder]
AI: "✅ Y 60 dakika mute aldı"
AI: "📊 История наказание: 1 (наказание длительность artırıldı)"
```

### Пример 3: Взаимный Мат
```
Пользователь A: "B bana мат etti"
AI: [Каждый iki сканироватьfı da analiz eder]
AI: "⚖️ Взаимный правило нарушение tespit edildi!"
AI: "✅ A 30 dakika mute aldı"
AI: "✅ B 30 dakika mute aldı"
```

### Пример 4: Низкий Доверие
```
Пользователь: "X bana kötü davrandı"
AI: [Analiz eder]
AI: "🤔 AI Доверие Skoru: %45 (Низкий)"
AI: "Bu состояние net значение, администрации iletiyorum."
```

### Пример 5: Апелляция
```
Пользователь: "апелляция ediyorum, bu haksızlık"
AI: "📝 Апелляция alındı!"
AI: [Yeniden значение]
AI: "✅ Апелляция kabul edildi! Администрации iletiyorum."
```

---

## 📊 Performans Beklentileri

### AI Верно Oranı
- **Высокий доверие kararlar:** %90+ верно
- **Orta доверие kararlar:** %70-80% верно
- **Низкий доверие:** Автоматически escalate (администраторы karar verir)

### Yük Azaltma
- **Basit vakalar:** AI автоматически çözer (%70-80)
- **Karmaşık vakalar:** Администрации escalate (%20-30)
- **Администраторы только zor vakaları видеть**

### Пользователь Memnuniyeti
- **Adil наказание:** Каждый iki сканироватьf da eşit muamele видеть
- **Быстрый yanıt:** AI anında karar verir
- **Апелляция hakkı:** Неверно kararlar düzeltilebilir

---

## 🎯 В конецuç

Aether AI Ticket система теперь:
- ✅ Взаимный нарушение tespit ediyor
- ✅ Удален сообщения analiz ediyor
- ✅ Апелляция система var
- ✅ Наказание gradasyonu uyguluyor
- ✅ Ek доказательство kabul ediyor
- ✅ AI доверие skoru hesaplıyor
- ✅ Детали статистика sunuyor

**В конецuç:** Более adil, более akıllı, более автоматически moderasyon система! 🚀
