# 🛡️ AI Moderator Sistemi - Tam Rehber

## 🎯 Sistem Özeti

**Aether AI Moderator** artık sadece sohbet botu değil, **tam yetkili bir moderatör** gibi çalışıyor:

✅ Şikayetleri dinler ve **kanıt ister**  
✅ Ekran görüntülerini analiz eder  
✅ Mesaj geçmişini kontrol eder  
✅ **Jail cezası verebilir** (otomatik)  
✅ Sadece gerçekten gerektiğinde yetkililere yönlendirir  

---

## 🔄 Yeni Çalışma Akışı

### 1️⃣ Kullanıcı Ticket Açar

```
Kullanıcı: [Ticket açar]
    ↓
AI Moderator: "Merhabalar, ben Aether Moderator.
               Sorununuzu detaylı açıklayınız.
               
               Şikayet için:
               1️⃣ Kullanıcı: @kullanıcı
               2️⃣ Olay açıklaması
               3️⃣ KANIT: Ekran görüntüsü
               
               ⚠️ Kanıtsız şikayetler işleme alınmaz."
```

### 2️⃣ Kullanıcı Şikayet Eder

```
Kullanıcı: "X kişisi bana hakaret etti"
    ↓
AI Moderator: "Şikayetinizi incelemek için:
               • Kullanıcı ID'si veya @mention
               • Ekran görüntüsü yükleyiniz
               • Ne zaman oldu belirtiniz"
```

### 3️⃣ Kullanıcı Kanıt Yükler

```
Kullanıcı: [Ekran görüntüsü yükler]
           "@user123 bana 'aptal' dedi, 10 dakika önce"
    ↓
AI Moderator: [Ekran görüntüsünü analiz eder]
              [Mesaj geçmişini kontrol eder]
              [Zaman farkını kontrol eder]
```

### 4️⃣ AI Karar Verir

**Senaryo A: Hafif İhlal**
```
AI Moderator: "✅ İnceleme tamamlandı.
               
               Kullanıcıya uyarı verildi.
               Tekrar ederse daha ağır ceza alacaktır."
```

**Senaryo B: Orta Seviye İhlal (Jail)**
```
AI Moderator: "✅ İnceleme tamamlandı.
               
               📋 KARAR: Jail cezası verildi
               👤 Kullanıcı: @user123
               ⏱️ Süre: 30 dakika
               📝 Sebep: Tekrarlayan hakaret
               
               Olayı çözmekte size yetkili ekibimiz
               yardımcı olacaktır."
               
[Kullanıcıya otomatik jail rolü verilir]
[30 dakika sonra otomatik kaldırılır]
```

**Senaryo C: Ağır İhlal (Jail + Yönlendirme)**
```
AI Moderator: "✅ İnceleme tamamlandı.
               
               📋 KARAR: Jail cezası verildi
               👤 Kullanıcı: @user123
               ⏱️ Süre: 120 dakika
               📝 Sebep: Ağır hakaret ve tehdit
               
               🔄 Yetkililere yönlendiriliyor..."
               
[Jail verilir + Destek rolü ping atılır]
```

**Senaryo D: Kanıt Yetersiz**
```
AI Moderator: "❌ Şikayetiniz reddedildi.
               
               📋 SEBEP:
               - Mesajlar uyuşmuyor
               - Zaman farkı çok fazla (30+ dakika)
               - Ciddi ihlal tespit edilemedi
               
               ⚠️ Sahte şikayet ceza alabilir."
```

---

## 🎯 AI Moderator Yetenekleri

### ✅ Yapabilecekleri

1. **Kanıt İsteme**
   - Ekran görüntüsü talep eder
   - Kullanıcı ID/mention ister
   - Olay detaylarını sorar

2. **Analiz**
   - Ekran görüntüsünü inceler
   - Mesaj geçmişini kontrol eder
   - Zaman farkını hesaplar (30+ dakika = red)

3. **Karar Verme**
   - Hafif: Sadece uyarı
   - Orta: Jail 30-60 dakika
   - Ağır: Jail 120 dakika + yönlendirme

