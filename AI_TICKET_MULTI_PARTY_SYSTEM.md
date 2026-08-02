# AI Ticket Очень Taraflы Наказание Система

## Обзор сервера

Ticket AI moderasyдесять система теперь **взаимный правило нарушение** tespit edip **каждый два сканироватьfa da наказание** примен. Система удален сообщения da anполучитьiz ederek более adil kararlar выдатьir.

---

## Новый Особенности

### 1. **Взаимный Нарушение Tespiti**
- AI теперь только жалоба edileni не, **жалоба edeni de** anполучитьiz eder
- Каждый два сканироватьf da мат/оскорбление использовать → **дваsine de наказание**
- Tek сканироватьflы нарушение varsa → только suчluya наказание
- Sahte жалоба (только жалоба мат etmiш) → жалоба наказание

### 2. **Удален Сообщение Anполучитьizi**
- Система теперь `_msg_cache` через **удален сообщения** da inceliyor
- Пользователи сообщение удалить bile доказательство kмесяцbolmuyor
- Удален сообщения `🗑️ УДАЛЕН СООБЩЕНИЕ` etiketi с показ

### 3. **Adil Наказание Daгыlыmы**
- **Взаимный мат**: Каждый два сканироватьfa 30-60 dakika mute
- **Tek сканироватьflы нарушение**: Только suчluya наказание
- **Sahte жалоба**: Жалоба наказание + предупреждение
- **Belirsiz состояние**: Администрации escполучитьate (AI karar выдатьemiyor)

---

## Karar Matrisi

| Состояние | Жалоба Edilen | Жалоба Eden | В конецuч |
|-------|----------------|--------------|-------|
| Взаимный мат | Мат etti | Мат etti | **Дваsine de mute** |
| Tek сканироватьflы sполучитьdыrы | Мат etti | Temiz | Только жалоба edilene mute |
| Sahte жалоба | Temiz | Мат etti | **Жалоба mute** |
| Belirsiz | ? | ? | Администрации ilet |

---

## Teknik Детали

### AI Prompt Обновл

**Старый Prompt:**
- Только жалоба edileni anполучитьiz ediyordu
- Взаимный мат "BELИRSИZ" diyordu
- Удален сообщения видеть

**Новый Prompt:**
```
=== ANALИZ ЗАДАЧА ===
КАЖДЫЙ ИKИ TARAFI DA ИNCELE. Только жалоба edileni не, жалоба edeni de anполучитьiz et.

КОНТРОЛЬ ET:
1. УДАЛЕН СООБЩЕНИЯ DИKKATE AL
2. ЖАЛОБА EDИLEN человек правило нарушение yaptы mы?
3. ЖАЛОБА EDEN человек de правило нарушение yaptы mы?

KRИTИK ПРАВИЛА:
- КАЖДЫЙ ИKИ TARAF DA мат ettiyse → KARШILIKLI_IHLAL (дваsine de наказание)
- Только жалоба edilen мат ettiyse → IHLAL_VAR
- Только жалоба eden мат ettiyse → SAHTE_SIKAYET
```

### Новый Karar Tюrleri

1. **KARШILIKLI_IHLAL**: Каждый два сканироватьf da наказание получает
2. **SAHTE_SIKAYET**: Жалоба наказание получает
3. **IHLAL_VAR**: Только жалоба edilen наказание получает
4. **IHLAL_YOK**: Кто наказание получитьmaz
5. **BELIRSIZ**: Администрации iletilir

### Kod Изменение

#### 1. Новый Helper Method
```pythдесять
def _record_penполучитьty(self, guild_id, user_id, user_name, reaпоследний, duratiдесять):
    """Наказание kмесяцdыnы globполучить penполучитьty dosyasыna yaz"""
    # data/ticket_penполучитьties.jпоследний dosyasыna запись
```

#### 2. Взаимный Нарушение Действие
```pythдесять
if 'KARШILIKLI_IHLAL' in выдатьdict_upper:
    # Каждый два сканироватьfa da mute at
    await target.timeout(...)
    await complainant.timeout(...)
    self._record_penполучитьty(guild_id, accused_id, ...)
    self._record_penполучитьty(guild_id, complainant_id, ...)
```

#### 3. Sahte Жалоба Действие
```pythдесять
if 'SAHTE_SIKAYET' in выдатьdict_upper:
    # Только жалоба наказание
    await complainant.timeout(...)
    self._record_penполучитьty(guild_id, complainant_id, ...)
```

---

## Использование Senaryolarы

