# White Hat Hacking Rehberi
## Kendi Ağını Güvenlik Test Etme Kılavuzu

---

## ⚠️ ÖNEMLİ UYARI
Bu rehber **sadece kendi ağınızı ve sistemlerinizi test etmek** içindir. Başkalarının ağlarına, sistemlerine veya hesaplarına izinsiz erişim:
- **YASA DIŞIDIR**
- **AĞIR CEZALARI VARDIR**
- **ETİK DEĞİLDİR**

White hat hacker'lar izinli test yapar, black hat'ler izinsiz.

---

## 🎯 TEMEL KAVRAMLAR

### 1. White Hat vs Black Hat
- **White Hat**: İzinli güvenlik testi yapar, açıkları raporlar
- **Black Hat**: İzinsiz erişim, zarar verme amacı güder
- **Grey Hat**: Arada kalan, bazen izinsiz test yapar ama zarar vermez

### 2. Pentesting (Penetrasyon Testi)
- Sistemlerin güvenliğini test etme süreci
- **Sadece yazılı izinle** yapılır
- Raporlanır ve düzeltilir

---

## 🔧 KENDİ AĞINI TEST ETME ARAÇLARI

### 1. Ağ Keşfi (Network Discovery)
```bash
# Kendi IP'nizi öğrenme
ipconfig /all  # Windows
ifconfig       # Linux/Mac
ip addr        # Modern Linux

# Yerel ağı tarama (kendi ağınız)
nmap -sn 192.168.1.0/24  # Aktif cihazları bul
ping 192.168.1.1         # Router'a ping at
```

### 2. Port Tarama (Sadece Kendi Cihazlarınız)
```bash
# Kendi bilgisayarınızı tarayın
nmap -sS 127.0.0.1          # SYN scan
nmap -sV 192.168.1.100      # Versiyon tespiti (kendi IP'niz)
nmap -p 1-1000 localhost    # Belirli portlar

# Hangi portlar açık?
netstat -an                  # Windows/Linux
ss -tuln                     # Modern Linux
```

### 3. WiFi Güvenlik Testi (Sadece Kendi Ağlarınız)
```bash
# Windows - Kayıtlı WiFi şifreleri
netsh wlan show profiles
netsh wlan show profile "AğAdı" key=clear

# Linux - WiFi analizi (monitor mode)
sudo airmon-ng start wlan0
sudo airodump-ng wlan0mon
```

---

## 🛡️ SAVUNMA TEKNİKLERİNİ ÖĞRENME

### 1. Firewall Kurallarını Anlama
```bash
# Windows Firewall
netsh advfirewall show allprofiles
netsh advfirewall firewall show rule name=all

# Linux iptables
sudo iptables -L -n -v
sudo ufw status verbose
```

### 2. Saldırı Tespit Sistemleri (IDS)
- **Wireshark**: Ağ trafiğini analiz et
- **Snort**: Açık kaynaklı IDS
- **Security Onion**: Tam IDS dağıtımı

### 3. Log Analizi
```bash
# Windows Event Logs
Get-EventLog -LogName Security -Newest 50
Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4625}

# Linux Logs
sudo tail -f /var/log/auth.log
sudo journalctl -f
```

---

## 🧪 LAB ORTAMI KURMA

### 1. Sanal Lab (Tamamen Yasal)
- **VirtualBox** veya **VMware** kur
- **Metasploitable**: Güvenlik açıklı test sanal makinesi
- **DVWA**: Zafiyetli web uygulaması
- **Kali Linux**: Pentesting dağıtımı

### 2. Kendi Test Ağı
```
Internet
   |
Router (192.168.1.1)
   |
   +-- Kali Linux (Saldırgan) - 192.168.1.100
   +-- Metasploitable (Hedef) - 192.168.1.101
   +-- Windows 10 (Hedef) - 192.168.1.102
```

### 3. Docker ile Test Ortamı
```bash
# Zafiyetli konteynerler
docker run -d --name dvwa vulnerables/web-dvwa
docker run -d --name metasploitable tleemcjr/metasploitable2
```

---

## 📚 ÖĞRENME YOLLARI

### 1. Sertifikalar (Yasal Yol)
- **CEH**: Certified Ethical Hacker
- **OSCP**: Offensive Security Certified Professional
- **CompTIA Security+**: Temel güvenlik
- **CISSP**: İleri seviye

### 2. Pratik Platformlar
- **HackTheBox**: Yasal hacking platformu
- **TryHackMe**: Eğitim odaklı
- **VulnHub**: Zafiyetli VM'ler
- **OverTheWire**: War games

### 3. Kitaplar
- "The Web Application Hacker's Handbook"
- "Penetration Testing: A Hands-On Introduction"
- "Metasploit: The Penetration Tester's Guide"

---

## ⚔️ SALDIRI TEKNİKLERİNİ ANLAMA (SADECE LAB'DA)