4. **Ceza Uygulama**
   - Jail rolü verir (otomatik)
   - Kullanıcıya DM gönderir
   - Süre bitince otomatik kaldırır

5. **Loglama**
   - Tüm işlemleri loglar
   - Mod log'a kaydeder
   - Web panel'de görüntülenebilir

### ❌ Yapamayacakları

- **Ban/Kick** (sadece yetkililer)
- **Rol verme/alma** (jail hariç)
- **Kanal/sunucu ayarları**
- **Ekonomi işlemleri**

---

## 📊 Ciddiyet Seviyeleri

### 🟢 Hafif Seviye (Sadece Uyarı)
- Tek seferlik küfür
- Küçük tartışma
- Spam (1-2 mesaj)

**AI Aksiyonu**: Uyarı mesajı

### 🟡 Orta Seviye (Jail 30-60 dakika)
- Tekrarlayan hakaret
- Küçük düşürme
- Orta seviye spam
- Sürekli rahatsız etme

**AI Aksiyonu**: Jail + açıklama

### 🔴 Ağır Seviye (Jail 120 dakika + Yönlendirme)
- Ağır hakaret, tehdit
- Irkçılık, nefret söylemi
- Cinsel taciz
- Sürekli spam/raid

**AI Aksiyonu**: Jail + yetkililere yönlendirme

---

## 🛠️ Teknik Detaylar

### Jail Sistemi

**Jail Rolü:**
- Otomatik oluşturulur (yoksa)
- Tüm kanallarda `send_messages: False`
- Gri renk

**Jail Süreci:**
```python
1. Jail rolü ver
2. Kullanıcıya DM gönder
3. Ticket'e bildir
4. Mod log'a kaydet
5. X dakika bekle
6. Jail rolünü kaldır
7. Kullanıcıya DM gönder (serbest)
```

### Mesaj Geçmişi Kontrolü

```python
1. Son 50 mesajı al
2. Bot mesajlarını filtrele
3. Zaman damgalarını kontrol et
4. Şikayet edilen kullanıcının mesajlarını bul
5. Ekran görüntüsü ile karşılaştır
6. Zaman farkı 30+ dakika ise → RED
```

### AI Action Parsing

AI cevabında özel tag'ler:

```
[JAIL]
user_id: 123456789
duration: 30
reason: Tekrarlayan hakaret
```

```
[CHECK_HISTORY]
→ Mesaj geçmişini kontrol et
```

```
[ANALYZE_IMAGE]
→ Ekran görüntüsünü analiz et
```

```
[ESCALATE]
Kategori: agir_ihlal
Aciklama: Tehdit içeren mesajlar
```

---

## 🎮 Yeni Komutlar

### Kullanıcı İçin
- Ticket aç → AI Moderator otomatik karşılar
- Kanıt yükle → AI analiz eder
- İtiraz et → Yetkililere yönlendirilir

### Yetkili İçin

#### `/ticket-ai-stats`
AI moderator istatistiklerini gösterir
- Toplam jail sayısı
- Reddedilen şikayetler
- Ortalama çözüm süresi

#### `/ticket-ai-toggle`
AI moderator sistemini aç/kapat

#### `/ticket-force-escalate`
Mevcut ticket'i hemen yetkililere yönlendir

---

## 📋 Örnek Senaryolar

### Senaryo 1: Başarılı Jail

```
👤 Kullanıcı: "X kişisi bana hakaret etti"
🤖 AI: "Kanıt yükleyiniz"
👤 Kullanıcı: [Ekran görüntüsü] "@user123 bana aptal dedi"
🤖 AI: [Analiz ediyor...]
       [Mesaj geçmişini kontrol ediyor...]
       ✅ "Jail cezası verildi: 30 dakika"
[user123'e jail rolü verilir]
[30 dakika sonra otomatik kaldırılır]
```

### Senaryo 2: Reddedilen Şikayet

