/* ============================================================
   Hakumo Panel — App Kit (Light Edition)
   Единый клиентский слой панели: темы, тосты, подтверждения,
   ETag-кэш, live-refresh, палитра команд (Ctrl+K), уведомления,
   лента активности и мелкие утилиты для всех страниц.
   ============================================================ */
(function () {
  'use strict';

  var doc = document;

  /* ── 1. Утилиты ─────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtTime(ts) {
    if (!ts) return '';
    try {
      return new Date(ts * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return ''; }
  }

  function timeAgo(ts) {
    if (!ts) return '';
    /* принимаем и epoch-секунды, и ISO-строки; битые значения → «только что» */
    var v = ts;
    if (typeof v === 'string' && !/^\d+$/.test(v.trim())) {
      var p = Date.parse(v);
      v = isNaN(p) ? null : p / 1000;
    } else {
      v = Number(v);
    }
    if (v == null || !isFinite(v)) return 'только что';
    var diff = Math.max(0, (Date.now() / 1000) - v);
    if (diff < 60) return 'только что';
    if (diff < 3600) return Math.floor(diff / 60) + ' мин назад';
    if (diff < 86400) return Math.floor(diff / 3600) + ' ч назад';
    return Math.floor(diff / 86400) + ' дн назад';
  }

  /* ── 2. Тема ────────────────────────────────────────────── */
  function bootTheme() {
    var t = '';
    try { t = localStorage.getItem('hakumo_theme') || ''; } catch (e) {}
    if (!t) {
      // первый визит — следуем за системной темой
      try {
        t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      } catch (e) { t = 'light'; }
    }
    if (t !== 'light' && t !== 'dark') t = 'light';
    doc.documentElement.setAttribute('data-theme', t);
  }

  window.toggleTheme = function () {
    var cur = doc.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    doc.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('hakumo_theme', next); } catch (e) {}
    return next;
  };

  /* Динамический акцент (страница «Тема панели») */
  window.applyAccent = function (hex) {
    if (!hex) return;
    var s = String(hex).replace('#', '');
    if (s.length === 3) s = s.split('').map(function (c) { return c + c; }).join('');
    var n = parseInt(s, 16);
    if (isNaN(n)) return;
    var c = { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    var st = doc.documentElement.style;
    var rgba = function (a) { return 'rgba(' + c.r + ',' + c.g + ',' + c.b + ',' + a + ')'; };
    var light = function (f) {
      return 'rgb(' + Math.min(255, Math.round(c.r + (255 - c.r) * f)) + ',' +
        Math.min(255, Math.round(c.g + (255 - c.g) * f)) + ',' +
        Math.min(255, Math.round(c.b + (255 - c.b) * f)) + ')';
    };
    var dark = function (f) { return 'rgb(' + Math.round(c.r * f) + ',' + Math.round(c.g * f) + ',' + Math.round(c.b * f) + ')'; };
    st.setProperty('--ac', '#' + s);
    st.setProperty('--ac-2', light(0.35));
    st.setProperty('--ac-3', dark(0.72));
    st.setProperty('--ac-soft', rgba(0.10));
    st.setProperty('--ac-line', rgba(0.28));
    /* применяем и градиент кнопок/лого — перекраска полная, без индиго-хвостов */
    st.setProperty('--ac-grad', 'linear-gradient(135deg, #' + s + ', ' + light(0.18) + ' 55%, ' + dark(0.62) + ')');
    try { localStorage.setItem('hakumo_accent', hex); } catch (e) {}
  };

  /* ── 3. Тосты ───────────────────────────────────────────── */
  function ensureToastHost() {
    var host = doc.getElementById('toastHost');
    if (host) return host;
    host = doc.createElement('div');
    host.id = 'toastHost';
    doc.body.appendChild(host);
    return host;
  }

  window.showToast = function (msg, ok, opts) {
    opts = opts || {};
    var host = ensureToastHost();
    var el = doc.createElement('div');
    el.className = 'toast' + (ok === false ? ' err' : (ok === 'warn' ? ' warn' : ''));
    var icon = ok === false ? 'fa-circle-exclamation' : (ok === 'warn' ? 'fa-triangle-exclamation' : 'fa-circle-check');
    var ttl = opts.ttl || (opts.undo ? 6000 : 3200);
    el.style.setProperty('--toast-ttl', (ttl / 1000) + 's');
    var iconHtml = (ok === false || ok === 'warn')
      ? '<i class="fas ' + icon + '"></i>'
      : '<svg class="toast-check" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 13l4 4L19 7"/></svg>';
    el.innerHTML = iconHtml + '<span>' + esc(msg) + '</span>' +
      (opts.undo ? '<button type="button" class="undo-btn">Отменить</button>' : '');
    if (opts.undo) {
      el.querySelector('.undo-btn').addEventListener('click', function () {
        try { opts.undo(); } catch (e) {}
        dismiss(el);
      });
    }
    host.appendChild(el);
    var timer = setTimeout(function () { dismiss(el); }, ttl);
    function dismiss(node) {
      clearTimeout(timer);
      if (!node.parentNode) return;
      node.classList.add('leaving');
      setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 240);
    }
    el.addEventListener('click', function (e) {
      if (e.target && e.target.classList.contains('undo-btn')) return;
      dismiss(el);
    });
    while (host.children.length > 4) host.removeChild(host.firstChild);
  };

  window.uxUndo = function (label, undoFn) {
    window.showToast(label || 'Действие выполнено', true, { undo: undoFn });
  };

  /* ── 4. Подтверждения ───────────────────────────────────── */
  var confirmCb = null;
  var confirmBox = null;

  function buildConfirm() {
    if (confirmBox) return confirmBox;
    var overlay = doc.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.style.display = 'none';
    overlay.innerHTML =
      '<div class="modal-box" style="max-width:400px">' +
      '  <div class="modal-head">' +
      '    <div><h3 id="cfTitle">Подтверждение</h3><div class="sub" id="cfDesc"></div></div>' +
      '    <button type="button" class="close" aria-label="Закрыть"><i class="fas fa-xmark"></i></button>' +
      '  </div>' +
      '  <div class="modal-actions">' +
      '    <button type="button" class="btn" id="cfCancel">Отмена</button>' +
      '    <button type="button" class="btn" id="cfOk">Подтвердить</button>' +
      '  </div>' +
      '</div>';
    doc.body.appendChild(overlay);
    confirmBox = overlay;
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeConfirm(); });
    overlay.querySelector('.close').addEventListener('click', closeConfirm);
    overlay.querySelector('#cfCancel').addEventListener('click', closeConfirm);
    overlay.querySelector('#cfOk').addEventListener('click', function () {
      var cb = confirmCb;
      closeConfirm();
      if (cb) { try { cb(); } catch (e) {} }
    });
    return overlay;
  }

  function closeConfirm() {
    confirmCb = null;
    if (confirmBox) confirmBox.style.display = 'none';
  }

  window.confirmAction = window.askConfirm = function (title, desc, onOk, opts) {
    opts = opts || {};
    var box = buildConfirm();
    box.querySelector('#cfTitle').textContent = title || 'Подтверждение';
    box.querySelector('#cfDesc').textContent = desc || '';
    var ok = box.querySelector('#cfOk');
    ok.textContent = opts.okText || 'Подтвердить';
    ok.className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');
    confirmCb = typeof onOk === 'function' ? onOk : null;
    box.style.display = 'flex';
    setTimeout(function () { try { ok.focus(); } catch (e) {} }, 10);
  };

  /* ── 5. ETag-кэш: см. самостоятельный блок в конце файла ── */

  /* ── 6. Live-refresh ────────────────────────────────────── */
  var liveFns = [];
  var livePaused = false;

  /* Кнопка «молча не работает» — худшее, что есть в панели.
     Показываем понятный тост при непойманной JS-ошибке (не чаще раза в 20 с),
     чтобы сбой был виден, а не выглядел мёртвой кнопкой. */
  (function () {
    var lastToast = 0;
    function failToast() {
      var n = Date.now();
      if (n - lastToast < 20000) return;
      lastToast = n;
      if (typeof window.showToast === 'function') {
        try { window.showToast('Что-то загрузилось со сбоем — обновите страницу', false); } catch (e) {}
      }
    }
    window.addEventListener('error', function (e) {
      if (e && e.filename && String(e.filename).indexOf('/static/') === -1) return; // чужие скрипты не шумят
      failToast();
    });
    window.addEventListener('unhandledrejection', function () { failToast(); });
  })();

  /* «Противоударная» защита нажатий: пока палец/курсор нажаты (и чуть-чуть
     после отпускания), живые перерисовки списков откладываются — иначе
     элемент мог исчезнуть из-под пальца в середине клика, и нажатие
     «уходило в никуда» (те самые «пиксели»). */
  var liveHoldUntil = 0;
  function holdLiveRefresh(ms) {
    var t = Date.now() + ms;
    if (t > liveHoldUntil) liveHoldUntil = t;
  }
  window.addEventListener('pointerdown', function () { holdLiveRefresh(2600); }, { capture: true, passive: true });
  window.addEventListener('pointerup', function () { holdLiveRefresh(900); }, { capture: true, passive: true });
  window.addEventListener('pointercancel', function () { holdLiveRefresh(700); }, { capture: true, passive: true });
  Object.defineProperty(window, '__modLivePaused', {
    get: function () { return livePaused; },
    set: function (v) { livePaused = !!v; }
  });

  /* Тихие обновления: страницы сравнивают сигнатуру данных и пропускают
     перерисовку, когда данные не изменились (никаких миганий «как F5») */
  /* Структурированный HEALTH-лог бота:
     «HEALTH | uptime … | guilds 1 | ping 159ms | errors 0 (hour 0, crit 0, …) |
      warn 0 | dc 2 | webhook 0/0 | lag max 0.0s | alerts 0»
     → строка чипов с иконками и цветами вместо сырого текста. */
  window.fmtHealthLog = function (msg) {
    var parts = String(msg || '').split('|').map(function (s) { return s.trim(); });
    if (parts[0] !== 'HEALTH') return null;
    function escH(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
    function pluralH(n, one, few, many) {
      var m10 = n % 10, m100 = n % 100;
      if (m100 >= 11 && m100 <= 19) return many;
      if (m10 === 1) return one;
      if (m10 >= 2 && m10 <= 4) return few;
      return many;
    }
    function chip(icon, text, tone) {
      return '<span class="log-chip' + (tone ? ' ' + tone : '') + '"><i class="fas ' + icon + '"></i>' + escH(text) + '</span>';
    }
    var out = '<span class="log-health"><i class="fas fa-heart-pulse"></i> Здоровье</span>';
    for (var i = 1; i < parts.length; i++) {
      var p = parts[i], m;
      if ((m = p.match(/^uptime (.+)$/))) out += chip('fa-clock', m[1]);
      else if ((m = p.match(/^guilds (\d+)$/))) out += chip('fa-server', m[1] + ' ' + pluralH(+m[1], 'сервер', 'сервера', 'серверов'));
      else if ((m = p.match(/^ping (\d+(?:\.\d+)?)ms$/))) {
        var v = +m[1];
        out += chip('fa-signal', m[1] + ' мс', v < 120 ? 'ok' : v < 300 ? 'warn' : 'err');
      }
      else if ((m = p.match(/^errors (\d+) \(hour (\d+), crit (\d+), filtered (\d+), repeats (\d+)\)$/))) {
        var n = +m[1];
        out += chip('fa-bug', n + ' ' + pluralH(n, 'ошибка', 'ошибки', 'ошибок'), n > 0 ? 'err' : 'ok');
        out += chip('fa-filter', 'час ' + m[2] + ' · крит ' + m[3] + ' · фильтр ' + m[4] + ' · повторы ' + m[5], n > 0 ? 'err' : '');
      }
      else if ((m = p.match(/^warn (\d+)$/))) out += chip('fa-triangle-exclamation', m[1] + ' ' + pluralH(+m[1], 'варн', 'варна', 'варнов'), +m[1] > 0 ? 'warn' : '');
      else if ((m = p.match(/^dc (\d+)$/))) out += chip('fa-plug', m[1] + ' dc', +m[1] > 0 ? 'warn' : '');
      else if ((m = p.match(/^webhook (\d+)\/(\d+)$/))) out += chip('fa-link', 'вебхуки ' + m[1] + '/' + m[2], +m[1] > 0 ? 'warn' : '');
      else if ((m = p.match(/^lag max ([\d.]+)s$/))) out += chip('fa-gauge-high', 'лаг макс ' + m[1] + 'с', +m[1] > 1 ? 'warn' : '');
      else if ((m = p.match(/^alerts (\d+)$/))) out += chip('fa-bell', m[1] + ' ' + pluralH(+m[1], 'алерт', 'алерта', 'алертов'), +m[1] > 0 ? 'err' : 'ok');
      else out += chip('fa-circle-info', p);
    }
    return out;
  };

  window.silentGuard = function (key, sig) {
    if (typeof sig === 'undefined' || sig === null) return false;
    if (!window.__silentFp) window.__silentFp = {};
    if (window.__silentFp[key] === sig) return true;
    window.__silentFp[key] = sig;
    return false;
  };

  window.setLiveRefresh = function (fn, ms) {
    if (typeof fn !== 'function') return;
    liveFns.push({ fn: fn, ms: ms || 1500, last: 0 });
    if (liveFns.length > 60) liveFns.shift();
  };

  setInterval(function () {
    if (livePaused) return;
    /* Вкладка в фоне — опрос стоит: браузер всё равно рвёт ответы
       (отсюда шквал «context canceled» у туннеля). Вернёшься — само
       догонит живьём. */
    if (document.hidden) return;
    var now = Date.now();
    if (now < liveHoldUntil) return;
    liveFns.forEach(function (e) {
      if (now - e.last >= e.ms) { e.last = now; try { e.fn(); } catch (err) {} }
    });
  }, 500);

  /* Тихий live: перерисовка только если данные реально изменились.
     Убивает «как будто страницу перезагружают» при автообновлении. */
  window.__liveSig = window.__liveSig || {};
  window.renderIfChanged = function (key, data, renderFn) {
    if (typeof renderFn !== 'function') return;
    var sig;
    try { sig = JSON.stringify(data); } catch (e) { sig = String(Date.now()); }
    if (window.__liveSig[key] === sig) return false;   // ничего не поменялось — не трогаем DOM
    window.__liveSig[key] = sig;
    renderFn();
    return true;
  };
  window.dropLiveSig = function (key) { delete window.__liveSig[key]; };

  window.renderSafe = function (renderFn) {
    var y = window.scrollY, x = window.scrollX;
    if (typeof renderFn === 'function') { try { renderFn(); } catch (e) {} }
    var restore = function () { window.scrollTo(x, y); };
    requestAnimationFrame(restore);
    setTimeout(restore, 0);
  };

  /* Асинхронная версия: вернуть прокрутку ПОСЛЕ того, как
     промис завершился и DOM обновился (фикс прыжка страницы вверх
     при живых перерисовках списков). */
  window.keepScrollAsync = function (promise) {
    var y = window.scrollY, x = window.scrollX;
    Promise.resolve(promise).then(function () {
      requestAnimationFrame(function () { window.scrollTo(x, y); });
      setTimeout(function () { window.scrollTo(x, y); }, 50);
    }).catch(function () {});
    return promise;
  };

  window.keepScroll = function (renderFn) {
    window.renderSafe(renderFn);
  };

  /* ── 7. Кнопки-загрузки ─────────────────────────────────── */
  window.qualitySetLoading = function (btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.dataset.origHtml = btn.dataset.origHtml || btn.innerHTML;
      btn.classList.add('loading');
      btn.disabled = true;
      var i = btn.querySelector('i');
      if (i) {
        i.dataset.origClass = i.dataset.origClass || i.className;
        i.outerHTML = '<span class="btn-spinner" aria-hidden="true"></span>';
      }
    } else {
      btn.classList.remove('loading');
      btn.disabled = false;
      if (btn.dataset.origHtml) btn.innerHTML = btn.dataset.origHtml;
    }
  };

  /* ── 8. Donut-шкала ─────────────────────────────────────── */
  window.drawDonut = function (el, percent, color) {
    if (!el) return;
    var r = 15.9155, c = 2 * Math.PI * r;
    var size = el.getAttribute('data-size') || '96';
    var p = Math.max(0, Math.min(100, Number(percent) || 0));
    var track = getComputedStyle(doc.documentElement).getPropertyValue('--surface-3').trim() || '#eef0f3';
    var stroke = color || getComputedStyle(doc.documentElement).getPropertyValue('--ac').trim() || '#4f46e5';
    el.classList.add('donut');
    el.innerHTML =
      '<svg viewBox="0 0 36 36" style="width:' + size + 'px;height:' + size + 'px">' +
      '<circle cx="18" cy="18" r="' + r + '" fill="none" stroke="' + track + '" stroke-width="3.4"/>' +
      '<circle class="donut-fill" cx="18" cy="18" r="' + r + '" fill="none" stroke="' + stroke + '" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="' + c + '" stroke-dashoffset="' + c + '" style="filter:drop-shadow(0 2px 3px ' + stroke + '55)"/>' +
      '</svg>';
    var fill = el.querySelector('.donut-fill');
    if (!fill) return;
    var cur = parseFloat(el.getAttribute('data-val')) || 0;
    var t0 = null, dur = 700;
    function step(ts) {
      if (t0 == null) t0 = ts;
      var pr = Math.min((ts - t0) / dur, 1);
      var e = 1 - Math.pow(1 - pr, 3);
      fill.style.strokeDashoffset = c * (1 - (cur + (p - cur) * e) / 100);
      if (pr < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
    el.setAttribute('data-val', p);
  };

  /* ── 9. Палитра команд (Ctrl+K) ─────────────────────────── */
  var paletteData = [];
  var paletteEl = null;
  var paletteIndex = -1;
  var paletteMatches = [];

  function paletteInitData() {
    try {
      var node = doc.getElementById('palette-data');
      if (node) paletteData = JSON.parse(node.textContent || '[]');
    } catch (e) { paletteData = []; }
  }

  function paletteBuild() {
    if (paletteEl) return paletteEl;
    var el = doc.createElement('div');
    el.className = 'kbd-palette';
    el.hidden = true;
    el.innerHTML =
      '<div class="kbd-palette-panel">' +
      '  <div class="kbd-palette-search"><i class="fas fa-magnifying-glass"></i>' +
      '    <input type="text" placeholder="Перейти к разделу…" autocomplete="off">' +
      '    <span class="kbd-hint">ESC</span></div>' +
      '  <div class="kbd-palette-results"></div>' +
      '  <div class="kbd-palette-foot">' +
      '    <div><span class="kbd-hint">↑↓</span> навигация</div>' +
      '    <div><span class="kbd-hint">↵</span> открыть</div>' +
      '    <div><span class="kbd-hint">Ctrl K</span> вызов</div>' +
      '  </div>' +
      '</div>';
    doc.body.appendChild(el);
    paletteEl = el;
    var input = el.querySelector('input');
    input.addEventListener('input', paletteRender);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { paletteClose(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); paletteMove(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); paletteMove(-1); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        var item = paletteMatches[paletteIndex];
        if (item) { paletteClose(); paletteRemember(item.path); window.location.href = item.path; }
      }
    });
    el.addEventListener('click', function (e) { if (e.target === el) paletteClose(); });
    return el;
  }

  var paletteReqToken = 0;
  var paletteRemoteTimer = null;

  function paletteFavs() {
    try { return JSON.parse(localStorage.getItem('hakumo_favs') || '[]'); } catch (e) { return []; }
  }

  /* «Недавние» разделы: функция вызывалась, но не была определена —
     глобальный поиск падал с ReferenceError при каждом открытии */
  function paletteRecents() {
    try { return JSON.parse(localStorage.getItem('hakumo_recents') || '[]'); } catch (e) { return []; }
  }

  function paletteRemember(path) {
    try {
      var list = paletteRecents().filter(function (p) { return p !== path; });
      list.unshift(path);
      localStorage.setItem('hakumo_recents', JSON.stringify(list.slice(0, 8)));
    } catch (e) {}
  }

  function paletteLocalMatches(q) {
    var favs = paletteFavs();
    var recents = paletteRecents();
    var idx = {};
    var flat = [];
    paletteData.forEach(function (grp) {
      grp.pages.forEach(function (p) {
        idx[p.path] = p;
        flat.push({
          group: 'Разделы панели',
          path: p.path, label: p.label, icon2: p.icon, desc: p.description || '', sub: p.path,
          fav: favs.indexOf(p.path) !== -1
        });
      });
    });
    // недавние — поверх общего списка
    recents.forEach(function (path) {
      var p = idx[path];
      if (!p) return;
      var i = flat.findIndex(function (x) { return x.path === path; });
      if (i !== -1) flat.splice(i, 1);
      flat.unshift({
        group: 'Недавние',
        path: p.path, label: p.label, icon2: p.icon, desc: p.description || '', sub: p.path,
        fav: false
      });
    });
    return flat.filter(function (p) {
      if (!q) return true;
      return (p.label + ' ' + p.desc).toLowerCase().indexOf(q) !== -1;
    }).sort(function (a, b) { return (b.fav ? 1 : 0) - (a.fav ? 1 : 0); }).slice(0, 24);
  }

  function markMatch(text, q) {
    if (!q) return esc(text);
    var idx = String(text || '').toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return esc(text);
    return esc(text.slice(0, idx)) + '<span class="mark">' + esc(text.slice(idx, idx + q.length)) + '</span>' + esc(text.slice(idx + q.length));
  }

  function palettePaint(matches, hasRemotePending) {
    var box = paletteBuild();
    var input = box.querySelector('input');
    var q = (input.value || '').trim();
    var results = box.querySelector('.kbd-palette-results');
    paletteMatches = matches;
    paletteIndex = matches.length ? 0 : -1;
    if (!matches.length) {
      results.innerHTML = '<div class="kbd-palette-empty">' +
        (hasRemotePending ? 'Ищем по участникам, транскриптам и объявлениям…' : 'Ничего не найдено — попробуйте другой запрос') +
        '</div>';
      return;
    }
    var byGroup = {};
    matches.forEach(function (p) {
      (byGroup[p.group] = byGroup[p.group] || []).push(p);
    });
    var html = '';
    Object.keys(byGroup).forEach(function (g) {
      html += '<div class="kbd-palette-group"><div class="kbd-palette-group-title">' + esc(g) + '</div>';
      byGroup[g].forEach(function (p) {
        html += '<button type="button" class="kbd-palette-item" data-path="' + esc(p.path) + '"' + (p.run ? ' data-action="1"' : '') + '>' +
          '<i class="fas ' + esc(p.icon2 || 'fa-circle') + '"></i>' +
          '<span style="min-width:0;flex:1">' + markMatch(p.label, q) +
          (p.sub ? ' <small style="display:block;color:var(--text-3);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(p.sub) + '</small>' : '') +
          '</span>' +
          '<span class="kpi-path">' + esc(p.path) + '</span></button>';
      });
      html += '</div>';
    });
    results.innerHTML = html;
    Array.prototype.forEach.call(results.querySelectorAll('.kbd-palette-item'), function (node, i) {
      node.addEventListener('click', function () {
        var item = paletteMatches[i];
        if (item && item.run) {
          paletteClose();
          try { item.run(); } catch (e) { /* действие опционально */ }
          return;
        }
        paletteClose();
        paletteRemember(node.dataset.path);
        window.location.href = node.dataset.path;
      });
      node.addEventListener('mousemove', function () { paletteIndex = i; paletteHighlight(); });
    });
    paletteHighlight();
  }

  /* ── Действия палитры (команды, а не только страницы) ── */
  var PALETTE_ACTIONS = [
    { label: 'Сменить тему', icon: 'fa-circle-half-stroke', sub: 'переключить светлая/тёмная', run: function () { window.toggleTheme(); window.showToast('Тема переключена', true); } },
    { label: 'Светлая тема', icon: 'fa-sun', sub: 'включить светлый режим', run: function () { document.documentElement.setAttribute('data-theme', 'light'); try { localStorage.setItem('hakumo_theme', 'light'); } catch (e) {} } },
    { label: 'Тёмная тема', icon: 'fa-moon', sub: 'включить тёмный режим', run: function () { document.documentElement.setAttribute('data-theme', 'dark'); try { localStorage.setItem('hakumo_theme', 'dark'); } catch (e) {} } },
    { label: 'Скопировать ссылку страницы', icon: 'fa-link', sub: 'в буфер обмена', run: function () {
      var done = function () { window.showToast('Ссылка скопирована', true); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(window.location.href).then(done, function () {});
      else done();
    } },
    { label: 'Журнал: выгрузка CSV', icon: 'fa-file-csv', sub: 'последние 7 дней', run: function () { window.open('/logs/export?days=7', '_self'); } },
    { label: 'Отчёт модерации: CSV', icon: 'fa-file-csv', sub: 'статистика команды', run: function () { window.open('/api/mod-report.csv?days=7', '_self'); } },
    { label: 'Досье участника', icon: 'fa-id-card', sub: 'аналитика рисков по ID', run: function () { window.location.href = '/mod-insights'; } },
    { label: 'Центр безопасности', icon: 'fa-shield-halved', sub: 'политики и лаборатория', run: function () { window.location.href = '/security'; } },
    { label: 'Справка по горячим клавишам', icon: 'fa-keyboard', sub: 'все сочетания панели', run: function () { if (typeof window.openHelp === 'function') window.openHelp(); } },
    { label: 'Фокус-режим', icon: 'fa-eye', sub: 'только контент, без панелей', run: function () { document.body.classList.toggle('zen'); } },
    { label: 'Тур по панели', icon: 'fa-route', sub: 'знакомство с интерфейсом за минуту', run: function () { if (typeof window.tourStart === 'function') window.tourStart(); } },
    { label: 'Звук уведомлений', icon: 'fa-volume-high', sub: 'переключить вкл/выкл', run: function () {
      var off = false;
      try { off = localStorage.getItem('hakumo_sound') === 'off'; } catch (e) {}
      try { localStorage.setItem('hakumo_sound', off ? 'on' : 'off'); } catch (e) {}
      window.showToast(off ? 'Звук уведомлений включён' : 'Звук уведомлений выключен', true);
      if (!off && typeof window.notifyDing === 'function') window.notifyDing();
    } }
  ];

  function paletteActionMatches(q) {
    return PALETTE_ACTIONS.filter(function (a) {
      if (!q) return true;
      return (a.label + ' ' + (a.sub || '')).toLowerCase().indexOf(q.toLowerCase()) !== -1;
    }).map(function (a) {
      return { group: 'Действия', path: '#', label: a.label, icon2: a.icon, sub: a.sub, run: a.run };
    }).slice(0, 8);
  }

  function paletteRender() {
    var box = paletteBuild();
    var input = box.querySelector('input');
    var q = (input.value || '').toLowerCase().trim();
    var local = paletteActionMatches(q).concat(paletteLocalMatches(q));
    palettePaint(local, false);
    clearTimeout(paletteRemoteTimer);
    if (q.length < 2) return;
    palettePaint(local, true);
    paletteRemoteTimer = setTimeout(function () {
      var token = ++paletteReqToken;
      fetch('/api/ux/search?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (token !== paletteReqToken) return;
          var remote = [];
          ((d && d.groups) || []).forEach(function (grp) {
            if (grp.key === 'pages') return; // локальные страницы уже показаны
            (grp.items || []).forEach(function (it) {
              remote.push({
                group: grp.title || 'Результаты',
                path: it.href || '/',
                label: it.title || '—',
                icon2: it.icon || 'fa-circle',
                sub: it.sub || ''
              });
            });
          });
          palettePaint(local.concat(remote).slice(0, 40), false);
        })
        .catch(function () { palettePaint(local, false); });
    }, 180);
  }

  function paletteHighlight() {
    if (!paletteEl) return;
    Array.prototype.forEach.call(paletteEl.querySelectorAll('.kbd-palette-item'), function (node, i) {
      node.classList.toggle('selected', i === paletteIndex);
      if (i === paletteIndex && node.scrollIntoView) node.scrollIntoView({ block: 'nearest' });
    });
  }

  function paletteMove(dir) {
    if (!paletteMatches.length) return;
    paletteIndex = (paletteIndex + dir + paletteMatches.length) % paletteMatches.length;
    paletteHighlight();
  }

  function paletteOpen() {
    var box = paletteBuild();
    box.hidden = false;
    var input = box.querySelector('input');
    input.value = '';
    paletteRender();
    setTimeout(function () { input.focus(); }, 10);
  }

  function paletteClose() {
    if (paletteEl) paletteEl.hidden = true;
  }

  window.uxPaletteOpen = paletteOpen;

  /* ── 10. Сайдбар ────────────────────────────────────────── */
  window.sidebarInit = sidebarInit;  /* живой сайдбар: переподвязка после свапа */
  function sidebarInit() {
    var nav = doc.getElementById('sidebarNav');
    if (!nav) return;
    // Группы
    Array.prototype.forEach.call(nav.querySelectorAll('.nav-group-title[data-toggle]'), function (title) {
      title.addEventListener('click', function () {
        var grp = title.closest('.nav-group');
        if (grp) {
          grp.classList.toggle('collapsed');
          try { localStorage.setItem('sb_' + grp.dataset.group, grp.classList.contains('collapsed') ? '1' : '0'); } catch (e) {}
        }
      });
    });
    // Подгруппы (раздел модерации): активную раскрываем сразу
    Array.prototype.forEach.call(nav.querySelectorAll('.nav-subgroup'), function (sub) {
      var btn = sub.querySelector('.nav-subgroup-title');
      if (!btn) return;
      if (sub.classList.contains('has-active')) sub.classList.add('open');
      btn.addEventListener('click', function () { sub.classList.toggle('open'); });
    });
    // Поиск-фильтр по меню: подсветка совпадений, авто-раскрытие групп,
    // счётчик у группы, «ничего не найдено», Esc и хоткей «/»
    var search = doc.getElementById('sidebarSearch');
    if (search) {
      var sBox = search.parentNode;
      var sClear = doc.getElementById('sidebarSearchClear');
      var sEmpty = null;
      var sFavs = nav.querySelector('.nav-favs');

      function hl(span, q) {
        var label = span.textContent;
        var i = label.toLowerCase().indexOf(q);
        if (i === -1) return;
        if (!span.getAttribute('data-orig')) span.setAttribute('data-orig', span.innerHTML);
        span.textContent = '';
        span.appendChild(doc.createTextNode(label.slice(0, i)));
        var mk = doc.createElement('mark');
        mk.textContent = label.slice(i, i + q.length);
        span.appendChild(mk);
        span.appendChild(doc.createTextNode(label.slice(i + q.length)));
      }
      function unhl(span) {
        var o = span.getAttribute('data-orig');
        if (o !== null) { span.innerHTML = o; span.removeAttribute('data-orig'); }
      }

      function applyFilter() {
        var q = search.value.trim().toLowerCase();
        sBox.classList.toggle('has-value', !!q);
        if (sClear) sClear.hidden = !q;
        nav.classList.toggle('filtering', !!q);
        if (sFavs) sFavs.classList.toggle('nav-hide', !!q);
        var total = 0;
        Array.prototype.forEach.call(nav.querySelectorAll('.nav-link'), function (l) {
          if (l.closest('.nav-favs')) return;
          var span = l.querySelector('span');
          var label = span ? span.textContent : l.textContent;
          var hay = (label + ' ' + (l.getAttribute('title') || '')).toLowerCase();
          var hit = !q || hay.indexOf(q) !== -1;
          l.classList.toggle('nav-hide', !!q && !hit);
          if (q && hit && span) hl(span, q);
          else if (span) unhl(span);
          if (q && hit) total++;
        });
        Array.prototype.forEach.call(nav.querySelectorAll('.nav-subgroup'), function (sub) {
          var vis = sub.querySelectorAll('.nav-link:not(.nav-hide)').length;
          sub.classList.toggle('nav-hide', !!q && !vis);
        });
        Array.prototype.forEach.call(nav.querySelectorAll('.nav-group'), function (grp) {
          var vis = grp.querySelectorAll('.nav-link:not(.nav-hide)').length;
          grp.classList.toggle('nav-hide', !!q && !vis);
          var cnt = grp.querySelector('[data-count]');
          if (cnt) cnt.textContent = (q && vis) ? String(vis) : '';
        });
        if (q && !total) {
          if (!sEmpty) {
            sEmpty = doc.createElement('div');
            sEmpty.className = 'nav-empty';
            sEmpty.innerHTML = '<i class="fas fa-magnifying-glass-minus"></i>' +
              '<div>Ничего не нашлось по «<b></b>»<br><small>попробуйте другое слово</small></div>';
            nav.appendChild(sEmpty);
          }
          sEmpty.querySelector('b').textContent = search.value.trim();
          sEmpty.classList.add('show');
        } else if (sEmpty) {
          sEmpty.classList.remove('show');
        }
      }

      function resetFilter() { search.value = ''; applyFilter(); }
      search.addEventListener('input', applyFilter);
      search.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); resetFilter(); }
      });
      if (sClear) sClear.addEventListener('click', function () { resetFilter(); search.focus(); });
      doc.addEventListener('keydown', function (e) {
        if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
        var el = doc.activeElement;
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return;
        if (doc.body.classList.contains('zen')) return;
        var sb = doc.getElementById('sidebar');
        if (sb && sb.classList.contains('collapsed')) return;
        if (sBox.offsetParent === null) return;
        e.preventDefault();
        search.focus();
        search.select();
      });
    }
  }

  /* ── 11. Верхняя панель ─────────────────────────────────── */
  function topbarInit() {
    var clock = doc.getElementById('navClock');
    var sysClock = doc.getElementById('sysClock');

    // Живой пинг в шапке
    var pingPill = doc.getElementById('pingPill');
    if (pingPill) {
      function paintPing() {
        try {
          var v = localStorage.getItem('hakumo_last_ping');
          if (v === null) return;
          var parts = v.split('|');
          var ms = parseInt(parts[0], 10) || 0;
          var age = Date.now() - (parseInt(parts[1], 10) || 0);
          if (age > 8000) {
            pingPill.className = 'ping-pill lat-off';
            pingPill.innerHTML = '<span class="ping-dot"></span>—<small>мс</small>';
          } else {
            var cls = ms < 80 ? '' : ms < 150 ? 'lat-warn' : 'lat-bad';
            pingPill.className = 'ping-pill ' + cls;
            pingPill.innerHTML = '<span class="ping-dot"></span>' + ms + '<small>мс</small>';
          }
        } catch (e) {}
      }
      paintPing();
      setInterval(paintPing, 2000);
      pingPill.addEventListener('click', function () {
        window.location.href = '/bot-stats';
      });
    }

    // Сохранение пинга из /api/stats
    function trackPing() {
      fetch('/api/stats', { guardSilent: true })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && typeof d.latency === 'number') {
            try { localStorage.setItem('hakumo_last_ping', Math.round(d.latency) + '|' + Date.now()); } catch (e) {}
          }
        })
        .catch(function () {});
    }
    trackPing();
    setInterval(trackPing, 3000);
    var tick = function () {
      var t = new Date().toLocaleTimeString('ru-RU');
      if (clock) clock.textContent = t;
      if (sysClock) sysClock.textContent = t;
    };
    tick();
    setInterval(tick, 1000);
    // Тонкий индикатор прокрутки страницы
    var prog = document.createElement('div');
    prog.className = 'scroll-progress';
    doc.body.appendChild(prog);
    var onScroll = function () {
      var max = doc.documentElement.scrollHeight - window.innerHeight;
      prog.style.width = (max > 0 ? Math.min(100, (window.scrollY / max) * 100) : 0) + '%';
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    var fsBtn = doc.getElementById('fullscreenBtn');
    if (fsBtn) {
      fsBtn.addEventListener('click', function () {
        if (!doc.fullscreenElement) {
          (doc.documentElement.requestFullscreen || function () {}).call(doc.documentElement);
        } else if (doc.exitFullscreen) doc.exitFullscreen();
      });
    }
    var themeBtn = doc.getElementById('themeToggle');
    if (themeBtn) themeBtn.addEventListener('click', function () { window.toggleTheme(); });
    var pill = doc.querySelector('.user-pill');
    if (pill) {
      pill.addEventListener('click', function (e) {
        e.stopPropagation();
        if (window.closeTopOverlays) window.closeTopOverlays();
        pill.classList.toggle('open');
      });
      doc.addEventListener('click', function () { pill.classList.remove('open'); });
    }
    var mobile = doc.getElementById('mobileMenu');
    var sidebar = doc.getElementById('sidebar');
    if (mobile && sidebar) {
      mobile.addEventListener('click', function () { sidebar.classList.toggle('open'); });
      doc.addEventListener('click', function (e) {
        if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== mobile && !mobile.contains(e.target)) {
          sidebar.classList.remove('open');
        }
      });
    }
    var searchBtn = doc.getElementById('globalSearchBtn');
    if (searchBtn) searchBtn.addEventListener('click', paletteOpen);
  }

  /* ── Общий закрыватель верхних оверлеев ─────────────────────
     Уведомления, лента активности, меню пользователя и попап
     акцента никогда не висят одновременно — меню не смешиваются. */
  window.closeTopOverlays = function (exceptId) {
    ['notifDrawer', 'activityDrawer'].forEach(function (id) {
      var el = doc.getElementById(id);
      if (el && id !== exceptId) el.classList.remove('open');
    });
    ['drawerBackdrop', 'activityBackdrop'].forEach(function (id) {
      var el = doc.getElementById(id);
      if (el) el.classList.remove('open');
    });
    var pill = doc.querySelector('.user-pill.open');
    if (pill) pill.classList.remove('open');
    var pop = doc.querySelector('.accent-pop');
    if (pop && !pop.hidden) pop.hidden = true;
  };

  /* ── 12. Уведомления (v2) и лента активности ───────────── */
  var notifLastSeen = 0;
  var notifTab = 'all';

  function notifInit() {
    var bell = doc.getElementById('notifBtn');
    var badge = doc.getElementById('notifBadge');
    var drawer = doc.getElementById('notifDrawer');
    var backdrop = doc.getElementById('drawerBackdrop');
    if (!bell || !drawer) return;

    function closeDrawer() {
      drawer.classList.remove('open');
      if (backdrop) backdrop.classList.remove('open');
      if (badge) { badge.style.display = 'none'; badge.textContent = '0'; }
    }

    bell.addEventListener('click', function () {
      if (drawer.classList.contains('open')) { closeDrawer(); return; }
      if (window.closeTopOverlays) window.closeTopOverlays('notifDrawer');
      drawer.classList.add('open');
      if (backdrop) backdrop.classList.add('open');
      loadNotifs();
      try {
        fetch('/api/my-notifications').catch(function () {});
        notifLastSeen = Date.now() / 1000;
      } catch (e) {}
    });
    if (backdrop) backdrop.addEventListener('click', closeDrawer);
    var closeBtn = drawer.querySelector('.drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    var markAll = doc.getElementById('notifMarkAll');
    if (markAll) markAll.addEventListener('click', function () {
      fetch('/api/my-notifications').catch(function () {});
      notifLastSeen = Date.now() / 1000;
      loadNotifs();
      window.showToast('Все уведомления отмечены прочитанными', true);
    });

    function notifIcon(n) {
      var raw = String(n.icon || 'fa-bell');
      return /^fa-/.test(raw) ? raw : 'fa-bell';
    }

    function paintTitle(unread) {
      try {
        var base = doc.title.replace(/^\(\d+\)\s*/, "");
        if (unread > 0 && !drawer.classList.contains("open")) {
          doc.title = "(" + (unread > 99 ? "99+" : unread) + ") " + base;
        } else {
          doc.title = base;
        }
      } catch (e) {}
    }

    function loadNotifs() {
      var body = doc.getElementById('notifBody');
      if (!body) return;
      var sysP = fetch('/api/notifications/poll').then(function (r) { return r.json(); }).catch(function () { return { notifications: [], unread: 0 }; });
      var ownP = fetch('/api/my-notifications').then(function (r) { return r.json(); }).catch(function () { return []; });
      Promise.all([sysP, ownP]).then(function (both) {
        var sys = both[0].notifications || [];
        var own = Array.isArray(both[1]) ? both[1] : [];
        var sysItems = sys.map(function (n) {
          return { title: n.title, body: n.body, icon: notifIcon(n), ts: n.ts, kind: 'system', link: n.link || '' };
        });
        var ownItems = own.map(function (n) {
          return {
            title: n.title || n.action || 'Уведомление',
            body: n.body || n.detail || '',
            icon: /^fa-/.test(n.icon || '') ? n.icon : 'fa-bell',
            ts: n.ts || n.created_at || n.timestamp || 0,
            kind: 'personal',
            link: n.link || n.path || ''
          };
        });
        var all = sysItems.concat(ownItems).sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); });
        var list = notifTab === 'system' ? sysItems : notifTab === 'personal' ? ownItems : all;
        if (!list.length) {
          body.innerHTML = '<div class="empty"><i class="fas fa-bell-slash"></i><span>Уведомлений нет</span></div>';
        } else {
          body.innerHTML = list.slice(0, 30).map(function (n) {
            var t = n.ts ? timeAgo(n.ts) : '';
            var isNew = n.ts && (n.ts * 1 || 0) > notifLastSeen && drawer.classList.contains('open') === false;
            var inner =
              '<div class="feed-item-icon"><i class="fas ' + esc(n.icon) + '"></i></div>' +
              '<div style="min-width:0"><div class="feed-item-title">' + esc(n.title || '') + '</div>' +
              (n.body ? '<div class="feed-item-sub">' + esc(n.body) + '</div>' : '') +
              '<div class="feed-item-time">' +
                (n.kind === 'personal'
                  ? '<span class="badge neutral" style="font-size:9px;padding:0 6px">личное</span> '
                  : '<span class="badge security" style="font-size:9px;padding:0 6px">система</span> ') +
                esc(t) + '</div></div>';
            if (n.link) {
              return '<a class="feed-item' + (isNew ? ' is-new' : '') + '" href="' + esc(n.link) + '" data-notif-link>' + inner + '</a>';
            }
            return '<div class="feed-item' + (isNew ? ' is-new' : '') + '">' + inner + '</div>';
          }).join('');
          Array.prototype.forEach.call(body.querySelectorAll('[data-notif-link]'), function (a) {
            a.addEventListener('click', function (e) {
              e.preventDefault();
              closeDrawer();
              window.location.href = a.getAttribute('href');
            });
          });
        }
        var unread = both[0].unread || 0;
        if (unread > 0 && badge && !drawer.classList.contains('open')) {
          var prev = Number(badge.textContent) || 0;
          if (unread > prev && typeof window.notifyDing === 'function') window.notifyDing();
          badge.textContent = unread > 99 ? '99+' : unread;
          badge.style.display = 'grid';
        }
        paintTitle(unread);
      });
    }

    Array.prototype.forEach.call(doc.querySelectorAll('[data-notif-tab]'), function (tab) {
      tab.addEventListener('click', function () {
        notifTab = tab.dataset.notifTab;
        Array.prototype.forEach.call(doc.querySelectorAll('[data-notif-tab]'), function (t) {
          t.classList.toggle('active', t === tab);
        });
        loadNotifs();
      });
    });

    loadNotifs();
    setInterval(loadNotifs, 30000);
  }

  function activityInit() {
    var btn = doc.getElementById('activityBtn');
    var drawer = doc.getElementById('activityDrawer');
    var backdrop = doc.getElementById('activityBackdrop');
    if (!btn || !drawer) return;
    var loaded = false;

    function close() {
      drawer.classList.remove('open');
      if (backdrop) backdrop.classList.remove('open');
    }

    btn.addEventListener('click', function () {
      if (drawer.classList.contains('open')) { close(); return; }
      if (window.closeTopOverlays) window.closeTopOverlays('activityDrawer');
      drawer.classList.add('open');
      if (backdrop) backdrop.classList.add('open');
      if (!loaded) { loadActivity(); loaded = true; }
    });
    if (backdrop) backdrop.addEventListener('click', close);
    var closeBtn = drawer.querySelector('.drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
    var refresh = doc.getElementById('activityRefresh');
    if (refresh) refresh.addEventListener('click', loadActivity);

    function loadActivity() {
      var body = doc.getElementById('activityBody');
      if (!body) return;
      fetch('/api/activity-feed')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var items = Array.isArray(d) ? d : (d.items || []);
          if (!items.length) {
            body.innerHTML = '<div class="empty"><i class="fas fa-stream"></i><span>Событий пока нет</span></div>';
            return;
          }
          body.innerHTML = items.slice(0, 40).map(function (it) {
            var ic = /^fa-/.test(it.icon || '') ? it.icon : 'fa-circle';
            var inner =
              '<div class="feed-item-icon"><i class="fas ' + esc(ic) + '"></i></div>' +
              '<div style="min-width:0"><div class="feed-item-title">' + esc(it.title || '') + '</div>' +
              '<div class="feed-item-sub">' + esc(it.user || '') + (it.detail ? ' — ' + esc(it.detail) : '') + '</div>' +
              '<div class="feed-item-time">' + esc(timeAgo(it.ts)) + '</div></div>';
            if (it.link) {
              return '<a class="feed-item" href="' + esc(it.link) + '" data-activity-link>' + inner + '</a>';
            }
            return '<div class="feed-item">' + inner + '</div>';
          }).join('');
          Array.prototype.forEach.call(body.querySelectorAll('[data-activity-link]'), function (a) {
            a.addEventListener('click', function (e) {
              e.preventDefault();
              close();
              window.location.href = a.getAttribute('href');
            });
          });
          var stamp = doc.getElementById('activityLastUpdate');
          if (stamp) stamp.textContent = 'Обновлено ' + new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        })
        .catch(function () {});
    }
  }

  /* ── 13. Копирование по клику ───────────────────────────── */
  function copyInit() {
    doc.addEventListener('click', function (e) {
      var node = e.target && e.target.closest ? e.target.closest('[data-copy]') : null;
      if (!node) return;
      var text = node.getAttribute('data-copy') || node.textContent;
      var done = function () { window.showToast('Скопировано в буфер обмена', true); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () { fallback(); });
      } else fallback();
      function fallback() {
        var ta = doc.createElement('textarea');
        ta.value = text;
        doc.body.appendChild(ta);
        ta.select();
        try { doc.execCommand('copy'); done(); } catch (err) {}
        doc.body.removeChild(ta);
      }
    });
  }

  /* ── 14. WebSocket (если сервер доступен) ───────────────── */
  function wsInit() {
    if (typeof WebSocket === 'undefined' || typeof window.WebSocketClient === 'undefined') return;
    var userId = window.__panelUserId || '';
    var roomId = userId ? 'user_' + userId : 'global';
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = proto + '//' + (window.location.hostname || 'localhost') + ':8765';
    try {
      var ws = new window.WebSocketClient({ url: wsUrl, roomId: roomId, userId: userId, autoConnect: true });
      window.wsClient = ws;
      ws.on('connected', function () {
        try { ws.sendPresence('online'); } catch (e) {}
      });
      ws.on('ticket_update', function (d) { if (typeof window.handleTicketUpdate === 'function') window.handleTicketUpdate(d); });
      ws.on('new_ticket', function (d) {
        window.showToast('Новый тикет создан', true);
        if (typeof window.handleNewTicket === 'function') window.handleNewTicket(d);
      });
      ws.on('stats_update', function (d) {
        if (typeof window.handleStatsUpdate === 'function') window.handleStatsUpdate(d);
        try { doc.dispatchEvent(new CustomEvent('hakumo:live', { detail: d || {} })); } catch (e) {}
      });
      ws.on('notification', function (d) {
        if (d && d.data && d.data.title) {
          var el = document.createElement('div');
          el.className = 'toast bot-event';
          var ttl = 4000;
          el.style.setProperty('--toast-ttl', (ttl / 1000) + 's');
          el.innerHTML = '<i class="fas fa-robot"></i><span>' + esc(d.data.title) + '</span>';
          var host = document.getElementById('toastHost');
          if (!host) {
            host = document.createElement('div');
            host.id = 'toastHost';
            document.body.appendChild(host);
          }
          host.appendChild(el);
          setTimeout(function () {
            el.classList.add('leaving');
            setTimeout(function () { el.remove(); }, 240);
          }, ttl);
        }
        if (typeof window.handleNotification === 'function') window.handleNotification(d);
      });
      ws.on('typing', function (d) { if (typeof window.handleTypingIndicator === 'function') window.handleTypingIndicator(d); });
      ws.on('presence', function (d) { if (typeof window.handlePresenceStatus === 'function') window.handlePresenceStatus(d); });
      window.addEventListener('beforeunload', function () {
        if (window.wsClient && window.wsClient.isConnected) {
          try { window.wsClient.sendPresence('offline'); } catch (e) {}
        }
      });
    } catch (e) { /* вебсокет недоступен — панель работает без real-time */ }
  }

  /* ── 13a. Анимация переключения вкладок ─────────────────── */
  function tabTransitions() {
    doc.addEventListener('click', function (e) {
      var tab = e.target && e.target.closest ? e.target.closest('.tab-btn, .seg-btn, .eco-tab, .tm-tab') : null;
      if (!tab) return;
      doc.querySelectorAll('.tab-content').forEach(function (el) {
        if (el.style.display !== 'none' && el.offsetParent !== null) el.dataset.tabWas = '1';
        else delete el.dataset.tabWas;
      });
      setTimeout(function () {
        doc.querySelectorAll('.tab-content').forEach(function (el) {
          var visible = el.style.display !== 'none' && el.offsetParent !== null;
          if (visible && !el.dataset.tabWas) {
            el.classList.remove('tab-switch');
            void el.offsetWidth;
            el.classList.add('tab-switch');
          }
          delete el.dataset.tabWas;
        });
      }, 40);
    });
  }

  /* ── 14a. Плавные переходы между страницами ─────────────── */
  function pageTransitions() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    doc.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      if (!a) return;
      var href = a.getAttribute('href') || '';
      if (!href || href.charAt(0) !== '/' || href.charAt(1) === '/') return;
      if (href.charAt(1) === '#') return;
      if (a.target === '_blank' || a.hasAttribute('download')) return;
      if (href === window.location.pathname + window.location.search) return;
      e.preventDefault();
      doc.body.classList.add('page-leaving');
      setTimeout(function () { window.location.href = href; }, 150);
    });
  }

  /* ── 14b. Автопоиск: Enter в пустом списке фокусирует поиск ── */
  function autoSearchInit() {
    doc.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var t = e.target;
      var tag = t && t.tagName ? t.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
      // если пользователь стоит на пустом состоянии — фокус на поиск
      var panel = document.querySelector('.panel:has(.empty)');
      var search = document.querySelector('#search, #logs-search, #pf-q');
      if (search && panel) {
        search.focus();
        search.classList.remove('search-flash');
        void search.offsetWidth;
        search.classList.add('search-flash');
      }
    });
  }

  /* ── 15. Хоткеи ─────────────────────────────────────────── */
  function hotkeysInit() {
    doc.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K' || e.key === 'л' || e.key === 'Л')) {
        e.preventDefault();
        paletteOpen();
      }
    });
  }

  /* ── 15a. Появление при прокрутке ([data-reveal]) ───────── */
  function revealInit() {
    var els = doc.querySelectorAll('[data-reveal]');
    if (!els.length) return;
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (e) { e.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });
    function observe(el) { if (el && !el.classList.contains('in')) io.observe(el); }
    els.forEach(observe);
    var mo = new MutationObserver(function (muts) {
      muts.forEach(function (mu) {
        (mu.addedNodes || []).forEach(function (n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches('[data-reveal]')) observe(n);
          if (n.querySelectorAll) n.querySelectorAll('[data-reveal]').forEach(observe);
        });
      });
    });
    mo.observe(doc.body, { childList: true, subtree: true });
  }

  /* ── 16. Прочее ─────────────────────────────────────────── */
  window.applyCompact = function (on) {
    doc.body.classList.toggle('dense', !!on);
  };

  window.UX = {
    esc: esc,
    undo: window.uxUndo,
    openPalette: paletteOpen,
    toast: window.showToast,
    confirm: window.confirmAction
  };

  /* ── Старт ──────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  bootTheme();
  /* Восстановление сохранённого акцента: иначе цвет сбрасывался
     при каждой перезагрузке страницы / смене канала. */
  (function bootAccent() {
    try {
      var acc = localStorage.getItem('hakumo_accent');
      if (acc && acc !== '#4f46e5') window.applyAccent(acc);
    } catch (e) {}
  })();
  ready(function () {
    paletteInitData();
    topbarInit();
    sidebarInit();
    notifInit();
    activityInit();
    copyInit();
    hotkeysInit();
    pageTransitions();
    tabTransitions();
    autoSearchInit();
    revealInit();
    wsInit();
  });
})();

