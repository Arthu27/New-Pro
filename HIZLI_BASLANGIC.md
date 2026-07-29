# 🚀 AI Ticket Sistemi - Hızlı Başlangıç

## 1️⃣ Sistem Hazır mı Kontrol Et

```bash
# Bot'u çalıştır
python main.py
```

Bot başladığında şu mesajı göreceksin:
```
✅ Ticket cog loaded (AI enabled)
```

---

## 2️⃣ İlk Ticket Panelini Gönder

Discord'da bir kanala git ve:

```
/ticket-panel
```

Panel gönderildi! Artık kullanıcılar "🎫 Destek Talebi Oluştur" butonuna tıklayabilir.

---

## 3️⃣ Test Et

### Test 1: Basit Soru
1. Ticket aç
2. AI'nin karşılama mesajını gör
3. Yaz: "bot komutları nedir?"
4. AI cevap verecek

### Test 2: Yönlendirme
1. Ticket aç
2. Yaz: "X kişisi spam yapıyor, ban atın"
3. AI yönlendirecek ve destek rolünü ping atacak

---

## 4️⃣ İstatistikleri Gör

### Discord'da:
```
/ticket-ai-stats
```

### Web Panel'de:
1. Panel'e giriş yap
2. İstatistik → 🤖 AI Destek Ticketları
3. Tüm konuşmaları gör

---

## 5️⃣ AI'yi Kapat/Aç

```
/ticket-ai-toggle
```

Her çalıştırdığında tersine çevrilir (açık → kapalı, kapalı → açık)

---

## 6️⃣ Manuel Yönlendirme

Bir ticket kanalında:

```
/ticket-force-escalate
```

AI durur, destek rolü ping atılır.

---

## ⚙️ Ayarları Değiştir

`cogs/ticket.py` dosyasını aç:

```python
AI_ENABLED = True  # False yap = AI tamamen kapalı
MAX_AI_MESSAGES = 10  # 5 yap = daha hızlı yönlendirir
```

Değiştirdikten sonra botu yeniden başlat.

---

## 🐛 Sorun Giderme

### AI cevap vermiyor
- `AI_ENABLED = True` olduğundan emin ol
- OpenRouter API key'in geçerli olduğunu kontrol et
- Bot loglarına bak (hata var mı?)

### Destek rolü ping atılmıyor
- "Destek" adında bir rol olduğundan emin ol
- Rolün mention edilebilir olduğunu kontrol et

### Web panel'de ticket görünmüyor
- Ticket açıldıktan sonra en az 1 mesaj yazıldığından emin ol
- `data/ai_tickets_<guild_id>.json` dosyasının var olduğunu kontrol et

---

## 📚 Daha Fazla Bilgi

- **Detaylı Dokümantasyon**: `AI_TICKET_SYSTEM.md`
- **Akış Diyagramı**: `AI_TICKET_FLOW.txt`
- **Kısa Özet**: `AI_TICKET_OZET.md`

---

## ✅ Checklist

- [ ] Bot çalışıyor
- [ ] `/ticket-panel` gönderildi
- [ ] Test ticket açıldı
- [ ] AI cevap verdi
- [ ] Yönlendirme test edildi
- [ ] Web panel'de görüntülendi
- [ ] İstatistikler kontrol edildi

**Hepsi tamamsa, sistem hazır! 🎉**
