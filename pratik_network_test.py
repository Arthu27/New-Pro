#!/usr/bin/env python3
"""
Pratik Ağ Test Örnaddri - Sadece Kendi Ağınız İçin
"""

import socket
import subprocess
import platform
import os
import json
from datetime import datetime

def print_header(text):
    """Заголовок записатьdır"""
    print("\n" + "="*60)
    print(f" {text}")
    print("="*60)

def test_1_local_network_discovery():
    """Test 1: Yerel Ağ Keşfi"""
    print_header("TEST 1: YEREL AĞ KEŞFİ")
    
    # Kendi IP adresini bul
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"📍 Yerel IP Имяresiniz: {local_ip}")
    except:
        local_ip = "127.0.0.1"
        print(f"📍 Yerel IP Имяresiniz: {local_ip} (localhost)")
    
    # Ağ maskesini tahmin et (genellikle /24)
    network_base = ".".join(local_ip.split(".")[:3]) + ".0/24"
    print(f"🌐 Tahmini Ağ Поискlığı: {network_base}")
    
    # Router IP'si (genellikle .1)
    router_ip = ".".join(local_ip.split(".")[:3]) + ".1"
    print(f"🛜 Router IP: {router_ip}")
    
    # Router'a ping at
    print(f"\n📡 Router'a ping atılıyor...")
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["ping", "-n", "2", router_ip], 
                                  capture_output=True, text=True)
        else:
            result = subprocess.run(["ping", "-c", "2", router_ip], 
                                  capture_output=True, text=True)
        
        if "TTL=" in result.stdout or "ttl=" in result.stdout.lower():
            print("✅ Router erişilebilir")
        else:
            print("❌ Router erişilemiyor")
    except:
        print("⚠️ Ping testi yapılamadı")
    
    return local_ip, router_ip

def test_2_open_ports_check():
    """Test 2: Открытьık Port Kontroleü (Sadece Kendi Информацияsayarınız)"""
    print_header("TEST 2: AÇIK PORT KONTROLÜ")
    
    print("🔍 Kendi infosayarınızdaki açık portlar taranıyor...")
    
    # Yaygın portlar
    common_ports = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        443: "HTTPS",
        3306: "MySQL",
        3389: "RDP",
        5432: "PostgreSQL",
        8080: "HTTP-Alt"
    }
    
    open_ports = []
    
    for port, service in common_ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            
            if result == 0:
                open_ports.append((port, service))
                print(f"⚠️  AÇIK: Port {port} ({service})")
            else:
                print(f"✅ KAPALI: Port {port} ({service})")
        except:
            print(f"❌ HATA: Port {port} taranamadı")
    
    if open_ports:
        print(f"\n🚨 {len(open_ports)} açık port найдено!")
        print("Güvenlik için gereksiz portları закрытьın.")
    else:
        print("\n✅ Harika! Yaygın portlar kapalı.")
    
    return open_ports

