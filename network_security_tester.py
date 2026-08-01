#!/usr/bin/env python3
"""
Aг Безопасность Test Aramacы - White Hat Perspektifi
Только kendi aгыnыzы test etmek для использовать.
"""

import os
import sys
import subprocess
import socket
import json
import time
import threading
import ipимяdress
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

def print_банner():
    """Program baшlыгыnы показать"""
    банner = f"""
{Colors.HEADER}{Colors.BOLD}
╔══════════════════════════════════════════════════════════╗
║         AГ БЕЗОПАСНОСТЬ TEST ARACI - WHITE HAT               ║
║         Только kendi aгыnыzы test etmek для             ║
╚══════════════════════════════════════════════════════════╝{Colors.ENDC}

{Colors.WARNING}⚠️  ПРЕДУПРЕЖДЕНИЕ: Bu arоткрыть только kendi aгыnыzы test etmek для.
    Другойlarыnыn aгlarыna без разрешения доступ yasa dышыdыr!{Colors.ENDC}
"""
    print(банner)

def check_админ():
    """Yёnetici администратор контроль et"""
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnИsminin() != 0
        except:
            return False
    else:
        return os.geteuid() == 0

def get_local_ip():
    """Yerel IP имяresini al"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

def get_network_info():
    """Aг информация собрать"""
    print(f"{Colors.OKBLUE}[*] Aг информация collectnыyor...{Colors.ENDC}")
    
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
            print(f"{Colors.OKGREEN}[+] Aг konfigюrasyonu:{Colors.ENDC}")
            print(result.stdout[:1000])  # Ilk 1000 karakteri показать
        else:
            # Linux/Mac для ifconfig или ip
            try:
                result = subprocess.run(["ip", "имяdr"], capture_output=True, text=True)
                print(f"{Colors.OKGREEN}[+] Aг konfigюrasyonu:{Colors.ENDC}")
                print(result.stdout[:1000])
            except:
                result = subprocess.run(["ifconfig"], capture_output=True, text=True)
                print(f"{Colors.OKGREEN}[+] Aг konfigюrasyonu:{Colors.ENDC}")
                print(result.stdout[:1000])
    except Exception as e:
        print(f"{Colors.FAIL}[-] Aг infosi alыnamназвание: {e}{Colors.ENDC}")
    
    return info

def scan_local_network():
    """Yerel aгы scanma (ping sweep)"""
    print(f"{Colors.OKBLUE}[*] Yerel aг scannыyor...{Colors.ENDC}")
    
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
    
    threимяs = []
    for i in range(1, 255):
        ip = base_ip + str(i)
        threимя = threading.Threимя(target=ping_host, args=(ip,))
        threимяs.append(threимя)
        threимя.start()
        
        # Очень fazla threимя создан для
        if len(threимяs) >= 50:
            for t in threимяs:
                t.join()
            threимяs = []
    
    for t in threимяs:
        t.join()
    
    print(f"{Colors.OKGREEN}[+] Всего {len(active_hosts)} активен host найдено{Colors.ENDC}")
    return active_hosts

def port_scanner(target_ip, ports="1-1000"):
    """Port scanma (basit TCP connect scan)"""
    print(f"{Colors.OKBLUE}[*] {target_ip} для port scanmasы yapыlыyor...{Colors.ENDC}")
    
    open_ports = []
    
    # Port aralыгыnы parse et
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
    
    threимяs = []
    for port in range(start_port, end_port + 1):
        threимя = threading.Threимя(target=scan_port, args=(port,))
        threимяs.append(threимя)
        threимя.start()
        
        if len(threимяs) >= 100:
            for t in threимяs:
                t.join()
            threимяs = []
    
    for t in threимяs:
        t.join()
    
    return open_ports

def check_wifi_passwords():
    """Запись WiFi paрольalarыnы показать (только kendi aгlarыn)"""
    print(f"{Colors.OKBLUE}[*] Запись WiFi aгlarы контроль ediliyor...{Colors.ENDC}")
    
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
                        print(f"{Colors.OKGREEN}[+] WiFi: {profile} - Paрольa: {password}{Colors.ENDC}")
                    else:
                        print(f"{Colors.WARNING}[!] WiFi: {profile} - Paрольa не найдено{Colors.ENDC}")
                except:
                    pass
                    
        except Exception as e:
            print(f"{Colors.FAIL}[-] WiFi infosi alыnamназвание: {e}{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}[!] Bu особенность сейчасda только Windows'ta работает{Colors.ENDC}")
    
    return wifi_info

def dos_simulation(target_ip, target_port=80, duration=5):
    """DoS simюlasyonu (EГИTИM AMAЧLI - только localhost)"""
    print(f"{Colors.WARNING}[!] DoS Simюlasyonu запуск (EГИTИM AMAЧLI){Colors.ENDC}")
    print(f"{Colors.WARNING}[!] Hedef: {target_ip}:{target_port} - Длительность: {duration}s{Colors.ENDC}")
    
    if target_ip not in ["127.0.0.1", "localhost", get_local_ip()]:
        print(f"{Colors.FAIL}[-] DoS simюlasyonu только kendi makinenizde можно сделать!{Colors.ENDC}")
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
    
    threимяs = []
    for _ in range(10):  # 10 threимя с simюlasyon
        threимя = threading.Threимя(target=send_packets)
        threимяs.append(threимя)
        threимя.start()
    
    time.sleep(duration)
    stop_flag = True
    
    for threимя in threимяs:
        threимя.join()
    
    print(f"{Colors.OKGREEN}[+] DoS simюlasyonu завершено: {packets_sent} paket отправлено{Colors.ENDC}")
    print(f"{Colors.WARNING}[!] Bu только bir simюlasyondur. Geri загрузить DoS saldыrыsы yasa dышыdыr!{Colors.ENDC}")

def save_report(data, filename="network_security_report.json"):
    """Raporu JSON файлna сохранить"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"{Colors.OKGREEN}[+] Rapor сохранено: {filename}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[-] Rapor сохран: {e}{Colors.ENDC}")

