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
/* Полный живой аудит панели: 152 страницы, реальные проблемы в браузере. */
const puppeteer = require('puppeteer-core');
const fs = require('fs');

const BASE = 'http://127.0.0.1:5001';
const pages = fs.readFileSync('/tmp/pages.txt', 'utf8').split('\n').map(s => s.trim()).filter(s => s.startsWith('/'));

(async () => {
  const b = await puppeteer.launch({
    executablePath: '/tmp/chromium',
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--headless=new'],
    headless: 'new'
  });
  const pg = await b.newPage();
  await pg.setViewport({ width: 1920, height: 1080 });

  // логин
  await pg.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 });
  await pg.type('#passUsername', 'owner');
  await pg.type('#passPassword', 'preview123');
  await Promise.all([
    pg.click('button[type=submit]'),
    pg.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {})
  ]);

  // эталон названий каналов из демо-данных
  const chans = await pg.evaluate(async () => {
    const r = await fetch('/api/channels');
    const j = await r.json();
    const arr = Array.isArray(j) ? j : (j.channels || j.items || []);
    return arr.map(c => c.name || '').filter(Boolean);
  });
  console.log('КАНАЛОВ В ДАННЫХ:', chans.length, JSON.stringify(chans.slice(0, 6)) + '…');

  const report = [];
  for (const path of pages) {
    const entry = { path, errors: [], failedReqs: [], brokenImgs: 0, emptySelects: 0,
                    badText: [], overflowX: false, chanNames: 0, chanPickers: 0, status: 0, redirected: null };
    const onConsole = m => { if (m.type() === 'error') entry.errors.push(m.text().slice(0, 160)); };
    const onPageErr = e => entry.errors.push('PAGEERROR: ' + String(e).slice(0, 160));
    const onResp = r => { if (r.status() >= 400 && r.url().startsWith(BASE)) entry.failedReqs.push(r.status() + ' ' + r.url().replace(BASE, '')); };
    pg.on('console', onConsole); pg.on('pageerror', onPageErr); pg.on('response', onResp);
    try {
      const resp = await pg.goto(BASE + path, { waitUntil: 'networkidle2', timeout: 25000 });
      entry.status = resp ? resp.status() : 0;
      if (pg.url() !== BASE + path) entry.redirected = pg.url().replace(BASE, '');
      await new Promise(r => setTimeout(r, 1400));
      const info = await pg.evaluate((chanNames) => {
        const res = { brokenImgs: 0, emptySelects: 0, badText: [], chanNames: 0, chanPickers: 0, overflowX: false };
        // битые картинки
        document.querySelectorAll('img').forEach(im => { if (im.complete && im.naturalWidth === 0 && im.src && !im.src.includes('data:')) res.brokenImgs++; });
        // пустые видимые селекты
        document.querySelectorAll('select').forEach(s => {
          const vis = s.offsetParent !== null || getComputedStyle(s).display !== 'none';
          if (vis && s.options.length === 0) res.emptySelects++;
        });
        // мусорный текст
        const txt = document.body.innerText || '';
        const junk = [];
        if (/(^|[^\p{L}\p{N}#._-])undefined([^\p{L}\p{N}_-]|$)/mu.test(txt)) junk.push('undefined');
        if (/(^|[^\p{L}\p{N}#._-])NaN([^\p{L}\p{N}_-]|$)/mu.test(txt)) junk.push('NaN');
        if (/(^|[^\p{L}\p{N}#._-])null([^\p{L}\p{N}_-]|$)/mu.test(txt)) junk.push('null');
        res.badText = junk;
// горизонтальный скролл
        res.overflowX = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
        // названия каналов в DOM (любые текстовые узлы с точным именем канала)
        const body = txt || '';
        for (const n of chanNames) { if (body.includes(n)) res.chanNames++; }
        // кастомные пикеры каналов
        res.chanPickers = document.querySelectorAll('.hakumo-select, [data-channel-picker], .channel-item, .chan-name').length;
        return res;
      }, chans);
      Object.assign(entry, info);
    } catch (e) {
      entry.errors.push('NAV: ' + String(e).slice(0, 120));
    }
    pg.off('console', onConsole); pg.off('pageerror', onPageErr); pg.off('response', onResp);
    report.push(entry);
    const flag = (entry.errors.length || entry.failedReqs.length || entry.brokenImgs || entry.emptySelects || entry.badText.length || entry.overflowX) ? '⚠' : ' ';
    console.log(flag, path, entry.status,
      entry.redirected ? '→' + entry.redirected : '',
      entry.errors.length ? 'ERR:' + entry.errors.length : '',
      entry.failedReqs.length ? 'REQ:' + entry.failedReqs.join('|') : '',
      entry.brokenImgs ? 'IMG:' + entry.brokenImgs : '',
      entry.emptySelects ? 'EMPTY-SELECT:' + entry.emptySelects : '',
      entry.badText.length ? 'TXT:' + entry.badText.join(',') : '',
      entry.overflowX ? 'OVERFLOW-X' : '');
  }
  fs.writeFileSync('/tmp/audit_all.json', JSON.stringify(report, null, 1));
  const bad = report.filter(e => e.errors.length || e.failedReqs.length || e.brokenImgs || e.emptySelects || e.badText.length || e.overflowX);
  console.log('======================================');
  console.log('СТРАНИЦ:', report.length, '· С ПРОБЛЕМАМИ:', bad.length);
  await b.close();
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
