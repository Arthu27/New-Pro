/* ============================================================
   Aether Panel — App Kit (Light Edition)
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
    var diff = Math.max(0, (Date.now() / 1000) - ts);
    if (diff < 60) return 'только что';
    if (diff < 3600) return Math.floor(diff / 60) + ' мин назад';
    if (diff < 86400) return Math.floor(diff / 3600) + ' ч назад';
    return Math.floor(diff / 86400) + ' дн назад';
  }

  /* ── 2. Тема ────────────────────────────────────────────── */
  function bootTheme() {
    var t = 'light';
    try { t = localStorage.getItem('aether_theme') || 'light'; } catch (e) {}
    if (t !== 'light' && t !== 'dark') t = 'light';
    doc.documentElement.setAttribute('data-theme', t);
  }

  window.toggleTheme = function () {
    var cur = doc.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    doc.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('aether_theme', next); } catch (e) {}
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
    try { localStorage.setItem('aether_accent', hex); } catch (e) {}
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
    el.innerHTML = '<i class="fas ' + icon + '"></i><span>' + esc(msg) + '</span>' +
      (opts.undo ? '<button type="button" class="undo-btn">Отменить</button>' : '');
    if (opts.undo) {
      el.querySelector('.undo-btn').addEventListener('click', function () {
        try { opts.undo(); } catch (e) {}
        dismiss(el);
      });
    }
    host.appendChild(el);
    var ttl = opts.ttl || (opts.undo ? 6000 : 3200);
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
  Object.defineProperty(window, '__modLivePaused', {
    get: function () { return livePaused; },
    set: function (v) { livePaused = !!v; }
  });

  window.setLiveRefresh = function (fn, ms) {
    if (typeof fn !== 'function') return;
    liveFns.push({ fn: fn, ms: ms || 2500, last: 0 });
    if (liveFns.length > 60) liveFns.shift();
  };

  setInterval(function () {
    if (livePaused) return;
    var now = Date.now();
    liveFns.forEach(function (e) {
      if (now - e.last >= e.ms) { e.last = now; try { e.fn(); } catch (err) {} }
    });
  }, 500);

  window.renderSafe = function (renderFn) {
    var y = window.scrollY, x = window.scrollX;
    if (typeof renderFn === 'function') { try { renderFn(); } catch (e) {} }
    requestAnimationFrame(function () { window.scrollTo(x, y); });
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
        i.className = 'fas fa-circle-notch fa-spin';
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
      '<circle class="donut-fill" cx="18" cy="18" r="' + r + '" fill="none" stroke="' + stroke + '" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="' + c + '" stroke-dashoffset="' + c + '"/>' +
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
        if (item) { paletteClose(); window.location.href = item.path; }
      }
    });
    el.addEventListener('click', function (e) { if (e.target === el) paletteClose(); });
    return el;
  }

  function paletteRender() {
    var box = paletteBuild();
    var input = box.querySelector('input');
    var q = (input.value || '').toLowerCase().trim();
    var results = box.querySelector('.kbd-palette-results');
    var flat = [];
    paletteData.forEach(function (grp) {
      grp.pages.forEach(function (p) {
        flat.push({ group: grp.group, icon: grp.icon, path: p.path, label: p.label, icon2: p.icon, desc: p.description || '' });
      });
    });
    paletteMatches = flat.filter(function (p) {
      if (!q) return true;
      return (p.label + ' ' + p.desc + ' ' + p.group).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 30);
    paletteIndex = paletteMatches.length ? 0 : -1;
    if (!paletteMatches.length) {
      results.innerHTML = '<div class="kbd-palette-empty">Ничего не найдено</div>';
      return;
    }
    var byGroup = {};
    paletteMatches.forEach(function (p) {
      (byGroup[p.group] = byGroup[p.group] || []).push(p);
    });
    var html = '';
    Object.keys(byGroup).forEach(function (g) {
      html += '<div class="kbd-palette-group"><div class="kbd-palette-group-title">' + esc(g) + '</div>';
      byGroup[g].forEach(function (p) {
        html += '<button type="button" class="kbd-palette-item" data-path="' + esc(p.path) + '">' +
          '<i class="fas ' + esc(p.icon2 || 'fa-circle') + '"></i>' +
          '<span>' + esc(p.label) + '</span>' +
          '<span class="kpi-path">' + esc(p.path) + '</span></button>';
      });
      html += '</div>';
    });
    results.innerHTML = html;
    Array.prototype.forEach.call(results.querySelectorAll('.kbd-palette-item'), function (node, i) {
      node.addEventListener('click', function () {
        paletteClose();
        window.location.href = node.dataset.path;
      });
      node.addEventListener('mousemove', function () { paletteIndex = i; paletteHighlight(); });
    });
    paletteHighlight();
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
    // Поиск-фильтр
    var search = doc.getElementById('sidebarSearch');
    if (search) {
      search.addEventListener('input', function () {
        var q = search.value.toLowerCase().trim();
        var any = false;
        Array.prototype.forEach.call(nav.querySelectorAll('.nav-group'), function (grp) {
          var links = Array.prototype.slice.call(grp.querySelectorAll('.nav-link'));
          var visible = 0;
          links.forEach(function (l) {
            var hit = !q || l.textContent.toLowerCase().indexOf(q) !== -1;
            l.style.display = hit ? '' : 'none';
            if (hit) visible++;
          });
          var subs = grp.querySelectorAll('.nav-subgroup');
          subs.forEach(function (s) { s.style.display = (q && !visible) ? 'none' : ''; });
          grp.style.display = (!q || visible) ? '' : 'none';
          if (!q && visible === 0) grp.style.display = 'none';
          if (q && visible) any = true;
        });
      });
    }
  }

  /* ── 11. Верхняя панель ─────────────────────────────────── */
  function topbarInit() {
    var clock = doc.getElementById('navClock');
    if (clock) {
      var tick = function () {
        clock.textContent = new Date().toLocaleTimeString('ru-RU');
      };
      tick();
      setInterval(tick, 1000);
    }
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

  /* ── 12. Уведомления и лента активности ─────────────────── */
  var notifLastSeen = 0;

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

    function loadNotifs() {
      var body = doc.getElementById('notifBody');
      if (!body) return;
      fetch('/api/notifications/poll')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var list = d.notifications || [];
          if (!list.length) {
            body.innerHTML = '<div class="empty"><i class="fas fa-bell-slash"></i><span>Уведомлений нет</span></div>';
          } else {
            body.innerHTML = list.map(function (n) {
              var t = n.ts ? timeAgo(n.ts) : '';
              return '<div class="feed-item">' +
                '<div class="feed-item-icon">' + esc(n.icon || '<i class="fas fa-bell"></i>') + '</div>' +
                '<div style="min-width:0"><div class="feed-item-title">' + esc(n.title || '') + '</div>' +
                '<div class="feed-item-sub">' + esc(n.body || '') + '</div>' +
                '<div class="feed-item-time">' + esc(t) + '</div></div></div>';
            }).join('');
          }
          var unread = (d.unread || 0) - (d.ts > notifLastSeen ? 0 : 0);
          if (unread > 0 && badge && !drawer.classList.contains('open')) {
            badge.textContent = unread > 99 ? '99+' : unread;
            badge.style.display = 'grid';
          }
        })
        .catch(function () {});
    }
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
            return '<div class="feed-item">' +
              '<div class="feed-item-icon">' + esc(it.icon || '•') + '</div>' +
              '<div style="min-width:0"><div class="feed-item-title">' + esc(it.title || '') + '</div>' +
              '<div class="feed-item-sub">' + esc(it.user || '') + (it.detail ? ' — ' + esc(it.detail) : '') + '</div>' +
              '<div class="feed-item-time">' + esc(timeAgo(it.ts)) + '</div></div></div>';
          }).join('');
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
      ws.on('stats_update', function (d) { if (typeof window.handleStatsUpdate === 'function') window.handleStatsUpdate(d); });
      ws.on('notification', function (d) {
        if (d && d.data && d.data.title) window.showToast(d.data.title, true);
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
  ready(function () {
    paletteInitData();
    topbarInit();
    sidebarInit();
    notifInit();
    activityInit();
    copyInit();
    hotkeysInit();
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
