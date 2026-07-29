# 🛡️ AI Moderator - Hızlı Özet

## Ne Değişti?

AI artık **sadece sohbet botu değil**, **tam yetkili moderatör** gibi çalışıyor:

### Önceki Sistem ❌
```
Kullanıcı: "X kişisi bana hakaret etti"
AI: "Yetkililere yönlendiriyorum..."
[Destek rolü ping atılır]
```

### Yeni Sistem ✅
```
Kullanıcı: "X kişisi bana hakaret etti"
AI: "Kanıt yükleyiniz (ekran görüntüsü)"
Kullanıcı: [Ekran görüntüsü yükler]
AI: [Analiz eder, mesaj geçmişini kontrol eder]
AI: "✅ Jail cezası verildi: 30 dakika"
[Otomatik jail rolü verilir]
[30 dakika sonra otomatik kaldırılır]
```

---

## 🎯 Yeni Yetenekler

### 1. Kanıt İsteme
- Ekran görüntüsü talep eder
- Kullanıcı ID ister
- Olay detaylarını sorar

### 2. Analiz
- Ekran görüntüsünü inceler
- Mesaj geçmişini kontrol eder
- Zaman farkını hesaplar

### 3. Karar Verme
- **Hafif**: Sadece uyarı
- **Orta**: Jail 30-60 dakika
- **Ağır**: Jail 120 dakika + yönlendirme

### 4. Ceza Uygulama
- Jail rolü verir (otomatik)
- Kullanıcıya DM gönderir
- Süre bitince otomatik kaldırır

---

## 📋 Çalışma Akışı

```
1. Kullanıcı şikayet eder
   ↓
2. AI kanıt ister
   ↓
3. Kullanıcı ekran görüntüsü yükler
   ↓
4. AI analiz eder:
   • Ekran görüntüsü gerçek mi?
   • Mesaj geçmişi uyuşuyor mu?
   • Zaman farkı 30 dakikadan az mı?
   ↓
5. AI karar verir:
   ├─ Hafif → Uyarı
   ├─ Orta → Jail 30-60 dk
   └─ Ağır → Jail 120 dk + Yönlendirme
   ↓
6. Ceza uygulanır (otomatik)
```

---

## 🛡️ Güvenlik Önlemleri

### Sahte Şikayet Koruması
✅ Mesaj geçmişi kontrolü  
✅ Zaman farkı kontrolü (30+ dakika = red)  
✅ Sahte şikayet yapana uyarı  

### Jail Koruması
✅ Max jail: 120 dakika  
✅ Tüm işlemler loglanır  
✅ Yetkililer override edebilir  

---

## 🎮 Örnek Senaryo

### Başarılı Jail

```
👤 Kullanıcı: "X kişisi bana hakaret etti"

🤖 AI: "Şikayetinizi incelemek için:
       1️⃣ Kullanıcı ID
       2️⃣ Olay açıklaması
       3️⃣ KANIT: Ekran görüntüsü"

👤 Kullanıcı: [Ekran görüntüsü yükler]
              "@user123 bana 'aptal' dedi, 5 dakika önce"

🤖 AI: [Analiz ediyor...]
       [Mesaj geçmişini kontrol ediyor...]
       
       ✅ İnceleme tamamlandı.
       
       📋 KARAR: Jail cezası verildi
       👤 Kullanıcı: @user123
       ⏱️ Süre: 30 dakika
       📝 Sebep: Tekrarlayan hakaret
       
       Olayı çözmekte size yetkili ekibimiz
       yardımcı olacaktır.

[user123'e otomatik jail rolü verilir]
[30 dakika sonra otomatik kaldırılır]
```

---

## ⚙️ Ayarlar

```python
# cogs/ticket.py
AI_ENABLED = True  # AI moderator aktif/pasif
MAX_AI_MESSAGES = 10  # Max mesaj sayısı
```

---

## 📊 Ciddiyet Seviyeleri

| Seviye | Örnekler | AI Aksiyonu |
|--------|----------|-------------|
| 🟢 Hafif | Tek küfür, küçük tartışma | Sadece uyarı |
| 🟡 Orta | Tekrarlayan hakaret, spam | Jail 30-60 dk |
| 🔴 Ağır | Tehdit, nefret söylemi | Jail 120 dk + Yönlendirme |

---

## ✅ Avantajlar

**Kullanıcılar:**
- ⚡ Anında moderasyon (7/24)
- 📋 Adil ve tutarlı kararlar

**Yetkililer:**
- 🎯 Sadece ciddi durumlarla ilgilenirler
- 📊 Tüm işlemler loglanır

**Sunucu:**
- 🛡️ Daha hızlı moderasyon
- 📉 Daha az toksik ortam

---

## 🚀 Test Et

1. Ticket aç
2. "X kişisi bana hakaret etti" yaz
3. Sahte ekran görüntüsü yükle
4. AI'nin jail verdiğini gör

---

**Sistem Hazır! 🛡️**

AI artık tam yetkili moderatör gibi çalışıyor!
