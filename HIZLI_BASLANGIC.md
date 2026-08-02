# 🚀 AI Ticket Система - Быстрый Начало

## 1️⃣ Система Готов mы Контроль Et

```bash
# Bot'u запустить
pythдесять main.py
```

Bot началсягыnda шu сообщение видеть:
```
✅ Ticket cog loaded (AI enabled)
```

---

## 2️⃣ В начало Ticket Panelini Отправить

Discord'da один канал git ve:

```
/ticket-panel
```

Panel отправлено! Теперь пользователи "🎫 Создать тикет поддержки" butдесятьuna клик.

---

## 3️⃣ Тест Et

### Тест 1: Basit Soru
1. Ticket открыть
2. AI'nin приветствие сообщение видеть
3. Yaz: "bot команды nedir?"
4. AI ответитьecek

### Тест 2: Направление
1. Ticket открыть
2. Yaz: "X человек spam yapыyor, ban atыn"
3. AI направление ve поддержка роль ping atacak

---

## 4️⃣ Статистика Видеть

### Discord'da:
```
/ticket-ai-stats
```

### Web Panel'de:
1. Panel'e вход yap
2. Статистика → 🤖 AI Поддержка Ticketlarы
3. Все разговор видеть

---

## 5️⃣ AI'yi Закрыть/Открыть

```
/ticket-ai-toggle
```

Каждый запуститьdыгыnda tersine чevrilir (открыт → закрыт, закрыт → открыт)

---

## 6️⃣ Manuel Направление

Один ticket в канале:

```
/ticket-force-escполучитьate
```

AI durur, поддержка роль ping atыlыr.

---

## ⚙️ Настройкиы Deгiшtir

`cogs/ticket.py` dosyasыnы открыть:

```pythдесять
AI_ENABLED = True  # Fполучитьse yap = AI готовоen закрыт
MAX_AI_MESSAGES = 10  # 5 yap = более быстрый направление
```

Deгiшtirdikten после botu новыйden запустить.

---

## 🐛 Sorun Giderme

### AI ответитьmiyor
- `AI_ENABLED = True` olduгundan emin ol
- OpenRouter API key'in действительный olduгunu контроль et
- Bot loglarыna bak (ошибка var mы?)

### Поддержка роль ping atыlmыyor
- "Поддержка" adыnda один роль olduгundan emin ol
- Роль mentiдесять edilebilir olduгunu контроль et

### Web panel'de ticket видеть
- Ticket открытьыldыktan после en az 1 сообщение написано emin ol
- `data/ai_tickets_<guild_id>.jпоследний` dosyasыnыn var olduгunu контроль et

---

## 📚 Более Fazla Информация

- **Детали Dokюmantasyдесять**: `AI_TICKET_SYSTEM.md`
- **Akыш Diyagramы**: `AI_TICKET_FLOW.txt`
- **Краткий Сводка**: `AI_TICKET_OZET.md`

---

## ✅ Checklist

- [ ] Bot работает
- [ ] `/ticket-panel` отправлено
- [ ] Тест ticket открытьыldы
- [ ] AI ответитьdi
- [ ] Направление тест edildi
- [ ] Web panel'de скриншот
- [ ] Статистика контроль edildi

**Hepsi готовоsa, система готов! 🎉**