// ============================================================
// ETag-кэш для частых GET-опросов. 304 — штатный «данные не
// изменились»: возвращаем сохранённый JSON и не заставляем
// страницы разбирать пустое тело.
// ============================================================
(function () {
  var _etagStore = Object.create(null);

  window._etagCache = {
    _d: Object.create(null),
    get: function (url) { return this._d[url]; },
    has: function (url) { return Object.prototype.hasOwnProperty.call(this._d, url); },
    set: function (url, data) { this._d[url] = data; return data; }
  };

  function requestOptions(opts) {
    opts = opts || {};
    var init = Object.assign({}, opts);
    var headers = new Headers(opts.headers || {});
    init.headers = headers;
    return init;
  }

  window.fetchCached = function (url, opts) {
    var init = requestOptions(opts);
    if (_etagStore[url]) init.headers.set('If-None-Match', _etagStore[url]);
    return fetch(url, init).then(function (r) {
      var etag = r.headers.get('ETag');
      if (etag) _etagStore[url] = etag;
      return r;
    });
  };

  window.fetchCachedJSON = function (url, opts) {
    function consume(response, retried) {
      if (response.status === 304) {
        if (window._etagCache.has(url)) return window._etagCache.get(url);

        // После перезагрузки страницы браузер/прокси иногда помнит ETag, а
        // JS-память с JSON уже пуста. Один раз повторяем без валидатора.
        if (!retried) {
          delete _etagStore[url];
          var fresh = requestOptions(opts);
          fresh.cache = 'no-store';
          fresh.headers.delete('If-None-Match');
          return window.fetchCached(url, fresh).then(function (r) { return consume(r, true); });
        }
        throw new Error('HTTP 304 получен без сохранённых данных: ' + url);
      }
      if (!response.ok) throw new Error('HTTP ' + response.status + ': ' + url);
      return response.json().then(function (data) {
        return window._etagCache.set(url, data);
      });
    }

    return window.fetchCached(url, opts).then(function (r) { return consume(r, false); });
  };
})();

