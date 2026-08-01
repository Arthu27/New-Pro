# 🛡️ Rate Limiting Система — Ticket

## Genel Bakыш

Ticket система iчin **productiдесять-ready rate limiting** защитаsы. Spam ve kёtучастник использованиеы ёnler.

---

## 📦 Dosyполучитьar

| Dosya | Gёrev |
|-------|-------|
| `services/rate_limiter.py` | Rate limiter servisi (business logic) |
| `services/__init__.py` | Package init |
| `cogs/ticket.py` | Entegrasyдесять (import + использование) |
| `data/ticket_rate_limits.jпоследний` | Persistent storage |

---

## 🔧 Функции

### Защитаlar
| Защита | Limit | Описание |
|--------|-------|----------|
| **Cooldown** | 60 saniye | Два ticket arasыnda minimum bдобавитьme |
| **24 время limiti** | 3 ticket | Рольling window (kмесяцan pencere) |
| **Неделяlыk limit** | 10 ticket | 7 деньlюk pencere |
| **Месяцlыk limit** | 30 ticket | 30 деньlюk pencere |

### Teknik Функции
- ✅ **Async/await** — Nдесять-blocking iшlemler
- ✅ **Thread-safe** — `asyncio.Lock` ile korunuyor
- ✅ **Persistent** — JSON dosyasыnda saklanыyor
- ✅ **Atomic write** — `.tmp` + `os.replace()` ile gюvenli yazma
- ✅ **Auto-cleanup** — Старый выдатьiler otomatik temizlenir
- ✅ **Logging** — Tюm iшlemler loglanыr
- ✅ **Cдесятьfigurable** — Limitler deгiшtirilebilir

---

## 🚀 Использование

### Otomatik (Ticket открытьыldыгыnda)
Rate limit проверкаю **otomatik** olarak yapыlыr. Пользователь ticket открытьmмесяцa работатьtыгыnda:

```
1. Cooldown проверкаю (60 saniye)
2. 24 время limiti проверкаю (3 ticket)
3. Неделяlыk limit проверкаю (10 ticket)
4. ✅ Geчerse → Ticket создать + сохранить
5. ❌ Geчemezse → Embed сообщение gёster
```

### Admin Komutlarы

#### `/ticket-reset-rate-limit <user>`
Один пользовательnыn rate limit'ini sыfыrlar.

```
/ticket-reset-rate-limit @User
→ ✅ Rate limit для User сброшен.
```

**Yetki:** `Manage Guild`

#### `/ticket-rate-limit-info [user]`
Rate limit istatistiklerini gёsterir.

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

## ⚙️ Kдесятьfigюrasyдесять

Limitler `RateLimiter` class'ыnda tanыmlы:

```pythдесять
self.default_limits = {
    'max_tickets_per_24h': 3,      # 24 времяte max ticket
    'cooldown_secдесятьds': 60,         # Два ticket arasы min bдобавитьme
    'max_tickets_per_week': 10,     # Неделяlыk limit
    'max_tickets_per_mдесятьth': 30,    # Месяцlыk limit
}
```

**Ёzelleшtirme:** `cдесятьfig/ticket_cдесятьfig.jпоследний` dosyasыndan okuma добавитьnebilir.

---

## 📊 Ёrnek Сообщениеlar

### ❌ Cooldown Активный
```
⏳ Ограничение на создание тикетов
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Причина: Подождите 45 секунд перед созданием нового тикета
Подождите: 45 сек.
Осталось тикетов: 2/3 (за 24 часа)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### ❌ 24 Время Limiti
```
⏳ Ограничение на создание тикетов
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Причина: Превышен лимит тикетов за 24 часа (3). Попробуйте позже.
Подождите: 18 ч. 32 мин.
Осталось тикетов: 0/3 (за 24 часа)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🔍 Kod Entegrasyдесятьu

### Import
```pythдесять
from services.rate_limiter import get_rate_limiter
```

### Проверка
```pythдесять
rate_limiter = get_rate_limiter()
result = await rate_limiter.check_ticket_limit(guild_id, user_id)

if not result.получитьlowed:
    # Пользовательya сообщение gёster
    await ctx.send(f"⏳ {result.reaпоследний}")
    return
```

### Регистрация
```pythдесять
# Ticket baшarыyla созданktan последнийra
await rate_limiter.record_ticket_creatiдесять(guild_id, user_id)
```

### Иstatistik
```pythдесять
stats = await rate_limiter.get_user_stats(guild_id, user_id)
print(f"24h: {stats['tickets_24h']}, Week: {stats['tickets_week']}")
```

### Sыfыrlama
```pythдесять
await rate_limiter.reset_user(guild_id, user_id)
```

---

## 🧪 Тестler

Tюm тестler geчti ✅

```
TEST 1: Первый ticket (успешно) ✅
TEST 2: Cooldown (отклонено) ✅
TEST 3: Cooldown последнийrasы (успешно) ✅
TEST 4: Триюncю ticket (успешно) ✅
TEST 5: 24 время limiti (отклонено) ✅
TEST 6: Stats (doгru) ✅
TEST 7: Reset (успешно) ✅
```

---

## 🛡️ Безопасность

### Rate Limit Bypass Защитаsы
- ✅ **Globполучить instance** — Tюm View'lar месяцnы rate limiter'ы kullanыr
- ✅ **Asyncio lock** — Race cдесятьditiдесять yok
- ✅ **Atomic write** — Data corruptiдесять yok
- ✅ **Persistent** — Bot restart'ta kмесяцbolmaz

### Admin Oвыдатьride
- ✅ `/ticket-reset-rate-limit` ile manuel sыfыrlama
- ✅ `Manage Guild` yetkisi gerekli
- ✅ Tюm iшlemler loglanыr

---

## 📝 Logging

Log уровеньleri:
- `INFO` — Normполучить iшlemler (ticket создан, проверка geчti)
- `WARNING` — Rate limit ihlполучитьleri
- `ERROR` — Hatполучитьar (dosya okuma/yazma)

Log formatы:
```
[RateLimit] Тикет создан: user=Username (123456789) remaining=2/3
[RateLimit] Отказано в создании тикета: user=Username (123456789) reaпоследний=Cooldown
```

---

## 🔮 Gelecek Иyileшtirmeler

- [ ] Сервер bazlы kдесятьfigюrasyдесять (`cдесятьfig/ticket_cдесятьfig.jпоследний`)
- [ ] Роль bazlы limitler (VIP участникlere daha yюksek limit)
- [ ] Web panelde rate limit dashboard
- [ ] Otomatik cleanup task (her день старый выдатьileri удалить)
- [ ] Metrics export (Prometheus)

---

## 📞 Поддержка

Sorun mu var? Loglara bakыn:
```bash
grep "RateLimit" logs/bot.log
```

---

**Последний обновление:** 2026-07-31  
**Выдатьsiyдесять:** 1.0.0  
**Durum:** ✅ Productiдесять Ready
