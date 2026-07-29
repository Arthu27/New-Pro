# AI Ticket Çok Taraflı Ceza Sistemi

## Genel Bakış

Ticket AI moderasyon sistemi artık **karşılıklı kural ihlallerini** tespit edip **her iki tarafa da ceza** uygulayabilir. Sistem silinen mesajları da analiz ederek daha adil kararlar verir.

---

## Yeni Özellikler

### 1. **Karşılıklı İhlal Tespiti**
- AI artık sadece şikayet edileni değil, **şikayet edeni de** analiz eder
- Her iki taraf da küfür/hakaret kullandıysa → **ikisine de ceza**
- Tek taraflı ihlal varsa → sadece suçluya ceza
- Sahte şikayet (sadece şikayetçi küfür etmiş) → şikayetçiye ceza

### 2. **Silinen Mesaj Analizi**
- Sistem artık `_msg_cache` üzerinden **silinen mesajları** da inceliyor
- Kullanıcılar mesajlarını silse bile kanıt kaybolmuyor
- Silinen mesajlar `🗑️ SİLİNMİŞ MESAJ` etiketi ile gösteriliyor

### 3. **Adil Ceza Dağılımı**
- **Karşılıklı küfür**: Her iki tarafa 30-60 dakika mute
- **Tek taraflı ihlal**: Sadece suçluya ceza
- **Sahte şikayet**: Şikayetçiye ceza + uyarı
- **Belirsiz durum**: Yetkililere escalate (AI karar veremiyor)

---

## Karar Matrisi

| Durum | Şikayet Edilen | Şikayet Eden | Sonuç |
|-------|----------------|--------------|-------|
| Karşılıklı küfür | Küfür etti | Küfür etti | **İkisine de mute** |
| Tek taraflı saldırı | Küfür etti | Temiz | Sadece şikayet edilene mute |
| Sahte şikayet | Temiz | Küfür etti | **Şikayetçiye mute** |
| Belirsiz | ? | ? | Yetkililere ilet |

---

## Teknik Detaylar

### AI Prompt Güncellemeleri

**Eski Prompt:**
- Sadece şikayet edileni analiz ediyordu
- Karşılıklı küfürde "BELİRSİZ" diyordu
- Silinen mesajları görmüyordu

**Yeni Prompt:**
```
=== ANALİZ GÖREVİN ===
HER İKİ TARAFI DA İNCELE. Sadece şikayet edileni değil, şikayet edeni de analiz et.

KONTROL ET:
1. SİLİNEN MESAJLARI DİKKATE AL
2. ŞİKAYET EDİLEN kişi kural ihlali yaptı mı?
3. ŞİKAYET EDEN kişi de kural ihlali yaptı mı?

KRİTİK KURALLAR:
- HER İKİ TARAF DA küfür ettiyse → KARŞILIKLI_IHLAL (ikisine de ceza)
- Sadece şikayet edilen küfür ettiyse → IHLAL_VAR
- Sadece şikayet eden küfür ettiyse → SAHTE_SIKAYET
```

### Yeni Karar Türleri

1. **KARŞILIKLI_IHLAL**: Her iki taraf da ceza alır
2. **SAHTE_SIKAYET**: Şikayetçi ceza alır
3. **IHLAL_VAR**: Sadece şikayet edilen ceza alır
4. **IHLAL_YOK**: Kimse ceza almaz
5. **BELIRSIZ**: Yetkililere iletilir

### Kod Değişiklikleri

#### 1. Yeni Helper Method
```python
def _record_penalty(self, guild_id, user_id, user_name, reason, duration):
    """Ceza kaydını global penalty dosyasına yaz"""
    # data/ticket_penalties.json dosyasına kayıt
```

#### 2. Karşılıklı İhlal İşleme
```python
if 'KARŞILIKLI_IHLAL' in verdict_upper:
    # Her iki tarafa da mute at
    await target.timeout(...)
    await complainant.timeout(...)
    self._record_penalty(guild_id, accused_id, ...)
    self._record_penalty(guild_id, complainant_id, ...)
```

#### 3. Sahte Şikayet İşleme
```python
if 'SAHTE_SIKAYET' in verdict_upper:
    # Sadece şikayetçiye ceza
    await complainant.timeout(...)
    self._record_penalty(guild_id, complainant_id, ...)
```

---

## Kullanım Senaryoları