// ============================================================
// GLOBAL LIVE REFRESH — страницы регистрируют свои загрузчики,
// общий интервал обновляет их каждые 2.5s (реализован в app.js).
// ============================================================

// ============================================================
// HAKUMO PREMIUM KIT — счётчики, сортировка таблиц, графики
// ============================================================
(function () {
  'use strict';

  var doc = document;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function cssVar(name, fallback) {
    try {
      var v = getComputedStyle(doc.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  function reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ── Анимированный счётчик числа ─────────────────────── */
  window.countUp = function (el, target, opts) {
    opts = opts || {};
    if (!el) return;
    var dur = opts.duration || 700;
    var start = 0;
    var m = /([\d\s.,]+)/.exec(el.textContent || '');
    if (m) start = parseFloat(m[1].replace(/\\s/g, '').replace(',', '.')) || 0;
    target = Number(target) || 0;
    var fmt = opts.fmt || function (v) { return Math.round(v).toLocaleString('ru-RU'); };
    if (reduced || Math.abs(target - start) < 1) { el.textContent = fmt(target); return; }
    var t0 = null;
    function step(ts) {
      if (t0 == null) t0 = ts;
      var pr = Math.min(1, (ts - t0) / dur);
      var e = 1 - Math.pow(1 - pr, 3);
      el.textContent = fmt(start + (target - start) * e);
      if (pr < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  };

  /* ── Клиентская сортировка таблиц ────────────────────── */
  function readSortVal(cell) {
    var raw = cell.getAttribute('data-sort');
    if (raw != null && raw !== '') return raw;
    return (cell.textContent || '').trim();
  }

  window.attachTableSort = function (table) {
    if (!table || table.dataset.sortReady) return;
    table.dataset.sortReady = '1';
    Array.prototype.forEach.call(table.querySelectorAll('thead th.sortable'), function (th) {
      var ico = doc.createElement('i');
      ico.className = 'fas fa-sort sort-ico';
      ico.setAttribute('aria-hidden', 'true');
      th.appendChild(ico);
      th.addEventListener('click', function () {
        var tbody = table.tBodies && table.tBodies[0];
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.rows);
        var col = Array.prototype.indexOf.call(th.parentNode.children, th);
        var key = th.getAttribute('data-sort-key') || null;
        var dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        Array.prototype.forEach.call(table.querySelectorAll('thead th.sortable'), function (other) {
          if (other !== th) other.removeAttribute('aria-sort');
          var oi = other.querySelector('.sort-ico');
          if (oi) oi.className = 'fas fa-sort sort-ico';
        });
        th.setAttribute('aria-sort', dir);
        ico.className = 'fas ' + (dir === 'ascending' ? 'fa-sort-up' : 'fa-sort-down') + ' sort-ico';
        rows.sort(function (a, b) {
          var ca = a.children[col], cb = b.children[col];
          var va = ca ? (key ? readSortVal(ca.querySelector('[data-sort="' + key + '"]') || ca) : readSortVal(ca)) : '';
          var vb = cb ? (key ? readSortVal(cb.querySelector('[data-sort="' + key + '"]') || cb) : readSortVal(cb)) : '';
          var na = parseFloat(String(va).replace(/\\s/g, '').replace(',', '.'));
          var nb = parseFloat(String(vb).replace(/\\s/g, '').replace(',', '.'));
          var res;
          if (!isNaN(na) && !isNaN(nb) && String(va).replace(/\\D/g, '') && String(vb).replace(/\\D/g, '')) {
            res = na - nb;
          } else {
            res = String(va).localeCompare(String(vb), 'ru', { numeric: true, sensitivity: 'base' });
          }
          return dir === 'ascending' ? res : -res;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  };

  /* ── Графический движок (чистый SVG, без внешних библиотек) ── */
  function colorWithAlpha(hex, alpha) {
    var s = String(hex || '').replace('#', '');
    if (s.length === 3) s = s.split('').map(function (c) { return c + c; }).join('');
    var n = parseInt(s, 16);
    if (isNaN(n)) return 'rgba(79,70,229,' + alpha + ')';
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  function svgEl(tag, attrs) {
    var el = doc.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  function numPath(values, w, h, pad) {
    var v = values.map(function (x) { return Number(x) || 0; });
    var min = Math.min.apply(null, v.concat([0]));
    var max = Math.max.apply(null, v.concat([1]));
    if (max === min) max = min + 1;
    var step = v.length > 1 ? (w - pad * 2) / (v.length - 1) : 0;
    return v.map(function (val, i) {
      var x = pad + step * i;
      var y = h - pad - ((val - min) / (max - min)) * (h - pad * 2);
      return [x, y];
    });
  }

  function axisLabels(values) {
    var v = values.map(function (x) { return Number(x) || 0; });
    var max = Math.max.apply(null, v.concat([1]));
    return { max: max, mid: Math.round(max / 2) };
  }

  /* Спарклайн: линия + заливка + точка на последнем значении */
  window.HakumoChart = {
    sparkline: function (el, values, opts) {
      opts = opts || {};
      if (!el) return;
      var data = (values || []).map(function (x) { return Number(x) || 0; });
      var w = 640, h = Number(opts.height) || 64, pad = Number(opts.pad) || 12;
      var color = opts.color || cssVar('--ac', '#4f46e5');
      if (!data.length) { el.innerHTML = '<span class="muted" style="font-size:11px">нет данных</span>'; return; }
      var gutter = opts.labels ? 40 : 10;
      var pts = numPath(data, w, h, 10);
      // плавная кривая (катмулл-ром → безье)
      var line = 'M' + pts[0][0].toFixed(1) + ' ' + pts[0][1].toFixed(1);
      for (var i = 0; i < pts.length - 1; i++) {
        var p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
        var c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
        var c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
        line += ' C' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
      }
      var baseY = h - 10;
      var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + baseY + ' L' + pts[0][0].toFixed(1) + ' ' + baseY + ' Z';
      var svg = svgEl('svg', { viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none', style: 'width:100%;height:' + h + 'px' });
      window.__chartUid = (window.__chartUid || 0) + 1;
      var uid = 's' + window.__chartUid;
      var defs = svgEl('defs', {});
      var lg = svgEl('linearGradient', { id: uid + '-fill', x1: '0', y1: '0', x2: '0', y2: '1' });
      lg.appendChild(svgEl('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': '0.32' }));
      lg.appendChild(svgEl('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': '0.02' }));
      defs.appendChild(lg);
      var flt = svgEl('filter', { id: uid + '-glow', x: '-30%', y: '-30%', width: '160%', height: '160%' });
      flt.appendChild(svgEl('feDropShadow', { dx: '0', dy: '2', stdDeviation: '2.4', 'flood-color': color, 'flood-opacity': '0.38' }));
      defs.appendChild(flt);
      svg.appendChild(defs);
      // горизонтальная сетка (3 линии) и подписи значений
      if (opts.grid) {
        var gridColor = cssVar('--line', 'rgba(127,135,159,0.18)');
        var minV = Math.min.apply(null, data.concat([0]));
        var maxV = Math.max.apply(null, data.concat([1]));
        if (maxV === minV) maxV = minV + 1;
        for (var g = 0; g <= 2; g++) {
          var gy = 10 + (baseY - 10) * (g / 2);
          var gv = maxV - (maxV - minV) * (g / 2);
          svg.appendChild(svgEl('line', { x1: 10, y1: gy, x2: w - 10, y2: gy, stroke: gridColor, 'stroke-width': '1', 'class': 'grid-line' }));
          if (opts.labels) {
            var txt = svgEl('text', { x: 4, y: gy + 3, 'font-size': '9', fill: cssVar('--text-3', '#7f879f'), 'class': 'grid-label' });
            txt.textContent = String(Math.round(gv * 10) / 10) + (opts.unit || '');
            svg.appendChild(txt);
          }
        }
        if (opts.labels) {
          // отступ слева под подписи — сдвигаем сам svg, а не геометрию
          svg.style.marginLeft = gutter - 10 + 'px';
          svg.style.width = 'calc(100% - ' + (gutter - 10) + 'px)';
        }
      }
      svg.appendChild(svgEl('path', { d: area, fill: 'url(#' + uid + '-fill)', 'class': 'area-fill' }));
      svg.appendChild(svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': '2.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'class': 'line-path', filter: 'url(#' + uid + '-glow)' }));
      var last = pts[pts.length - 1];
      var surf = cssVar('--surface', '#ffffff');
      svg.appendChild(svgEl('circle', { cx: last[0], cy: last[1], r: 4.6, fill: color, stroke: surf, 'stroke-width': '1.8', 'class': 'last-dot' }));
      if (opts.title) svg.appendChild(svgEl('title', {}));
      if (opts.title) svg.querySelector('title').textContent = opts.title;
      el.innerHTML = '';
      el.appendChild(svg);
      if (opts.axis) {
        var ax = doc.createElement('div');
        ax.className = 'chart-axis';
        var lab = axisLabels(data);
        ax.innerHTML = '<span>' + (opts.axisMin || '0') + '</span><span>' + lab.mid + '</span><span>' + lab.max + '</span>';
        el.appendChild(ax);
      }
    },

    /* Площадной график с сеткой (для крупных блоков) */
    area: function (el, values, opts) {
      opts = opts || {};
      if (!el) return;
      var data = (values || []).map(function (x) { return Number(x) || 0; });
      var w = 640, h = Number(opts.height) || 180, pad = 14;
      var color = opts.color || cssVar('--ac', '#4f46e5');
      if (!data.length) { el.innerHTML = '<div class="empty" style="padding:20px"><i class="fas fa-chart-area"></i><span>нет данных</span></div>'; return; }
      var pts = numPath(data, w, h, pad + 8);
      var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
      var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (h - pad - 8) + ' L' + pts[0][0].toFixed(1) + ' ' + (h - pad - 8) + ' Z';
      var svg = svgEl('svg', { viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none', style: 'width:100%;height:' + h + 'px' });
      window.__chartUid = (window.__chartUid || 0) + 1;
      var uid = 'g' + window.__chartUid;
      var defs = svgEl('defs', {});
      var lg = svgEl('linearGradient', { id: uid + '-fill', x1: '0', y1: '0', x2: '0', y2: '1' });
      lg.appendChild(svgEl('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': '0.36' }));
      lg.appendChild(svgEl('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': '0.02' }));
      defs.appendChild(lg);
      var flt = svgEl('filter', { id: uid + '-glow', x: '-30%', y: '-30%', width: '160%', height: '160%' });
      flt.appendChild(svgEl('feDropShadow', { dx: '0', dy: '3', stdDeviation: '3', 'flood-color': color, 'flood-opacity': '0.4' }));
      defs.appendChild(flt);
      svg.appendChild(defs);
      [0.25, 0.5, 0.75].forEach(function (f) {
        var y = pad + (h - pad * 2) * f;
        svg.appendChild(svgEl('line', { x1: pad, y1: y.toFixed(1), x2: w - pad, y2: y.toFixed(1), 'class': 'grid-line' }));
      });
      svg.appendChild(svgEl('path', { d: area, fill: 'url(#' + uid + '-fill)', 'class': 'area-fill' }));
      var linePath = svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': '2.5', 'class': 'line-path', filter: 'url(#' + uid + '-glow)' });
      svg.appendChild(linePath);
      var surf = cssVar('--surface', '#ffffff');
      pts.forEach(function (p, i) {
        var dot = svgEl('circle', { cx: p[0], cy: p[1], r: i === pts.length - 1 ? 4.5 : 3.2, fill: color, stroke: surf, 'stroke-width': '1.6', opacity: i === pts.length - 1 ? 1 : 0.8 });
        if (opts.labels && opts.labels[i] != null) {
          var t = svgEl('title', {});
          t.textContent = opts.labels[i] + ': ' + data[i];
          dot.appendChild(t);
        }
        svg.appendChild(dot);
      });
      el.innerHTML = '';
      el.appendChild(svg);
      if (opts.tooltip !== false && typeof window.attachChartTooltip === 'function') {
        window.attachChartTooltip(el, data, { labels: opts.labels, color: color, height: h });
      }
      // Рисование линии слева направо
      if (!reducedMotion()) {
        try {
          var len = linePath.getTotalLength();
          linePath.style.strokeDasharray = len;
          linePath.style.strokeDashoffset = len;
          linePath.style.transition = 'stroke-dashoffset 0.9s cubic-bezier(0.25, 0.6, 0.3, 1)';
          requestAnimationFrame(function () {
            requestAnimationFrame(function () { linePath.style.strokeDashoffset = 0; });
          });
        } catch (e) { /* SVG-анимация опциональна */ }
      }
      if (opts.labels && opts.labels.length) {
        var ax = doc.createElement('div');
        ax.className = 'chart-axis';
        var lab = axisLabels(data);
        ax.innerHTML = '<span>' + esc0(opts.labels[0]) + '</span><span>' + lab.mid + '</span><span>' + esc0(opts.labels[opts.labels.length - 1]) + '</span>';
        el.appendChild(ax);
      }
    },

    /* Горизонтальные бары-распределения */
    vbars: function (el, items, opts) {
      opts = opts || {};
      if (!el) return;
      var list = (items || []).filter(function (x) { return x && x.label != null; });
      if (!list.length) { el.innerHTML = '<span class="muted">нет данных</span>'; return; }
      var max = Math.max.apply(null, list.map(function (x) { return Number(x.value) || 0; }).concat([1]));
      var color = opts.color || cssVar('--ac', '#4f46e5');
      el.innerHTML = list.slice(0, opts.limit || 8).map(function (x) {
        var v = Number(x.value) || 0;
        var pct = Math.round((v / max) * 100);
        return '<div class="vbar-row" title="' + esc0(x.label) + ': ' + v + '">' +
          '<span class="vbar-label">' + esc0(x.label) + '</span>' +
          '<span class="vbar-track"><span class="vbar-fill" style="width:' + pct + '%;' + (x.color ? 'background:' + x.color : '') + '"></span></span>' +
          '<span class="vbar-val">' + v.toLocaleString('ru-RU') + '</span></div>';
      }).join('');
    }
  };

  function esc0(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* Авто-подключение сортировки на страницах с data-sortable */
  ready0(function () {
    doc.querySelectorAll('table[data-sortable]').forEach(function (t) { window.attachTableSort(t); });
  });

  function ready0(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
})();

// ============================================================
// HAKUMO PREMIUM KIT 2 — кольца, теплокарта, CSV, акценты
// ============================================================
(function () {
  'use strict';
  var doc = document;

  /* была скрытая ошибка: reducedMotion() определена в KIT 1, а здесь
     вызывалась без определения → ReferenceError при каждой отрисовке кольца */
  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function esc0(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function svgEl(tag, attrs) {
    var el = doc.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  /* ── Кольцевой график (доли мер) ─────────────────────── */
  window.HakumoRing = function (el, segments, opts) {
    opts = opts || {};
    if (!el) return;
    var list = (segments || []).filter(function (x) { return x && (Number(x.value) || 0) > 0; });
    if (!list.length) { el.innerHTML = '<span class="muted">нет данных</span>'; return; }
    var total = list.reduce(function (acc, x) { return acc + (Number(x.value) || 0); }, 0);
    var size = Number(opts.size) || 118;
    var stroke = Number(opts.stroke) || 13;
    var r = (size - stroke) / 2;
    var c = 2 * Math.PI * r;
    var svg = svgEl('svg', { viewBox: '0 0 ' + size + ' ' + size, style: 'width:' + size + 'px;height:' + size + 'px' });
    var track = svgEl('circle', {
      cx: size / 2, cy: size / 2, r: r, fill: 'none',
      stroke: getComputedStyle(doc.documentElement).getPropertyValue('--surface-3').trim() || '#eef0f3',
      'stroke-width': stroke
    });
    svg.appendChild(track);
    var off = 0;
    list.forEach(function (seg) {
      var v = Number(seg.value) || 0;
      var frac = v / total;
      var dash = frac * c - 3; // зазор между сегментами
      if (dash < 0) dash = 0;
      var circle = svgEl('circle', {
        cx: size / 2, cy: size / 2, r: r, fill: 'none',
        stroke: seg.color || '#4f46e5',
        'stroke-width': stroke,
        'stroke-dasharray': dash + ' ' + (c - dash),
        'stroke-dashoffset': -(off * c),
        'stroke-linecap': 'round',
        'data-anim': '1',
        'data-final': dash + ' ' + (c - dash)
      });
      var t = svgEl('title', {});
      t.textContent = seg.label + ': ' + v;
      circle.appendChild(t);
      svg.appendChild(circle);
      off += frac;
    });
    var wrap = doc.createElement('div');
    wrap.className = 'ring-wrap';
    var box = doc.createElement('div');
    box.className = 'ring-box';
    var center = doc.createElement('div');
    center.className = 'ring-center';
    center.innerHTML = '<div><b>' + total.toLocaleString('ru-RU') + '</b><small>' + esc0(opts.totalLabel || 'всего') + '</small></div>';
    box.appendChild(svg);
    box.appendChild(center);
    wrap.appendChild(box);
    if (opts.legend !== false) {
      var leg = doc.createElement('div');
      leg.className = 'ring-legend';
      list.slice(0, 7).forEach(function (seg) {
        var v = Number(seg.value) || 0;
        var pct = total ? Math.round((v / total) * 100) : 0;
        var li = doc.createElement('div');
        li.className = 'ring-li';
        li.innerHTML = '<span class="sw" style="background:' + esc0(seg.color || '#4f46e5') + '"></span>' +
          '<span class="nm">' + esc0(seg.label) + '</span>' +
          '<span class="vl">' + v.toLocaleString('ru-RU') + '</span>' +
          '<span class="pc">' + pct + '%</span>';
        leg.appendChild(li);
      });
      wrap.appendChild(leg);
    }
    el.innerHTML = '';
    el.appendChild(wrap);
    // сегменты кольца проявляются волной
    if (!reducedMotion()) {
      var segs = svg.querySelectorAll('circle[data-anim]');
      segs.forEach(function (c2, i) {
        var finalDash = c2.getAttribute('data-final');
        c2.setAttribute('stroke-dasharray', '0 ' + c);
        setTimeout(function () {
          c2.setAttribute('stroke-dasharray', finalDash);
        }, 80 + i * 90);
      });
    }
  };

  /* ── Тепловая карта (24 часа) ────────────────────────── */
  window.HakumoHeat = function (el, values, opts) {
    opts = opts || {};
    if (!el) return;
    var vals = (values || []).map(function (v) { return Number(v) || 0; });
    var max = Math.max.apply(null, vals.concat([1]));
    var grid = doc.createElement('div');
    grid.className = 'heat-grid';
    vals.forEach(function (v, i) {
      var cell = doc.createElement('div');
      var level = Math.max(0, Math.min(4, Math.round((v / max) * 4)));
      cell.className = 'heat-cell' + (level ? ' h' + level : '');
      if (opts.labels && opts.labels[i] != null) cell.title = opts.labels[i] + ': ' + v;
      grid.appendChild(cell);
    });
    el.innerHTML = '';
    el.appendChild(grid);
    if (opts.labels && opts.labels.length) {
      var ax = doc.createElement('div');
      ax.className = 'heat-axis';
      ax.innerHTML = '<span>' + esc0(opts.labels[0]) + '</span><span>' + esc0(opts.labels[Math.floor(opts.labels.length / 2)]) + '</span><span>' + esc0(opts.labels[opts.labels.length - 1]) + '</span>';
      el.appendChild(ax);
    }
  };

  /* ── Клиентский CSV-экспорт таблиц ───────────────────── */
  window.csvDownload = function (filename, rows) {
    try {
      var csv = rows.map(function (r) {
        return r.map(function (cell) {
          var v = String(cell == null ? '' : cell);
          if (/[;"\\n]/.test(v)) v = '"' + v.replace(/"/g, '""') + '"';
          return v;
        }).join(';');
      }).join('\\r\\n');
      var blob = new Blob(['\\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
      var a = doc.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      doc.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
      return true;
    } catch (e) { return false; }
  };

  /* ── Пресеты акцентов + попап ────────────────────────── */
  var ACCENTS = [
    { name: 'Индиго', hex: '#4f46e5' },
    { name: 'Фиолет', hex: '#7c3aed' },
    { name: 'Небо', hex: '#0284c7' },
    { name: 'Изумруд', hex: '#059669' },
    { name: 'Роза', hex: '#e11d48' },
    { name: 'Янтарь', hex: '#d97706' }
  ];
  window.accentPresets = ACCENTS;

  window.initAccentPicker = function (btn) {
    if (!btn || btn.dataset.accentReady) return;
    btn.dataset.accentReady = '1';
    var pop = doc.createElement('div');
    pop.className = 'accent-pop';
    pop.hidden = true;
    pop.innerHTML = '<div class="accent-pop-title">Акцент панели</div><div class="accent-grid"></div>';
    btn.parentNode.appendChild(pop);
    var grid = pop.querySelector('.accent-grid');
    ACCENTS.forEach(function (a) {
      var sw = doc.createElement('button');
      sw.type = 'button';
      sw.className = 'accent-swatch';
      sw.title = a.name;
      sw.style.background = 'linear-gradient(135deg, ' + a.hex + ', ' + a.hex + 'cc)';
      sw.innerHTML = '<i class="fas fa-check"></i>';
      sw.addEventListener('click', function () {
        if (typeof window.applyAccent === 'function') window.applyAccent(a.hex);
        paint();
      });
      grid.appendChild(sw);
    });
    function paint() {
      var cur = '';
      try { cur = localStorage.getItem('hakumo_accent') || '#4f46e5'; } catch (e) {}
      cur = String(cur).toLowerCase();
      Array.prototype.forEach.call(grid.children, function (sw, i) {
        sw.classList.toggle('active', ACCENTS[i].hex.toLowerCase() === cur);
      });
    }
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (window.closeTopOverlays) window.closeTopOverlays();
      pop.hidden = !pop.hidden;
      if (!pop.hidden) paint();
    });
    doc.addEventListener('click', function (e) {
      if (!pop.hidden && !pop.contains(e.target) && e.target !== btn) pop.hidden = true;
    });
    paint();
  };

  /* ── Таймер сессии в сайдбаре ────────────────────────── */
  function sessionTimer() {
    var el = doc.getElementById('sysSession');
    if (!el) return;
    var t0 = Date.now();
    var tick = function () {
      var s = Math.floor((Date.now() - t0) / 1000);
      var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      var p = function (v) { return String(v).padStart(2, '0'); };
      el.textContent = p(h) + ':' + p(m) + ':' + p(sec);
    };
    tick();
    setInterval(tick, 1000);
  }

  /* ── Глобальные горячие клавиши ──────────────────────── */
  function globalKeys() {
    doc.addEventListener('keydown', function (e) {
      // Alt+M — палитра команд
      if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'm' || e.key === 'M' || e.key === 'ь' || e.key === 'Ь')) {
        e.preventDefault();
        if (typeof window.uxPaletteOpen === 'function') window.uxPaletteOpen();
      }
      // Escape закрывает открытые дроверы/меню
      if (e.key === 'Escape') {
        if (window.closeTopOverlays) window.closeTopOverlays();
      }
    });
  }

  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  ready(function () {
    initAccentPicker(doc.getElementById('accentBtn'));
    sessionTimer();
    globalKeys();
  });
})();

// ============================================================
// HAKUMO PREMIUM KIT 3 — тултипы, tilt, ripple
// ============================================================
(function () {
  'use strict';
  var doc = document;

  function reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ── Тултип для площадных графиков ───────────────────────
     Вызывается из HakumoChart.area при opts.tooltip !== false. */
  window.attachChartTooltip = function (box, values, opts) {
    var svg = box.querySelector('svg');
    if (!svg || !values || !values.length || reducedMotion() && false) return;
    var w = 640, h = Number(opts.height) || 180, pad = 22;
    var step = values.length > 1 ? (w - pad * 2) / (values.length - 1) : 0;
    var min = Math.min.apply(null, values.concat([0]));
    var max = Math.max.apply(null, values.concat([1]));
    if (max === min) max = min + 1;

    var tip = doc.createElement('div');
    tip.className = 'chart-tooltip';
    tip.hidden = true;
    box.style.position = box.style.position || 'relative';
    box.appendChild(tip);

    var guide = doc.createElementNS('http://www.w3.org/2000/svg', 'line');
    guide.setAttribute('class', 'chart-guide');
    guide.setAttribute('y1', pad - 8);
    guide.setAttribute('y2', h - pad + 8);
    guide.setAttribute('opacity', '0');
    svg.appendChild(guide);

    var dot = doc.createElementNS('http://www.w3.org/2000/svg', 'circle');
    dot.setAttribute('r', 5);
    dot.setAttribute('opacity', '0');
    svg.appendChild(dot);

    var overlay = doc.createElementNS('http://www.w3.org/2000/svg', 'rect');
    overlay.setAttribute('x', pad - 4);
    overlay.setAttribute('y', 0);
    overlay.setAttribute('width', w - pad * 2 + 8);
    overlay.setAttribute('height', h);
    overlay.setAttribute('fill', 'transparent');
    svg.appendChild(overlay);

    function show(i) {
      var x = pad + step * i;
      var val = values[i];
      var y = h - pad - ((val - min) / (max - min)) * (h - pad * 2);
      guide.setAttribute('x1', x);
      guide.setAttribute('x2', x);
      guide.setAttribute('opacity', '0.5');
      dot.setAttribute('cx', x);
      dot.setAttribute('cy', y);
      dot.setAttribute('fill', opts.color || 'var(--ac)');
      dot.setAttribute('opacity', '1');
      tip.innerHTML = '<b>' + (opts.labels && opts.labels[i] != null ? String(opts.labels[i]) : '') + '</b><span>' + val + '</span>';
      tip.hidden = false;
      var bw = box.getBoundingClientRect().width;
      var ratio = bw / w;
      var lx = x * ratio;
      tip.style.left = Math.min(Math.max(0, lx - tip.offsetWidth / 2), bw - tip.offsetWidth - 4) + 'px';
      tip.style.top = Math.max(0, y * ratio - tip.offsetHeight - 10) + 'px';
    }
    function hide() {
      guide.setAttribute('opacity', '0');
      dot.setAttribute('opacity', '0');
      tip.hidden = true;
    }

    overlay.addEventListener('mousemove', function (e) {
      var rect = svg.getBoundingClientRect();
      var x = (e.clientX - rect.left) / rect.width * w;
      var i = Math.round((x - pad) / step);
      i = Math.max(0, Math.min(values.length - 1, i));
      show(i);
    });
    overlay.addEventListener('mouseleave', hide);
    box.addEventListener('mouseleave', hide);
  };
})();

// ============================================================
// HAKUMO PREMIUM KIT 4 — 3D-tilt и ripple
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Лёгкий 3D-tilt у карточек ─────────────────────────── */
  window.tiltCards = function (root, selector) {
    if (coarse || reduced) return;
    var els = (root || doc).querySelectorAll(selector || '.kpi, .stat-box, .cc-tile');
    Array.prototype.forEach.call(els, function (el) {
      if (el.dataset.tilt) return;
      el.dataset.tilt = '1';
      el.addEventListener('mousemove', function (e) {
        var r = el.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        el.style.transform = 'perspective(600px) rotateX(' + (-py * 5).toFixed(2) + 'deg) rotateY(' + (px * 5).toFixed(2) + 'deg) translateY(-2px)';
      });
      el.addEventListener('mouseleave', function () {
        el.style.transform = '';
      });
    });
  };

  /* ── Ripple-эффект кнопок ─────────────────────────────── */
  doc.addEventListener('pointerdown', function (e) {
    if (reduced) return;
    var target = e.target.closest ? e.target.closest('.btn, .cc-tile, .kbd-palette-item') : null;
    if (!target) return;
    var r = target.getBoundingClientRect();
    var span = doc.createElement('span');
    span.className = 'ripple';
    var size = Math.max(r.width, r.height) * 1.4;
    span.style.width = span.style.height = size + 'px';
    span.style.left = (e.clientX - r.left - size / 2) + 'px';
    span.style.top = (e.clientY - r.top - size / 2) + 'px';
    target.appendChild(span);
    setTimeout(function () { span.remove(); }, 650);
  });
})();

// ============================================================
// HAKUMO FX KIT — частицы, курсор-свечение, сплэш, вспышки,
// параллакс фона
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

  function accentRGB() {
    try {
      var v = getComputedStyle(doc.documentElement).getPropertyValue('--ac').trim() || '#4f46e5';
      v = v.replace('#', '');
      if (v.length === 3) v = v.split('').map(function (c) { return c + c; }).join('');
      var n = parseInt(v, 16);
      if (isNaN(n)) return { r: 79, g: 70, b: 229 };
      return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    } catch (e) { return { r: 79, g: 70, b: 229 }; }
  }

  /* ── 1. Созвездие частиц на фоне ───────────────────────── */
  function fxParticles() {
    var canvas = doc.getElementById('fx-particles');
    if (!canvas || reduced) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    var W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);
    function resize() {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);
    var N = W < 860 ? 22 : 40;
    var pts = [];
    window.__fxParticles = { pts: pts };
    for (var i = 0; i < N; i++) {
      pts.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.3 + 0.5
      });
    }
    var LINK = 110;
    var lastStep = 0;
    function step(now) {
      requestAnimationFrame(step);
      if (doc.hidden) return;
      if (now - lastStep < 34) return;
      lastStep = now;
      ctx.clearRect(0, 0, W, H);
      var c = accentRGB();
      var dark = doc.documentElement.getAttribute('data-theme') === 'dark';
      var alphaBase = dark ? 0.5 : 0.32;
      var i, j, p;
      for (i = 0; i < N; i++) {
        p = pts[i];
        p.x += p.vx; p.y += p.vy;
        if (p.x < -12) p.x = W + 12; else if (p.x > W + 12) p.x = -12;
        if (p.y < -12) p.y = H + 12; else if (p.y > H + 12) p.y = -12;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + c.r + ',' + c.g + ',' + c.b + ',' + alphaBase + ')';
        ctx.fill();
      }
      for (i = 0; i < N; i++) {
        for (j = i + 1; j < N; j++) {
          var dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
          var d2 = dx * dx + dy * dy;
          if (d2 < LINK * LINK) {
            var alpha = (1 - Math.sqrt(d2) / LINK) * 0.16 * (dark ? 1 : 0.8);
            ctx.strokeStyle = 'rgba(' + c.r + ',' + c.g + ',' + c.b + ',' + alpha + ')';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(pts[i].x, pts[i].y);
            ctx.lineTo(pts[j].x, pts[j].y);
            ctx.stroke();
          }
        }
      }
    }
    requestAnimationFrame(step);
  }

  /* ── 2. Мягкое свечение за курсором ────────────────────── */
  /* ── 3. Загрузочный сплэш ──────────────────────────────── */
  function fxBoot() {
    var el = doc.getElementById('bootSplash');
    if (!el) return;
    /* сплэш показываем один раз за сессию — на каждой навигации
       он давал вспышку и воспринимался как нестабильность */
    var seen = false;
    try { seen = !!window.sessionStorage.getItem('hakumo_splash_done'); } catch (e) {}
    if (reduced || seen) { el.remove(); return; }
    try { window.sessionStorage.setItem('hakumo_splash_done', '1'); } catch (e) {}
    setTimeout(function () {
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 620);
    }, 650);
  }

  /* ── 4. Вспышка обновлённых значений ───────────────────── */
  function fxValueFlash() {
    if (reduced) return;
    var last = {};
    var COOLDOWN = 3000;
    function flash(el) {
      var now = Date.now();
      if (now - (last[el] || 0) < COOLDOWN) return;
      last[el] = now;
      el.classList.remove('value-flash');
      void el.offsetWidth;
      el.classList.add('value-flash');
    }
    function scan(node) {
      if (!node || node.nodeType !== 1) return;
      if (node.matches && node.matches('.kpi-value, .stat-value, .stat-val')) {
        node.classList.add('fx-watch');
      }
      if (node.querySelectorAll) {
        node.querySelectorAll('.kpi-value, .stat-value, .stat-val').forEach(function (el) {
          el.classList.add('fx-watch');
        });
      }
    }
    var mo = new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === 'characterData' && m.target && m.target.parentElement) {
          var el = m.target.parentElement;
          if (el.classList && el.classList.contains('fx-watch')) flash(el);
        }
        m.addedNodes && Array.prototype.forEach.call(m.addedNodes, function (n) {
          if (n.nodeType === 1 && n.matches && n.matches('.kpi-value, .stat-value, .stat-val')) {
            n.classList.add('fx-watch');
            flash(n);
          }
          if (n.nodeType === 1 && n.querySelectorAll) {
            n.querySelectorAll('.kpi-value, .stat-value, .stat-val').forEach(function (el) {
              el.classList.add('fx-watch');
            });
          }
        });
      });
    });
    scan(doc.body);
    mo.observe(doc.body, { childList: true, subtree: true, characterData: true });
  }

  /* ── 5. Параллакс aurora: скролл + мышь ───────────────── */
  function fxParallax() {
    var bg = doc.querySelector('.bg-aurora');
    if (!bg) return;
    var scrollY = 0;
    if (!reduced) {
      window.addEventListener('scroll', function () {
        scrollY = window.scrollY * -0.04;
        paint();
      }, { passive: true });
    }
    var ticking = false;
    function paint() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        bg.style.transform = 'translate(0px, ' + scrollY + 'px)';
        ticking = false;
      });
    }
  }

  /* ── 5a. Частицы разбегаются от курсора ───────────────── */
  function fxParticlesRepulse() {
    if (reduced) return;
    var mx = -9999, my = -9999;
    doc.addEventListener('mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
    }, { passive: true });
    // встраиваемся в основной цикл частиц через лёгкий шейкер позиций
    var shaker = setInterval(function () {
      try {
        var data = window.__fxParticles;
        if (!data) return;
        var pts = data.pts;
        for (var i = 0; i < pts.length; i++) {
          var p = pts[i];
          var dx = p.x - mx, dy = p.y - my;
          var d2 = dx * dx + dy * dy;
          var R = 110;
          if (d2 < R * R && d2 > 0.01) {
            var d = Math.sqrt(d2);
            var push = (R - d) / R * 1.6;
            p.x += (dx / d) * push;
            p.y += (dy / d) * push;
          }
        }
      } catch (e) { clearInterval(shaker); }
    }, 30);
  }

  /* ── Старт ────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    fxBoot();
    /* фоновый canvas частиц отключён: постоянная перерисовка фона
       заставляла перекомпоновывать все стеклянные поверхности.
       Параллакс авроры тоже выключен: трансформация полноэкранного
       слоя на каждый скролл-кадр стоила композитинга. */
    fxValueFlash();
  });
})();

