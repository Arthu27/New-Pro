#!/bin/bash

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       MOEBIUS BOT BASLATILIYOR        ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# Python kontrolü
if ! command -v python3 &> /dev/null; then
    echo "  [HATA] Python3 bulunamadi!"
    echo "  Lutfen Python 3.8+ yukleyin."
    echo ""
    exit 1
fi

echo "  [OK] Python bulundu: $(python3 --version)"
echo ""

# .env dosyası kontrolü
if [ ! -f .env ]; then
    echo "  [UYARI] .env dosyasi bulunamadi!"
    echo "  Lutfen .env dosyasini olusturun ve TOKEN ekleyin."
    echo ""
fi

echo "  [INFO] Bot baslatiliyor..."
echo ""
python3 main.py
