# 🤖 AI Destek Ticket Sistemi - Hızlı Özet

## Ne Yaptık?

Aether botuna **AI-powered destek sistemi** ekledik. Artık kullanıcılar ticket açtığında:

1. **AI otomatik karşılar** ve yardımcı olmaya çalışır
2. **Basit soruları çözer** (bot komutları, genel bilgiler)
3. **Çözemediği durumlarda yetkililere yönlendirir** (şikayet, ban talebi, vb.)

---

## Nasıl Çalışıyor?

### Kullanıcı Tarafı
```
Kullanıcı ticket açar
    ↓
AI: "Merhaba! Sana nasıl yardımcı olabilirim?"
    ↓
Kullanıcı sorusunu sorar
    ↓
AI cevap verir VEYA yetkililere yönlendirir
```

### Yönlendirme Durumları
AI şunlarda otomatik yönlendirir:
- ❌ Ban/kick/timeout talepleri
- ❌ Rol verme/alma
- ❌ Sunucu ayarları
- ❌ Ciddi şikayetler
- ❌ 10 mesaj limitine ulaşıldığında
- ❌ AI hata verdiğinde

---

## Yeni Komutlar

### `/ticket-ai-stats`
AI istatistiklerini gösterir (kaç ticket, kaç yönlendirildi, vb.)

### `/ticket-ai-toggle`
AI sistemini aç/kapat

### `/ticket-force-escalate`
Mevcut ticket'i hemen yetkililere yönlendir

---

## Web Panel

**Yeni Sayfa**: `/ai-tickets`

- Tüm AI konuşmalarını görüntüle
- İstatistikler (toplam, AI işliyor, yönlendirildi)
- Her ticket'in konuşma geçmişini incele

**Menüde**: İstatistik → 🤖 AI Destek Ticketları

---

## Ayarlar

`cogs/ticket.py` dosyasında:

```python
AI_ENABLED = True  # AI'yi kapat/aç
MAX_AI_MESSAGES = 10  # AI max kaç mesaj cevaplasın
```

---

## Örnek Kullanım

### ✅ AI Çözebilir
**Kullanıcı**: "Bot komutları nasıl kullanılır?"  
**AI**: "/help komutunu kullanarak tüm komutları görebilirsin..."

### 🔄 AI Yönlendirir
**Kullanıcı**: "X kişisi bana hakaret etti, ban atın"  
**AI**: "Bu konuda yetkililere yönlendiriyorum..."  
*[Destek rolü ping atılır]*

---

## Teknik Detaylar

- **AI Model**: OpenRouter Gemini 2.0 Flash
- **Dil**: Sadece Türkçe
- **Veri**: `data/ai_tickets_<guild_id>.json`
- **Max Mesaj**: 10 (sonra otomatik yönlendirir)
- **History**: Son 20 mesaj tutulur

---

## Önemli Notlar

✅ AI asla yetki gerektiren işlem yapmaz  
✅ Staff mesaj attığında AI otomatik durur  
✅ Tüm konuşmalar loglanır  
✅ AI kapatılabilir (`/ticket-ai-toggle`)  
✅ Staff her zaman manuel yönlendirme yapabilir  

---

## Test Etmek İçin

1. Ticket aç (panel butonu)
2. AI'nin karşılama mesajını gör
3. Basit bir soru sor (örn: "bot komutları nedir?")
4. AI'nin cevabını gör
5. Şimdi şikayet et (örn: "X kişisi spam yapıyor")
6. AI'nin yönlendirme yaptığını gör

---

**Hazır! 🚀**

Artık botun AI destekli ticket sistemi var. Kullanıcılar daha hızlı yardım alacak, yetkililer daha az basit soruyla uğraşacak.