// ============================================================
// HAKUMO FX KIT 2 — календарь, свёрнутый сайдбар, фокус-режим,
// избранное, конфетти, тултипы, справка, тонировка разделов
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc0(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── 1. Календарь активности (GitHub-стиль, 90 дней) ────── */
  window.HakumoCalendar = function (el, counts, opts) {
    opts = opts || {};
    if (!el) return;
    var map = counts || {};
    var days = Number(opts.days) || 90;
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var start = new Date(today.getTime() - (days - 1) * 86400000);
    // выровнять на понедельник
    while (start.getDay() !== 1) start = new Date(start.getTime() - 86400000);

    var max = 1;
    Object.keys(map).forEach(function (k) { max = Math.max(max, Number(map[k]) || 0); });

    var cell = function (d) {
      var key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
      var v = Number(map[key]) || 0;
      var lvl = Math.max(0, Math.min(4, Math.round((v / max) * 4)));
      var label = String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0') + ' · ' + v + ' действий';
      return '<span class="cal-cell' + (lvl ? ' c' + lvl : '') + '" title="' + esc0(label) + '"></span>';
    };

    // недели: столбцы по 7 дней
    var weeks = [];
    var cur = new Date(start.getTime());
    while (cur <= today) {
      var week = [];
      for (var i = 0; i < 7; i++) {
        week.push(new Date(cur.getTime()));
        cur = new Date(cur.getTime() + 86400000);
      }
      weeks.push(week);
    }
    var bodyHtml = weeks.map(function (w) {
      return '<span class="cal-week">' + w.map(function (d) {
        return d <= today ? cell(d) : '<span class="cal-cell" style="visibility:hidden"></span>';
      }).join('') + '</span>';
    }).join('');

    // подписи месяцев над колонками
    var monthMarks = [];
    weeks.forEach(function (w, i) {
      var d = w[0];
      var keyM = d.getFullYear() + '-' + d.getMonth();
      if (!monthMarks.length || monthMarks[monthMarks.length - 1].key !== keyM) {
        monthMarks.push({ key: keyM, label: d.toLocaleDateString('ru-RU', { month: 'short' }).replace('.', ''), col: i });
      }
    });
    var total = Math.max(weeks.length, 1);
    var monthsHtml = '<div class="cal-months">' + monthMarks.map(function (m, idx) {
      var flex = (idx === monthMarks.length - 1)
        ? Math.max(m.col, total - m.col)
        : (monthMarks[idx + 1].col - m.col);
      return '<span style="flex:' + Math.max(flex, 1) + '">' + esc0(m.label) + '</span>';
    }).join('') + '</div>';

    el.innerHTML = monthsHtml +
      '<div class="cal-body">' + bodyHtml + '</div>' +
      '<div class="cal-legend">меньше <span class="cal-cell"></span><span class="cal-cell c1"></span><span class="cal-cell c2"></span><span class="cal-cell c3"></span><span class="cal-cell c4"></span> больше</div>';
  };

  /* ── 2. Подсветка совпадений (для таблиц с поиском) ─────── */
  window.hlEsc = function (raw, q) {
    var e = esc0(raw);
    if (!q) return e;
    var qe = esc0(q);
    if (!qe) return e;
    var re = new RegExp('(' + qe.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return e.replace(re, '<span class="hl">$1</span>');
  };

  /* ── 3. Конфетти ───────────────────────────────────────── */
  window.celebrate = function () {
    if (reduced) return;
    var colors = ['#4f46e5', '#7c3aed', '#0284c7', '#059669', '#e11d48', '#d97706', '#16a34a', '#ec4899'];
    var host = doc.createElement('div');
    host.className = 'confetti-host';
    doc.body.appendChild(host);
    var cx = window.innerWidth / 2;
    var n = 42;
    for (var i = 0; i < n; i++) {
      var piece = doc.createElement('span');
      piece.className = 'confetti-piece';
      piece.style.left = cx + 'px';
      piece.style.background = colors[i % colors.length];
      var angle = (Math.random() * Math.PI) - Math.PI;      // вверх веером
      var power = 260 + Math.random() * 320;
      var dx = Math.cos(angle) * power;
      var dy = -Math.abs(Math.sin(angle)) * power - 120 - Math.random() * 200;
      piece.style.setProperty('--dx', dx + 'px');
      piece.style.setProperty('--dy', dy + 'px');
      piece.style.setProperty('--rot', (Math.random() * 900 - 450) + 'deg');
      piece.style.setProperty('--dur', (1.2 + Math.random() * 0.9) + 's');
      host.appendChild(piece);
    }
    setTimeout(function () { host.remove(); }, 2400);
  };

  /* ── 4. Тултипы data-tip ───────────────────────────────── */
  function tipInit() {
    var tip = doc.createElement('div');
    tip.className = 'ui-tip';
    doc.body.appendChild(tip);
    var cur = null;
    function show(el) {
      tip.textContent = el.getAttribute('data-tip') || el.getAttribute('title') || '';
      tip.classList.add('show');
    }
    function move(e) {
      tip.style.left = (e.clientX + 14) + 'px';
      tip.style.top = (e.clientY + 16) + 'px';
    }
    doc.addEventListener('mouseover', function (e) {
      var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
      if (el && el !== cur) {
        cur = el;
        show(el);
        move(e);
      } else if (!el) {
        tip.classList.remove('show');
        cur = null;
      }
    });
    doc.addEventListener('mousemove', function (e) {
      if (cur) move(e);
    });
    doc.addEventListener('mouseout', function (e) {
      var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!el || el === cur) { tip.classList.remove('show'); cur = null; }
    });
  }

  /* ── 5. Свёрнутый сайдбар ──────────────────────────────── */
  function sidebarCollapseInit() {
    var btn = doc.getElementById('sidebarCollapseBtn');
    var sidebar = doc.getElementById('sidebar');
    if (!btn || !sidebar) return;
    try {
      if (localStorage.getItem('hakumo_sidebar') === 'collapsed') sidebar.classList.add('collapsed');
    } catch (e) {}
    btn.addEventListener('click', function () {
      var collapsed = sidebar.classList.toggle('collapsed');
      try { localStorage.setItem('hakumo_sidebar', collapsed ? 'collapsed' : 'full'); } catch (e) {}
    });
  }

  /* ── 6. Фокус-режим ────────────────────────────────────── */
  function focusInit() {
    var btn = doc.getElementById('focusBtn');
    if (btn) {
      btn.addEventListener('click', function () {
        var on = doc.body.classList.toggle('zen');
        window.showToast(on ? 'Фокус-режим: Esc — вернуться' : 'Фокус-режим выключен', true);
      });
    }
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && doc.body.classList.contains('zen')) {
        doc.body.classList.remove('zen');
      }
      // Shift+F — фокус-режим
      if (e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'F' || e.key === 'f' || e.key === 'а' || e.key === 'А')) {
        var t = e.target;
        var tag = t && t.tagName ? t.tagName.toLowerCase() : '';
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
        e.preventDefault();
        doc.body.classList.toggle('zen');
      }
    });
  }

  /* ── 7. Избранное ──────────────────────────────────────── */
  function favsInit() {
    var nav = doc.getElementById('sidebarNav');
    if (!nav) return;
    var container = doc.getElementById('navFavs');
    function loadFavs() {
      try { return JSON.parse(localStorage.getItem('hakumo_favs') || '[]'); }
      catch (e) { return []; }
    }
    function saveFavs(list) {
      try { localStorage.setItem('hakumo_favs', JSON.stringify(list)); } catch (e) {}
    }
    function star(path) {
      var list = loadFavs();
      var idx = list.indexOf(path);
      if (idx === -1) list.push(path); else list.splice(idx, 1);
      saveFavs(list);
      renderFavs();
      paintStars();
    }
    function renderFavs() {
      if (!container) return;
      var list = loadFavs();
      var favs = [];
      var all = doc.getElementById('palette-data');
      if (all) {
        try {
          JSON.parse(all.textContent || '[]').forEach(function (grp) {
            grp.pages.forEach(function (p) {
              if (list.indexOf(p.path) !== -1) favs.push(p);
            });
          });
        } catch (e) {}
      }
      if (!favs.length) { container.hidden = true; return; }
      container.hidden = false;
      container.innerHTML = '<div class="nav-favs-title"><i class="fas fa-star"></i> Избранное</div>' +
        '<div class="nav-favs-links">' + favs.map(function (p) {
          var active = window.location.pathname === p.path ? ' active' : '';
          return '<a href="' + esc0(p.path) + '" class="nav-link' + active + '" draggable="true"><i class="fas ' + esc0(p.icon) + '"></i> <span>' + esc0(p.label) + '</span>' +
            '<button type="button" class="nav-star on" data-fav="' + esc0(p.path) + '" aria-label="Убрать из избранного"><i class="fas fa-star"></i></button></a>';
        }).join('') + '</div>';
    }
    function paintStars() {
      var list = loadFavs();
      nav.querySelectorAll('.nav-link').forEach(function (link) {
        var path = link.getAttribute('href') || '';
        if (!path || path.charAt(0) !== '/') return;
        if (link.querySelector('.nav-star')) return;
        if (link.closest('.nav-favs-links')) return;
        /* локальная переменная называлась star и перекрывала функцию star()
           → клик по звезде давал «star is not a function» на всех страницах */
        var starBtn = doc.createElement('button');
        starBtn.type = 'button';
        starBtn.className = 'nav-star' + (list.indexOf(path) !== -1 ? ' on' : '');
        starBtn.setAttribute('aria-label', 'В избранное');
        starBtn.innerHTML = '<i class="fas fa-star"></i>';
        starBtn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          star(path);
        });
        link.appendChild(starBtn);
      });
    }
    if (container) container.addEventListener('click', function (e) {
      var b = e.target.closest('[data-fav]');
      if (b) { e.preventDefault(); star(b.dataset.fav); }
    });
    renderFavs();
    paintStars();
    /* хуки для FX-слоя 9 (drag-сортировка избранного) */
    window.__loadFavs = loadFavs;
    window.__renderFavs = renderFavs;
  }

  /* ── 8. Справка по горячим клавишам ────────────────────── */
  window.openHelp = function () {
    var existing = doc.getElementById('hkModal');
    if (existing) { existing.style.display = 'flex'; return; }
    var overlay = doc.createElement('div');
    overlay.id = 'hkModal';
    overlay.className = 'modal-overlay';
    overlay.style.display = 'flex';
    var rows = [
      ['Ctrl + K', 'Палитра команд и поиск'],
      ['Alt + M', 'Палитра команд'],
      ['?', 'Эта справка'],
      ['Shift + F', 'Фокус-режим'],
      ['Ctrl + S', 'Сохранить форму'],
      ['/', 'Фокус на поиск списка'],
      ['Esc', 'Закрыть окна и режимы']
    ];
    overlay.innerHTML =
      '<div class="modal-box" style="max-width:460px">' +
      '  <div class="modal-head">' +
      '    <div><h3><i class="fas fa-keyboard"></i> Горячие клавиши</h3><div class="sub">Всё управление панелью с клавиатуры.</div></div>' +
      '    <button type="button" class="close" aria-label="Закрыть"><i class="fas fa-xmark"></i></button>' +
      '  </div>' +
      '  <div class="modal-body">' +
      '    <div class="hk-grid">' + rows.map(function (r) {
        return '<span class="k">' + esc0(r[1]) + '</span><span class="kbd-hint">' + esc0(r[0]) + '</span>';
      }).join('') + '</div>' +
      '  </div>' +
      '  <div class="modal-actions"><button type="button" class="btn btn-primary" id="hkClose"><i class="fas fa-check"></i> Понятно</button></div>' +
      '</div>';
    doc.body.appendChild(overlay);
    function close() { overlay.remove(); }
    overlay.querySelector('.close').addEventListener('click', close);
    overlay.querySelector('#hkClose').addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    doc.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close(); doc.removeEventListener('keydown', esc); }
    });
  };

  /* ── 9. Тонировка фона по разделу ──────────────────────── */
  function sectionTint() {
    try {
      var node = doc.getElementById('palette-data');
      if (!node) return;
      var groups = JSON.parse(node.textContent || '[]');
      var path = window.location.pathname;
      for (var i = 0; i < groups.length; i++) {
        for (var j = 0; j < groups[i].pages.length; j++) {
          if (groups[i].pages[j].path === path) {
            doc.body.dataset.section = groups[i].key;
            return;
          }
        }
      }
    } catch (e) { /* опционально */ }
  }

  /* ── 10. Ступенчатый заголовок ─────────────────────────── */
  function titleStagger() {
    if (reduced) return;
    doc.querySelectorAll('.page-head h1, .navbar h1').forEach(function (h) {
      if (h.querySelector('i') || h.querySelector('span') || h.dataset.staggered) return;
      var words = (h.textContent || '').trim().split(/\s+/);
      if (words.length < 2 || words.length > 8) return;
      h.dataset.staggered = '1';
      h.classList.add('title-stagger');
      h.innerHTML = words.map(function (w, i) {
        return '<span style="animation-delay:' + (i * 55) + 'ms">' + esc0(w) + '</span>';
      }).join(' ');
    });
  }

  /* ── 11. Справка по «?» ────────────────────────────────── */
  doc.addEventListener('keydown', function (e) {
    if (e.key !== '?' && e.key !== '/') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    var tag = t && t.tagName ? t.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
    if (e.key === '?') {
      e.preventDefault();
      window.openHelp();
    }
  });

  /* ── Старт ────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    sidebarCollapseInit();
    focusInit();
    favsInit();
    tipInit();
    sectionTint();
    titleStagger();
    var helpLink = doc.getElementById('helpLink');
    if (helpLink) {
      helpLink.addEventListener('click', function (e) {
        e.preventDefault();
        window.openHelp();
      });
    }
  });
})();

// ============================================================
// HAKUMO KIT 3 — пауза live-обновлений, плотность, штамп
// ============================================================
(function () {
  'use strict';

  /* Кнопка паузы live-обновлений (работает с setLiveRefresh) */
  window.livePauseButton = function (btn) {
    if (!btn || btn.dataset.lpReady) return;
    btn.dataset.lpReady = '1';
    function paint() {
      var paused = !!window.__modLivePaused;
      btn.innerHTML = paused
        ? '<i class="fas fa-play"></i> Продолжить live'
        : '<i class="fas fa-pause"></i> Пауза live';
      btn.classList.toggle('btn-primary', paused);
      btn.title = paused ? 'Возобновить автообновление' : 'Приостановить автообновление';
    }
    btn.addEventListener('click', function () {
      window.__modLivePaused = !window.__modLivePaused;
      paint();
      if (typeof window.showToast === 'function') {
        window.showToast(window.__modLivePaused ? 'Live на паузе' : 'Live продолжается', true);
      }
      if (!window.__modLivePaused) {
        try { document.dispatchEvent(new CustomEvent('hakumo:live')); } catch (e) {}
      }
    });
    paint();
  };

  /* Кнопка плотности таблиц */
  window.densityButton = function (btn) {
    if (!btn || btn.dataset.denReady) return;
    btn.dataset.denReady = '1';
    function paint() {
      var dense = document.body.classList.contains('dense');
      btn.innerHTML = dense ? '<i class="fas fa-arrows-to-dot"></i> Стандартно' : '<i class="fas fa-compress"></i> Компактно';
      btn.title = dense ? 'Вернуть стандартную плотность' : 'Включить компактный режим таблиц';
    }
    btn.addEventListener('click', function () {
      document.body.classList.toggle('dense');
      var dense = document.body.classList.contains('dense');
      try { localStorage.setItem('hakumo_dense', dense ? '1' : '0'); } catch (e) {}
      /* плотность следует за учёткой — сохраняем на сервере */
      try {
        fetch('/api/ux/prefs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ compact: dense })
        }).catch(function () {});
      } catch (e) {}
      paint();
    });
    try {
      if (localStorage.getItem('hakumo_dense') === '1') document.body.classList.add('dense');
    } catch (e) {}
    paint();
  };
})();

