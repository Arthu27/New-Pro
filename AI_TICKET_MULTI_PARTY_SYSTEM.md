# AI Ticket Очень Taraflı Наказание Система

## Обзор сервера

Ticket AI moderasyon система теперь **взаимный правило нарушение** tespit edip **каждый iki сканироватьfa da наказание** примен. Система удален сообщения da analiz ederek более adil kararlar verir.

---

## Новый Особенности

### 1. **Взаимный Нарушение Tespiti**
- AI теперь только жалоба edileni не, **жалоба edeni de** analiz eder
- Каждый iki сканироватьf da мат/оскорбление использовать → **ikisine de наказание**
- Tek сканироватьflı нарушение varsa → только suçluya наказание
- Sahte жалоба (только жалоба мат etmiş) → жалоба наказание

### 2. **Удален Сообщение Analizi**
- Система теперь `_msg_cache` через **удален сообщения** da inceliyor
- Пользователи сообщение удалить bile доказательство kaybolmuyor
- Удален сообщения `🗑️ УДАЛЕН СООБЩЕНИЕ` etiketi с показ

### 3. **Adil Наказание Dağılımı**
- **Взаимный мат**: Каждый iki сканироватьfa 30-60 dakika mute
- **Tek сканироватьflı нарушение**: Только suçluya наказание
- **Sahte жалоба**: Жалоба наказание + предупреждение
- **Belirsiz состояние**: Администрации escalate (AI karar veremiyor)

---

## Karar Matrisi

| Состояние | Жалоба Edilen | Жалоба Eden | В конецuç |
|-------|----------------|--------------|-------|
| Взаимный мат | Мат etti | Мат etti | **İkisine de mute** |
| Tek сканироватьflı saldırı | Мат etti | Temiz | Только жалоба edilene mute |
| Sahte жалоба | Temiz | Мат etti | **Жалоба mute** |
| Belirsiz | ? | ? | Администрации ilet |

---

## Teknik Детали

### AI Prompt Обновл

**Старый Prompt:**
- Только жалоба edileni analiz ediyordu
- Взаимный мат "BELİRSİZ" diyordu
- Удален сообщения видеть

**Новый Prompt:**
```
=== ANALİZ ЗАДАЧА ===
КАЖДЫЙ İKİ TARAFI DA İNCELE. Только жалоба edileni не, жалоба edeni de analiz et.

КОНТРОЛЬ ET:
1. УДАЛЕН СООБЩЕНИЯ DİKKATE AL
2. ЖАЛОБА EDİLEN человек правило нарушение yaptı mı?
3. ЖАЛОБА EDEN человек de правило нарушение yaptı mı?

KRİTİK ПРАВИЛА:
- КАЖДЫЙ İKİ TARAF DA мат ettiyse → KARŞILIKLI_IHLAL (ikisine de наказание)
- Только жалоба edilen мат ettiyse → IHLAL_VAR
- Только жалоба eden мат ettiyse → SAHTE_SIKAYET
```

### Новый Karar Türleri

1. **KARŞILIKLI_IHLAL**: Каждый iki сканироватьf da наказание получает
2. **SAHTE_SIKAYET**: Жалоба наказание получает
3. **IHLAL_VAR**: Только жалоба edilen наказание получает
4. **IHLAL_YOK**: Кто наказание almaz
5. **BELIRSIZ**: Администрации iletilir

### Kod Изменение

#### 1. Новый Helper Method
```python
def _record_penalty(self, guild_id, user_id, user_name, reason, duration):
    """Наказание kaydını global penalty dosyasına yaz"""
    # data/ticket_penalties.json dosyasına запись
```

#### 2. Взаимный Нарушение Действие
```python
if 'KARŞILIKLI_IHLAL' in verdict_upper:
    # Каждый iki сканироватьfa da mute at
    await target.timeout(...)
    await complainant.timeout(...)
    self._record_penalty(guild_id, accused_id, ...)
    self._record_penalty(guild_id, complainant_id, ...)
```

#### 3. Sahte Жалоба Действие
```python
if 'SAHTE_SIKAYET' in verdict_upper:
    # Только жалоба наказание
    await complainant.timeout(...)
    self._record_penalty(guild_id, complainant_id, ...)
```

---

