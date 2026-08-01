# 🛡️ Rate Limiting Sistemi — Ticket

## Genel Bakış

Ticket sistemi için **production-ready rate limiting** koruması. Spam ve kötüye kullanımı önler.

---

## 📦 Dosyalar

| Dosya | Görev |
|-------|-------|
| `services/rate_limiter.py` | Rate limiter servisi (business logic) |
| `services/__init__.py` | Package init |
| `cogs/ticket.py` | Entegrasyon (import + kullanım) |
| `data/ticket_rate_limits.json` | Persistent storage |

---

## 🔧 Özellikler

### Korumalar
| Koruma | Limit | Açıklama |
|--------|-------|----------|
| **Cooldown** | 60 saniye | İki ticket arasında minimum bekleme |
| **24 saat limiti** | 3 ticket | Rolling window (kayan pencere) |
| **Haftalık limit** | 10 ticket | 7 günlük pencere |
| **Aylık limit** | 30 ticket | 30 günlük pencere |

### Teknik Özellikler
- ✅ **Async/await** — Non-blocking işlemler
- ✅ **Thread-safe** — `asyncio.Lock` ile korunuyor
- ✅ **Persistent** — JSON dosyasında saklanıyor
- ✅ **Atomic write** — `.tmp` + `os.replace()` ile güvenli yazma
- ✅ **Auto-cleanup** — Eski veriler otomatik temizlenir
- ✅ **Logging** — Tüm işlemler loglanır
- ✅ **Configurable** — Limitler değiştirilebilir

---

## 🚀 Kullanım

### Otomatik (Ticket açıldığında)
Rate limit kontrolü **otomatik** olarak yapılır. Kullanıcı ticket açmaya çalıştığında:

```
1. Cooldown kontrolü (60 saniye)
2. 24 saat limiti kontrolü (3 ticket)
3. Haftalık limit kontrolü (10 ticket)
4. ✅ Geçerse → Ticket oluştur + kaydet
5. ❌ Geçemezse → Embed mesaj göster
```

### Admin Komutları

#### `/ticket-reset-rate-limit <user>`
Bir kullanıcının rate limit'ini sıfırlar.

```
/ticket-reset-rate-limit @User
→ ✅ Rate limit для User сброшен.
```

**Yetki:** `Manage Guild`

#### `/ticket-rate-limit-info [user]`
Rate limit istatistiklerini gösterir.

```
/ticket-rate-limit-info @User
→ 📊 Rate Limit — User
  ├── Тикетов за 24ч: 2
  ├── Тикетов за неделю: 5
  ├── Тикетов за месяц: 12
  ├── Последний тикет: 2 часа назад
  └── Кулдаун: Готов
```

**Yetki:** `Manage Guild`

---

## ⚙️ Konfigürasyon

Limitler `RateLimiter` class'ında tanımlı:

```python
self.default_limits = {
    'max_tickets_per_24h': 3,      # 24 saatte max ticket
    'cooldown_seconds': 60,         # İki ticket arası min bekleme
    'max_tickets_per_week': 10,     # Haftalık limit
    'max_tickets_per_month': 30,    # Aylık limit
}
```

**Özelleştirme:** `config/ticket_config.json` dosyasından okuma eklenebilir.

---

## 📊 Örnek Mesajlar

### ❌ Cooldown Aktif
```
⏳ Ограничение на создание тикетов
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Причина: Подождите 45 секунд перед созданием нового тикета
Подождите: 45 сек.
Осталось тикетов: 2/3 (за 24 часа)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### ❌ 24 Saat Limiti
```
⏳ Ограничение на создание тикетов
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Причина: Превышен лимит тикетов за 24 часа (3). Попробуйте позже.
Подождите: 18 ч. 32 мин.
Осталось тикетов: 0/3 (за 24 часа)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🔍 Kod Entegrasyonu

### Import
```python
from services.rate_limiter import get_rate_limiter
```

### Kontrol
```python
rate_limiter = get_rate_limiter()
result = await rate_limiter.check_ticket_limit(guild_id, user_id)

if not result.allowed:
    # Kullanıcıya mesaj göster
    await ctx.send(f"⏳ {result.reason}")
    return
```

### Kayıt
```python
# Ticket başarıyla oluşturulduktan sonra
await rate_limiter.record_ticket_creation(guild_id, user_id)
```

### İstatistik
```python
stats = await rate_limiter.get_user_stats(guild_id, user_id)
print(f"24h: {stats['tickets_24h']}, Week: {stats['tickets_week']}")
```

### Sıfırlama
```python
await rate_limiter.reset_user(guild_id, user_id)
```

---

## 🧪 Testler

Tüm testler geçti ✅

```
TEST 1: İlk ticket (başarılı) ✅
TEST 2: Cooldown (reddedildi) ✅
TEST 3: Cooldown sonrası (başarılı) ✅
TEST 4: Üçüncü ticket (başarılı) ✅
TEST 5: 24 saat limiti (reddedildi) ✅
TEST 6: Stats (doğru) ✅
TEST 7: Reset (başarılı) ✅
```

---

## 🛡️ Güvenlik

### Rate Limit Bypass Koruması
- ✅ **Global instance** — Tüm View'lar aynı rate limiter'ı kullanır
- ✅ **Asyncio lock** — Race condition yok
- ✅ **Atomic write** — Data corruption yok
- ✅ **Persistent** — Bot restart'ta kaybolmaz

### Admin Override
- ✅ `/ticket-reset-rate-limit` ile manuel sıfırlama
- ✅ `Manage Guild` yetkisi gerekli
- ✅ Tüm işlemler loglanır

---

## 📝 Logging

Log seviyeleri:
- `INFO` — Normal işlemler (ticket oluşturuldu, kontrol geçti)
- `WARNING` — Rate limit ihlalleri
- `ERROR` — Hatalar (dosya okuma/yazma)

Log formatı:
```
[RateLimit] Тикет создан: user=Username (123456789) remaining=2/3
[RateLimit] Отказано в создании тикета: user=Username (123456789) reason=Cooldown
```

---

## 🔮 Gelecek İyileştirmeler

- [ ] Sunucu bazlı konfigürasyon (`config/ticket_config.json`)
- [ ] Rol bazlı limitler (VIP üyelere daha yüksek limit)
- [ ] Web panelde rate limit dashboard
- [ ] Otomatik cleanup task (her gün eski verileri sil)
- [ ] Metrics export (Prometheus)

---

## 📞 Destek

Sorun mu var? Loglara bakın:
```bash
grep "RateLimit" logs/bot.log
```

---

**Son güncelleme:** 2026-07-31  
**Versiyon:** 1.0.0  
**Durum:** ✅ Production Ready