// ============================================================
// HAKUMO KIT 4 — иконка раздела в заголовке, тень шапки,
// ripple на KPI
// ============================================================
(function () {
  'use strict';
  var doc = document;

  /* ── 1. Авто-иконка текущего раздела в заголовке страницы ── */
  function sectionIcon() {
    try {
      var node = doc.getElementById('palette-data');
      var head = doc.querySelector('.page-head');
      if (!node || !head) return;
      if (head.querySelector('.page-head-icon')) return;
      var groups = JSON.parse(node.textContent || '[]');
      var path = window.location.pathname;
      for (var i = 0; i < groups.length; i++) {
        for (var j = 0; j < groups[i].pages.length; j++) {
          if (groups[i].pages[j].path === path) {
            var icon = groups[i].pages[j].icon || groups[i].icon || 'fa-file';
            var chip = doc.createElement('div');
            chip.className = 'page-head-icon';
            chip.innerHTML = '<i class="fas ' + icon.replace(/[^a-z0-9-]/gi, '') + '"></i>';
            head.insertBefore(chip, head.firstChild);
            return;
          }
        }
      }
    } catch (e) { /* опционально */ }
  }

  /* ── 2. Тень шапки при прокрутке ────────────────────────── */
  function topbarShadow() {
    var bar = doc.querySelector('.topbar');
    if (!bar) return;
    var on = false;
    var paint = function () {
      var scrolled = window.scrollY > 8;
      if (scrolled !== on) {
        on = scrolled;
        bar.classList.toggle('scrolled', on);
      }
    };
    window.addEventListener('scroll', paint, { passive: true });
    paint();
  }

  /* ── 3. Ripple на KPI ───────────────────────────────────── */
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  doc.addEventListener('pointerdown', function (e) {
    if (reduced) return;
    var target = e.target && e.target.closest ? e.target.closest('.kpi, .stat-box') : null;
    if (!target) return;
    var r = target.getBoundingClientRect();
    var span = doc.createElement('span');
    span.className = 'ripple';
    var size = Math.max(r.width, r.height) * 1.4;
    span.style.width = span.style.height = size + 'px';
    span.style.left = (e.clientX - r.left - size / 2) + 'px';
    span.style.top = (e.clientY - r.top - size / 2) + 'px';
    target.appendChild(span);
    setTimeout(function () { span.remove(); }, 650);
  });

  /* ── 4. Анимация прогресса на KPI при наведении (бар) ───── */
  doc.addEventListener('mouseover', function (e) {
    var bar = e.target && e.target.closest ? e.target.closest('.kpi') : null;
    if (!bar) return;
    var fill = bar.querySelector('.modern-progress > span, .modern-progress-bar > span');
    if (fill) fill.style.filter = 'brightness(1.15)';
  });
  doc.addEventListener('mouseout', function (e) {
    var bar = e.target && e.target.closest ? e.target.closest('.kpi') : null;
    if (!bar) return;
    var fill = bar.querySelector('.modern-progress > span, .modern-progress-bar > span');
    if (fill) fill.style.filter = '';
  });

  /* ── Старт ─────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    sectionIcon();
    topbarShadow();
  });
})();

// ============================================================
// HAKUMO FX KIT 5 — FAB, тур по панели, звук уведомлений,
// перестановка виджетов
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc0(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── 1. Плавающее меню быстрых действий (FAB) ──────────── */
  function fabInit() {
    var host = doc.getElementById('fabHost');
    if (!host) return;

    var backdrop = doc.createElement('div');
    backdrop.className = 'fab backdrop';
    doc.body.appendChild(backdrop);

    var wrap = doc.createElement('div');
    wrap.className = 'fab';
    var items = [
      { icon: 'fa-clock', label: 'Новая мера', href: '/temp-moderation', tone: 'tone-info' },
      { icon: 'fa-triangle-exclamation', label: 'Выдать варн', href: '/warnings', tone: 'tone-warn' },
      { icon: 'fa-table-columns', label: 'Задача команде', href: '/team-board', tone: '' },
      { icon: 'fa-house-lock', label: 'Локдаун', href: '/lockdown', tone: 'tone-err' },
      { icon: 'fa-user-secret', label: 'Скан профиля', href: '/antifake', tone: '' },
      { icon: 'fa-palette', label: 'Студия темы', href: '/theme-studio', tone: 'tone-ok' }
    ];
    wrap.innerHTML = items.map(function (it) {
      return '<a class="fab-item ' + it.tone + '" href="' + esc0(it.href) + '">' +
        '<span class="ico"><i class="fas ' + it.icon + '"></i></span>' + esc0(it.label) + '</a>';
    }).join('') +
    '<button type="button" class="fab-main" aria-label="Быстрые действия"><i class="fas fa-plus"></i></button>';
    host.appendChild(wrap);

    var mainBtn = wrap.querySelector('.fab-main');
    function close() {
      wrap.classList.remove('open');
      backdrop.classList.remove('show');
    }
    mainBtn.addEventListener('click', function () {
      var open = wrap.classList.toggle('open');
      backdrop.classList.toggle('show', open);
    });
    backdrop.addEventListener('click', close);
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
      if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'n' || e.key === 'N' || e.key === 'т' || e.key === 'Т')) {
        e.preventDefault();
        mainBtn.click();
      }
    });
  }

  /* ── 2. Интерактивный тур по панели ────────────────────── */
  var TOUR_STEPS = [
    { sel: '.sidebar', title: 'Меню панели', icon: 'fa-bars',
      text: 'Все разделы бота в одном меню. Группы сворачиваются, у пунктов есть звёздочка для избранного.' },
    { sel: '#globalSearchBtn', title: 'Поиск — Ctrl+K', icon: 'fa-magnifying-glass',
      text: 'Глобальная палитра: страницы, участники, транскрипты и действия. Начните печатать — остальное она сделает сама.' },
    { sel: '.kpi-row', title: 'Живые метрики', icon: 'fa-gauge-high',
      text: 'Карточки KPI обновляются сами. Цифры вспыхивают при изменении, а на карточку можно навести — она подсветится.' },
    { sel: '#notifBtn', title: 'Уведомления', icon: 'fa-bell',
      text: 'Системные и личные уведомления в одном колокольчике — с табами и отметкой «прочитано».' },
    { sel: '#accentBtn', title: 'Свой стиль', icon: 'fa-droplet',
      text: 'Акцент, тема, скругления и масштаб — в студии темы. Панель выглядит так, как хочется вам.' }
  ];

  function tourStart() {
    if (reduced) {
      window.showToast('Тур недоступен в режиме reduced motion', false);
      return;
    }
    var mask = doc.createElement('div');
    mask.className = 'tour-mask';
    doc.body.appendChild(mask);

    var card = doc.createElement('div');
    card.className = 'tour-card';
    doc.body.appendChild(card);

    var step = 0;
    var target = null;

    function highlight(el) {
      if (target) target.classList.remove('tour-target');
      target = el || null;
      if (target) {
        target.classList.add('tour-target');
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }

    function placeCard() {
      var r;
      if (target) {
        r = target.getBoundingClientRect();
      } else {
        r = { left: window.innerWidth / 2 - 160, top: window.innerHeight / 2 - 100, width: 320, height: 200 };
      }
      var left = r.left;
      var top = r.top + r.height + 14;
      // не вылезаем за экран
      if (top + 260 > window.innerHeight) top = Math.max(14, r.top - 280);
      if (left + 320 > window.innerWidth) left = window.innerWidth - 336;
      left = Math.max(14, left);
      card.style.left = left + 'px';
      card.style.top = top + 'px';
    }

    function paint() {
      var st = TOUR_STEPS[step];
      var el = st.sel ? doc.querySelector(st.sel) : null;
      highlight(el);
      card.innerHTML =
        '<div class="step-dots">' + TOUR_STEPS.map(function (s, i) {
          return '<i class="' + (i === step ? 'on' : '') + '"></i>';
        }).join('') + '</div>' +
        '<h3><i class="fas ' + esc0(st.icon) + '"></i> ' + esc0(st.title) + '</h3>' +
        '<p>' + esc0(st.text) + '</p>' +
        '<div class="row">' +
          '<button type="button" class="btn btn-ghost skip" id="tourSkip">Пропустить</button>' +
          '<span class="spacer"></span>' +
          (step > 0 ? '<button type="button" class="btn" id="tourPrev"><i class="fas fa-arrow-left"></i> Назад</button>' : '') +
          (step < TOUR_STEPS.length - 1
            ? '<button type="button" class="btn btn-primary" id="tourNext">Далее <i class="fas fa-arrow-right"></i></button>'
            : '<button type="button" class="btn btn-primary" id="tourNext"><i class="fas fa-check"></i> Готово</button>') +
        '</div>';
      setTimeout(placeCard, 60);

      var skip = card.querySelector('#tourSkip');
      var prev = card.querySelector('#tourPrev');
      var next = card.querySelector('#tourNext');
      skip.addEventListener('click', finish);
      if (prev) prev.addEventListener('click', function () { step = Math.max(0, step - 1); paint(); });
      next.addEventListener('click', function () {
        if (step < TOUR_STEPS.length - 1) { step++; paint(); }
        else finish();
      });
    }

    function finish() {
      try { localStorage.setItem('hakumo_tour', 'done'); } catch (e) {}
      if (target) target.classList.remove('tour-target');
      card.remove();
      mask.remove();
      window.showToast('Тур завершён — теперь панель ваша', true);
    }

    paint();
  }
  window.tourStart = tourStart;

  /* ── 3. Звук уведомлений (WebAudio, отключаемый) ───────── */
  var audioCtx = null;
  function ding() {
    try {
      if (localStorage.getItem('hakumo_sound') === 'off') return;
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      var t = audioCtx.currentTime;
      [0, 0.12].forEach(function (offset, i) {
        var o = audioCtx.createOscillator();
        var g = audioCtx.createGain();
        o.type = 'sine';
        o.frequency.value = i === 0 ? 880 : 1174.66;
        g.gain.setValueAtTime(0.0001, t + offset);
        g.gain.exponentialRampToValueAtTime(0.08, t + offset + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + offset + 0.35);
        o.connect(g);
        g.connect(audioCtx.destination);
        o.start(t + offset);
        o.stop(t + offset + 0.4);
      });
    } catch (e) { /* звук опционален */ }
  }
  window.notifyDing = ding;

  /* ── 4. Перестановка виджетов главной ──────────────────── */
  function widgetOrderApply() {
    var main = doc.querySelector('.main-content');
    var els = doc.querySelectorAll('[data-widget]');
    if (!main || !els.length) return;
    var order = [];
    var stored = false;
    try {
      order = JSON.parse(localStorage.getItem('cc_widgets_order_v2') || '[]');
      stored = Array.isArray(order) && order.length > 0;
    } catch (e) { order = []; stored = false; }
    if (!Array.isArray(order)) order = [];
    if (!stored) {
      /* порядка нет — натуральный DOM-порядок, никаких order-сдвигов */
      main.classList.remove('cc-orderable');
      els.forEach(function (el) { el.style.order = ''; });
      return;
    }
    /* нормализация: только существующие виджеты, недостающие — в DOM-порядке.
       Иначе неполный список уводил блоки на 100+ и разбрасывал вёрстку. */
    var keys = [];
    els.forEach(function (el) { keys.push(el.dataset.widget); });
    var seen = {};
    var clean = [];
    order.forEach(function (k) {
      if (keys.indexOf(k) !== -1 && !seen[k]) { clean.push(k); seen[k] = 1; }
    });
    keys.forEach(function (k) { if (!seen[k]) { clean.push(k); seen[k] = 1; } });
    main.classList.add('cc-orderable');
    els.forEach(function (el) {
      /* +1: hero (order 0) всегда остаётся сверху */
      el.style.order = String(clean.indexOf(el.dataset.widget) + 1);
    });
  }
  window.widgetOrderApply = widgetOrderApply;

  /* ── Старт ────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    fabInit();
    widgetOrderApply();
  });
})();

// ============================================================
// HAKUMO KIT 6 — оффлайн-баннер
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var banner = doc.createElement('div');
  banner.className = 'offline-banner';
  banner.innerHTML = '<i class="fas fa-plug-circle-xmark"></i> Соединение потеряно';
  doc.body.appendChild(banner);

  function show() { banner.classList.add('show'); }
  function hide() { banner.classList.remove('show'); }

  window.addEventListener('offline', show);
  window.addEventListener('online', function () {
    hide();
    if (typeof window.showToast === 'function') window.showToast('Соединение восстановлено', true);
  });
  if (!navigator.onLine) show();
})();

// ============================================================
// HAKUMO KIT 7 — FX слой 9: живой градиентный обод карточек,
// параллакс при прокрутке, конфетти при входе,
// drag-сортировка избранного, плотность следует за учёткой
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var win = window;
  var reduced = win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var narrow = function () { return win.innerWidth < 900; };
  var PALETTE = ['#4f46e5', '#7c3aed', '#a78bfa', '#22d3ee', '#818cf8', '#c7d2fe'];

  /* ── 1. Регистрация @property для вращения градиента ── */
  function fxRegisterAngle() {
    try {
      if (typeof win.CSS !== 'undefined' && win.CSS.registerProperty) {
        win.CSS.registerProperty({
          name: '--fx-ang', syntax: '<angle>', inherits: false, initialValue: '0deg'
        });
      }
    } catch (e) { /* уже зарегистрировано или не поддержано */ }
  }

  /* ── 2. Живой градиентный обод на .panel и .kpi ── */
  function fxRingScan() {
    if (narrow() || doc.body.dataset.fxRings === 'done' && !win.__fxRingForce) return;
    var total = 0;
    doc.querySelectorAll('.panel, .kpi').forEach(function (el) {
      if (total > 80) return;
      if (el.querySelector('.fx-ring-el')) return;
      /* KPI внутри панели не обводим — панель уже обведена */
      if (el.classList.contains('kpi') && el.closest('.panel')) return;
      var tag = doc.createElement('i');
      tag.className = 'fx-ring-el';
      tag.setAttribute('aria-hidden', 'true');
      el.classList.add('fx-ring-host');
      el.appendChild(tag);
      total++;
    });
  }
  var ringTimer = null;
  function fxRingSchedule() {
    if (ringTimer) return;
    ringTimer = setTimeout(function () { ringTimer = null; fxRingScan(); }, 600);
  }
  fxRegisterAngle();
  fxRingSchedule();

  /* Параллакс карточек отключён: субпиксельные transform'ы
     размывали текст панелей («эффект 144p»). */

  /* ── 4. Конфетти при входе (раз за сессию) ── */
  function fxEntranceConfetti() {
    if (reduced) return;
    try {
      if (win.sessionStorage && win.sessionStorage.getItem('hakumo_confetti_done')) return;
      if (win.sessionStorage) win.sessionStorage.setItem('hakumo_confetti_done', '1');
    } catch (e) { /* приватный режим */ }
    var cv = doc.createElement('canvas');
    cv.id = 'fx-confetti';
    doc.body.appendChild(cv);
    var ctx = cv.getContext('2d');
    var W = cv.width = win.innerWidth;
    var H = cv.height = win.innerHeight;
    var parts = [];
    var count = 46;
    for (var i = 0; i < count; i++) {
      parts.push({
        x: Math.random() * W,
        y: -20 - Math.random() * H * 0.35,
        w: 5 + Math.random() * 7,
        h: 8 + Math.random() * 8,
        c: PALETTE[i % PALETTE.length],
        vy: 1.6 + Math.random() * 2.4,
        vx: (Math.random() - 0.5) * 1.6,
        rot: Math.random() * Math.PI * 2,
        vr: (Math.random() - 0.5) * 0.16,
        sway: Math.random() * Math.PI * 2
      });
    }
    var start = performance.now();
    var DUR = 2400;
    function frame(now) {
      var t = now - start;
      if (t > DUR) { cv.remove(); return; }
      ctx.clearRect(0, 0, W, H);
      var fade = t > DUR - 500 ? (DUR - t) / 500 : 1;
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        p.y += p.vy;
        p.x += p.vx + Math.sin(p.sway + t * 0.004) * 0.5;
        p.rot += p.vr;
        ctx.save();
        ctx.globalAlpha = fade * Math.min(1, (p.y + 40) / 140);
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      win.requestAnimationFrame(frame);
    }
    win.requestAnimationFrame(frame);
  }
  function onReady(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  onReady(function () { setTimeout(fxEntranceConfetti, 350); });

  /* ── 5. Drag-сортировка избранного ── */
  function favsDragSort() {
    var linksBox = doc.querySelector('.nav-favs-links');
    if (!linksBox) return;
    var dragEl = null;
    linksBox.addEventListener('dragstart', function (e) {
      var a = e.target.closest('a[draggable="true"]');
      if (!a || !a.closest('.nav-favs-links')) return;
      dragEl = a;
      a.classList.add('fx-drag');
      try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', a.getAttribute('href')); } catch (err) {}
    });
    linksBox.addEventListener('dragend', function () {
      if (dragEl) dragEl.classList.remove('fx-drag');
      linksBox.querySelectorAll('.fx-drag-over').forEach(function (el) { el.classList.remove('fx-drag-over'); });
      dragEl = null;
    });
    linksBox.addEventListener('dragover', function (e) {
      if (!dragEl) return;
      e.preventDefault();
      var over = e.target.closest('a[draggable="true"]');
      if (!over || over === dragEl || !over.closest('.nav-favs-links')) return;
      var box = over.getBoundingClientRect();
      linksBox.querySelectorAll('.fx-drag-over').forEach(function (el) { el.classList.remove('fx-drag-over'); });
      if (e.clientY < box.top + box.height / 2) linksBox.insertBefore(dragEl, over);
      else linksBox.insertBefore(dragEl, over.nextSibling);
    });
    linksBox.addEventListener('drop', function (e) {
      e.preventDefault();
      if (!dragEl) return;
      var order = [];
      linksBox.querySelectorAll('a[draggable="true"]').forEach(function (a) {
        var path = a.getAttribute('href');
        if (path) order.push(path);
      });
      try { localStorage.setItem('hakumo_favs', JSON.stringify(order)); } catch (err) {}
      if (typeof win.__renderFavs === 'function') win.__renderFavs();
      if (typeof win.showToast === 'function') win.showToast('Порядок избранного сохранён', true);
    });
  }
  favsDragSort();

  /* ── 6. Плотность следует за учёткой ── */
  function densityFromAccount() {
    if (!localStorage.getItem('hakumo_dense')) {
      fetch('/api/ux/prefs', { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var p = (d && d.prefs) || {};
          if (p.compact === true) doc.body.classList.add('dense');
        })
        .catch(function () {});
    }
  }
  densityFromAccount();

  /* ── 7. Пересканирование колец при живых перерисовках ── */
  if (typeof win.MutationObserver !== 'undefined') {
    var mo = new win.MutationObserver(function () { fxRingSchedule(); });
    mo.observe(doc.body, { childList: true, subtree: true });
  }
  doc.addEventListener('hakumo:live', function () { win.__fxRingForce = true; fxRingSchedule(); });
})();

