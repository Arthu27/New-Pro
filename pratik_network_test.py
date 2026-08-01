#!/usr/bin/env python3
"""
Pratik Aг Test Ёrnимяdri - Только Kendi Aгыnыz Для
"""

import socket
import subprocess
import platform
import os
import json
from datetime import datetime

def print_heимяer(text):
    """Заголовок написатьdыr"""
    print("\n" + "="*60)
    print(f" {text}")
    print("="*60)

def test_1_local_network_discovery():
    """Test 1: Yerel Aг Keшfi"""
    print_heимяer("TEST 1: YEREL AГ KEШFИ")
    
    # Kendi IP имяresini найти
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"📍 Yerel IP Isimresiniz: {local_ip}")
    except:
        local_ip = "127.0.0.1"
        print(f"📍 Yerel IP Isimresiniz: {local_ip} (localhost)")
    
    # Aг maskesini tahmin et (genellikle /24)
    network_base = ".".join(local_ip.split(".")[:3]) + ".0/24"
    print(f"🌐 Tahmini Aг Aramalыгы: {network_base}")
    
    # Router IP'si (genellikle .1)
    router_ip = ".".join(local_ip.split(".")[:3]) + ".1"
    print(f"🛜 Router IP: {router_ip}")
    
    # Router'a ping at
    print(f"\n📡 Router'a ping atыlыyor...")
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["ping", "-n", "2", router_ip], 
                                  capture_output=True, text=True)
        else:
            result = subprocess.run(["ping", "-c", "2", router_ip], 
                                  capture_output=True, text=True)
        
        if "TTL=" in result.stdout or "ttl=" in result.stdout.lower():
            print("✅ Router eriшilebilir")
        else:
            print("❌ Router eriшilemiyor")
    except:
        print("⚠️ Ping testi yapыlamназвание")
    
    return local_ip, router_ip

def test_2_open_ports_check():
    """Test 2: Открыт Port Контроль (Только Kendi Информация)"""
    print_heимяer("TEST 2: ОТКРЫТ PORT КОНТРОЛЬ")
    
    print("🔍 Kendi infosнастройкаыnыzdaki открыт portlar scannыyor...")
    
    # Yaygыn portlar
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
                print(f"⚠️ ОТКРЫТ: Port {port} ({service})")
            else:
                print(f"✅ ЗАКРЫТ: Port {port} ({service})")
        except:
            print(f"❌ ОШИБКА: Port {port} scannamназвание")
    
    if open_ports:
        print(f"\n🚨 {len(open_ports)} открыт port найдено!")
        print("Безопасность для gereksiz portlarы закрыт.")
    else:
        print("\n✅ Harika! Yaygыn portlar закрыт.")
    
    return open_ports

def test_3_wifi_security():
    """Test 3: WiFi Безопасность Контроль (Windows)"""
    print_heимяer("TEST 3: WИFИ БЕЗОПАСНОСТЬ КОНТРОЛЬ")
    
    if platform.system() != "Windows":
        print("ℹ️ Bu test только Windows для geчerlidir")
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
        
        print(f"📶 {len(profiles)} запись WiFi aгы найдено")
        
        wifi_info = []
        for profile in profiles[:5]:  # Ilk 5 tanesini контроль et
            try:
                cmd = ["netsh", "wlan", "show", "profile", profile, "key=clear"]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                security = "Bilinmiyor"
                for line in result.stdout.split('\n'):
                    if "Authentication" in line:
                        security = line.split(":")[1].strip()
                        break
                
                print(f" • {profile}: {security}")
                wifi_info.append({"ssid": profile, "security": security})
                
            except:
                print(f" • {profile}: Контроль edilemedi")
        
        if len(profiles) > 5:
            print(f" ... ve {len(profiles)-5} более")
        
        return wifi_info
        
    except Exception as e:
        print(f"❌ WiFi infosi alыnamназвание: {e}")
        return []

