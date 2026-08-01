#!/usr/bin/env python3
"""
Ağ Безопасность Test Aramacı - White Hat Perspektifi
Только kendi ağınızı test etmek для использовать.
"""

import os
import sys
import subprocess
import socket
import json
import time
import threading
import ipaddress
from datetime import datetime
import platform

# Renkli вышел для
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_banner():
    """Program başlığını показать"""
    banner = f"""
{Colors.HEADER}{Colors.BOLD}
╔══════════════════════════════════════════════════════════╗
║         AĞ БЕЗОПАСНОСТЬ TEST ARACI - WHITE HAT               ║
║         Только kendi ağınızı test etmek для             ║
╚══════════════════════════════════════════════════════════╝{Colors.ENDC}

{Colors.WARNING}⚠️  ПРЕДУПРЕЖДЕНИЕ: Bu araç только kendi ağınızı test etmek для.
    Başkalarının ağlarına без разрешения erişim yasa dışıdır!{Colors.ENDC}
"""
    print(banner)

def check_admin():
    """Yönetici администратор контроль et"""
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnİsminin() != 0
        except:
            return False
    else:
        return os.geteuid() == 0

def get_local_ip():
    """Yerel IP adresini al"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

def get_network_info():
    """Ağ информация собрать"""
    print(f"{Colors.OKBLUE}[*] Ağ информация collectnıyor...{Colors.ENDC}")
    
    info = {
        "timestamp": datetime.now().isoformat(),
        "platform": platform.platform(),
        "local_ip": get_local_ip(),
        "hostname": socket.gethostname(),
        "interfaces": []
    }
    
    try:
        # Windows для ipconfig
        if platform.system() == "Windows":
            result = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, encoding='utf-8', errors='ignore')
            print(f"{Colors.OKGREEN}[+] Ağ konfigürasyonu:{Colors.ENDC}")
            print(result.stdout[:1000])  # Ilk 1000 karakteri показать
        else:
            # Linux/Mac для ifconfig или ip
            try:
                result = subprocess.run(["ip", "addr"], capture_output=True, text=True)
                print(f"{Colors.OKGREEN}[+] Ağ konfigürasyonu:{Colors.ENDC}")
                print(result.stdout[:1000])
            except:
                result = subprocess.run(["ifconfig"], capture_output=True, text=True)
                print(f"{Colors.OKGREEN}[+] Ağ konfigürasyonu:{Colors.ENDC}")
                print(result.stdout[:1000])
    except Exception as e:
        print(f"{Colors.FAIL}[-] Ağ infosi alınamadı: {e}{Colors.ENDC}")
    
    return info

def scan_local_network():
    """Yerel ağı scanma (ping sweep)"""
    print(f"{Colors.OKBLUE}[*] Yerel ağ scannıyor...{Colors.ENDC}")
    
    local_ip = get_local_ip()
    base_ip = ".".join(local_ip.split(".")[:3]) + "."
    
    active_hosts = []
    
    def ping_host(ip):
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["ping", "-n", "1", "-w", "500", ip], 
                                      capture_output=True, text=True)
                if "TTL=" in result.stdout or "TTL" in result.stdout:
                    active_hosts.append(ip)
                    print(f"{Colors.OKGREEN}[+] Активен host: {ip}{Colors.ENDC}")
            else:
                result = subprocess.run(["ping", "-c", "1", "-W", "1", ip], 
                                      capture_output=True, text=True)
                if "1 received" in result.stdout or "ttl=" in result.stdout.lower():
                    active_hosts.append(ip)
                    print(f"{Colors.OKGREEN}[+] Активен host: {ip}{Colors.ENDC}")
        except:
            pass
    
    threads = []
    for i in range(1, 255):
        ip = base_ip + str(i)
        thread = threading.Thread(target=ping_host, args=(ip,))
        threads.append(thread)
        thread.start()
        
        # Очень fazla thread создан для
        if len(threads) >= 50:
            for t in threads:
                t.join()
            threads = []
    
    for t in threads:
        t.join()
    
    print(f"{Colors.OKGREEN}[+] Всего {len(active_hosts)} активен host найдено{Colors.ENDC}")
    return active_hosts

def port_scanner(target_ip, ports="1-1000"):
    """Port scanma (basit TCP connect scan)"""
    print(f"{Colors.OKBLUE}[*] {target_ip} для port scanması yapılıyor...{Colors.ENDC}")
    
    open_ports = []
    
    # Port aralığını parse et
    if "-" in ports:
        start_port, end_port = map(int, ports.split("-"))
    else:
        start_port, end_port = 1, int(ports)
    
    def scan_port(port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((target_ip, port))
            sock.close()
            if result == 0:
                open_ports.append(port)
                try:
                    service = socket.getservbyport(port)
                except:
                    service = "bilinmiyor"
                print(f"{Colors.OKGREEN}[+] Открыт port: {port} ({service}){Colors.ENDC}")
        except:
            pass
    
    threads = []
    for port in range(start_port, end_port + 1):
        thread = threading.Thread(target=scan_port, args=(port,))
        threads.append(thread)
        thread.start()
        
        if len(threads) >= 100:
            for t in threads:
                t.join()
            threads = []
    
    for t in threads:
        t.join()
    
    return open_ports

def check_wifi_passwords():
    """Запись WiFi parolalarını показать (только kendi ağların)"""
    print(f"{Colors.OKBLUE}[*] Запись WiFi ağları контроль ediliyor...{Colors.ENDC}")
    
    wifi_info = []
    
    if platform.system() == "Windows":
        try:
            # Windows для netsh команда
            result = subprocess.run(["netsh", "wlan", "show", "profiles"], 
                                  capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            profiles = []
            for line in result.stdout.split('\n'):
                if "All User Profile" in line:
                    profile = line.split(":")[1].strip()
                    profiles.append(profile)
            
            for profile in profiles:
                try:
                    cmd = ["netsh", "wlan", "show", "profile", profile, "key=clear"]
                    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    
                    password = None
                    for line in result.stdout.split('\n'):
                        if "Key Content" in line:
                            password = line.split(":")[1].strip()
                            break
                    
                    if password:
                        wifi_info.append({"ssid": profile, "password": password})
                        print(f"{Colors.OKGREEN}[+] WiFi: {profile} - Parola: {password}{Colors.ENDC}")
                    else:
                        print(f"{Colors.WARNING}[!] WiFi: {profile} - Parola не найдено{Colors.ENDC}")
                except:
                    pass
                    
        except Exception as e:
            print(f"{Colors.FAIL}[-] WiFi infosi alınamadı: {e}{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}[!] Bu особенность şu anda только Windows'ta работает{Colors.ENDC}")
    
    return wifi_info

def dos_simulation(target_ip, target_port=80, duration=5):
    """DoS simülasyonu (EĞİTİM AMAÇLI - только localhost)"""
    print(f"{Colors.WARNING}[!] DoS Simülasyonu запуск (EĞİTİM AMAÇLI){Colors.ENDC}")
    print(f"{Colors.WARNING}[!] Hedef: {target_ip}:{target_port} - Длительность: {duration}s{Colors.ENDC}")
    
    if target_ip not in ["127.0.0.1", "localhost", get_local_ip()]:
        print(f"{Colors.FAIL}[-] DoS simülasyonu только kendi makinenizde yapılabilir!{Colors.ENDC}")
        return
    
    packets_sent = 0
    stop_flag = False
    
    def send_packets():
        nonlocal packets_sent
        while not stop_flag:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                sock.connect((target_ip, target_port))
                sock.send(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                sock.close()
                packets_sent += 1
            except:
                pass
    
    threads = []
    for _ in range(10):  # 10 thread с simülasyon
        thread = threading.Thread(target=send_packets)
        threads.append(thread)
        thread.start()
    
    time.sleep(duration)
    stop_flag = True
    
    for thread in threads:
        thread.join()
    
    print(f"{Colors.OKGREEN}[+] DoS simülasyonu завершено: {packets_sent} paket отправлено{Colors.ENDC}")
    print(f"{Colors.WARNING}[!] Bu только bir simülasyondur. Geri загрузить DoS saldırısı yasa dışıdır!{Colors.ENDC}")

def save_report(data, filename="network_security_report.json"):
    """Raporu JSON dosyasına сохранить"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"{Colors.OKGREEN}[+] Rapor сохранено: {filename}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[-] Rapor сохран: {e}{Colors.ENDC}")