def test_3_wifi_security():
    """Test 3: WiFi Güvenlik Kontroleü (Windows)"""
    print_header("TEST 3: WİFİ GÜVENLİK KONTROLÜ")
    
    if platform.system() != "Windows":
        print("ℹ️  Bu test sadece Windows için geçerlidir")
        return []
    
    try:
        # WiFi profillerini listele
        result = subprocess.run(["netsh", "wlan", "show", "profiles"], 
                              capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        profiles = []
        for line in result.stdout.split('\n'):
            if "All User Profile" in line:
                profile = line.split(":")[1].strip()
                profiles.append(profile)
        
        print(f"📶 {len(profiles)} записейlı WiFi ağı найдено")
        
        wifi_info = []
        for profile in profiles[:5]:  # Первый 5 tanesini контrole et
            try:
                cmd = ["netsh", "wlan", "show", "profile", profile, "key=clear"]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                security = "Bilinmiyor"
                for line in result.stdout.split('\n'):
                    if "Authentication" in line:
                        security = line.split(":")[1].strip()
                        break
                
                print(f"   • {profile}: {security}")
                wifi_info.append({"ssid": profile, "security": security})
                
            except:
                print(f"   • {profile}: Kontrole edilemedi")
        
        if len(profiles) > 5:
            print(f"   ... ve {len(profiles)-5} daha")
        
        return wifi_info
        
    except Exception as e:
        print(f"❌ WiFi infosi alınamadı: {e}")
        return []

def test_4_dns_security():
    """Test 4: DNS Güvenlik Testi"""
    print_header("TEST 4: DNS GÜVENLİK TESTİ")
    
    dns_servers = [
        ("Google DNS", "8.8.8.8"),
        ("Cloudflare DNS", "1.1.1.1"),
        ("Yandex DNS", "77.88.8.8"),
        ("OpenDNS", "208.67.222.222"),
        ("Local DNS", "192.168.1.1")  # Genellikle router
    ]
    
    test_domains = [
        "google.com",
        "github.com",
        "wikipedia.org"
    ]
    
    print("🌐 DNS serverları test ediliyor...")
    
    results = []
    for dns_name, dns_ip in dns_servers:
        print(f"\n{dns_name} ({dns_ip}):")
        
        for domain in test_domains:
            try:
                # DNS sorgusu yap
                if platform.system() == "Windows":
                    cmd = ["nslookup", domain, dns_ip]
                else:
                    cmd = ["nslookup", domain, dns_ip]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if "Имяdress" in result.stdout or "answer" in result.stdout.lower():
                    print(f"   ✅ {domain}: Erişilebilir")
                else:
                    print(f"   ❌ {domain}: Erişilemez")
                    
            except subprocess.МутExpired:
                print(f"   ⏱️  {domain}: Мут")
            except:
                print(f"   ❌ {domain}: Ошибка")
    
    print("\n💡 İpucu: Güvenli DNS (1.1.1.1 veya 8.8.8.8) kullanın")

def test_5_firewall_check():
    """Test 5: Firewall Статусu"""
    print_header("TEST 5: FIREWALL KONTROLÜ")
    
    print("🛡️  Firewall statusu контrole ediliyor...")
    
    if platform.system() == "Windows":
        try:
            result = subprocess.run(["netsh", "advfirewall", "show", "allprofiles"], 
                                  capture_output=True, text=True)
            
            if "State ON" in result.stdout:
                print("✅ Windows Firewall: AKTİF")
            elif "State OFF" in result.stdout:
                print("⚠️  Windows Firewall: PASİF")
            else:
                print("❌ Firewall statusu belirlenemedi")
                
        except:
            print("❌ Firewall контroleü yapılamadı")
    
    else:
        print("ℹ️  Bu test sadece Windows için")
        # Linux için alternatif
        try:
            result = subprocess.run(["sudo", "ufw", "status"], 
                                  capture_output=True, text=True)
            if "inactive" in result.stdout.lower():
                print("⚠️  UFW Firewall: PASİF")
            else:
                print("✅ UFW Firewall: AKTİF")
        except:
            print("ℹ️  UFW контrole edilemedi")

def test_6_system_hardening():
    """Test 6: Sistem Sertleştirme Предложениеleri"""
    print_header("TEST 6: SİSTEM SERTLEŞTİRME ÖNERİLERİ")
    
    recommendations = [
        "✅ Обновитьmeleri yükleyin: Windows Update veya apt/yum update",
        "✅ Antivirüs kurun: Windows Defender veya üçüncü parti",
        "✅ Firewall'ı açın: Windows Firewall veya UFW",
        "✅ Паrole администраторsi kullanın: LastPass, Bitwarden",
        "✅ 2FA etkinleştirin: Google, GitHub, Discord hesaplarınızda",
        "✅ Yedaddme yapın: Önemli dosyaları cloud'a veya harici diske",
        "✅ Gereksiz programları убратьın: Kullanmadığınız записатьılımlar",
        "✅ Guest hesabını закрытьın: Windows'ta misafir hesabı",
        "✅ Remote Desktop'ı закрытьın: Eğer kullanmıyorsanız",
        "✅ Paylaşımı sınırlayın: Sadece gerekli dosyaları paylaşın"
    ]
    
    print("🛡️  Güvenlik предложениеleri:\n")
    for i, rec in enumerate(recommendations, 1):
        print(f"{i:2d}. {rec}")

def generate_report(test_results):
    """Test raporu создать"""
    print_header("📊 TEST RAPORU")
    
    report = {
        "test_датаi": datetime.now().isoformat(),
        "sistem": platform.platform(),
        "hostname": socket.gethostname(),
        "testler": test_results
    }
    
    # Raporu dosyaya сохранить
    filename = f"ag_test_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"✅ Rapor сохранено: {filename}")
    except Exception as e:
        print(f"❌ Rapor kaydedilemedi: {e}")
    
    # Ekran çıktısı
    print("\n📈 TEST SONUÇLARI ÖZETİ:")
    print(f"• Yerel IP: {test_results.get('local_ip', 'Bilinmiyor')}")
    print(f"• Router IP: {test_results.get('router_ip', 'Bilinmiyor')}")
    print(f"• Открытьık Portlar: {len(test_results.get('open_ports', []))}")
    print(f"• WiFi Ağları: {len(test_results.get('wifi_info', []))}")
    
    if test_results.get('open_ports'):
        print("\n🚨 DİKKAT: Открытьık portlar найдено!")
        for port, service in test_results['open_ports']:
            print(f"   - Port {port} ({service})")
    
    print("\n🔒 SONRAKİ ADIMLAR:")
    print("1. Открытьık portları закрытьın")
    print("2. Firewall'ı контrole edin")
    print("3. Обновитьmeleri yükleyin")
    print("4. Güçlü паroleler kullanın")
    print("5. Düzenli yedek alın")

def main():
    """Ana fonksiyon"""
    print("🔐 AĞ GÜVENLİK TEST ARACI - PRATİK ÖRNEKLER")
    print("⚠️  Sadece kendi ağınızı test etmek için kullanın!\n")
    
    test_results = {}
    
    # Tüm testleri çalıştır
    try:
        local_ip, router_ip = test_1_local_network_discovery()
        test_results['local_ip'] = local_ip
        test_results['router_ip'] = router_ip
    except:
        pass
    
    try:
        open_ports = test_2_open_ports_check()
        test_results['open_ports'] = open_ports
    except:
        pass
    
    try:
        wifi_info = test_3_wifi_security()
        test_results['wifi_info'] = wifi_info
    except:
        pass
    
    try:
        test_4_dns_security()
    except:
        pass
    
    try:
        test_5_firewall_check()
    except:
        pass
    
    try:
        test_6_system_hardening()
    except:
        pass
    
    # Rapor создать
    generate_report(test_results)
    
    print("\n" + "="*60)
    print("🎉 TESTLER TAMAMLANDI!")
    print("="*60)
    print("\n💡 Unutmayın: Güvenlik bir süreçtir, bir kerelik iş değil.")
    print("   Düzenli olarak test yapın ve güncel kalın.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Testler user tarafından остановлено.")
    except Exception as e:
        print(f"\n\n❌ Baddnmeyen ошибка: {e}")