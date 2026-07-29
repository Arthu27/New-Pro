# 🤖 AI Destek Ticket Sistemi

## Genel Bakış

Aether Discord botu artık **AI-powered destek ticket sistemi** ile donatıldı. Kullanıcılar ticket açtığında, önce AI asistan yardımcı olur. AI çözemediği durumlarda otomatik olarak yetkililere yönlendirir.

---

## 🎯 Özellikler

### 1. **Otomatik AI Karşılama**
- Kullanıcı ticket açtığında AI asistan otomatik karşılar
- Sorun kategorisine göre özelleştirilmiş karşılama mesajları
- Kullanıcıya ne yapması gerektiğini açıklar

### 2. **Akıllı Konuşma**
- AI kullanıcının mesajlarını anlar ve Türkçe cevap verir
- Konuşma geçmişini hatırlar (son 20 mesaj)
- Profesyonel ama samimi ton

### 3. **Otomatik Yönlendirme**
AI aşağıdaki durumlarda otomatik yönlendirir:
- Ban/kick/timeout gibi ceza işlemleri
- Rol verme/alma işlemleri
- Kanal/sunucu ayarları değişiklikleri
- Ciddi şikayet ve anlaşmazlıklar
- Ödeme/ekonomi sorunları
- Güvenlik ve gizlilik konuları
- 10 mesaj limitine ulaşıldığında
- AI hata verdiğinde

### 4. **Staff Kontrolü**
- Yetkili mesaj attığında AI otomatik durur
- Staff istediği zaman manuel yönlendirme yapabilir
- AI'yi tamamen kapatma seçeneği

### 5. **Web Panel Entegrasyonu**
- Tüm AI konuşmalarını görüntüleme
- İstatistikler (toplam ticket, AI işliyor, yönlendirildi)
- Konuşma geçmişini detaylı inceleme

---

## 📋 Komutlar

### Kullanıcı Komutları
- **Ticket Aç**: Panel butonuna tıkla → AI otomatik karşılar

### Yetkili Komutları

#### `/ticket-panel`
Ticket panelini gönderir (AI destekli)
- **Yetki**: Administrator

#### `/ticket-ai-stats`
AI destek istatistiklerini gösterir
- **Yetki**: Manage Server
- **Gösterir**: Toplam ticket, AI işliyor, yönlendirildi, ortalama mesaj

#### `/ticket-ai-toggle`
AI destek sistemini aç/kapat
- **Yetki**: Administrator
- **Kullanım**: Toggle switch (tekrar çalıştır = tersine çevir)

#### `/ticket-force-escalate`
Mevcut ticket'i hemen yetkililere yönlendir
- **Yetki**: Manage Channels
- **Kullanım**: Ticket kanalında çalıştır

#### `/ticket-ekle <user>`
Ticket'e kullanıcı ekle
- **Yetki**: Manage Channels

#### `/ticket-cikar <user>`
Ticket'ten kullanıcı çıkar
- **Yetki**: Manage Channels

---

## 🔧 Teknik Detaylar

### Dosya Yapısı

```
cogs/ticket.py          # Ana ticket sistemi + AI entegrasyonu
web/ai_helper.py        # AI fonksiyonları (OpenRouter Gemini 2.0 Flash)
web/routes_extra.py     # Web panel route'ları
web/templates/ai_tickets.html  # AI ticket görüntüleme sayfası
data/ai_tickets_<guild_id>.json  # AI ticket verileri
```

### Veri Yapısı

```json
{
  "channel_id": {
    "user_id": 123456789,
    "category": "sikayet|soru|teknik|diger",
    "history": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "status": "ai_handling|escalated|staff_handling",
    "ai_message_count": 5,
    "escalated_at": "2026-04-11T12:34:56",
    "staff_notified": true
  }
}
```

### AI Model
- **Provider**: OpenRouter
- **Model**: Google Gemini 2.0 Flash
- **Max Tokens**: 512 (hızlı yanıt için)
- **Temperature**: 0.7 (dengeli yaratıcılık)

### Limitler
- **Max AI Mesaj**: 10 (sonra otomatik yönlendirir)
- **History**: Son 20 mesaj tutulur
- **Timeout**: 30 saniye (AI yanıt süresi)

---

## 🎨 Web Panel

### AI Destek Ticketları Sayfası
**URL**: `/ai-tickets`  
**Yetki**: Mod+

