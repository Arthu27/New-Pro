# ProBotum Console

Discord sunucu yönetim paneli — React + Vite dashboard, FastAPI backend ve discord.py botundan oluşur.

## Proje yapısı

```
.
├── index.html               # Vite giriş noktası
├── package.json             # Frontend bağımlılıkları
├── vite.config.ts
├── tsconfig.json
├── requirements.txt         # Python bağımlılıkları
├── .env.example             # Örnek konfigürasyon (kopyalayıp .env yap)
│
├── src/                     # Frontend (React + TypeScript + Tailwind)
│   ├── main.tsx             # React kökü
│   ├── App.tsx              # Router + global state
│   ├── index.css            # Tailwind + tema
│   ├── components/          # Layout, Modal, Drawer, Toast, ui
│   ├── pages/               # Dashboard sayfaları
│   ├── data/                # api.ts, store.ts, dashData.ts
│   └── lib/                 # utils.ts (cn helper)
│
├── server/                  # FastAPI backend
│   ├── api.py               # REST endpointleri
│   ├── db.py                # SQLite katmanı
│   ├── discord_rest.py      # Discord REST istemcisi
│   └── dev_seed.py          # Demo veri yükleyici
│
├── bot/                     # Discord bot (discord.py)
│   ├── main.py              # Bot giriş noktası
│   ├── permissions.py
│   ├── logging_setup.py
│   ├── private_settings_menu.py
│   └── modules/automod.py
│
└── scripts/                 # Windows yardımcı .bat dosyaları
    ├── START_FULL.bat       # Dashboard + API + Bot (her şeyi otomatik kurar)
    ├── START.bat            # Sadece dashboard
    ├── SEED_DEMO.bat        # Demo veri yükle
    ├── STOP.bat             # Servisleri durdur
    └── _deps.bat            # Ortak kurulum yardımcısı (elle çalıştırılmaz)
```

## Hızlı başlangıç (Windows)

Hiçbir şey kurmana gerek yok — **`scripts\START_FULL.bat`** dosyasına çift tıkla, yeter.

Script sırayla şunları yapar:

1. **Node.js** yoksa indirip kurar (önce `winget`, olmazsa nodejs.org'dan)
2. **Python** yoksa indirip kurar (Microsoft Store'un sahte `python` kısayolunu atlar)
3. `.env` yoksa `.env.example`'dan oluşturur ve Notepad'de açar
4. `npm install` ile Node paketlerini kurar
5. `.venv` sanal ortamı oluşturup Python paketlerini kurar
6. Veritabanı yoksa demo veriyi yükler
7. API + Bot + Dashboard'u başlatır ve tarayıcıyı açar

> **Not:** Node.js veya Python ilk kez kurulduysa script "pencereyi kapatıp tekrar çalıştır" diyecek.
> Bu normaldir — Windows'un yeni programı tanıması için gereklidir. İkinci çalıştırmada
> her şey sorunsuz devam eder.

Discord token girmezsen bot başlamaz ama **dashboard ve API demo veriyle çalışır** —
paneli incelemek için token gerekmez.

Durdurmak için: `scripts\STOP.bat`

## Elle kurulum (Linux / macOS / manuel tercih edenler)

Gereksinimler: **Node.js 18+** ve **Python 3.10+**

```bash
# 1) Konfigürasyon
cp .env.example .env        # Windows: copy .env.example .env
# .env içine DISCORD_TOKEN ve GUILD_ID yaz

# 2) Frontend
npm install

# 3) Backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Çalıştırma

```bash
# Dashboard (http://localhost:5173)
npm run dev

# API (http://localhost:3000/api)
python -m uvicorn server.api:app --host 0.0.0.0 --port 3000

# Discord bot
python -m bot.main

# Demo veri (bot olmadan test için)
python -m server.dev_seed
```

Windows'ta hepsini tek seferde başlatmak için `scripts\START_FULL.bat` çalıştırılabilir.

## Build

```bash
npm run build       # dist/index.html — tek dosya halinde paketlenir
npm run preview
npm run typecheck
```

## Notlar

- `.env` dosyası git'e **eklenmez**; gerçek tokenlar yalnızca yerelde tutulmalıdır.
- `DEV_USE_SNAPSHOT=true` iken bot çalışmadan da panel snapshot verisiyle test edilebilir.
- `ALLOW_LIVE_DISCORD_ACTIONS=false` iken Discord tarafında gerçek değişiklik yapılmaz, yalnızca önizleme üretilir.
