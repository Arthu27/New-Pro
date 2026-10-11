/* Soft navigation: сайдбар и data-soft без полной перезагрузки. */
(function () {
  'use strict';
  if (window.__PANEL_SOFT__) return;
  window.__PANEL_SOFT__ = 1;

  const cache = new Map();
  let ctrl = null;
  let busy = false;

  function sameOrigin(href) {
    try {
      const u = new URL(href, location.origin);
      return u.origin === location.origin;
    } catch (_) {
      return false;
    }
  }

  function shouldSoft(a) {
    if (!a || a.target === '_blank' || a.hasAttribute('download')) return false;
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) return false;
    if (a.dataset.noSoft != null) return false;
    if (!sameOrigin(href)) return false;
    // logout / oauth — полная перезагрузка
    if (/\/(logout|login|oauth)/i.test(href)) return false;
    return true;
  }

  function runScripts(container) {
    const list = [...container.querySelectorAll('script')];
    list.forEach((old) => {
      const s = document.createElement('script');
      if (old.src) {
        s.src = old.src;
        s.async = false; // порядок: конфиг → warn-live.js
      } else {
        s.textContent = old.textContent;
      }
      old.replaceWith(s);
    });
  }

  function applyDoc(html, url, push) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const nextMain = doc.querySelector('main.main');
    const curMain = document.querySelector('main.main');
    if (!nextMain || !curMain) {
      location.href = url;
      return;
    }
    curMain.innerHTML = nextMain.innerHTML;
    runScripts(curMain);
    const title = doc.querySelector('title');
    if (title) document.title = title.textContent;
    document.querySelectorAll('.side .nav a').forEach((a) => {
      try {
        const u = new URL(a.href, location.origin);
        a.classList.toggle('on', u.pathname === new URL(url, location.origin).pathname);
      } catch (_) {}
    });
    if (push) history.pushState({ soft: 1 }, '', url);
    window.scrollTo(0, 0);
  }

  async function softGoto(url, push) {
    if (busy) return;
    busy = true;
    const main = document.querySelector('main.main');
    if (main) main.classList.add('is-soft-loading');
    if (ctrl) try { ctrl.abort(); } catch (_) {}
    ctrl = new AbortController();
    try {
      let html = cache.get(url);
      if (!html) {
        const r = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'X-Soft-Nav': '1', Accept: 'text/html' },
          signal: ctrl.signal,
        });
        if (!r.ok) throw new Error('http ' + r.status);
        html = await r.text();
        if (cache.size > 24) {
          const k = cache.keys().next().value;
          cache.delete(k);
        }
        cache.set(url, html);
      }
      applyDoc(html, url, push);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      location.href = url;
    } finally {
      busy = false;
      const m = document.querySelector('main.main');
      if (m) m.classList.remove('is-soft-loading');
    }
  }

  function prefetch(url) {
    if (!url || cache.has(url)) return;
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Soft-Nav': '1', Accept: 'text/html' },
    }).then((r) => r.ok ? r.text() : null).then((html) => {
      if (html) {
        if (cache.size > 24) cache.delete(cache.keys().next().value);
        cache.set(url, html);
      }
    }).catch(() => {});
  }

  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a');
    if (!a || !shouldSoft(a)) return;
    // Warn live сам обрабатывает data-live-*
    if (a.hasAttribute('data-live-tab') || a.hasAttribute('data-live-page')) return;
    const inShell = a.closest('.side .nav') || a.hasAttribute('data-soft') || a.closest('.crumb');
    if (!inShell && !a.closest('.side')) return;
    // внутри warn live root — только data-soft / crumb
    if (a.closest('#warnLiveRoot') && !a.hasAttribute('data-soft')) return;
    e.preventDefault();
    softGoto(a.href, true);
  });

  document.addEventListener('mouseenter', (e) => {
    const a = e.target.closest && e.target.closest('.side .nav a');
    if (!a || !shouldSoft(a)) return;
    prefetch(a.href);
  }, true);

  window.addEventListener('popstate', () => {
    softGoto(location.href, false);
  });

  // idle prefetch: только лёгкие пункты, без тяжёлых /member /users /logs /channels
  const HEAVY = /\/(member|users|logs|channels|staff|org)(\?|$)/i;
  function lightPrefetch() {
    let n = 0;
    document.querySelectorAll('.side .nav a').forEach((a) => {
      if (n >= 2 || !shouldSoft(a) || HEAVY.test(a.getAttribute('href') || '')) return;
      prefetch(a.href);
      n += 1;
    });
  }
  if ('requestIdleCallback' in window) {
    requestIdleCallback(lightPrefetch, { timeout: 8000 });
  } else {
    setTimeout(lightPrefetch, 4000);
  }
})();
