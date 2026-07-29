# AI Ticket Sistemi - Kategorize Destek

## 🎯 Yeni Özellik: Akıllı Kategorizasyon

AI artık kullanıcının mesajını otomatik olarak kategorize ediyor ve ona göre davranıyor:

### Kategoriler

1. **Şikayet** 🛡️
   - Kanıt ister
   - Mesaj geçmişini kontrol eder
   - Jail cezası verebilir
   - Ağır durumlarda yönlendirir

2. **Soru** 💡
   - Panel, kayıt, komutlar
   - Roller, ekonomi, level
   - Genel bilgiler
   - Kısa ve net cevaplar

3. **Teknik** 🔧
   - Bot çalışmıyor
   - Müzik/ses sorunları
   - Ticket açılmıyor
   - Panel sorunları
   - Çözüm odaklı

4. **Diğer** 📋
   - Belirsiz durumlar
   - Genel yardım
   - Kategori tespiti

## 🔄 Nasıl Çalışır?

```
Kullanıcı mesajı
       ↓
Kategori Tespiti
(anahtar kelime analizi)
       ↓
  ┌────────────┬────────────┬────────────┐
  ↓            ↓            ↓            ↓
Şikayet      Soru        Teknik       Diğer
Prompt       Prompt      Prompt       Prompt
  ↓            ↓            ↓            ↓
Kanıt iste   Cevapla     Çözüm sun    Yönlendir
```

## 📝 Örnekler

### Şikayet
```
Kullanıcı: "X kişisi bana hakaret etti"
AI: [Şikayet prompt'u aktif]
    "📋 Şikayetinizi incelemek için kanıt yükleyiniz..."
```

### Soru
```
Kullanıcı: "Panel nasıl kullanılır?"
AI: [Soru prompt'u aktif]
    "🌐 Panel adresi duyurularda paylaşılır.
    Discord ile giriş yapabilirsin..."
```

### Teknik
```
Kullanıcı: "Bot cevap vermiyor"
AI: [Teknik prompt'u aktif]
    "🔧 Slash komutları (/) kullanıyor musun?
    /help komutunu dene..."
```

## 🎨 Avantajlar

✅ **Daha Tutarlı**: Her kategori kendi prompt'una odaklanır
✅ **Daha Hızlı**: AI kafası karışmaz, direkt cevap verir
✅ **Daha Akıllı**: Kategori geçmişi korunur
✅ **Daha Esnek**: Yeni kategoriler kolayca eklenebilir

## 🛠️ Teknik Detaylar

### Yeni Fonksiyonlar

- `_detect_category(message, history)` → Kategori tespiti
- `_prompt_sikayet()` → Şikayet prompt'u
- `_prompt_soru()` → Soru prompt'u
- `_prompt_teknik()` → Teknik prompt'u
- `_prompt_diger()` → Genel prompt
- `_get_prompt_by_category(category)` → Prompt seçici

### Güncellenen Fonksiyonlar

- `ai_ticket_response()` → Artık kategoriye göre prompt kullanıyor
- `ai_ticket_greeting()` → Daha genel karşılama mesajı

## 🚀 Kullanım

Hiçbir değişiklik gerekmez! `ticket.py` aynı şekilde çalışmaya devam eder.

```python
response, should_escalate, category, history = ai_ticket_response(
    user_message=message.content,
    history=state.get('history', []),
    guild_context={'guild_name': guild.name}
)
```

AI otomatik olarak kategoriyi tespit edip doğru prompt'u kullanacak.

## 📊 Kategori Anahtar Kelimeleri

**Şikayet:**
- şikayet, hakaret, küfür, tehdit, taciz, zorbalık, saldırı, rapor, ihbar

**Soru:**
- nasıl, panel, kayıt, giriş, nerede, komut, yardım, bilgi, öğrenmek

**Teknik:**
- çalışmıyor, hata, bug, sorun, bozuk, açılmıyor, müzik, ses, voice

## 🎯 Sonuç

AI artık hem şikayetleri çözüyor, hem sorulara cevap veriyor, hem de teknik destek sağlıyor — hepsi aynı ticket sisteminde!