```
👤 Kullanıcı: "X kişisi bana hakaret etti"
🤖 AI: "Kanıt yükleyiniz"
👤 Kullanıcı: [Ekran görüntüsü] "2 saat önce böyle dedi"
🤖 AI: [Analiz ediyor...]
       [Mesaj geçmişini kontrol ediyor...]
       ❌ "Şikayet reddedildi: Zaman farkı çok fazla"
```

### Senaryo 3: Ağır İhlal

```
👤 Kullanıcı: "X kişisi bana ölümle tehdit etti"
🤖 AI: "Kanıt yükleyiniz"
👤 Kullanıcı: [Ekran görüntüsü] "Seni öldüreceğim dedi"
🤖 AI: [Analiz ediyor...]
       ✅ "Jail cezası verildi: 120 dakika"
       🔄 "Yetkililere yönlendiriliyor..."
[Jail verilir + Destek rolü ping atılır]
```

---

## ⚙️ Ayarlar

### `cogs/ticket.py`

```python
AI_ENABLED = True  # AI moderator aktif/pasif
MAX_AI_MESSAGES = 10  # Max mesaj sayısı
```

### Jail Süreleri

```python
# web/ai_helper.py içinde AI prompt'ta tanımlı:
Hafif: Jail yok (sadece uyarı)
Orta: 30-60 dakika
Ağır: 120 dakika
```

---

## 🔒 Güvenlik Önlemleri

### Sahte Şikayet Koruması
- Mesaj geçmişi kontrolü
- Zaman farkı kontrolü (30+ dakika = red)
- Sahte şikayet yapana uyarı

### Jail Kötüye Kullanım Koruması
- Max jail süresi: 120 dakika
- Tüm jail'ler loglanır
- Yetkililer her zaman override edebilir

### İtiraz Mekanizması
- Kullanıcı itiraz ederse → otomatik yönlendirme
- Yetkililer jail'i manuel kaldırabilir

---

## 📊 Web Panel

### AI Moderator Logları
**URL**: `/ai-tickets`

**Gösterir**:
- Tüm AI moderator kararları
- Jail cezaları
- Reddedilen şikayetler
- Konuşma geçmişi

---

## 🚀 Test Etmek İçin

### Test 1: Başarılı Jail
1. Ticket aç
2. "X kişisi bana hakaret etti" yaz
3. Sahte ekran görüntüsü yükle
4. AI'nin jail verdiğini gör

### Test 2: Reddedilen Şikayet
1. Ticket aç
2. "2 saat önce X kişisi böyle dedi" yaz
3. AI'nin reddettiğini gör

### Test 3: Yönlendirme
1. Ticket aç
2. "X kişisi bana ölümle tehdit etti" yaz
3. AI'nin jail verip yönlendirdiğini gör

---

## ✅ Avantajlar

**Kullanıcılar İçin:**
- ⚡ Anında moderasyon
- 🤖 7/24 aktif
- 📋 Adil ve tutarlı kararlar

**Yetkililer İçin:**
- 🎯 Sadece ciddi durumlarla ilgilenirler
- 📊 Tüm işlemler loglanır
- 🔄 İstedikleri zaman override edebilirler

**Sunucu İçin:**
- 🛡️ Daha hızlı moderasyon
- 📉 Daha az toksik ortam
- 📈 Daha fazla kullanıcı memnuniyeti

---

## 🎓 Önemli Notlar

⚠️ **AI Moderator**:
- Sadece jail verebilir (ban/kick değil)
- Kanıt olmadan ceza vermez
- Zaman farkını kontrol eder
- Ağır durumlarda yetkililere yönlendirir

✅ **Yetkililer**:
- Her zaman AI'yi override edebilir
- Jail'i manuel kaldırabilir
- AI'yi tamamen kapatabilir

---

**Sistem Hazır! 🛡️**

Artık AI Moderator tam yetkili gibi çalışıyor. Şikayetleri dinliyor, kanıt istiyor, analiz ediyor ve jail cezası verebiliyor!