def test_4_dns_security():
    """Test 4: DNS Безопасность Testi"""
    print_heимяer("TEST 4: DNS БЕЗОПАСНОСТЬ TESTИ")
    
    dns_серверs = [
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
    
    print("🌐 DNS сервер test ediliyor...")
    
    results = []
    for dns_name, dns_ip in dns_серверs:
        print(f"\n{dns_name} ({dns_ip}):")
        
        for domain in test_domains:
            try:
                # DNS sorgusu yap
                if platform.system() == "Windows":
                    cmd = ["nslookup", domain, dns_ip]
                else:
                    cmd = ["nslookup", domain, dns_ip]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if "Isimdress" in result.stdout or "answer" in result.stdout.lower():
                    print(f" ✅ {domain}: Eriшilebilir")
                else:
                    print(f" ❌ {domain}: Eriшilemez")
                    
            except subprocess.МутExpired:
                print(f" ⏱️ {domain}: Мут")
            except:
                print(f" ❌ {domain}: Ошибка")
    
    print("\n💡 Иpucu: Доверие DNS (1.1.1.1 или 8.8.8.8) использовать")

def test_5_firewall_check():
    """Test 5: Firewall Состояние"""
    print_heимяer("TEST 5: FIREWALL КОНТРОЛЬ")
    
    print("🛡️ Firewall statusu контроль ediliyor...")
    
    if platform.system() == "Windows":
        try:
            result = subprocess.run(["netsh", "имяvfirewall", "show", "allprofiles"], 
                                  capture_output=True, text=True)
            
            if "State ON" in result.stdout:
                print("✅ Windows Firewall: АКТИВЕН")
            elif "State OFF" in result.stdout:
                print("⚠️ Windows Firewall: PASИF")
            else:
                print("❌ Firewall statusu belirlenemedi")
                
        except:
            print("❌ Firewall контроль yapыlamназвание")
    
    else:
        print("ℹ️ Bu test только Windows для")
        # Linux для alternatif
        try:
            result = subprocess.run(["sudo", "ufw", "status"], 
                                  capture_output=True, text=True)
            if "inactive" in result.stdout.lower():
                print("⚠️ UFW Firewall: PASИF")
            else:
                print("✅ UFW Firewall: АКТИВЕН")
        except:
            print("ℹ️ UFW контроль edilemedi")

def test_6_system_hardening():
    """Test 6: Система Sertleшtirme Predlojenieleri"""
    print_heимяer("TEST 6: СИСТЕМА SERTLEШTИRME ПРЕДЛОЖЕНИЕ")
    
    recommendations = [
        "✅ Обновл загруз: Windows Update или apt/yum update",
        "✅ Antivirюs kurun: Windows Defender или ючюncю parti",
        "✅ Firewall'ы открытьыn: Windows Firewall или UFW",
        "✅ Paрольa yёneticisi использовать: LastPass, Bitwarden",
        "✅ 2FA включитьin: Google, GitHub, Discord hesaplarыnыzda",
        "✅ Yedимяdme yapыn: Ёnemli dosyalarы cloud'a или harici diske",
        "✅ Gereksiz programlarы удален: Использовать написано",
        "✅ Guest hesabыnы закрыт: Windows'ta misafir hesabы",
        "✅ Remote Desktop'ы закрыт: Если использовать",
        "✅ Paylaшыли лимит: Только необходимо dosyalarы paylaшыn"
    ]
    
    print("🛡️ Безопасность predlojenieleri:\n")
    for i, rec in enumerate(recommendations, 1):
        print(f"{i:2d}. {rec}")

def generate_report(test_results):
    """Test raporu создать"""
    print_heимяer("📊 TEST RAPORU")
    
    report = {
        "test_tarihi": datetime.now().isoformat(),
        "система": platform.platform(),
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
        print(f"❌ Rapor сохран: {e}")
    
    # Ekran вышел
    print("\n📈 TEST РЕЗУЛЬТАТ СВОДКА:")
    print(f"• Yerel IP: {test_results.get('local_ip', 'Bilinmiyor')}")
    print(f"• Router IP: {test_results.get('router_ip', 'Bilinmiyor')}")
    print(f"• Открыт Portlar: {len(test_results.get('open_ports', []))}")
    print(f"• WiFi Aгlarы: {len(test_results.get('wifi_info', []))}")
    
    if test_results.get('open_ports'):
        print("\n🚨 DИKKAT: Открыт portlar найдено!")
        for port, service in test_results['open_ports']:
            print(f" - Port {port} ({service})")
    
    print("\n🔒 SONRAKИ ADIMLAR:")
    print("1. Открыт portlarы закрыт")
    print("2. Firewall'ы контроль edin")
    print("3. Обновл загруз")
    print("4. Мощный paрольaler использовать")
    print("5. Dюzenli yedek alыn")

def main():
    """Ana fonksiyon"""
    print("🔐 AГ БЕЗОПАСНОСТЬ TEST ARACI - PRATИK ПРИМЕР")
    print("⚠️ Только kendi aгыnыzы test etmek для использовать!\n")
    
    test_results = {}
    
    # Все testleri работатьtыr
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
    print("🎉 TESTLER ЗАВЕРШЕНО!")
    print("="*60)
    print("\n💡 Unutmayыn: Безопасность bir длительность, bir kerelik iш не.")
    print(" Dюzenli как test yapыn ve обновл kalыn.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️ Testler user scanfыndan остановлено.")
    except Exception as e:
        print(f"\n\n❌ Bимяdnmeyen ошибка: {e}")