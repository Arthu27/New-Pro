# White Hat Hacking Руководство
## Kendi Ağını Безопасность Test Etme Kılavuzu

---

## ⚠️ ÖNEMLİ ПРЕДУПРЕЖДЕНИЕ
Bu руководство **только kendi ağınızı ve sistemlerinizi test etmek** для. Başkalarının ağlarına, sistemlerine или hesaplarına без разрешения erişim:
- **YASA DIŞIDIR**
- **ТЯЖЕЛЫЙ НАКАЗАНИЕ VARDIR**
- **ETİK DEĞİLDİR**

White hat hacker'lar izinli test yapar, black hat'ler без разрешения.

---

## 🎯 TEMEL KAVRAMLAR

### 1. White Hat vs Black Hat
- **White Hat**: İzinli безопасность testi yapar, açıkları raporlar
- **Black Hat**: İzinsiz erişim, zarar verme amacı güder
- **Grey Hat**: Arada kalan, bazen без разрешения test yapar ama zarar vermez

### 2. Pentesting (Penetrasyon Testi)
- Sistemlerin доверие test etme длительность
- **Только написано izinle** yapılır
- Raporlanır ve düzeltilir

---

## 🔧 KENDİ AĞINI TEST ETME ARAÇLARI

### 1. Ağ Keşfi (Network Discovery)
```bash
# Kendi IP'nizi öğrenme
ipconfig /all  # Windows
ifconfig       # Linux/Mac
ip addr        # Modern Linux

# Yerel ağı сканироватьma (kendi ağınız)
nmap -sn 192.168.1.0/24  # Активен cihazları bul
ping 192.168.1.1         # Router'a ping at
```

### 2. Port Tarama (Только Kendi Cihazlarınız)
```bash
# Kendi информация сканироватьyın
nmap -sS 127.0.0.1          # SYN scan
nmap -sV 192.168.1.100      # Versiyon tespiti (kendi IP'niz)
nmap -p 1-1000 localhost    # Belirli portlar

# Какой portlar открыт?
netstat -an                  # Windows/Linux
ss -tuln                     # Modern Linux
```

### 3. WiFi Безопасность Testi (Только Kendi Ağlarınız)
```bash
# Windows - Запись WiFi пароль
netsh wlan show profiles
netsh wlan show profile "AğAdı" key=clear

# Linux - WiFi analizi (monitor mode)
sudo airmon-ng start wlan0
sudo airodump-ng wlan0mon
```

---

## 🛡️ SAVUNMA TEKNİKLERİNİ ÖĞRENME

### 1. Firewall Правил Anlama
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
- **Snort**: Открыт kaynaklı IDS
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
- **VirtualBox** или **VMware** kur
- **Metasploitable**: Безопасность açıklı test sanal makinesi
- **DVWA**: Zafiyetli web примен
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

### 3. Docker с Test Ortamı
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
- **CompTIA Security+**: Temel безопасность
- **CISSP**: İleri seviye

### 2. Pratik Platformlar
- **HackTheBox**: Yasal hacking platformu
- **TryHackMe**: Eğitim комната
- **VulnHub**: Zafiyetli VM'ler
- **OverTheWire**: War games

### 3. Kitaplar
- "The Web Application Hacker's Handbook"
- "Penetration Testing: A Hands-On Introduction"
- "Metasploit: The Penetration Tester's Guide"

---

## ⚔️ SALDIRI TEKNİKLERİNİ ANLAMA (ТОЛЬКО LAB'DA)

### 1. Password Cracking (Kendi Пароль)
```bash
# Hashcat с kendi hash'lerinizi kırın
hashcat -m 0 hash.txt rockyou.txt
hashcat -m 1000 ntlm_hash.txt wordlist.txt

# John the Ripper
john --format=raw-md5 hash.txt
john --wordlist=passwords.txt hash.txt
```

### 2. SQL Injection (Только DVWA'da)
```sql
-- Test aматчlı
' OR '1'='1
' UNION SELECT username, password FROM users--
```

### 3. XSS (Cross-Site Scripting)
```html
<!-- Только test ortamında -->
<script>alert('XSS Test')</script>
<img src=x onerror=alert(1)>
```

