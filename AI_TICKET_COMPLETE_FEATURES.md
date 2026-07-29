# AI Ticket Sistemi - Tüm Özellikler Dokümantasyonu

## 🎯 Genel Bakış

Aether Discord botunun AI ticket moderasyon sistemi artık **tam otomatik, adil ve akıllı** bir moderasyon platformu. Tüm Tier 1, Tier 2 ve bazı Tier 3 özellikler eklendi.

---

## ✅ Eklenen Özellikler

### 🔥 **Tier 1: Kritik Özellikler** (TAMAMLANDI)

#### 1. ✅ **Karşılıklı İhlal Tespiti**
- AI artık **her iki tarafı da** analiz ediyor
- Karşılıklı küfür → **ikisine de ceza**
- Tek taraflı ihlal → sadece suçluya ceza
- Sahte şikayet → şikayetçiye ceza

**Kod:**
```python
if 'KARŞILIKLI_IHLAL' in verdict_upper:
    # Her iki tarafa da mute at
    await target.timeout(...)
    await complainant.timeout(...)
```

---

#### 2. ✅ **Silinen Mesaj Analizi**
- `_msg_cache` üzerinden silinen mesajları inceliyor
- Silinen mesajlar `🗑️ SİLİNMİŞ MESAJ` etiketi ile gösteriliyor
- Kullanıcılar kanıt karartamıyor

**Kod:**
```python
# Silinmiş mesajları cache'den çek
from cogs.logs import _msg_cache as _lc
for msg_id, cached_msg in list(_lc.items()):
    if cached_msg.get('channel_id') != channel_id:
        continue
    deleted_msgs.append(f"🗑️ SİLİNMİŞ MESAJ: {cached_msg['content']}")
```

---

#### 3. ✅ **İtiraz Sistemi**
- Kullanıcılar AI kararına **1 kez itiraz** edebilir
- AI itirazı yeniden değerlendirir
- İtiraz kabul edilirse → yetkililere escalate
- İtiraz reddedilirse → ceza geçerli kalır

**Kullanım:**
```
Kullanıcı: "itiraz ediyorum, bu haksızlık"
Bot: "📝 İtirazın alındı! Yeniden değerlendiriliyor..."
```

**Kod:**
```python
async def _handle_appeal(self, channel, state, guild_id, channel_id, penalty):
    # AI'ya itirazı gönder
    verdict = _call_text([...], prompt)
    
    if 'KABUL' in verdict:
        await channel.send("✅ İtirazın kabul edildi!")
        await self._escalate_ticket(...)
```

---

#### 4. ✅ **Ceza Gradasyonu (Tekrarlayan İhlaller)**
- **İlk ihlal:** 15-30 dakika (base duration)
- **İkinci ihlal (7 gün içinde):** 2x (30-60 dakika)
- **Üçüncü ihlal:** 4x (60-120 dakika)
- **Dördüncü+ ihlal:** 8x (max 24 saat)

**Kod:**
```python
def _calculate_penalty_duration(self, guild_id, user_id, base_duration):
    history = self._get_penalty_history(guild_id, user_id, days=7)
    multiplier = 2 ** min(len(history), 3)
    return min(base_duration * multiplier, 1440)  # max 24 saat
```

**Örnek:**
```
İlk küfür: 30 dakika mute
İkinci küfür (3 gün sonra): 60 dakika mute
Üçüncü küfür (5 gün sonra): 120 dakika mute
```

---

#### 5. ✅ **Kanıt Ekleme Sistemi**
- AI "ihlal yok" dediğinde → ek kanıt teklif ediyor
- Kullanıcı screenshot/ek mesaj ekleyebilir
- AI yeniden analiz eder

**Kullanım:**
```
Bot: "İhlal tespit edemedim. Ek kanıt eklemek ister misin? (evet/hayır)"
Kullanıcı: "evet"
Bot: "📎 Ek kanıt ekleme modu aktif! Screenshot veya mesajları gönder."
Kullanıcı: [screenshot yükler]
Kullanıcı: "tamam"
Bot: "✅ Ek kanıtlar alındı. Yeniden analiz yapılıyor..."
```

**Kod:**
```python
if state.get('adding_evidence'):
    if content == 'tamam':
        # Yeniden analiz et
        await self._analyze_complaint(...)
    else:
        # Kanıtı ekle
        state['additional_evidence'].append(message.content)
```

---

#### 6. ✅ **AI Güven Skoru**
- Her karar için AI'nın güven seviyesi hesaplanıyor (%0-100)
- **Düşük güven (<60%)** → otomatik yetkililere escalate
- **Yüksek güven (>80%)** → ceza uygula