// ============================================================
// HAKUMO KIT 8 — FX слой 10: прогресс прокрутки, кнопка
// «наверх» с кольцом, магнитные кнопки, блик панелей
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var win = window;
  var reduced = win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var narrow = function () { return win.innerWidth < 900; };

  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  /* ── 1. Полоса прогресса прокрутки ── */
  function fxScrollProgress() {
    var bar = doc.createElement('div');
    bar.id = 'fx-scroll-progress';
    doc.body.appendChild(bar);
    var ticking = false;
    function paint() {
      ticking = false;
      var max = doc.documentElement.scrollHeight - win.innerHeight;
      var p = max > 0 ? win.scrollY / max : 0;
      bar.style.transform = 'scaleX(' + Math.min(1, Math.max(0, p)) + ')';
    }
    win.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; win.requestAnimationFrame(paint); }
    }, { passive: true });
    win.addEventListener('resize', function () {
      if (!ticking) { ticking = true; win.requestAnimationFrame(paint); }
    }, { passive: true });
    paint();
  }

  /* ── 2. Кнопка «наверх» с кольцом прогресса ── */
  function fxTopButton() {
    var btn = doc.createElement('button');
    btn.type = 'button';
    btn.id = 'fx-topbtn';
    btn.setAttribute('aria-label', 'Наверх');
    btn.title = 'Наверх';
    btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    doc.body.appendChild(btn);
    var ticking = false;
    var lastRing = 0;
    function paint(now) {
      ticking = false;
      now = now || performance.now();
      var max = doc.documentElement.scrollHeight - win.innerHeight;
      var p = max > 0 ? win.scrollY / max : 0;
      btn.classList.toggle('show', win.scrollY > 480);
      /* кольцо прогресса перерисовывается не чаще 8 раз/сек —
         conic-градиент не должен краситься на каждый кадр скролла */
      if (now - lastRing >= 120) {
        lastRing = now;
        btn.style.setProperty('--top-progress', Math.round(p * 100));
      }
    }
    win.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; win.requestAnimationFrame(paint); }
    }, { passive: true });
    btn.addEventListener('click', function () {
      win.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
    });
    paint();
  }

  /* ── 4. Магнитные кнопки ──
     Отключено по просьбе владельца: кнопки должны стоять на месте.
     Код сохранён, но обработчик не вешается. */
  function fxMagnetic() {
    return;
    if (reduced || narrow()) return;
    var SEL = '.btn, .send-btn, .fab-main, .hdr-btn, .analytics-refresh, .prompt-chip';
    var tick = false, lastE = null, lastTarget = null, lastRect = null;
    function apply(e) {
      tick = false;
      if (!e) return;
      var target = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (target !== lastTarget) { lastTarget = target; lastRect = target ? target.getBoundingClientRect() : null; }
      if (!target || !lastRect) return;
      var r = lastRect;
      var cx = r.left + r.width / 2;
      var cy = r.top + r.height / 2;
      var dx = e.clientX - cx;
      var dy = e.clientY - cy;
      var dist = Math.sqrt(dx * dx + dy * dy);
      var R = Math.max(60, r.width / 2 + 20);
      if (dist > R) { target.style.transform = ''; return; }
      var pull = (1 - dist / R) * 5;
      target.style.transform = 'translate(' + Math.round(dx / dist * pull) + 'px,' + Math.round(dy / dist * pull) + 'px)';
    }
    doc.addEventListener('mousemove', function (e) {
      lastE = e;
      if (!tick) { tick = true; requestAnimationFrame(function () { apply(lastE); }); }
    }, { passive: true });
    doc.addEventListener('mouseleave', function () {
      lastTarget = null; lastRect = null;
      doc.querySelectorAll(SEL).forEach(function (el) { el.style.transform = ''; });
    }, true);
    window.addEventListener('scroll', function () { lastTarget = null; lastRect = null; }, { passive: true });
  }

  /* ── 5. Блик панелей при наведении ── */
  function fxPanelShine() {
    var total = 0;
    function scan() {
      if (narrow()) return;
      doc.querySelectorAll('.panel').forEach(function (el) {
        if (total > 60) return;
        if (el.querySelector('.fx-shine')) return;
        var shine = doc.createElement('i');
        shine.className = 'fx-shine';
        shine.setAttribute('aria-hidden', 'true');
        el.appendChild(shine);
        total++;
      });
    }
    ready(scan);
    var timer = null;
    if (typeof win.MutationObserver !== 'undefined') {
      var mo = new win.MutationObserver(function () {
        if (timer) return;
        timer = setTimeout(function () { timer = null; scan(); }, 700);
      });
      mo.observe(doc.body, { childList: true, subtree: true });
    }
  }

  ready(function () {
    fxScrollProgress();
    fxTopButton();
    fxMagnetic();
    fxPanelShine();
  });
})();

