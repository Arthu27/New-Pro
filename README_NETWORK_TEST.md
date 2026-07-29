# Ağ Güvenlik Test Araçları

Bu araçlar **sadece kendi ağınızı ve sistemlerinizi test etmek** için geliştirilmiştir. White hat (etik hacker) perspektifiyle güvenlik testleri yapmayı öğrenmenize yardımcı olur.

## ⚠️ ÖNEMLİ UYARI

- **Başkalarının ağlarına izinsiz erişim YASA DIŞIDIR**
- **Sadece kendi bilgisayarınızı ve ağınızı test edin**
- **İzinsiz testler ağır cezalara sebep olabilir**

## 📁 DOSYALAR

1. **`network_security_tester.py`** - Ana ağ test aracı
2. **`pratik_network_test.py`** - Pratik test örnekleri
3. **`white_hack_rehberi.md`** - White hat hacking rehberi
4. **`README_NETWORK_TEST.md`** - Bu dosya

## 🚀 KURULUM VE ÇALIŞTIRMA

### Gereksinimler
- Python 3.6+
- Windows/Linux/Mac
- Yönetici/root yetkileri (bazı testler için)

### Windows'ta Çalıştırma
```cmd
# Komut istemini yönetici olarak açın
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

# Python3 kullanın
python3 network_security_tester.py

# Veya
sudo python3 pratik_network_test.py  # Bazı testler için root gerekir
```

## 🛠️ ARAÇLARIN ÖZELLİKLERİ

### 1. network_security_tester.py
- **Ağ keşfi**: Yerel ağdaki aktif cihazları bulma
- **Port tarama**: Kendi bilgisayarınızdaki açık portları tespit etme
- **WiFi güvenliği**: Kayıtlı WiFi şifrelerini görüntüleme (sadece kendi ağlarınız)
- **DoS simülasyonu**: Eğitim amaçlı localhost testi
- **Rapor oluşturma**: Test sonuçlarını JSON formatında kaydetme

### 2. pratik_network_test.py
- **6 pratik test** içerir:
  1. Yerel ağ keşfi
  2. Açık port kontrolü
  3. WiFi güvenlik kontrolü
  4. DNS güvenlik testi
  5. Firewall durumu
  6. Sistem sertleştirme önerileri
- **Otomatik rapor** oluşturur

### 3. white_hack_rehberi.md
- **Kapsamlı rehber**: 2000+ kelime
- **Etik kurallar**: Neler yapılıp yapılamaz
- **Öğrenme yolları**: Sertifikalar, platformlar, kitaplar
- **Pratik örnekler**: Lab kurulumu, test teknikleri
- **Yasal uyarılar**: Olası sonuçlar

## 🎯 NE ÖĞRENECEKSİNİZ?

### Temel Kavramlar
- Ağ protokolleri (TCP/IP, UDP)
- Portlar ve servisler
- Firewall ve güvenlik duvarları
- DNS ve ağ yapılandırması

### Test Teknikleri
- Pasif keşif (information gathering)
- Aktif tarama (port scanning)
- Zafiyet tespiti (vulnerability assessment)
- Güvenlik sertleştirme (hardening)

### Savunma Stratejileri
- Saldırı tespit sistemleri (IDS)
- Log analizi ve izleme
- Incident response (olay müdahalesi)
- Yedekleme ve kurtarma

## 🔒 GÜVENLİK ÖNLEMLERİ

### Yapılması Gerekenler
- [x] Sadece kendi ağınızı test edin
- [x] Sanal lab ortamı kurun (VirtualBox + Kali Linux)
- [x] İzinli test platformlarını kullanın (HackTheBox, TryHackMe)
- [x] Sertifika programlarına katılın (CEH, OSCP)
- [x] Etik kurallara uyun

### Yapılmaması Gerekenler
- [ ] Başkalarının WiFi'sini kırmaya çalışmayın
- [ ] İzinsiz port taraması yapmayın
- [ ] Sosyal medya hesaplarını hacklemeye çalışmayın
- [ ] Fidye yazılımı yazmayın/test etmeyin
- [ ] DDoS saldırısı yapmayın

## 📚 ÖĞRENME KAYNAKLARI

### Ücretsiz Platformlar
- **TryHackMe**: Başlangıç seviyesi, eğitim odaklı
- **HackTheBox**: Orta-ileri seviye, pratik
- **OverTheWire**: War games, temel Linux komutları
- **VulnHub**: Zafiyetli sanal makineler

### Sertifikalar
- **CEH** (Certified Ethical Hacker): Giriş seviyesi
- **eJPT** (eLearnSecurity Junior Penetration Tester): Pratik odaklı
- **OSCP** (Offensive Security Certified Professional): Zorlu, pratik sınav
- **CompTIA Security+**: Temel güvenlik bilgisi

### Kitaplar
- "The Web Application Hacker's Handbook"
- "Penetration Testing: A Hands-On Introduction"
- "Metasploit: The Penetration Tester's Guide"

## 🆘 SIK SORULAN SORULAR

### Q: Bu araçları başkalarının ağını test etmek için kullanabilir miyim?
**A: HAYIR!** Bu kesinlikle yasa dışıdır. Sadece kendi ağınızı test edin.

### Q: WiFi şifrelerini görüntülemek yasal mı?
**A:** Sadece kendi kayıtlı WiFi ağlarınızın şifrelerini görüntüleyebilirsiniz. Başkalarının WiFi şifrelerini almaya çalışmak yasa dışıdır.

### Q: Port taraması yapmak suç mu?
**A:** Kendi bilgisayarınızın portlarını taramak suç değildir. Ancak başkalarının sistemlerini izinsiz taramak "yetkisiz erişim" suçudur.

### Q: Nasıl yasal şekilde pratik yapabilirim?
**A:** 
1. Sanal lab kurun (VirtualBox + Metasploitable)
2. İzinli platformları kullanın (HackTheBox, TryHackMe)
3. CTF yarışmalarına katılın
4. Sertifika programları alın

### Q: Bir güvenlik açığı bulursam ne yapmalıyım?
**A:**
1. Açığı detaylı dokümante edin
2. Sistem sahibine sorumlu şekilde bildirin
3. Proof of concept hazırlayın
4. Düzeltme önerileri sunun
5. Halka açıklamadan önce süre tanıyın (genelde 90 gün)

## 📞 ACİL DURUM

Eğer:
- Bir siber saldırıya uğradıysanız
- Kişisel verileriniz çalındıysa
- Fidye yazılımı bulaştıysa

**Hemen:**
1. İnterneti kesin
2. Antivirüs taraması yapın
3. Şifrelerinizi değiştirin
4. Bankanızı bilgilendirin
5. Polise/EGM Siber Suçlarla Mücadele'ye başvurun

## 📝 LİSANS VE SORUMLULUK

Bu araçlar **eğitim amaçlıdır**. Kullanıcı tüm sorumluluğu kabul eder. Geliştirici hiçbir yasadışı kullanımdan sorumlu değildir.

**Unutmayın:** Bilgi güçtür, bu gücü sorumlulukla kullanın. İyi bir white hat hacker olmak zaman alır, sabırlı olun ve her zaman etik kalın.

---
*Son güncelleme: Mayıs 2026*  
*Geliştirici: White Hat Security Eğitim Projesi*