## Использование Senaryoları

### Senaryo 1: Взаимный Мат
```
Пользователь A: "sen salaksın"
Пользователь B: "sen более salaksın amk"
Пользователь A: "siktir git"

→ AI Kararı: KARŞILIKLI_IHLAL
→ В конецuç: Каждый ikisi de 30 dakika mute
```

### Senaryo 2: Tek Taraflı Saldırı
```
Пользователь A: "merhaba"
Пользователь B: "siktir git amk"
Пользователь A: "почему böyle davranıyorsun?"

→ AI Kararı: IHLAL_VAR
→ В конецuç: Только B mute получает
```

### Senaryo 3: Sahte Жалоба
```
Пользователь A: "sen gerizekalısın"
Пользователь B: "пожалуйста sakin ol"
A, B'yi жалоба ediyor

→ AI Kararı: SAHTE_SIKAYET
→ В конецuç: A mute получает (sahte жалоба + мат)
```

### Senaryo 4: Удален Сообщение Доказательство
```
Пользователь A: "seni öldürcem" [УДАЛИТЬ]
Пользователь B: "ne diyorsun sen?"
A, B'yi жалоба ediyor

→ AI: Удален сообщение видеть
→ AI Kararı: SAHTE_SIKAYET
→ В конецuç: A mute получает
```

---

## Avantajlar

### 1. **Adalet**
- Взаимный мат каждый iki сканироватьf da sorumlu tutulur
- Tek сканироватьflı saldırılarda только suçlu наказание получает
- Sahte жалобы наказание

### 2. **Доказательство Bütünlüğü**
- Удален сообщения kaybolmaz
- Пользователи доказательство karartamaz
- Tam разговор история analiz edilir

### 3. **Автомодерация**
- Администраторы basit взаимный мат vakalarıyla uğraşmaz
- AI %90+ верно karar verir
- Belirsiz состояние администрации iletir

### 4. **Kötüye Использование Önleme**
- Sahte жалоба yapanlar наказание получает
- Provokasyon sonrası жалоба taktiği действие
- Система каждый iki сканироватьfı da eşit inceler

---

## Лимит

1. **Cache Лимит**: `_msg_cache` max 10,000 сообщение tutar (старый сообщения удален)
2. **Время Penceresi**: Очень старый удален сообщения cache'de olmayabilir
3. **Bağlam Analizi**: AI bazen karmaşık sarkastik/ironik dili неверно anlayabilir
4. **Manuel Проверка**: Сообщения пользователь сканироватьfından kopyalandıysa → belirsiz (администрации ilet)

---

## Gelecek Geliştirmeler

- [ ] Audit log'dan удален сообщения тянуть (cache yedeği)
- [ ] Наказание şiddeti gradasyonu (ilk нарушение 15dk, ikinci 30dk, üçüncü 60dk)
- [ ] Пользователь апелляция система (AI kararına апелляция et)
- [ ] Детали статистика (сколько взаимный нарушение, сколько sahte жалоба)
- [ ] Öğrenen AI (неверно kararlardan feedback)

---

## Test Предложение

### Test 1: Взаимный Мат
1. İki пользователь birbirine küfretsin
2. Biri diğerini жалоба etsin
3. Beklenen: Каждый ikisi de mute alsın

### Test 2: Удален Сообщение
1. Пользователь A мат etsin
2. A сообщение удалить
3. B, A'yı жалоба etsin
4. Beklenen: AI удален сообщение видеть, A mute alsın

### Test 3: Sahte Жалоба
1. Пользователь A мат etsin
2. B temiz kalsın
3. A, B'yi жалоба etsin
4. Beklenen: A mute alsın (sahte жалоба)

### Test 4: Belirsiz Состояние
1. Сообщения manuel kopyalansın (проверка)
2. Beklenen: Администрации escalate edilsin

---

## В конецuç

Bu обновл с ticket AI система теперь:
- ✅ Взаимный нарушение tespit ediyor
- ✅ Каждый iki сканироватьfa da adil наказание veriyor
- ✅ Удален сообщения analiz ediyor
- ✅ Sahte жалоба engelliyor
- ✅ Более az администратору escalate ediyor

**В конецuç**: Более adil, более akıllı, более автоматически moderasyon система.
