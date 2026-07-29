#!/usr/bin/env python3
"""
PASSWORD CRACKER PRO - Паrole Kırma Поискcı
⚠️  SADECE kendi паrolelerini test etmek için!
"""

import hashlib
import itertools
import string
import time
import json
import os
from datetime import datetime
from colorama import init, Fore, Style

# Colorama'yı запустить
init(autoreset=True)

class PasswordCracker:
    def __init__(self):
        self.results = []
        self.start_time = None
        
    def print_banner(self):
        """Program banner'ını göster"""
        banner = f"""
{Fore.CYAN}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════╗
║         PASSWORD CRACKER PRO - ŞİFRE KIRMA ARACI         ║
║         ⚠️  SADECE KENDİ ŞİFRELERİNİ TEST ET!           ║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}

{Fore.YELLOW}UYARI: Başkalarının паrolelerini kırmaya çalışmak YASA DIŞIDIR!
        Sadece kendi паrolelerinizi veya izin verilen test паrolelerini kırın!{Style.RESET_ALL}
"""
        print(banner)
    
    def get_hash_type(self, hash_value):
        """Hash türünü tespit et"""
        hash_length = len(hash_value)
        
        hash_types = {
            32: "MD5",
            40: "SHA1",
            64: "SHA256",
            96: "SHA384",
            128: "SHA512",
            8: "CRC32",
            16: "MySQL323",
            40: "MySQLSHA1",
            34: "NTLM" if hash_value.startswith('$NT$') else None
        }
        
        return hash_types.get(hash_length, "Bilinmeyen")
    
    def create_hash(self, password, hash_type="md5"):
        """Паroleden hash создать"""
        password = password.encode('utf-8')
        
        hash_functions = {
            "md5": hashlib.md5,
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512
        }
        
        if hash_type.lower() in hash_functions:
            return hash_functions[hash_type.lower()]().hexdigest()
        else:
            return hashlib.md5(password).hexdigest()
    
    def brute_force_attack(self, target_hash, max_length=4, charset=None):
        """Brute Force saldırısı"""
        print(f"{Fore.BLUE}[*] Brute Force saldırısı запуститьılıyor...{Style.RESET_ALL}")
        print(f"{Fore.BLUE}[*] Maksimum uzunluk: {max_length}{Style.RESET_ALL}")
        
        if charset is None:
            charset = string.ascii_lowercase + string.digits
        
        attempts = 0
        found = False
        
        for length in range(1, max_length + 1):
            print(f"{Fore.CYAN}[*] {length} karakterli паroleler deneniyor...{Style.RESET_ALL}")
            
            for combo in itertools.product(charset, repeat=length):
                password = ''.join(combo)
                attempts += 1
                
                # Her 10000 denemede bir ilerleme göster
                if attempts % 10000 == 0:
                    print(f"{Fore.YELLOW}[*] {attempts} deneme yapıldı...{Style.RESET_ALL}")
                
                # Hash'i hesapla ve karşılaştır
                test_hash = hashlib.md5(password.encode()).hexdigest()
                
                if test_hash == target_hash:
                    print(f"{Fore.GREEN}[+] ŞİFRE BULUNDU!{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}[+] Паrole: {password}{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}[+] Deneme sayısı: {attempts}{Style.RESET_ALL}")
                    found = True
                    return password, attempts
                
                # Время kontroleü (çok uzun sürmesin)
                if time.time() - self.start_time > 300:  # 5 dakika
                    print(f"{Fore.YELLOW}[!] 5 dakika doldu, brute force остановитьuluyor...{Style.RESET_ALL}")
                    return None, attempts
        
        if not found:
            print(f"{Fore.RED}[-] Паrole bulunamadı (max {max_length} karakter){Style.RESET_ALL}")
            return None, attempts
    
    def dictionary_attack(self, target_hash, wordlist_path="wordlists/turkish_passwords.txt"):
        """Dictionary saldırısı"""
        print(f"{Fore.BLUE}[*] Dictionary saldırısı запуститьılıyor...{Style.RESET_ALL}")
        
        if not os.path.exists(wordlist_path):
            print(f"{Fore.RED}[-] Wordlist bulunamadı: {wordlist_path}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Örnek wordlist создатьuluyor...{Style.RESET_ALL}")
            self.create_sample_wordlist()
            wordlist_path = "wordlists/sample_passwords.txt"
        
        attempts = 0
        found = False
        
        try:
            with open(wordlist_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    password = line.strip()
                    if not password:
                        continue
                    
                    attempts += 1
                    
                    # Her 1000 denemede bir ilerleme göster
                    if attempts % 1000 == 0:
                        print(f"{Fore.YELLOW}[*] {attempts} deneme yapıldı...{Style.RESET_ALL}")
                    
                    # Hash'i hesapla
                    test_hash = hashlib.md5(password.encode()).hexdigest()
                    
                    if test_hash == target_hash:
                        print(f"{Fore.GREEN}[+] ŞİFRE BULUNDU!{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}[+] Паrole: {password}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}[+] Deneme sayısı: {attempts}{Style.RESET_ALL}")
                        found = True
                        return password, attempts
                    
                    # Время kontroleü
                    if time.time() - self.start_time > 300:
                        print(f"{Fore.YELLOW}[!] 5 dakika doldu...{Style.RESET_ALL}")
                        return None, attempts
        
        except Exception as e:
            print(f"{Fore.RED}[-] Wordlist okuma ошибкаsı: {e}{Style.RESET_ALL}")
        
        if not found:
            print(f"{Fore.RED}[-] Паrole bulunamadı ({attempts} deneme){Style.RESET_ALL}")
            return None, attempts
    
    def create_sample_wordlist(self):
        """Örnek wordlist создать"""
        os.makedirs("wordlists", exist_ok=True)
        
        common_passwords = [
            "123456", "password", "12345678", "qwerty", "12345",
            "123456789", "letmein", "1234567", "football", "iloveyou",
            "admin", "welcome", "monkey", "login", "abc123",
            "starwars", "123123", "dragon", "passw0rd", "master",
            "hello", "freedom", "whatever", "qazwsx", "trustno1",
            "654321", "jordan23", "harley", "password1", "1234",
            "robert", "matthew", "jordan", "asshole", "daniel",
            "andrew", "lakers", "andrea", "buster", "joshua",
            "1234567890", "superman", "george", "computer", "michelle",
            "sunshine", "123456a", "123abc", "aaa123", "donald",
            "qwerty123", "welcome1", "charlie", "123456789a", "samsung",
            "password123", "zaq12wsx", "baseball", "1qaz2wsx", "qwertyuiop"
        ]
        
        # Türkçe паroleler add
        turkish_passwords = [
            "паrole", "parolea", "123456", "ankara", "istanbul",
            "izmir", "adana", "mersin", "türkiye", "mustafa",
            "ahmet", "mehmet", "ayşe", "fatma", "ali",
            "veli", "49numara", "1903", "1907", "galatasaray",
            "fenerbahçe", "beşiktaş", "trabzonspor", "bjk1903", "fb1907",
            "gs1905", "ts1967", "ankara06", "istanbul34", "izmir35"
        ]
        
        with open("wordlists/sample_passwords.txt", 'w', encoding='utf-8') as f:
            for pwd in common_passwords + turkish_passwords:
                f.write(pwd + "\n")
        
        print(f"{Fore.GREEN}[+] Örnek wordlist создатьuldu: wordlists/sample_passwords.txt{Style.RESET_ALL}")
    
    def hybrid_attack(self, target_hash, wordlist_path, rules=None):
        """Hybrid saldırısı (dictionary + brute force)"""
        print(f"{Fore.BLUE}[*] Hybrid saldırısı запуститьılıyor...{Style.RESET_ALL}")
        
        if rules is None:
            rules = [
                lambda x: x,                    # Orijinal
                lambda x: x + "123",           # Последнийuna 123 add
                lambda x: x + "!",             # Последнийuna ! add
                lambda x: "123" + x,           # Başına 123 add
                lambda x: x.upper(),           # Büyük harf
                lambda x: x.lower(),           # Küçük harf
                lambda x: x.capitalize(),      # Первый harf büyük
                lambda x: x[::-1],             # Ters çevir
                lambda x: x + "2024",          # Последнийuna yıl add
                lambda x: x + "2025"           # Последнийuna gelecek yıl add
            ]
        
        attempts = 0
        found = False
        
        try:
            with open(wordlist_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    base_word = line.strip()
                    if not base_word:
                        continue
                    
                    for rule in rules:
                        try:
                            password = rule(base_word)
                            attempts += 1
                            
                            if attempts % 1000 == 0:
                                print(f"{Fore.YELLOW}[*] {attempts} deneme yapıldı...{Style.RESET_ALL}")
                            
                            test_hash = hashlib.md5(password.encode()).hexdigest()
                            
                            if test_hash == target_hash:
                                print(f"{Fore.GREEN}[+] ŞİFRE BULUNDU!{Style.RESET_ALL}")
                                print(f"{Fore.GREEN}[+] Паrole: {password}{Style.RESET_ALL}")
                                print(f"{Fore.GREEN}[+] Kural: {rule.__name__ if hasattr(rule, '__name__') else 'Custom'}{Style.RESET_ALL}")
                                found = True
                                return password, attempts
                            
                            if time.time() - self.start_time > 300:
                                print(f"{Fore.YELLOW}[!] 5 dakika doldu...{Style.RESET_ALL}")
                                return None, attempts
                                
                        except Exception:
                            continue
        
        except Exception as e:
            print(f"{Fore.RED}[-] Hybrid saldırı ошибкаsı: {e}{Style.RESET_ALL}")
        
        if not found:
            print(f"{Fore.RED}[-] Паrole bulunamadı ({attempts} deneme){Style.RESET_ALL}")
            return None, attempts
    
    def save_result(self, target_hash, password, method, attempts, time_taken):
        """Последнийucu сохранить"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "target_hash": target_hash,
            "password": password,
            "method": method,
            "attempts": attempts,
            "time_taken": time_taken,
            "hash_type": self.get_hash_type(target_hash)
        }
        
        self.results.append(result)
        
        # JSON dosyasına сохранить
        os.makedirs("results", exist_ok=True)
        filename = f"results/crack_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}[+] sonuç kaydedildi: {filename}{Style.RESET_ALL}")
        
        # Ekrana da yazdır
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}SONUÇ RAPORU:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"Hash: {target_hash}")
        print(f"Hash Türü: {self.get_hash_type(target_hash)}")
        print(f"Паrole: {password if password else 'BULUNAMADI'}")
        print(f"Metod: {method}")
        print(f"Deneme Sayısı: {attempts}")
        print(f"Geçen Süre: {time_taken:.2f} saniye")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def test_password_strength(self, password):
        """Паrole gücünü test et"""
        print(f"{Fore.BLUE}[*] Паrole gücü test ediliyor: {password}{Style.RESET_ALL}")
        
        score = 0
        feedback = []
        
        # Uzunluk kontroleü
        if len(password) >= 12:
            score += 3
            feedback.append("✅ Uzunluk: 12+ karakter (Çok iyi)")
        elif len(password) >= 8:
            score += 2
            feedback.append("⚠️  Uzunluk: 8-11 karakter (Orta)")
        else:
            score += 0
            feedback.append("❌ Uzunluk: 7 veya daha az karakter (Zayıf)")
        
        # Büyük/küçük harf kontroleü
        if any(c.isupper() for c in password) and any(c.islower() for c in password):
            score += 2
            feedback.append("✅ Büyük/küçük harf karışımı (İyi)")
        else:
            score += 0
            feedback.append("❌ Sadece büyük veya sadece küçük harf (Zayıf)")
        
        # Rakam kontroleü
        if any(c.isdigit() for c in password):
            score += 2
            feedback.append("✅ Rakam içeriyor (İyi)")
        else:
            score += 0
            feedback.append("❌ Rakam içermiyor (Zayıf)")
        
        # Özel karakter kontroleü
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?/"
        if any(c in special_chars for c in password):
            score += 2
            feedback.append("✅ Özel karakter içeriyor (İyi)")
        else:
            score += 0
            feedback.append("❌ Özel karakter içermiyor (Zayıf)")
        
        # Sözlük kontroleü (basit)
        common_words = ["password", "123456", "qwerty", "admin", "welcome"]
        if not any(word in password.lower() for word in common_words):
            score += 1
            feedback.append("✅ Yaygın паrole değil (İyi)")
        else:
            score += 0
            feedback.append("❌ Yaygın паrole kullanılmış (Çok zayıf)")
        
        # Skor değerlendirmesi
        print(f"\n{Fore.CYAN}ŞİFRE GÜCÜ ANALİZİ:{Style.RESET_ALL}")
        for item in feedback:
            print(f"  {item}")
        
        print(f"\n{Fore.CYAN}TOPLAM SKOR: {score}/10{Style.RESET_ALL}")
        
        if score >= 8:
            print(f"{Fore.GREEN}✅ Паrole GÜÇLÜ{Style.RESET_ALL}")
        elif score >= 5:
            print(f"{Fore.YELLOW}⚠️  Паrole ORTA{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ Паrole ZAYIF{Style.RESET_ALL}")
        
        return score
    
    def run(self):
        """Ana çalıştırma fonksiyonu"""
        self.print_banner()
        
        while True:
            print(f"\n{Fore.CYAN}{Style.BRIGHT}=== ANA MENÜ ==={Style.RESET_ALL}")
            print("1. Hash'ten паrole kır")
            print("2. Паrole gücünü test et")
            print("3. Hash создать")
            print("4. Wordlist создать")
            print("5. Geçmiş sonuçları gör")
            print("6. Выход")
            
            choice = input(f"\n{Fore.BLUE}[?] Выбратьiminiz (1-6): {Style.RESET_ALL}").strip()
            
            if choice == "1":
                self.crack_password()
            elif choice == "2":
                self.test_password_menu()
            elif choice == "3":
                self.create_hash_menu()
            elif choice == "4":
                self.create_wordlist_menu()
            elif choice == "5":
                self.show_history()
            elif choice == "6":
                print(f"{Fore.GREEN}[+] Programdan çıkılıyor...{Style.RESET_ALL}")
                break
            else:
                print(f"{Fore.RED}[-] Geçersiz выбратьim!{Style.RESET_ALL}")
    
    def crack_password(self):
        """Паrole kırma menüsü"""
        print(f"\n{Fore.CYAN}=== ŞİFRE KIRMA ==={Style.RESET_ALL}")
        
        # Hash girişi
        target_hash = input(f"{Fore.BLUE}[?] Hedef hash (MD5): {Style.RESET_ALL}").strip().lower()
        
        if not target_hash:
            print(f"{Fore.RED}[-] Hash gerekli!{Style.RESET_ALL}")
            return
        
        hash_type = self.get_hash_type(target_hash)
        print(f"{Fore.BLUE}[*] Hash türü: {hash_type}{Style.RESET_ALL}")
        
        # Metod выбратьimi
        print(f"\n{Fore.CYAN}Kırma Metodu:{Style.RESET_ALL}")
        print("1. Brute Force (Küçük harf + rakam)")
        print("2. Dictionary Attack (Wordlist)")
        print("3. Hybrid Attack (Wordlist + kurallar)")
        print("4. Özel Brute Force (Özel karakter seti)")
        
        method_choice = input(f"{Fore.BLUE}[?] Metod выбратьin (1-4): {Style.RESET_ALL}").strip()
        
        self.start_time = time.time()
        password = None
        attempts = 0
        
        if method_choice == "1":
            max_len = input(f"{Fore.BLUE}[?] Maksimum uzunluk (default: 4): {Style.RESET_ALL}").strip()
            max_len = int(max_len) if max_len.isdigit() else 4
            
            charset = string.ascii_lowercase + string.digits
            password, attempts = self.brute_force_attack(target_hash, max_len, charset)
            method = "Brute Force"
            
        elif method_choice == "2":
            wordlist = input(f"{Fore.BLUE}[?] Wordlist yolu (boş bırak: sample): {Style.RESET_ALL}").strip()
            if not wordlist:
                wordlist = "wordlists/sample_passwords.txt"
            
            password, attempts = self.dictionary_attack(target_hash, wordlist)
            method = "Dictionary Attack"
            
        elif method_choice == "3":
            wordlist = input(f"{Fore.BLUE}[?] Wordlist yolu (boş bırak: sample): {Style.RESET_ALL}").strip()
            if not wordlist:
                wordlist = "wordlists/sample_passwords.txt"
            
            password, attempts = self.hybrid_attack(target_hash, wordlist)
            method = "Hybrid Attack"
            
        elif method_choice == "4":
            charset = input(f"{Fore.BLUE}[?] Karakter seti (örn: abc123!@#): {Style.RESET_ALL}").strip()
            if not charset:
                charset = string.ascii_letters + string.digits + "!@#$%^&*"
            
            max_len = input(f"{Fore.BLUE}[?] Maksimum uzunluk: {Style.RESET_ALL}").strip()
            max_len = int(max_len) if max_len.isdigit() else 4
            
            password, attempts = self.brute_force_attack(target_hash, max_len, charset)
            method = "Özel Brute Force"
            
        else:
            print(f"{Fore.RED}[-] Geçersiz metod!{Style.RESET_ALL}")
            return
        
        time_taken = time.time() - self.start_time
        self.save_result(target_hash, password, method, attempts, time_taken)
    
    def test_password_menu(self):
        """Паrole test menüsü"""
        print(f"\n{Fore.CYAN}=== ŞİFRE GÜCÜ TESTİ ==={Style.RESET_ALL}")
        
        password = input(f"{Fore.BLUE}[?] Test edilecek паrole: {Style.RESET_ALL}").strip()
        
        if not password:
            print(f"{Fore.RED}[-] Паrole gerekli!{Style.RESET_ALL}")
            return
        
        # Hash'ini de göster
        hash_md5 = hashlib.md5(password.encode()).hexdigest()
        hash_sha1 = hashlib.sha1(password.encode()).hexdigest()
        hash_sha256 = hashlib.sha256(password.encode()).hexdigest()
        
        print(f"\n{Fore.CYAN}Паrole Hash'leri:{Style.RESET_ALL}")
        print(f"MD5:    {hash_md5}")
        print(f"SHA1:   {hash_sha1}")
        print(f"SHA256: {hash_sha256}")
        
        self.test_password_strength(password)
    
    def create_hash_menu(self):
        """Hash создатьma menüsü"""
        print(f"\n{Fore.CYAN}=== HASH OLUŞTUR ==={Style.RESET_ALL}")
        
        password = input(f"{Fore.BLUE}[?] Паrole: {Style.RESET_ALL}").strip()
        
        if not password:
            print(f"{Fore.RED}[-] Паrole gerekli!{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}Hash Türü:{Style.RESET_ALL}")
        print("1. MD5")
        print("2. SHA1")
        print("3. SHA256")
        print("4. SHA512")
        print("5. Tümü")
        
        choice = input(f"{Fore.BLUE}[?] Выбратьim (1-5): {Style.RESET_ALL}").strip()
        
        password_bytes = password.encode('utf-8')
        
        if choice == "1" or choice == "5":
            print(f"MD5:    {hashlib.md5(password_bytes).hexdigest()}")
        if choice == "2" or choice == "5":
            print(f"SHA1:   {hashlib.sha1(password_bytes).hexdigest()}")
        if choice == "3" or choice == "5":
            print(f"SHA256: {hashlib.sha256(password_bytes).hexdigest()}")
        if choice == "4" or choice == "5":
            print(f"SHA512: {hashlib.sha512(password_bytes).hexdigest()}")
    
    def create_wordlist_menu(self):
        """Wordlist создатьma menüsü"""
        print(f"\n{Fore.CYAN}=== WORDLIST OLUŞTUR ==={Style.RESET_ALL}")
        
        print("1. Örnek wordlist создать (tavsiye edilen)")
        print("2. Özel wordlist создать")
        
        choice = input(f"{Fore.BLUE}[?] Выбратьim (1-2): {Style.RESET_ALL}").strip()
        
        if choice == "1":
            self.create_sample_wordlist()
        
        elif choice == "2":
            filename = input(f"{Fore.BLUE}[?] Dosya adı: {Style.RESET_ALL}").strip()
            if not filename:
                filename = "custom_wordlist.txt"
            
            words = []
            print(f"{Fore.BLUE}[*] Kelimeleri girin (bitirmek için 'done' yazın):{Style.RESET_ALL}")
            
            while True:
                word = input(f"{Fore.BLUE}[?] Kelime: {Style.RESET_ALL}").strip()
                if word.lower() == 'done':
                    break
                if word:
                    words.append(word)
            
            if words:
                os.makedirs("wordlists", exist_ok=True)
                filepath = os.path.join("wordlists", filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    for word in words:
                        f.write(word + "\n")
                
                print(f"{Fore.GREEN}[+] Wordlist создатьuldu: {filepath}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}[+] {len(words)} kelime addndi{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[-] Hiç kelime addnmedi!{Style.RESET_ALL}")
    
    def show_history(self):
        """Geçmiş sonuçları göster"""
        print(f"\n{Fore.CYAN}=== GEÇMİŞ SONUÇLAR ==={Style.RESET_ALL}")
        
        if not os.path.exists("results"):
            print(f"{Fore.YELLOW}[!] Henüz sonuç yok{Style.RESET_ALL}")
            return
        
        result_files = [f for f in os.listdir("results") if f.endswith('.json')]
        
        if not result_files:
            print(f"{Fore.YELLOW}[!] Henüz sonuç yok{Style.RESET_ALL}")
            return
        
        for i, filename in enumerate(sorted(result_files, reverse=True)[:10]):  # Последний 10 sonuç
            filepath = os.path.join("results", filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                
                print(f"\n{Fore.CYAN}[{i+1}] {result['timestamp']}{Style.RESET_ALL}")
                print(f"  Hash: {result['target_hash'][:16]}...")
                print(f"  Паrole: {result['password'] if result['password'] else 'BULUNAMADI'}")
                print(f"  Metod: {result['method']}")
                print(f"  Deneme: {result['attempts']}")
                print(f"  Süre: {result['time_taken']:.2f}s")
                
            except Exception as e:
                print(f"{Fore.RED}[!] {filename} okunamadı: {e}{Style.RESET_ALL}")

def main():
    """Ana fonksiyon"""
    try:
        cracker = PasswordCracker()
        cracker.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[!] Program user tarafından остановитьuldu{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[-] Baddnmeyen ошибка: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()