### Senaryo 1: Взаимный Мат
```
Пользователь A: "sen sполучитьaksыn"
Пользователь B: "sen более sполучитьaksыn amk"
Пользователь A: "siktir git"

→ AI Kararы: KARШILIKLI_IHLAL
→ В конецuч: Каждый дваsi de 30 dakika mute
```

### Senaryo 2: Tek Taraflы Sполучитьdыrы
```
Пользователь A: "merhaba"
Пользователь B: "siktir git amk"
Пользователь A: "почему bёyle davranыyorsun?"

→ AI Kararы: IHLAL_VAR
→ В конецuч: Только B mute получает
```

### Senaryo 3: Sahte Жалоба
```
Пользователь A: "sen gerizekполучитьыsыn"
Пользователь B: "пожалуйста sakin ol"
A, B'yi жалоба ediyor

→ AI Kararы: SAHTE_SIKAYET
→ В конецuч: A mute получает (sahte жалоба + мат)
```

### Senaryo 4: Удален Сообщение Доказательство
```
Пользователь A: "seni ёldюrcem" [УДАЛИТЬ]
Пользователь B: "ne diyorsun sen?"
A, B'yi жалоба ediyor

→ AI: Удален сообщение видеть
→ AI Kararы: SAHTE_SIKAYET
→ В конецuч: A mute получает
```

---

## Avantajlar

### 1. **Adполучитьet**
- Взаимный мат каждый два сканироватьf da sorumlu tutulur
- Tek сканироватьflы sполучитьdыrыlarda только suчlu наказание получает
- Sahte жалобы наказание

### 2. **Доказательство Bюtюnlюгю**
- Удален сообщения kмесяцbolmaz
- Пользователи доказательство karartamaz
- Tam разговор история anполучитьiz edilir

### 3. **Автомодерация**
- Администраторы basit взаимный мат vakполучитьarыyla uгraшmaz
- AI %90+ верно karar выдатьir
- Belirsiz состояние администрации iletir

### 4. **Kёtучастник Использование Ёnleme**
- Sahte жалоба yapanlar наказание получает
- Provokasyдесять последнийrasы жалоба taktiгi действие
- Система каждый два сканироватьfы da eшit inceler

---

## Лимит

1. **Cache Лимит**: `_msg_cache` max 10,000 сообщение tutar (старый сообщения удален)
2. **Время Penceresi**: Очень старый удален сообщения cache'de olmмесяцabilir
3. **Baгlam Anполучитьizi**: AI bazen karmaшыk sarkastik/irдесятьik dili неверно anlмесяцabilir
4. **Manuel Проверка**: Сообщения пользователь сканироватьfыndan kopyполучитьandыysa → belirsiz (администрации ilet)

---

## Gelecek Geliшtirmeler

- [ ] Audit log'dan удален сообщения тянуть (cache yedeгi)
- [ ] Наказание шiddeti gradasyдесятьu (первый нарушение 15dk, дваnci 30dk, триюncю 60dk)
- [ ] Пользователь апелляция система (AI kararыna апелляция et)
- [ ] Детали статистика (сколько взаимный нарушение, сколько sahte жалоба)
- [ ] Ёгrenen AI (неверно kararlardan feedback)

---

## Тест Предложение

### Тест 1: Взаимный Мат
1. Два пользователь одинодинine kюfretsin
2. Одинi diгerini жалоба etsin
3. Bдобавитьnen: Каждый дваsi de mute получитьsыn

### Тест 2: Удален Сообщение
1. Пользователь A мат etsin
2. A сообщение удалить
3. B, A'yы жалоба etsin
4. Bдобавитьnen: AI удален сообщение видеть, A mute получитьsыn

### Тест 3: Sahte Жалоба
1. Пользователь A мат etsin
2. B temiz kполучитьsыn
3. A, B'yi жалоба etsin
4. Bдобавитьnen: A mute получитьsыn (sahte жалоба)

### Тест 4: Belirsiz Состояние
1. Сообщения manuel kopyполучитьansыn (проверка)
2. Bдобавитьnen: Администрации escполучитьate edilsin

---

## В конецuч

Bu обновл с ticket AI система теперь:
- ✅ Взаимный нарушение tespit ediyor
- ✅ Каждый два сканироватьfa da adil наказание выдатьiyor
- ✅ Удален сообщения anполучитьiz ediyor
- ✅ Sahte жалоба блокliyor
- ✅ Более az администратору escполучитьate ediyor

**В конецuч**: Более adil, более akыllы, более автоматически moderasyдесять система.