**Kod:**
```python
def _get_ai_confidence(self, verdict: str) -> int:
    confidence = 50
    if 'açık' in verdict or 'kesin' in verdict:
        confidence += 30
    if 'belirsiz' in verdict:
        confidence -= 30
    return max(0, min(100, confidence))

# Kullanım
confidence = self._get_ai_confidence(verdict)
if confidence < 60:
    await self._escalate_ticket(channel, state, 'low_confidence')
```

**Örnek:**
```
🔍 AI Analizi (Güven: %85):
"Şikayet edilen kişi açıkça küfür etmiş, şikayet eden temiz."

🔍 AI Analizi (Güven: %45):
"Bağlam belirsiz, yetkililere iletiyorum."
```

---

### ⚡ **Tier 2: Önemli Özellikler** (TAMAMLANDI)

#### 7. ✅ **Detaylı İstatistikler & Dashboard**
- Web panelinde `/ai_ticket_stats` sayfası
- Toplam ticket, ceza, karşılıklı ihlal, sahte şikayet sayıları
- En çok ceza alan kullanıcılar
- Ceza sebepleri dağılımı
- AI performans metrikleri

**Özellikler:**
- 📊 Karar dağılımı (tek taraflı, karşılıklı, sahte, ihlal yok)
- ⚖️ AI performansı (ortalama güven, itiraz oranı)
- 👥 En çok ceza alan kullanıcılar (top 10)
- 📋 Ceza sebepleri (küfür, tehdit, zorbalık, vb.)

**Erişim:**
```
Web Panel → /ai_ticket_stats
Yetki: Moderatör+
```

---

### 🎯 **Tier 3: Gelişmiş Özellikler** (KISMİ)

#### 8. ⚠️ **Proaktif Uyarı Sistemi** (PLANLANDI)
- Automod ile entegrasyon
- İlk küfürde → uyarı + mesaj silme
- İkinci küfürde → otomatik mute

#### 9. ⚠️ **Otomatik Özür Sistemi** (PLANLANDI)
- Ceza alan kullanıcıya özür dileme teklifi
- Özür dilerse → ceza %50 azalır

#### 10. ⚠️ **Sentiment Analizi** (PLANLANDI)
- Mesajların tonunu analiz et (agresif, şakacı, savunmacı)
- Tona göre ceza ağırlığı ayarla

---

## 📊 Veri Yapıları

### 1. **Penalty Dosyası** (`data/ticket_penalties.json`)
```json
{
  "guild_id": {
    "user_id": [
      {
        "name": "Kullanıcı Adı",
        "reason": "karşılıklı küfür/hakaret",
        "date": "2026-04-17T12:30:00",
        "duration": 30
      },
      {
        "name": "Kullanıcı Adı",
        "reason": "hakaret",
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

### **Akış 1: Karşılıklı Küfür**
```
1. Kullanıcı A ticket açar
2. "Şikayet" kategorisi seçer
3. Olayı anlatır: "B bana küfür etti"
4. Şikayet türü: Küfür/Hakaret
5. Şikayet edilen ID: B'nin ID'si
6. Kanal ID: Olayın gerçekleştiği kanal
7. AI mesajları tarar (silinen mesajlar dahil)
8. AI analiz eder:
   - A'nın mesajları: "sen salaksın"
   - B'nin mesajları: "sen daha salaksın"
9. AI kararı: KARŞILIKLI_IHLAL
10. Her ikisine de 30 dakika mute
11. Geçmiş ceza kontrolü:
    - A: İlk ihlal → 30 dakika
    - B: İkinci ihlal → 60 dakika
```

### **Akış 2: İtiraz**
```
1. Kullanıcı ceza alır
2. Ticket'ta "itiraz ediyorum" yazar
3. AI itirazı alır
4. İtiraz hakkı kontrolü (max 1)
5. AI itirazı değerlendirir
6. Karar:
   - KABUL → Yetkililere escalate
   - RED → Ceza geçerli
   - BELIRSIZ → Yetkililere escalate
