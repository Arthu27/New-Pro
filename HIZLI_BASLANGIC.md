# 🚀 AI Ticket Система - Быстрый Başlangıç

## 1️⃣ Система Hazır mı Контроль Et

```bash
# Bot'u çalıştır
python main.py
```

Bot başladığında şu сообщение видеть:
```
✅ Ticket cog loaded (AI enabled)
```

---

## 2️⃣ В начало Ticket Panelini Отправить

Discord'da bir канал git ve:

```
/ticket-panel
```

Panel отправлено! Теперь пользователи "🎫 Создать тикет поддержки" butonuna клик.

---

## 3️⃣ Test Et

### Test 1: Basit Soru
1. Ticket aç
2. AI'nin приветствие сообщение видеть
3. Yaz: "bot команды nedir?"
4. AI ответитьecek

### Test 2: Направление
1. Ticket aç
2. Yaz: "X человек spam yapıyor, ban atın"
3. AI направление ve поддержка роль ping atacak

---

## 4️⃣ Статистика Видеть

### Discord'da:
```
/ticket-ai-stats
```

### Web Panel'de:
1. Panel'e вход yap
2. Статистика → 🤖 AI Поддержка Ticketları
3. Все разговор видеть

---

## 5️⃣ AI'yi Закрыть/Aç

```
/ticket-ai-toggle
```

Каждый çalıştırdığında tersine çevrilir (открыт → закрыт, закрыт → открыт)

---

## 6️⃣ Manuel Направление

Bir ticket в канале:

```
/ticket-force-escalate
```

AI durur, поддержка роль ping atılır.

---

## ⚙️ Настройкиı Değiştir

`cogs/ticket.py` dosyasını aç:

```python
AI_ENABLED = True  # False yap = AI tamamen закрыт
MAX_AI_MESSAGES = 10  # 5 yap = более быстрый направление
```

Değiştirdikten после botu yeniden запустить.

---

## 🐛 Sorun Giderme

### AI ответитьmiyor
- `AI_ENABLED = True` olduğundan emin ol
- OpenRouter API key'in geçerli olduğunu контроль et
- Bot loglarına bak (ошибка var mı?)

### Поддержка роль ping atılmıyor
- "Поддержка" adında bir роль olduğundan emin ol
- Роль mention edilebilir olduğunu контроль et

### Web panel'de ticket видеть
- Ticket açıldıktan после en az 1 сообщение написано emin ol
- `data/ai_tickets_<guild_id>.json` dosyasının var olduğunu контроль et

---

## 📚 Более Fazla Информация

- **Детали Dokümantasyon**: `AI_TICKET_SYSTEM.md`
- **Akış Diyagramı**: `AI_TICKET_FLOW.txt`
- **Краткий Сводка**: `AI_TICKET_OZET.md`

---

## ✅ Checklist

- [ ] Bot работает
- [ ] `/ticket-panel` отправлено
- [ ] Test ticket açıldı
- [ ] AI ответитьdi
- [ ] Направление test edildi
- [ ] Web panel'de скриншот
- [ ] Статистика контроль edildi

**Hepsi tamamsa, система hazır! 🎉**
