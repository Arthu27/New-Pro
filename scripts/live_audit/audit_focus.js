/* ============================================================
   Живой аудит страниц панели реальным браузером (без headless-CDN).
   Находит то, чего не видят статические тесты: JS-падения на странице,
   битые запросы/картинки, пустые селекты, "undefined" в тексте,
   горизонтальный скролл, пропавшие названия каналов.

   Подготовка (один раз, npm-пакет несёт браузер внутри):
     mkdir -p /tmp/shot && cd /tmp/shot && npm i puppeteer-core @sparticuz/chromium
     node -e "require('@sparticuz/chromium').default.executablePath()"
     python3 -c "import tarfile,brotli,io;..." — распаковать bin/al2023.tar.br
     (см. scripts/live_audit/README.md)

   Запуск (панель должна слушать 127.0.0.1:5001, демо-режим):
     cd /tmp/shot && LD_LIBRARY_PATH=/tmp/chrome-al2023/lib \
       node /path/to/repo/scripts/live_audit/audit_pages.js
   Флаг: страницы берутся из /tmp/pages.txt (список всех GET-роутов).
   Выход: консоль + /tmp/audit_all.json.

   ВАЖНО: ошибки вида cdn.discordapp.com … ERR_CONNECTION_CLOSED —
   это внешние аватары Discord; из закрытой сети они не грузятся,
   в реальном браузере работают. Не баг.
   ============================================================ */
/* Точечный аудит: какие именно URL падают и что за пустые селекты. */
const puppeteer = require('puppeteer-core');

const BASE = 'http://127.0.0.1:5001';
const PAGES = process.argv.slice(2);

(async () => {
  const b = await puppeteer.launch({
    executablePath: '/tmp/chromium',
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--headless=new'],
    headless: 'new'
  });
  const pg = await b.newPage();
  await pg.setViewport({ width: 1920, height: 1080 });
  await pg.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 });
  await pg.type('#passUsername', 'owner');
  await pg.type('#passPassword', 'preview123');
  await Promise.all([pg.click('button[type=submit]'), pg.waitForNavigation({ waitUntil: 'networkidle2' }).catch(() => {})]);

  for (const path of PAGES) {
    const fails = [];
    const onFail = r => fails.push('FAIL ' + r.url().slice(0, 130) + ' ' + (r.failure() && r.failure().errorText));
    const onResp = r => { if (r.status() >= 400) fails.push(r.status() + ' ' + r.url().slice(0, 130)); };
    pg.on('requestfailed', onFail); pg.on('response', onResp);
    console.log('════', path);
    try {
      await pg.goto(BASE + path, { waitUntil: 'networkidle2', timeout: 20000 });
      await new Promise(r => setTimeout(r, 1500));
      const details = await pg.evaluate(() => {
        const out = { emptySelects: [], chanLike: 0, undefinedText: [], imgAlt: [] };
        document.querySelectorAll('select').forEach(s => {
          if (s.offsetParent !== null && s.options.length === 0)
            out.emptySelects.push((s.id || s.name || s.className || 'anon').slice(0, 60) + ' ← ' + (s.previousElementSibling && s.previousElementSibling.textContent || '').trim().slice(0, 40));
        });
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n; const seen = new Set();
        while ((n = walker.nextNode())) {
          const t = (n.textContent || '').trim();
          if (t === 'undefined' || t === 'NaN' || t === 'null') {
            const par = n.parentElement;
            const key = par.outerHTML.slice(0, 90);
            if (!seen.has(key)) { seen.add(key); out.undefinedText.push(par.outerHTML.slice(0, 120)); }
          }
        }
        document.querySelectorAll('img').forEach(im => {
          if (im.complete && im.naturalWidth === 0 && im.src && !im.src.includes('data:'))
            out.imgAlt.push((im.alt || '?') + ' ← ' + im.src.slice(0, 90));
        });
        return out;
      });
      const uniqFails = [...new Set(fails.map(f => f.replace(/\d{6,}/g, 'SNOWFLAKE')))];
      // группируем: сколько однотипных
      const groups = {};
      uniqFails.forEach(f => { const k = f.replace(/SNOWFLAKE/g, '*').slice(0, 80); groups[k] = (groups[k] || 0) + 1; });
      Object.entries(groups).forEach(([k, c]) => console.log('  ', c + '×', k));
      if (details.emptySelects.length) console.log('   ПУСТЫЕ СЕЛЕКТЫ:', JSON.stringify(details.emptySelects, null, 1));
      if (details.undefinedText.length) console.log('   UNDEFINED-ТЕКСТ:', details.undefinedText.slice(0, 3).join('\n      '));
      if (details.imgAlt.length) console.log('   БИТЫЕ IMG:', details.imgAlt.slice(0, 4).join(' | '));
    } catch (e) { console.log('   NAV ERR:', e.message.slice(0, 100)); }
    pg.off('requestfailed', onFail); pg.off('response', onResp);
  }
  await b.close();
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