```

### **Akış 3: Ek Kanıt**
```
1. AI "ihlal yok" der
2. "Ek kanıt eklemek ister misin?" sorar
3. Kullanıcı "evet" der
4. Ek kanıt ekleme modu aktif
5. Kullanıcı screenshot/mesaj gönderir
6. "tamam" yazınca AI yeniden analiz eder
7. Yeni karar verilir
```

---

## 🎮 Komutlar

### Discord Komutları
```
/ticket-panel              → Ticket panelini gönderir
/ticket-ekle @user         → Ticket'a kullanıcı ekler
/ticket-cikar @user        → Ticket'tan kullanıcı çıkarır
/ticket-ai-stats           → AI istatistiklerini gösterir
/ticket-ai-toggle          → AI sistemini aç/kapat
/ticket-force-escalate     → Ticket'i yetkililere yönlendir
```

### Web Panel
```
/ai_ticket_stats           → Detaylı AI istatistikleri
```

---

## 📈 İstatistik Metrikleri

### Hesaplanan Metrikler
1. **Toplam Ticket Sayısı**
2. **Toplam Ceza Sayısı**
3. **Karşılıklı İhlal Oranı** (%)
4. **Sahte Şikayet Oranı** (%)
5. **Tek Taraflı İhlal Oranı** (%)
6. **İhlal Yok Oranı** (%)
7. **Ortalama AI Güven Skoru** (%)
8. **Yüksek Güven Karar Sayısı**
9. **Düşük Güven (Escalate) Sayısı**
10. **İtiraz Oranı** (%)
11. **İtiraz Kabul Oranı** (%)
12. **En Çok Ceza Alan Kullanıcılar** (top 10)
13. **Ceza Sebepleri Dağılımı**

---

## 🔧 Teknik Detaylar

### Yeni Fonksiyonlar

#### `_record_penalty(guild_id, user_id, user_name, reason, duration)`
Ceza kaydını JSON dosyasına yazar (liste formatında, geçmiş cezalar için).

#### `_get_penalty_history(guild_id, user_id, days=7)`
Son X gün içindeki ceza geçmişini döner.

#### `_calculate_penalty_duration(guild_id, user_id, base_duration)`
Geçmiş cezalara göre gradation uygular (2^n multiplier).

#### `_get_ai_confidence(verdict)`
AI kararının güven skorunu hesaplar (0-100).

#### `_handle_appeal(channel, state, guild_id, channel_id, penalty)`
İtirazı AI ile değerlendirir.

#### `calculate_ai_ticket_stats(guild_id)`
Web paneli için istatistikleri hesaplar.

---

## 🚀 Kullanım Örnekleri

### Örnek 1: İlk İhlal
```
Kullanıcı: "X bana küfür etti"
AI: [Analiz eder]
AI: "✅ X 30 dakika mute aldı (ilk ihlal)"
```

### Örnek 2: Tekrarlayan İhlal
```
Kullanıcı: "Y yine küfür etti"
AI: [Geçmiş cezaları kontrol eder]
AI: "✅ Y 60 dakika mute aldı"
AI: "📊 Geçmiş ceza: 1 (ceza süresi artırıldı)"
```

### Örnek 3: Karşılıklı Küfür
```
Kullanıcı A: "B bana küfür etti"
AI: [Her iki tarafı da analiz eder]
AI: "⚖️ Karşılıklı kural ihlali tespit edildi!"
AI: "✅ A 30 dakika mute aldı"
AI: "✅ B 30 dakika mute aldı"
```

### Örnek 4: Düşük Güven
```
Kullanıcı: "X bana kötü davrandı"
AI: [Analiz eder]
AI: "🤔 AI Güven Skoru: %45 (Düşük)"
AI: "Bu durumu net değerlendiremiyorum, yetkililere iletiyorum."
```

### Örnek 5: İtiraz
```
Kullanıcı: "itiraz ediyorum, bu haksızlık"
AI: "📝 İtirazın alındı!"
AI: [Yeniden değerlendirir]
AI: "✅ İtirazın kabul edildi! Yetkililere iletiyorum."
```

---

## 📊 Performans Beklentileri

### AI Doğruluk Oranı
- **Yüksek güven kararlar:** %90+ doğruluk
- **Orta güven kararlar:** %70-80% doğruluk
- **Düşük güven:** Otomatik escalate (yetkililer karar verir)

### Yük Azaltma
- **Basit vakalar:** AI otomatik çözer (%70-80)
- **Karmaşık vakalar:** Yetkililere escalate (%20-30)
- **Yetkililer sadece zor vakaları görür**

### Kullanıcı Memnuniyeti
- **Adil ceza:** Her iki taraf da eşit muamele görür
- **Hızlı yanıt:** AI anında karar verir
- **İtiraz hakkı:** Yanlış kararlar düzeltilebilir

---

## 🎯 Sonuç

Aether AI Ticket sistemi artık:
- ✅ Karşılıklı ihlalleri tespit ediyor
- ✅ Silinen mesajları analiz ediyor
- ✅ İtiraz sistemi var
- ✅ Ceza gradasyonu uyguluyor
- ✅ Ek kanıt kabul ediyor
- ✅ AI güven skoru hesaplıyor
- ✅ Detaylı istatistikler sunuyor

**Sonuç:** Daha adil, daha akıllı, daha otomatik moderasyon sistemi! 🚀