def main_menu():
    """Ana menü"""
    while True:
        print(f"\n{Colors.BOLD}=== AĞ БЕЗОПАСНОСТЬ TEST MENÜSÜ ==={Colors.ENDC}")
        print("1. Ağ информация показать")
        print("2. Yerel ağı сканировать (активен cihazlar)")
        print("3. Port scanması yap")
        print("4. WiFi parolalarını показать (kendi ağların)")
        print("5. DoS Simülasyonu (EĞİTİM AMAÇLI - только localhost)")
        print("6. Все testleri çalıştır")
        print("7. Rapor создать")
        print("8. Çıkış")
        
        choice = input(f"\n{Colors.OKBLUE}[?] Выбор (1-8): {Colors.ENDC}").strip()
        
        if choice == "1":
            info = get_network_info()
        
        elif choice == "2":
            if input(f"{Colors.WARNING}[?] Yerel ağ scannacak. Devam et? (e/h): {Colors.ENDC}").lower() == 'e':
                hosts = scan_local_network()
        
        elif choice == "3":
            target = input(f"{Colors.OKBLUE}[?] Hedef IP (пусто bırakırsanız kendi IP'niz): {Colors.ENDC}").strip()
            if not target:
                target = get_local_ip()
            
            ports = input(f"{Colors.OKBLUE}[?] Port aralığı (напр.: 1-1000 или 80): {Colors.ENDC}").strip()
            if not ports:
                ports = "1-1000"
            
            if input(f"{Colors.WARNING}[?] {target} для port scanması yapılacak. Devam et? (e/h): {Colors.ENDC}").lower() == 'e':
                open_ports = port_scanner(target, ports)
        
        elif choice == "4":
            if platform.system() == "Windows":
                if check_admin():
                    wifi = check_wifi_passwords()
                else:
                    print(f"{Colors.FAIL}[-] Bu действие для yönetici администратор gerekli!{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}[!] Bu особенность şu anda только Windows'ta работает{Colors.ENDC}")
        
        elif choice == "5":
            print(f"{Colors.WARNING}[!] DİKKAT: Bu только eğitim amatchlı bir simülasyondur!{Colors.ENDC}")
            print(f"{Colors.WARNING}[!] Только kendi infosayarınızı (localhost) test edebilirsiniz!{Colors.ENDC}")
            
            confirm = input(f"{Colors.FAIL}[?] Devam et etmek istiyor musunuz? (e/h): {Colors.ENDC}").lower()
            if confirm == 'e':
                target = input(f"{Colors.OKBLUE}[?] Hedef IP (только 127.0.0.1 или localhost): {Colors.ENDC}").strip()
                if target not in ["127.0.0.1", "localhost"]:
                    print(f"{Colors.FAIL}[-] Только kendi infosayarınızı test edebilirsiniz!{Colors.ENDC}")
                    continue
                
                port = input(f"{Colors.OKBLUE}[?] Hedef port (напр.: 80): {Colors.ENDC}").strip()
                if not port:
                    port = 80
                else:
                    port = int(port)
                
                duration = input(f"{Colors.OKBLUE}[?] Длительность (saniye, max 10): {Colors.ENDC}").strip()
                if not duration:
                    duration = 5
                else:
                    duration = min(int(duration), 10)  # Max 10 saniye
                
                dos_simulation(target, port, duration)
        
        elif choice == "6":
            print(f"{Colors.OKBLUE}[*] Все testler çalıştırılıyor...{Colors.ENDC}")
            
            report = {
                "network_info": get_network_info(),
                "local_scan": scan_local_network(),
                "wifi_passwords": check_wifi_passwords() if platform.system() == "Windows" and check_admin() else [],
                "timestamp": datetime.now().isoformat()
            }
            
            save_report(report)
            print(f"{Colors.OKGREEN}[+] Все testler завершено!{Colors.ENDC}")
        
        elif choice == "7":
            filename = input(f"{Colors.OKBLUE}[?] Rapor dosya имя (напр.: rapor.json): {Colors.ENDC}").strip()
            if not filename:
                filename = "network_security_report.json"
            
            # Пример rapor создать
            report = {
                "test_tarihi": datetime.now().isoformat(),
                "yerel_ip": get_local_ip(),
                "hostname": socket.gethostname(),
                "система": platform.platform(),
                "not": "Bu bir пример безопасность test raporudur."
            }
            
            save_report(report, filename)
        
        elif choice == "8":
            print(f"{Colors.OKGREEN}[+] Programdan çıkılıyor...{Colors.ENDC}")
            break
        
        else:
            print(f"{Colors.FAIL}[-] Неверный выбор!{Colors.ENDC}")

def main():
    """Ana fonksiyon"""
    print_banner()
    
    # Yönetici контроль
    if not check_admin():
        print(f"{Colors.WARNING}[!] Bazı особенности для yönetici администратор gerekebilir{Colors.ENDC}")
        print(f"{Colors.WARNING}[!] Programı yönetici как çalıştırmanız predlojenielir{Colors.ENDC}")
    
    # Ana menüyü запустить
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{Colors.OKGREEN}[+] Program user scanfından durduruldu{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[-] Baddnmeyen ошибка: {e}{Colors.ENDC}")

if __name__ == "__main__":
    main()