### 4. MITM (Man-in-the-Middle)
```bash
# Только kendi lab ağınızda
sudo ettercap -T -i eth0 -M arp:remote /192.168.1.1// /192.168.1.101//
```

---

## 📝 RAPORLAMA VE ETİK

### 1. Безопасность Açığı Bulursanız
1. **Dokümantasyon**: Adımları сохран
2. **Proof of Concept**: Как çalıştığını показ
3. **Etki Analizi**: Ne kadar kritik?
4. **Предложение**: Как düzeltilmeli?

### 2. Rapor Formatı
```markdown
# Безопасность Açığı Raporu

## Сводка
- Открыт: SQL Injection
- URL: http://localhost/dvwa/vulnerabilities/sqli/
- Risk: Высокий

## Adımlar
1. Adım: ' OR '1'='1 girildi
2. Adım: Все пользователи listelendi

## Etki
- Все veritabanı erişilebilir
- Пользователь пароль видеть

## Предложение
- Parametreli sorgular использовать
- Input validation yapın
- WAF kurun
```

### 3. Sorumlu Açıklık Уведомление
1. Şirketin security@ email'ine bildirin
2. Детали rapor отправл
3. Время tanıyın (genelde 90 день)
4. Halka описание до onay alın

---

## 🚨 YAPMAYIN!

### ❌ Yasaklı Действия
- Başkalarının WiFi'sini kırmaya работать
- İzinsiz port сканироватьması yapmak
- Sosyal medya hesaplarını hacklemek
- Fidye написано yazmak/test etmek
- DDoS saldırısı yapmak

### ⚖️ Yasal В конецuçlar
- **Bilişim suçu**: 3-7 yıl hapis
- **Tazminat**: Milyonlarca TL
- **Kariyer bitirme**: Hiçbir şirket işe almaz
- **İtibar kaybı**: Toplumdan dışlanma

---

## 🎓 BAŞLANGIÇ YOL HARİTASI

### 1. Ay: Temeller
- Ağ temelleri (TCP/IP, OSI modeli)
- Linux команда satırı
- Python/scripting temelleri
- Sanallaştırma (VirtualBox)

### 2. Ay: Araçlar
- Nmap, Wireshark, Metasploit
- Burp Suite, OWASP ZAP
- John, Hashcat
- Git ve dokümantasyon

### 3. Ay: Pratik
- HackTheBox easy makineleri
- TryHackMe комната
- DVWA, bWAPP pratiği
- Kendi lab'ını kur

### 4. Ay: Sertifika
- CEH или eJPT hazırlığı
- CTF yarışmalarına katıl
- Blog yaz, GitHub'da proje yap
- LinkedIn'de network kur

---

## 🔗 FAYDALI KAYNAKLAR

### Web Siteleri
- [OWASP](https://owasp.org/) - Web доверие
- [SANS](https://www.sans.org/) - Eğitim ve araştırma
- [PortSwigger](https://portswigger.net/) - Web security
- [Cybrary](https://www.cybrary.it/) - Ücretsiz kurslar

### YouTube Каналы
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

1. **Каждый время yasal kal**: İzin almadan test yapma
2. **Öğrenmeye комната**: Para kazanma derdine düşme
3. **Paylaş**: Bildiklerini başkalarına öğret
4. **Обновл kal**: Siber безопасность длительность değişiyor
5. **Etik ol**: Gücü kötüye использовать

> "With great power comes great responsibility" - Uncle Ben

---

## 📞 ACİL СОСТОЯНИЕ

Если bir безопасность açığı bulduysanız ve:
- Kritik sistemler etkileniyorsa
- Kişisel veriler risk altındaysa
- Finansal kayıp oluşuyorsa

**Hemen**:
1. Система sahibine bildirin
2. CERT'e (Ulusal Siber Olaylara Müdahale Merkezi) заявка
3. Доказательство saklayın

---

**Unutmayın**: Gerçek bir white hat hacker olmak yıllar получает. Sabırlı olun, длительность öğrenin ve каждый время etik davranın. İyi şanslar! 🛡️