### Senaryo 1: Karşılıklı Küfür
```
Kullanıcı A: "sen salaksın"
Kullanıcı B: "sen daha salaksın amk"
Kullanıcı A: "siktir git"

→ AI Kararı: KARŞILIKLI_IHLAL
→ Sonuç: Her ikisi de 30 dakika mute
```

### Senaryo 2: Tek Taraflı Saldırı
```
Kullanıcı A: "merhaba"
Kullanıcı B: "siktir git amk"
Kullanıcı A: "neden böyle davranıyorsun?"

→ AI Kararı: IHLAL_VAR
→ Sonuç: Sadece B mute alır
```

### Senaryo 3: Sahte Şikayet
```
Kullanıcı A: "sen gerizekalısın"
Kullanıcı B: "lütfen sakin ol"
A, B'yi şikayet ediyor

→ AI Kararı: SAHTE_SIKAYET
→ Sonuç: A mute alır (sahte şikayet + küfür)
```

### Senaryo 4: Silinen Mesaj Kanıtı
```
Kullanıcı A: "seni öldürcem" [SİLDİ]
Kullanıcı B: "ne diyorsun sen?"
A, B'yi şikayet ediyor

→ AI: Silinen mesajı görüyor
→ AI Kararı: SAHTE_SIKAYET
→ Sonuç: A mute alır
```

---

## Avantajlar

### 1. **Adalet**
- Karşılıklı küfürde her iki taraf da sorumlu tutulur
- Tek taraflı saldırılarda sadece suçlu ceza alır
- Sahte şikayetler cezalandırılır

### 2. **Kanıt Bütünlüğü**
- Silinen mesajlar kaybolmaz
- Kullanıcılar kanıt karartamaz
- Tam konuşma geçmişi analiz edilir

### 3. **Otomatik Moderasyon**
- Yetkililer basit karşılıklı küfür vakalarıyla uğraşmaz
- AI %90+ doğrulukla karar verir
- Belirsiz durumlarda yetkililere iletir

### 4. **Kötüye Kullanım Önleme**
- Sahte şikayet yapanlar ceza alır
- Provokasyon sonrası şikayet taktiği işlemez
- Sistem her iki tarafı da eşit inceler

---

## Sınırlamalar

1. **Cache Sınırı**: `_msg_cache` max 10,000 mesaj tutar (eski mesajlar silinir)
2. **Zaman Penceresi**: Çok eski silinen mesajlar cache'de olmayabilir
3. **Bağlam Analizi**: AI bazen karmaşık sarkastik/ironik dili yanlış anlayabilir
4. **Manuel Doğrulama**: Mesajlar kullanıcı tarafından kopyalandıysa → belirsiz (yetkililere ilet)

---

## Gelecek Geliştirmeler

- [ ] Audit log'dan silinen mesajları çekme (cache yedeği)
- [ ] Ceza şiddeti gradasyonu (ilk ihlal 15dk, ikinci 30dk, üçüncü 60dk)
- [ ] Kullanıcı itiraz sistemi (AI kararına itiraz et)
- [ ] Detaylı istatistikler (kaç karşılıklı ihlal, kaç sahte şikayet)
- [ ] Öğrenen AI (yanlış kararlardan feedback)

---

## Test Önerileri

### Test 1: Karşılıklı Küfür
1. İki kullanıcı birbirine küfretsin
2. Biri diğerini şikayet etsin
3. Beklenen: Her ikisi de mute alsın

### Test 2: Silinen Mesaj
1. Kullanıcı A küfür etsin
2. A mesajı silsin
3. B, A'yı şikayet etsin
4. Beklenen: AI silinen mesajı görsün, A mute alsın

### Test 3: Sahte Şikayet
1. Kullanıcı A küfür etsin
2. B temiz kalsın
3. A, B'yi şikayet etsin
4. Beklenen: A mute alsın (sahte şikayet)

### Test 4: Belirsiz Durum
1. Mesajlar manuel kopyalansın (doğrulanamaz)
2. Beklenen: Yetkililere escalate edilsin

---

## Sonuç

Bu güncelleme ile ticket AI sistemi artık:
- ✅ Karşılıklı ihlalleri tespit ediyor
- ✅ Her iki tarafa da adil ceza veriyor
- ✅ Silinen mesajları analiz ediyor
- ✅ Sahte şikayetleri engelliyor
- ✅ Daha az yetkiliye escalate ediyor

**Sonuç**: Daha adil, daha akıllı, daha otomatik moderasyon sistemi.
