# AI Ticket Sistemi - Test Senaryoları

## 🧪 Test Senaryoları

### 1. Şikayet Testi

**Senaryo:** Kullanıcı şikayet ediyor

```
Kullanıcı: "X kişisi bana hakaret etti"
Beklenen: AI kanıt ister
```

**Adımlar:**
1. Ticket aç
2. "X kişisi bana hakaret etti" yaz
3. AI'nin kanıt istediğini kontrol et
4. Ekran görüntüsü yükle
5. AI'nin mesaj geçmişini kontrol ettiğini gör
6. AI'nin karar verdiğini gör (jail veya red)

**Beklenen Cevap:**
```
📋 Şikayetinizi incelemek için:

1️⃣ Şikayet ettiğiniz kullanıcı: @kullanıcı veya ID
2️⃣ Olay açıklaması: Ne oldu, ne zaman
3️⃣ KANIT: Ekran görüntüsü yükleyiniz

⚠️ Kanıtsız şikayetler işleme alınmaz.
```

---

### 2. Soru Testi

**Senaryo:** Kullanıcı panel hakkında soru soruyor

```
Kullanıcı: "Panel nasıl kullanılır?"
Beklenen: AI cevap verir
```

**Adımlar:**
1. Ticket aç
2. "Panel nasıl kullanılır?" yaz
3. AI'nin direkt cevap verdiğini kontrol et

**Beklenen Cevap:**
```
🌐 Panel adresi sunucu duyurularında paylaşılır.

Kayıt olmak için:
• Panel'e git → "Kayıt Ol"
• Discord ile giriş yap
• Yetkili değilsen "Üye" paneline erişirsin

💡 Başka sorun var mı?
```

---

### 3. Teknik Sorun Testi

**Senaryo:** Kullanıcı bot çalışmıyor diyor

```
Kullanıcı: "Bot cevap vermiyor"
Beklenen: AI çözüm sunar
```

**Adımlar:**
1. Ticket aç
2. "Bot cevap vermiyor" yaz
3. AI'nin çözüm önerdiğini kontrol et

**Beklenen Cevap:**
```
🔧 Bot cevap vermiyorsa:

• Slash komutları (/) kullanıyor musun?
• Botun yetkisi var mı?
• Doğru kanalda mısın?

Çözüm: /help komutunu dene
Hala çalışmazsa yetkililere bildireceğim.
```

---

### 4. Karışık Soru Testi

**Senaryo:** Kullanıcı belirsiz mesaj gönderiyor

```
Kullanıcı: "Yardım lazım"
Beklenen: AI kategori sorar
```

**Adımlar:**
1. Ticket aç
2. "Yardım lazım" yaz
3. AI'nin ne tür yardım istediğini sorduğunu kontrol et

**Beklenen Cevap:**
```
💡 Tabii, size yardımcı olayım!

Ne konuda yardım istersiniz?
• Şikayet mi var?
• Soru mu sormak istiyorsunuz?
• Teknik sorun mu yaşıyorsunuz?

Lütfen detaylı açıklayınız.
```

---

### 5. Kategori Geçiş Testi

**Senaryo:** Kullanıcı önce soru soruyor, sonra şikayet ediyor

```
Kullanıcı: "Panel nasıl kullanılır?"
AI: [Cevap verir]
Kullanıcı: "Ayrıca X kişisi bana hakaret etti"
Beklenen: AI kategoriyi değiştirir, kanıt ister
```

**Adımlar:**
1. Ticket aç
2. "Panel nasıl kullanılır?" yaz
3. AI cevap versin
4. "Ayrıca X kişisi bana hakaret etti" yaz
5. AI'nin kanıt istediğini kontrol et

---

## 🎯 Başarı Kriterleri

✅ AI doğru kategoriyi tespit ediyor
✅ Her kategoride uygun cevap veriyor
✅ Şikayetlerde kanıt istiyor
✅ Sorularda direkt cevap veriyor
✅ Teknik sorunlarda çözüm sunuyor
✅ Kategori geçişlerinde uyum sağlıyor
✅ Gerektiğinde yönlendiriyor

---

## 🐛 Hata Senaryoları

### Senaryo 1: AI yanlış kategori seçiyor
**Çözüm:** `_detect_category()` fonksiyonuna anahtar kelime ekle

### Senaryo 2: AI kanıt istemiyor
**Çözüm:** `_prompt_sikayet()` prompt'unu kontrol et

### Senaryo 3: AI çok uzun cevap veriyor
**Çözüm:** `max_tokens` parametresini azalt (şu an 512)

### Senaryo 4: AI Türkçe konuşmuyor
**Çözüm:** Her prompt'ta "Türkçe konuş" kuralı var, API key'i kontrol et

---

## 📊 Test Sonuçları

| Test | Durum | Not |
|------|-------|-----|
| Şikayet | ⏳ | Bekliyor |
| Soru | ⏳ | Bekliyor |
| Teknik | ⏳ | Bekliyor |
| Karışık | ⏳ | Bekliyor |
| Geçiş | ⏳ | Bekliyor |

**Durum Kodları:**
- ⏳ Bekliyor
- ✅ Başarılı
- ❌ Başarısız
- ⚠️ Kısmi Başarı
