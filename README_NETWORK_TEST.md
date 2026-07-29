# Ağ Безопасность Test Araçları

Bu araçlar **только kendi ağınızı ve sistemlerinizi test etmek** для geliştirilmiştir. White hat (etik hacker) perspektifiyle безопасность testleri yapmayı öğrenmenize помощник olur.

## ⚠️ ÖNEMLİ ПРЕДУПРЕЖДЕНИЕ

- **Başkalarının ağlarına без разрешения erişim YASA DIŞIDIR**
- **Только kendi информация ve ağınızı test edin**
- **İzinsiz testler тяжелый наказание причина olabilir**

## 📁 DOSYALAR

1. **`network_security_tester.py`** - Ana ağ test aracı
2. **`pratik_network_test.py`** - Pratik test пример
3. **`white_hack_rehberi.md`** - White hat hacking руководство
4. **`README_NETWORK_TEST.md`** - Bu dosya

## 🚀 УСТАНОВКА VE ÇALIŞTIRMA

### Gereksinimler
- Python 3.6+
- Windows/Linux/Mac
- Yönetici/root администратор (bazı testler для)

### Windows'ta Çalıştırma
```cmd
# Команда желание yönetici как açın
cd "d:\BACK\Documents\discord_bot"

# Ana test aracını çalıştırın
python network_security_tester.py

# Pratik testleri çalıştırın
python pratik_network_test.py
```

### Linux/Mac'te Çalıştırma
```bash
# Terminali açın
cd /path/to/discord_bot

# Python3 использовать
python3 network_security_tester.py

# Или
sudo python3 pratik_network_test.py  # Bazı testler для root gerekir
```

## 🛠️ ARAÇLARIN ОСОБЫЙ

### 1. network_security_tester.py
- **Ağ keşfi**: Yerel ağdaki активен cihazları bulma
- **Port сканироватьma**: Kendi информация открыт portları определитьme
- **WiFi доверие**: Запись WiFi пароль скриншот (только kendi ağlarınız)
- **DoS simülasyonu**: Eğitim aматчlı localhost testi
- **Rapor создан**: Test результат JSON formatında сохран

### 2. pratik_network_test.py
- **6 pratik test** содержимое:
  1. Yerel ağ keşfi
  2. Открыт port контроль
  3. WiFi безопасность контроль
  4. DNS безопасность testi
  5. Firewall состояние
  6. Система sertleştirme предложение
- **Автоматически rapor** создан

### 3. white_hack_rehberi.md
- **Kapsamlı руководство**: 2000+ kelime
- **Etik правила**: Neler yapılıp yapılamaz
- **Öğrenme yolları**: Sertifikalar, platformlar, kitaplar
- **Pratik пример**: Lab kurulumu, test teknikleri
- **Yasal предупреждения**: Olası результат

## 🎯 NE ÖĞRENECEKSİNİZ?

### Temel Kavramlar
- Ağ protokolleri (TCP/IP, UDP)
- Portlar ve servisler
- Firewall ve безопасность duvarları
- DNS ve ağ yapılandırması

### Test Teknikleri
- Pasif keşif (information gathering)
- Активен сканироватьma (port scanning)
- Zafiyet tespiti (vulnerability assessment)
- Безопасность sertleştirme (hardening)

### Savunma Stratejileri
- Saldırı tespit sistemleri (IDS)
- Log analizi ve izleme
- Incident response (olay müdahalesi)
- Yedekleme ve kurtarma

## 🔒 БЕЗОПАСНОСТЬ ÖNLEMLERİ

### Yapılması Gerekenler
- [x] Только kendi ağınızı test edin
- [x] Sanal lab ortamı kurun (VirtualBox + Kali Linux)
- [x] İzinli test platformlarını использовать (HackTheBox, TryHackMe)
- [x] Sertifika programlarına katılın (CEH, OSCP)
- [x] Etik правил uyun

### Yapılmaması Gerekenler
- [ ] Başkalarının WiFi'sini kırmaya работа
- [ ] İzinsiz port сканироватьması yapmayın
- [ ] Sosyal medya hesaplarını hacklemeye работа
- [ ] Fidye написано yazmayın/test etmeyin
- [ ] DDoS saldırısı yapmayın

## 📚 ÖĞRENME KAYNAKLARI

### Ücretsiz Platformlar
- **TryHackMe**: Başlangıç seviyesi, eğitim комната
- **HackTheBox**: Orta-ileri seviye, pratik
- **OverTheWire**: War games, temel Linux команды
- **VulnHub**: Zafiyetli sanal makineler

### Sertifikalar
- **CEH** (Certified Ethical Hacker): Вход seviyesi
- **eJPT** (eLearnSecurity Junior Penetration Tester): Pratik комната
- **OSCP** (Offensive Security Certified Professional): Zorlu, pratik sınav
- **CompTIA Security+**: Temel безопасность информация

### Kitaplar
- "The Web Application Hacker's Handbook"
- "Penetration Testing: A Hands-On Introduction"
- "Metasploit: The Penetration Tester's Guide"

## 🆘 SIK SORULAN SORULAR

### Q: Bu araçları başkalarının ağını test etmek для использовать miyim?
**A: HAYIR!** Bu строго yasa dışıdır. Только kendi ağınızı test edin.

### Q: WiFi пароль скриншот yasal mı?
**A:** Только kendi запись WiFi ağlarınızın пароль скриншот. Başkalarının WiFi пароль almaya работать yasa dışıdır.

### Q: Port сканироватьması yapmak suç mu?
**A:** Kendi информация portlarını сканироватьmak suç değildir. Ancak başkalarının sistemlerini без разрешения сканироватьmak "администратор erişim" suçudur.

### Q: Как yasal şekilde pratik yapabilirim?
**A:** 
1. Sanal lab kurun (VirtualBox + Metasploitable)
2. İzinli platformları использовать (HackTheBox, TryHackMe)
3. CTF yarışmalarına katılın
4. Sertifika programları alın

### Q: Bir безопасность açığı bulursam ne yapmalıyım?
**A:**
1. Açığı детали dokümante edin
2. Система sahibine sorumlu şekilde bildirin
3. Proof of concept hazırlayın
4. Düzeltme предложение sunun
5. Halka описание до длительность tanıyın (genelde 90 день)

## 📞 ACİL СОСТОЯНИЕ

Если:
- Bir siber saldırıya uğradıysanız
- Kişisel verileriniz çalındıysa
- Fidye написано bulaştıysa

**Hemen:**
1. İnterneti kesin
2. Antivirüs сканироватьması yapın
3. Пароль değiştirin
4. Bankanızı информация
5. Polise/EGM Siber Suçlarla Mücadele'ye заявка

## 📝 LİSANS VE SORUMLULUK

Bu araçlar **eğitim aматчlıdır**. Пользователь все sorumluluğu kabul eder. Geliştirici hiçbir yasadışı использовать sorumlu değildir.

**Unutmayın:** Информация güçtür, bu gücü sorumlulukla использовать. İyi bir white hat hacker olmak время получает, sabırlı olun ve каждый время etik kalın.

---
*В конец обновл: Mayıs 2026*  
*Geliştirici: White Hat Security Eğitim Projesi*