**Özellikler**:
- Tüm aktif AI ticket'ları görüntüleme
- İstatistik kartları (toplam, AI işliyor, yönlendirildi, staff)
- Her ticket için:
  - Kanal adı
  - Kullanıcı adı
  - Kategori
  - AI mesaj sayısı
  - Yönlendirilme zamanı
  - Konuşma geçmişini görüntüleme butonu

**Konuşma Modal**:
- Kullanıcı ve AI mesajlarını ayrı renklerde gösterir
- Zaman damgası yok (sadece içerik)
- ESC tuşu veya dışarı tıklayarak kapatılır

---

## 🚀 Kullanım Senaryoları

### Senaryo 1: Basit Soru
1. Kullanıcı ticket açar
2. AI karşılar: "Merhaba! Sana nasıl yardımcı olabilirim?"
3. Kullanıcı: "Bot komutları nasıl kullanılır?"
4. AI: "/help komutunu kullanarak tüm komutları görebilirsin..."
5. Kullanıcı memnun, ticket'i kapatır

### Senaryo 2: Şikayet (Yönlendirme)
1. Kullanıcı ticket açar
2. AI karşılar
3. Kullanıcı: "X kişisi bana hakaret etti, ban atın"
4. AI: "Bu konuda yetkililere yönlendiriyorum..."
5. AI otomatik yönlendirir, destek rolünü ping atar
6. Yetkili gelir, konuyu ele alır

### Senaryo 3: Staff Müdahalesi
1. Kullanıcı ticket açar
2. AI konuşuyor
3. Yetkili mesaj atar
4. AI otomatik durur
5. Yetkili konuyu ele alır

### Senaryo 4: Max Mesaj Limiti
1. Kullanıcı ticket açar
2. AI 10 mesaj cevap verir
3. Hala çözüm yok
4. AI otomatik yönlendirir: "Konuşma limiti aşıldı, yetkililer devralıyor"

---

## ⚙️ Ayarlar

### `cogs/ticket.py` içinde:

```python
AI_ENABLED = True  # AI sistemini aktif/pasif yap
MAX_AI_MESSAGES = 10  # AI'nin max kaç mesaj cevaplayacağı
```

### AI System Prompt Düzenleme
`web/ai_helper.py` → `_ticket_system_prompt()` fonksiyonu

---

## 🐛 Hata Durumları

### AI Hata Verirse
- Otomatik yönlendirme yapılır
- Kullanıcıya: "Sistem hatası, yetkililer devralıyor"
- Destek rolü ping atılır

### Ollama/OpenRouter Erişilemezse
- Graceful fallback
- Ticket normal şekilde açılır (AI olmadan)
- Destek rolü hemen ping atılır

### Ticket Kapatıldığında
- AI state otomatik temizlenir
- Transcript kaydedilir (AI mesajları dahil)

---

## 📊 İstatistikler

### Komut ile: `/ticket-ai-stats`
- Toplam ticket sayısı
- AI işliyor (kaç tane)
- Yönlendirildi (kaç tane)
- Staff işliyor (kaç tane)
- Toplam AI mesaj sayısı
- Ortalama mesaj/ticket

### Web Panel: `/ai-tickets`
- Görsel kartlar
- Filtreleme (yakında)
- Arama (yakında)

---

## 🔮 Gelecek Özellikler

- [ ] Kategori seçimi (ticket açarken dropdown)
- [ ] AI öğrenme (başarılı çözümlerden)
- [ ] Çoklu dil desteği
- [ ] Sentiment analizi (kullanıcı memnuniyeti)
- [ ] Otomatik ticket kapatma (AI çözdüyse)
- [ ] AI performans metrikleri
- [ ] Custom AI promptları (sunucu bazlı)

---

## 📝 Notlar

- AI sadece Türkçe konuşur
- AI asla yetki gerektiren işlem yapmaz
- Tüm AI konuşmaları loglanır
- Staff her zaman AI'yi override edebilir
- AI ticket sistemi tamamen opsiyonel (kapatılabilir)

---

## 🎓 Eğitim

### Yetkililer İçin
1. `/ticket-ai-stats` ile durumu kontrol edin
2. `/ai-tickets` sayfasından konuşmaları inceleyin
3. Gerekirse `/ticket-force-escalate` ile manuel yönlendirin
4. AI'yi kapatmak için `/ticket-ai-toggle`

### Kullanıcılar İçin
- Ticket açın, AI size yardımcı olacak
- Detaylı açıklama yapın
- AI çözemezse otomatik yönlendirileceksiniz
- Sabırlı olun, AI öğreniyor 🤖

---

**Geliştirici**: Kiro AI  
**Tarih**: 11 Nisan 2026  
**Versiyon**: 1.0.0