### 1. Password Cracking (Kendi Şifreleriniz)
```bash
# Hashcat ile kendi hash'lerinizi kırın
hashcat -m 0 hash.txt rockyou.txt
hashcat -m 1000 ntlm_hash.txt wordlist.txt

# John the Ripper
john --format=raw-md5 hash.txt
john --wordlist=passwords.txt hash.txt
```

### 2. SQL Injection (Sadece DVWA'da)
```sql
-- Test amaçlı
' OR '1'='1
' UNION SELECT username, password FROM users--
```

### 3. XSS (Cross-Site Scripting)
```html
<!-- Sadece test ortamında -->
<script>alert('XSS Test')</script>
<img src=x onerror=alert(1)>
```

### 4. MITM (Man-in-the-Middle)
```bash
# Sadece kendi lab ağınızda
sudo ettercap -T -i eth0 -M arp:remote /192.168.1.1// /192.168.1.101//
```

---

## 📝 RAPORLAMA VE ETİK

### 1. Güvenlik Açığı Bulursanız
1. **Dokümantasyon**: Adımları kaydedin
2. **Proof of Concept**: Nasıl çalıştığını gösterin
3. **Etki Analizi**: Ne kadar kritik?
4. **Öneriler**: Nasıl düzeltilmeli?

### 2. Rapor Formatı
```markdown
# Güvenlik Açığı Raporu

## Özet
- Açık: SQL Injection
- URL: http://localhost/dvwa/vulnerabilities/sqli/
- Risk: Yüksek

## Adımlar
1. Adım: ' OR '1'='1 girildi
2. Adım: Tüm kullanıcılar listelendi

## Etki
- Tüm veritabanı erişilebilir
- Kullanıcı şifreleri görülebilir

## Öneriler
- Parametreli sorgular kullanın
- Input validation yapın
- WAF kurun
```

### 3. Sorumlu Açıklık Bildirimi
1. Şirketin security@ email'ine bildirin
2. Detaylı rapor gönderin
3. Zaman tanıyın (genelde 90 gün)
4. Halka açıklamadan önce onay alın

---

## 🚨 YAPMAYIN!

### ❌ Yasaklı İşlemler
- Başkalarının WiFi'sini kırmaya çalışmak
- İzinsiz port taraması yapmak
- Sosyal medya hesaplarını hacklemek
- Fidye yazılımı yazmak/test etmek
- DDoS saldırısı yapmak

### ⚖️ Yasal Sonuçlar
- **Bilişim suçu**: 3-7 yıl hapis
- **Tazminat**: Milyonlarca TL
- **Kariyer bitirme**: Hiçbir şirket işe almaz
- **İtibar kaybı**: Toplumdan dışlanma

---

## 🎓 BAŞLANGIÇ YOL HARİTASI

### 1. Ay: Temeller
- Ağ temelleri (TCP/IP, OSI modeli)
- Linux komut satırı
- Python/scripting temelleri
- Sanallaştırma (VirtualBox)

### 2. Ay: Araçlar
- Nmap, Wireshark, Metasploit
- Burp Suite, OWASP ZAP
- John, Hashcat
- Git ve dokümantasyon

### 3. Ay: Pratik
- HackTheBox easy makineleri
- TryHackMe odaları
- DVWA, bWAPP pratiği
- Kendi lab'ını kur

### 4. Ay: Sertifika
- CEH veya eJPT hazırlığı
- CTF yarışmalarına katıl
- Blog yaz, GitHub'da proje yap
- LinkedIn'de network kur

---

## 🔗 FAYDALI KAYNAKLAR

### Web Siteleri
- [OWASP](https://owasp.org/) - Web güvenliği
- [SANS](https://www.sans.org/) - Eğitim ve araştırma
- [PortSwigger](https://portswigger.net/) - Web security
- [Cybrary](https://www.cybrary.it/) - Ücretsiz kurslar

### YouTube Kanalları
- NetworkChuck
- John Hammond
- IppSec
- The Cyber Mentor

### Topluluklar
- Reddit: r/netsec, r/cybersecurity
- Discord: HackTheBox, TryHackMe
- Twitter: #infosec, #cybersecurity

---

## 💡 SON TAVSİYELER

1. **Her zaman yasal kal**: İzin almadan test yapma
2. **Öğrenmeye odaklan**: Para kazanma derdine düşme
3. **Paylaş**: Bildiklerini başkalarına öğret
4. **Güncel kal**: Siber güvenlik sürekli değişiyor
5. **Etik ol**: Gücü kötüye kullanma

> "With great power comes great responsibility" - Uncle Ben

---

## 📞 ACİL DURUMLAR

Eğer bir güvenlik açığı bulduysanız ve:
- Kritik sistemler etkileniyorsa
- Kişisel veriler risk altındaysa
- Finansal kayıp oluşuyorsa

**Hemen**:
1. Sistem sahibine bildirin
2. CERT'e (Ulusal Siber Olaylara Müdahale Merkezi) başvurun
3. Kanıtları saklayın

---

**Unutmayın**: Gerçek bir white hat hacker olmak yıllar alır. Sabırlı olun, sürekli öğrenin ve her zaman etik davranın. İyi şanslar! 🛡️