// ============================================================
// HAKUMO KIT 9 — стабильность прокрутки: сайдбар и страница
// помнят позицию между переходами; активный пункт меню всегда
// виден (меню больше не «уезжает в самый вверх»)
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var win = window;
  var SB_KEY = 'hakumo_sb_scroll';
  var PG_KEY = 'hakumo_pg_scroll_';

  function sget(k) { try { return win.sessionStorage.getItem(k); } catch (e) { return null; } }
  function sset(k, v) { try { win.sessionStorage.setItem(k, v); } catch (e) {} }

  /* ── 1. Сайдбар: восстановление позиции + показ активного пункта ── */
  function sidebarScroll() {
    var nav = doc.getElementById('sidebarNav');
    if (!nav) return;
    var saved = sget(SB_KEY);
    if (saved !== null && saved !== '') {
      nav.scrollTop = parseInt(saved, 10) || 0;
      return;
    }
    /* первый заход на страницу — показываем активный пункт меню */
    var act = nav.querySelector('.nav-link.active');
    if (act) {
      var top = act.offsetTop - nav.clientHeight / 2 + act.offsetHeight / 2;
      nav.scrollTop = Math.max(0, top);
    }
  }
  var sbTimer = null;
  function saveSidebar() {
    var nav = doc.getElementById('sidebarNav');
    if (!nav) return;
    if (sbTimer) return;
    sbTimer = setTimeout(function () {
      sbTimer = null;
      sset(SB_KEY, String(nav.scrollTop || 0));
    }, 120);
  }
  function bindSidebar() {
    var nav = doc.getElementById('sidebarNav');
    if (!nav) return;
    nav.addEventListener('scroll', saveSidebar, { passive: true });
    win.addEventListener('beforeunload', function () {
      sset(SB_KEY, String(nav.scrollTop || 0));
    });
  }

  /* ── 2. Страница: память прокрутки по маршруту ── */
  var pgKey = PG_KEY + win.location.pathname;
  var pgSaved = sget(pgKey);
  var pgTimer = null;
  function savePage() {
    if (pgTimer) return;
    pgTimer = setTimeout(function () {
      pgTimer = null;
      sset(pgKey, String(win.scrollY || 0));
    }, 150);
  }
  function restorePage() {
    if (!pgSaved) return;
    if (win.scrollY > 4) return; /* пользователь уже прокрутил сам */
    var y = parseInt(pgSaved, 10) || 0;
    if (y > 0 && doc.documentElement.scrollHeight > y + win.innerHeight * 0.5) {
      win.scrollTo(0, y);
    }
  }
  function bindPage() {
    win.addEventListener('scroll', savePage, { passive: true });
    win.addEventListener('beforeunload', function () {
      sset(pgKey, String(win.scrollY || 0));
    });
  }

  function onReady(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  onReady(function () {
    sidebarScroll();
    bindSidebar();
    bindPage();
    restorePage();
    /* страницы догружаются асинхронно — дотягиваем позицию */
    setTimeout(restorePage, 400);
    setTimeout(restorePage, 1100);
  });
})();

