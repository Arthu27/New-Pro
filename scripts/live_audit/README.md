# Живой аудит страниц (scripts/live_audit)

Полная проверка всех страниц панели настоящим браузером: JS-ошибки,
битые запросы и картинки, пустые селекты, «undefined» в тексте,
горизонтальный скролл, видимость названий каналов.

## Подготовка окружения (один раз)

```bash
mkdir -p /tmp/shot && cd /tmp/shot
npm init -y && npm i puppeteer-core @sparticuz/chromium
# браузер + системные библиотеки NSS (внутри npm-пакета)
python3 - <<'PY'
import tarfile, brotli, io
data = brotli.decompress(open('node_modules/@sparticuz/chromium/bin/al2023.tar.br','rb').read())
tarfile.open(fileobj=io.BytesIO(data)).extractall('/tmp/chrome-al2023')
PY
# сам бинарник хромиума
python3 - <<'PY'
import brotli
open('/tmp/chromium','wb').write(brotli.decompress(open('node_modules/@sparticuz/chromium/bin/chromium.br','rb').read()))
PY
chmod +x /tmp/chromium
```

## Запуск

```bash
# панель должна быть поднята на 127.0.0.1:5001 (демо-режим)
cd /home/user/New-Pro && python3 - <<'PY' > /tmp/pages.txt
from web.app import app
for r in app.url_map.iter_rules():
    p = str(r)
    if 'GET' in r.methods and not p.startswith(('/api','/static','/favicon')) and '<' not in p:
        print(p)
PY
cd /tmp/shot
LD_LIBRARY_PATH=/tmp/chrome-al2023/lib node /home/user/New-Pro/scripts/live_audit/audit_pages.js
```

Итог в консоли и /tmp/audit_all.json; точечный разбор — audit_focus.js /страница.

## Как читать результат

- `cdn.discordapp.com … ERR_CONNECTION_CLOSED` — внешние аватары Discord,
  не грузятся только из закрытой сети. Не баг.
- `409 /api/guild/.../archive|fun/...` — задокументированное «честный 409
  без бота» (закреплено тестами test_archive_panel.py).
- `ERR_ABORTED` на скачиваниях (Content-Disposition) — норма.