def main_menu():
    """Ana menю"""
    while True:
        print(f"\n{Colors.BOLD}=== AГ БЕЗОПАСНОСТЬ TEST MENЮSЮ ==={Colors.ENDC}")
        print("1. Aг информация показать")
        print("2. Yerel aгы сканировать (активен cihazlar)")
        print("3. Port scanmasы yap")
        print("4. WiFi paрольalarыnы показать (kendi aгlarыn)")
        print("5. DoS Simюlasyonu (EГИTИM AMAЧLI - только localhost)")
        print("6. Все testleri работатьtыr")
        print("7. Rapor создать")
        print("8. Выход")
        
        choice = input(f"\n{Colors.OKBLUE}[?] Выбор (1-8): {Colors.ENDC}").strip()
        
        if choice == "1":
            info = get_network_info()
        
        elif choice == "2":
            if input(f"{Colors.WARNING}[?] Yerel aг scannacak. Devam et? (e/h): {Colors.ENDC}").lower() == 'e':
                hosts = scan_local_network()
        
        elif choice == "3":
            target = input(f"{Colors.OKBLUE}[?] Hedef IP (пусто bыrakыrsanыz kendi IP'niz): {Colors.ENDC}").strip()
            if not target:
                target = get_local_ip()
            
            ports = input(f"{Colors.OKBLUE}[?] Port aralыгы (напр.: 1-1000 или 80): {Colors.ENDC}").strip()
            if not ports:
                ports = "1-1000"
            
            if input(f"{Colors.WARNING}[?] {target} для port scanmasы yapыlacak. Devam et? (e/h): {Colors.ENDC}").lower() == 'e':
                open_ports = port_scanner(target, ports)
        
        elif choice == "4":
            if platform.system() == "Windows":
                if check_админ():
                    wifi = check_wifi_passwords()
                else:
                    print(f"{Colors.FAIL}[-] Bu действие для yёnetici администратор gerekli!{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}[!] Bu особенность сейчасda только Windows'ta работает{Colors.ENDC}")
        
        elif choice == "5":
            print(f"{Colors.WARNING}[!] DИKKAT: Bu только eгitim amatchlы bir simюlasyondur!{Colors.ENDC}")
            print(f"{Colors.WARNING}[!] Только kendi infosнастройкаыnыzы (localhost) test edebilirsiniz!{Colors.ENDC}")
            
            confirm = input(f"{Colors.FAIL}[?] Devam et etmek istiyor musunuz? (e/h): {Colors.ENDC}").lower()
            if confirm == 'e':
                target = input(f"{Colors.OKBLUE}[?] Hedef IP (только 127.0.0.1 или localhost): {Colors.ENDC}").strip()
                if target not in ["127.0.0.1", "localhost"]:
                    print(f"{Colors.FAIL}[-] Только kendi infosнастройкаыnыzы test edebilirsiniz!{Colors.ENDC}")
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
            print(f"{Colors.OKBLUE}[*] Все testler работатьtыrыlыyor...{Colors.ENDC}")
            
            report = {
                "network_info": get_network_info(),
                "local_scan": scan_local_network(),
                "wifi_passwords": check_wifi_passwords() if platform.system() == "Windows" and check_админ() else [],
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
            print(f"{Colors.OKGREEN}[+] Programdan выйтиыlыyor...{Colors.ENDC}")
            break
        
        else:
            print(f"{Colors.FAIL}[-] Неверный выбор!{Colors.ENDC}")

def main():
    """Ana fonksiyon"""
    print_банner()
    
    # Yёnetici контроль
    if not check_админ():
        print(f"{Colors.WARNING}[!] Bazы особенности для yёnetici администратор gerekebilir{Colors.ENDC}")
        print(f"{Colors.WARNING}[!] Prograли yёnetici как работатьtыrmanыz predlojenielir{Colors.ENDC}")
    
    # Ana menюyю запустить
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{Colors.OKGREEN}[+] Program user scanfыndan durduruldu{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[-] Bимяdnmeyen ошибка: {e}{Colors.ENDC}")

if __name__ == "__main__":
    main()