// ============================================================
// HAKUMO KIT 10 — единые премиум-шапки страниц: страницы без
// page-head/page-hero автоматически получают иконку-плитку,
// eyebrow и описание из меню панели (навбар-дубль скрывается)
// ============================================================
(function () {
  'use strict';
  var doc = document;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var GROUP_LEADS = {
    main: 'Главный обзор сервера и ключевые показатели.',
    mod: 'Инструменты модерации: реагирование, расследование, защита и команда.',
    members: 'Работа с участниками: профили, поиск, заметки и наблюдение.',
    roles: 'Роли и права: управление, автоматизация и выдача.',
    access: 'Доступы: кто видит какие разделы панели.',
    tickets: 'Тикеты и обращения: очереди, ответы и SLA.',
    fun: 'Развлечения и игровые механики сервера.',
    leveling: 'Уровни, опыт и карьерные системы.',
    economy: 'Экономика: валюта, магазины и награды.',
    admin: 'Администрирование сервера и бота.',
    logs: 'Журналы, история и расследования.',
    music: 'Музыкальные комнаты и плейлисты.',
    settings: 'Настройки панели и сервера.',
    other: 'Дополнительные инструменты панели Hakumo.'
  };

  function pageHeadAuto() {
    var main = doc.querySelector('.main-content');
    if (!main) return;
    if (main.querySelector(':scope > .page-head')) return;
    if (main.querySelector(':scope > .page-hero')) return;
    var navbar = main.querySelector(':scope > .navbar');
    if (!navbar) return;
    var data = doc.getElementById('palette-data');
    if (!data) return;
    var groups = [];
    try { groups = JSON.parse(data.textContent || '[]'); } catch (e) {}
    var path = window.location.pathname;
    var found = null, grp = null;
    for (var i = 0; i < groups.length; i++) {
      var pages = groups[i].pages || [];
      for (var j = 0; j < pages.length; j++) {
        if (pages[j].path === path) { found = pages[j]; grp = groups[i]; break; }
      }
      if (found) break;
    }
    if (!found) return;
    var h1 = navbar.querySelector('h1');
    var titleEl = h1 ? h1.cloneNode(true) : null;
    if (titleEl) titleEl.querySelectorAll('i').forEach(function (el) { el.remove(); });
    var title = (titleEl ? titleEl.textContent : found.label).trim() || found.label;
    var icon = (found.icon || (grp && grp.icon) || 'fa-file').replace(/[^a-z0-9-]/gi, '');
    var lead = found.description || GROUP_LEADS[(grp && grp.key)] || ('Раздел «' + ((grp && grp.group) || 'панель') + '» панели Hakumo.');
    var head = doc.createElement('div');
    head.className = 'page-head fx-built';
    head.setAttribute('data-fx-head', (grp && grp.key) || 'auto');
    head.innerHTML =
      '<div class="page-head-icon"><i class="fas ' + icon + '"></i></div>' +
      '<div class="page-head-copy">' +
        '<div class="eyebrow">' + esc((grp && grp.group) || 'Панель') + ' <span class="sep">·</span> ' + esc(found.label) + '</div>' +
        '<h1>' + esc(title) + '</h1>' +
        '<p class="lead">' + esc(lead) + '</p>' +
      '</div>';
    main.insertBefore(head, navbar);
  }

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', pageHeadAuto);
  else pageHeadAuto();
})();

// ============================================================
// HAKUMO KIT 11 — HakumoSelect: полностью кастомные дропдауны
// вместо нативных «классических» списков браузера. Стильная
// панель, поиск, галочка выбора, клавиатура, синхронизация с
// исходным <select> (change-события продолжают работать).
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var win = window;
  var reduced = win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var panel = null;
  var currentOrig = null;
  var listEl = null;
  var searchEl = null;
  var activeIndex = -1;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function ensurePanel() {
    if (panel) return;
    panel = doc.createElement('div');
    panel.className = 'aes-panel';
    panel.setAttribute('role', 'listbox');
    panel.innerHTML = '<input type="text" class="aes-search" placeholder="Поиск..." aria-label="Поиск в списке">' +
      '<div class="aes-list"></div>';
    doc.body.appendChild(panel);
    listEl = panel.querySelector('.aes-list');
    searchEl = panel.querySelector('.aes-search');
    searchEl.addEventListener('input', function () {
      var q = this.value.toLowerCase();
      var any = false;
      listEl.querySelectorAll('.aes-opt').forEach(function (o) {
        var hit = o.textContent.toLowerCase().indexOf(q) !== -1;
        o.style.display = hit ? '' : 'none';
        if (hit) any = true;
      });
      var empty = listEl.querySelector('.aes-empty');
      if (!empty) {
        empty = doc.createElement('div');
        empty.className = 'aes-empty';
        empty.textContent = 'Ничего не найдено';
        listEl.appendChild(empty);
      }
      empty.style.display = any ? 'none' : '';
    });
    /* Гарантированный скролл списка колесом: прокручиваем только список,
       страница за дропдауном не двигается (фикс «не листается вниз») */
    panel.addEventListener('wheel', function (e) {
      try {
        var sh = listEl.scrollHeight, ch = listEl.clientHeight;
        if (sh > ch) {
          var next = listEl.scrollTop + e.deltaY;
          listEl.scrollTop = Math.max(0, Math.min(next, sh - ch));
          e.preventDefault();
        }
      } catch (err) { /* метрики недоступны — нативное поведение */ }
    }, { passive: false });
  }

  function optionHtml(o, selected) {
    var dis = o.disabled ? ' dis' : '';
    return '<div class="aes-opt' + (selected ? ' sel' : '') + dis + '" role="option" aria-selected="' + (selected ? 'true' : 'false') + '" data-v="' + esc(o.value) + '">' +
      '<span class="aes-check"><i class="fas fa-check"></i></span>' +
      '<span class="aes-opt-label">' + esc(o.textContent || o.value || '—') + '</span></div>';
  }

  function buildList(orig) {
    var value = orig.value;
    var html = '';
    Array.prototype.forEach.call(orig.children, function (child) {
      if (child.tagName === 'OPTGROUP') {
        html += '<div class="aes-group">' + esc(child.label || '') + '</div>';
        Array.prototype.forEach.call(child.children, function (o) {
          html += optionHtml(o, o.value === value);
        });
      } else if (child.tagName === 'OPTION') {
        html += optionHtml(child, child.value === value);
      }
    });
    return html || optionHtml({ value: '', textContent: 'Нет вариантов', disabled: true }, false);
  }

  function positionPanel(btn) {
    var rect = btn.getBoundingClientRect();
    panel.style.minWidth = Math.max(rect.width, 230) + 'px';
    panel.style.maxWidth = Math.max(rect.width, 340) + 'px';
    var below = rect.bottom + 6;
    var est = Math.min(300, panel.offsetHeight || 300);
    if (below + est > win.innerHeight - 8 && rect.top - est - 6 > 8) {
      panel.style.top = Math.max(8, rect.top - est - 6) + 'px';
    } else {
      panel.style.top = below + 'px';
    }
    var left = Math.min(rect.left, win.innerWidth - (panel.offsetWidth || 260) - 10);
    panel.style.left = Math.max(8, left) + 'px';
  }

  function closePanel() {
    if (!panel) return;
    panel.classList.remove('open');
    if (currentOrig) {
      var shell = currentOrig.closest('.aes');
      if (shell) shell.classList.remove('open');
    }
    currentOrig = null;
    activeIndex = -1;
  }

  function setActive(idx) {
    var opts = listEl.querySelectorAll('.aes-opt:not(.dis)');
    var visible = [];
    opts.forEach(function (o) { if (o.style.display !== 'none') visible.push(o); });
    if (!visible.length) return;
    if (idx < 0) idx = visible.length - 1;
    if (idx >= visible.length) idx = 0;
    activeIndex = idx;
    visible.forEach(function (o) { o.classList.remove('active'); });
    visible[idx].classList.add('active');
    if (visible[idx].scrollIntoView) visible[idx].scrollIntoView({ block: 'nearest' });
  }

  function chooseValue(v) {
    var orig = currentOrig;
    closePanel();
    if (!orig || orig.disabled) return;
    if (orig.value === v) return;
    orig.value = v;
    syncLabel(orig);
    try { orig.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  }

  function openFor(orig) {
    ensurePanel();
    var shell = orig.closest('.aes');
    var btn = shell.querySelector('.aes-btn');
    if (!btn) return;
    if (currentOrig === orig && panel.classList.contains('open')) { closePanel(); return; }
    closePanel();
    currentOrig = orig;
    var many = orig.querySelectorAll('option').length > 8;
    searchEl.style.display = many ? '' : 'none';
    searchEl.value = '';
    listEl.innerHTML = buildList(orig);
    shell.classList.add('open');
    panel.classList.add('open');
    positionPanel(btn);
    var sel = listEl.querySelector('.aes-opt.sel');
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest' });
  }

  function syncLabel(orig) {
    var shell = orig.closest('.aes');
    if (!shell) return;
    var val = shell.querySelector('.aes-value');
    var sel = orig.selectedOptions && orig.selectedOptions[0];
    var label = sel ? sel.textContent : (orig.value || '—');
    if (val) val.textContent = label || '—';
  }

  function enhance(orig) {
    if (orig.getAttribute('data-aes') === '1') return;
    if (orig.matches('[multiple], [size], [data-no-aes]')) return;
    if (orig.closest('.aes')) return;
    var inline = !!orig.closest('.analytics-server-control');
    var cs = getComputedStyle(orig);
    var full = cs.display === 'block';
    var big = orig.classList.contains('guild-select') || orig.classList.contains('guild-sel') ||
              orig.id === 'ch-guild-select' || parseFloat(cs.minHeight) >= 40;
    orig.setAttribute('data-aes', '1');
    var shell = doc.createElement('div');
    shell.className = 'aes' + (inline ? ' aes-inline' : '') + (full ? ' aes-full' : '') + (big ? ' aes-lg' : '');
    if (parseFloat(cs.minWidth) > 0) shell.style.minWidth = cs.minWidth;
    var btn = doc.createElement('button');
    btn.type = 'button';
    btn.className = 'aes-btn';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.innerHTML = '<span class="aes-value"></span><span class="aes-arrow"></span>';
    shell.appendChild(btn);
    var parent = orig.parentNode;
    if (!parent) return;
    parent.replaceChild(shell, orig);   /* сначала меняем в исходном родителе… */
    shell.appendChild(orig);            /* …потом прячем select внутри shell */
    orig.classList.add('aes-native');
    orig.setAttribute('aria-hidden', 'true');
    orig.setAttribute('tabindex', '-1');
    syncLabel(orig);
    btn.addEventListener('click', function () { openFor(orig); });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        openFor(orig);
        setActive(e.key === 'ArrowDown' ? 0 : -1);
      }
    });
    orig._aesValue = orig.value;
  }

  function tryEnhance(el) {
    try { enhance(el); }
    catch (e) { el.removeAttribute('data-aes'); }
  }
  function scan(root) {
    (root || doc).querySelectorAll('select').forEach(function (el) {
      if (!el.closest('.aes') && !el.matches('[multiple], [size], [data-no-aes]')) tryEnhance(el);
    });
  }

  /* перерисовка опций из шаблонов (innerHTML) */
  var mo = new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.tagName === 'SELECT') { tryEnhance(n); return; }
        if (n.firstElementChild) n.querySelectorAll('select').forEach(tryEnhance);
      });
      if (m.target && m.target.tagName === 'SELECT' && m.type === 'childList') {
        syncLabel(m.target);
        if (currentOrig === m.target) {
          listEl.innerHTML = buildList(m.target);
          positionPanel(m.target.closest('.aes').querySelector('.aes-btn'));
        }
      }
    });
  });
  mo.observe(doc.body, { childList: true, subtree: true });

  /* программные изменения value — подтягиваем подпись */
  setInterval(function () {
    doc.querySelectorAll('select[data-aes="1"]').forEach(function (o) {
      if (o._aesValue !== o.value) { o._aesValue = o.value; syncLabel(o); }
    });
  }, 500);

  /* панель: выбор, клавиатура, закрытие */
  doc.addEventListener('click', function (e) {
    if (!panel || !panel.classList.contains('open')) return;
    var opt = e.target.closest('.aes-opt');
    if (opt && !opt.classList.contains('dis')) chooseValue(opt.dataset.v);
    else if (!e.target.closest('.aes-panel') && !e.target.closest('.aes-btn')) closePanel();
  });
  doc.addEventListener('keydown', function (e) {
    if (!panel || !panel.classList.contains('open')) return;
    if (e.key === 'Escape') { closePanel(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(activeIndex + 1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive(activeIndex - 1); return; }
    if (e.key === 'Enter') {
      var act = listEl.querySelector('.aes-opt.active') || listEl.querySelector('.aes-opt.sel');
      if (act) chooseValue(act.dataset.v);
    }
  });
  /* Скролл СТРАНИЦЫ закрывает панель. Прокрутка самого списка (.aes-list
     или поля поиска) панель НЕ закрывает — иначе дропдаун схлопывался
     при первом же движении колесом внутри. */
  win.addEventListener('scroll', function (e) {
    if (!panel || !panel.classList.contains('open')) return;
    if (e.target && panel.contains(e.target)) return;
    closePanel();
  }, true);
  win.addEventListener('resize', function () {
    if (panel && panel.classList.contains('open') && currentOrig) {
      positionPanel(currentOrig.closest('.aes').querySelector('.aes-btn'));
    }
  });

  function onReady(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  onReady(function () { scan(doc); });
  if (!reduced) {
    doc.addEventListener('hakumo:live', function () { scan(doc); });
  }
  win.hakumoSelect = { rescan: function () { scan(doc); } };
})();

// ============================================================
// HAKUMO KIT 12 — @-поиск: мгновенно найти всё в панели.
// Нажми @ в любом месте — откроется быстрый поиск по страницам,
// участникам, каналам, расшифровкам, триггерам и анонсам.
// ============================================================
(function () {
  'use strict';
  var doc = document;
  var win = window;
  var overlay = null;
  var input = null;
  var listEl = null;
  var timer = null;
  var lastQ = '';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function ensure() {
    if (overlay) return;
    overlay = doc.createElement('div');
    overlay.className = 'modal-overlay at-finder';
    overlay.innerHTML =
      '<div class="modal-box" style="max-width:580px">' +
        '<div class="modal-head"><b><i class="fas fa-magnifying-glass"></i> Поиск по панели</b>' +
        '<button type="button" class="icon-btn" id="atFinderClose" aria-label="Закрыть"><i class="fas fa-xmark"></i></button></div>' +
        '<div class="modal-body">' +
          '<input type="text" id="atFinderInput" class="form-input" placeholder="@ страница, участник, канал…" style="font-size:15px;padding:12px 14px" autocomplete="off" aria-label="Быстрый поиск">' +
          '<div id="atFinderList" style="margin-top:10px;max-height:46vh;overflow:auto"></div>' +
          '<div class="hint" style="margin-top:10px"><i class="fas fa-keyboard"></i> Вверх/Вниз — выбор · Enter — открыть · Esc — закрыть · Ctrl+K — меню панели</div>' +
        '</div>' +
      '</div>';
    doc.body.appendChild(overlay);
    input = overlay.querySelector('#atFinderInput');
    listEl = overlay.querySelector('#atFinderList');
    overlay.querySelector('#atFinderClose').addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    input.addEventListener('input', function () { schedule(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        move(e.key === 'ArrowDown' ? 1 : -1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var act = listEl.querySelector('.at-item.active') || listEl.querySelector('.at-item');
        if (act) { var href = act.getAttribute('href'); if (href) win.location.href = href; }
      } else if (e.key === 'Escape') {
        close();
      }
    });
  }

  function open() {
    ensure();
    overlay.classList.add('open');
    input.value = '@';
    schedule();
    setTimeout(function () { input.focus({ preventScroll: true }); }, 30);
  }
  function close() {
    if (overlay) overlay.classList.remove('open');
    lastQ = '';
  }
  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(render, 160);
  }
  function move(dir) {
    var items = listEl.querySelectorAll('.at-item');
    if (!items.length) return;
    var idx = -1;
    items.forEach(function (el, i) { if (el.classList.contains('active')) idx = i; });
    items.forEach(function (el) { el.classList.remove('active'); });
    idx = (idx + dir + items.length) % items.length;
    items[idx].classList.add('active');
    if (items[idx].scrollIntoView) items[idx].scrollIntoView({ block: 'nearest' });
  }

  function itemHtml(label, sub, href, icon) {
    return '<a class="at-item" href="' + esc(href) + '">' +
      '<span class="at-item-ico"><i class="fas ' + esc(icon || 'fa-file') + '"></i></span>' +
      '<span class="at-item-copy"><b>' + esc(label) + '</b>' + (sub ? '<small>' + esc(sub) + '</small>' : '') + '</span>' +
      '<i class="fas fa-arrow-right at-item-arrow" aria-hidden="true"></i></a>';
  }

  function groupHtml(title, items) {
    if (!items.length) return '';
    return '<div class="at-group">' + esc(title) + '</div>' + items.join('');
  }

  function pickHref(it) {
    return it.path || it.url || it.href || (it.page_path ? it.page_path : '');
  }

  async function render() {
    if (!listEl) return;
    var q = String(input.value || '').replace(/^@/, '').trim().toLowerCase();
    if (q === lastQ) return;
    lastQ = q;
    if (!q) {
      listEl.innerHTML = '<div class="at-empty">Начните печатать — найдём страницы, участников, каналы и команды.</div>';
      return;
    }
    listEl.innerHTML = '<div class="at-loading"><i class="fas fa-circle-notch fa-spin"></i> Ищем «' + esc(q) + '»…</div>';
    var html = '';
    var found = 0;
    try {
      var r = await fetch('/api/ux/search?q=' + encodeURIComponent(q), { headers: { 'Accept': 'application/json' } });
      if (r.status === 401) {
        listEl.innerHTML = '<div class="at-empty"><i class="fas fa-lock"></i> Поиск доступен после входа — <a href="/login" style="color:var(--ac);font-weight:700">войдите в панель</a></div>';
        return;
      }
      if (r.ok) {
        var d = await r.json();
        (d.groups || []).forEach(function (g) {
          var items = [];
          (g.items || []).forEach(function (it) {
            var href = pickHref(it);
            if (!href) return;
            items.push(itemHtml(it.label || it.name || it.title || '—', it.sub || it.description || '', href, it.icon || 'fa-file'));
            found++;
          });
          html += groupHtml(g.title || g.key, items);
        });
      }
    } catch (e) { /* офлайн — только каналы ниже */ }

    /* Каналы сервера — быстрое дополнение к поиску */
    try {
      var cr = await fetch('/api/channels', { headers: { 'Accept': 'application/json' } });
      if (cr.ok) {
        var chans = await cr.json();
        chans = Array.isArray(chans) ? chans : (chans.channels || []);
        var chanItems = [];
        chans.forEach(function (c) {
          if (c.type === 'category' || c.hidden) return;
          var name = String(c.name || '').toLowerCase();
          var cat = String(c.category || '').toLowerCase();
          if (name.indexOf(q) !== -1 || cat.indexOf(q) !== -1) {
            chanItems.push(itemHtml('#' + c.name, c.category ? ('Категория: ' + c.category) : 'Канал сервера', '/chat', 'fa-hashtag'));
            found++;
          }
        });
        html += groupHtml('Каналы', chanItems.slice(0, 6));
      }
    } catch (e) {}

    listEl.innerHTML = html || '<div class="at-empty">Ничего не нашлось по «' + esc(q) + '» — попробуйте короче.</div>';
  }

  doc.addEventListener('keydown', function (e) {
    if (e.key === '@' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var t = e.target;
      var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' ||
        (t.isContentEditable));
      if (!typing) {
        e.preventDefault();
        if (overlay && overlay.classList.contains('open')) close(); else open();
      }
    }
    if (e.key === 'Escape' && overlay && overlay.classList.contains('open')) {
      e.stopPropagation();
      close();
    }
  });
})();

/* ── Флаг готовности клиентского кита (бут-шим в base.html
   перестаёт дублировать live-refresh, когда app.js загружен) ── */
try { window.__panelKitReady = true; } catch (e) {}
