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
    var ttl = opts.ttl || (opts.undo ? 6000 : 3200);
    el.style.setProperty('--toast-ttl', (ttl / 1000) + 's');
    el.innerHTML = '<i class="fas ' + icon + '"></i><span>' + esc(msg) + '</span>' +
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

  var paletteReqToken = 0;
  var paletteRemoteTimer = null;

  function paletteLocalMatches(q) {
    var flat = [];
    paletteData.forEach(function (grp) {
      grp.pages.forEach(function (p) {
        flat.push({ group: 'Разделы панели', path: p.path, label: p.label, icon2: p.icon, desc: p.description || '', sub: p.path });
      });
    });
    return flat.filter(function (p) {
      if (!q) return true;
      return (p.label + ' ' + p.desc).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 24);
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
        window.location.href = node.dataset.path;
      });
      node.addEventListener('mousemove', function () { paletteIndex = i; paletteHighlight(); });
    });
    paletteHighlight();
  }

  /* ── Действия палитры (команды, а не только страницы) ── */
  var PALETTE_ACTIONS = [
    { label: 'Сменить тему', icon: 'fa-circle-half-stroke', sub: 'переключить светлая/тёмная', run: function () { window.toggleTheme(); window.showToast('Тема переключена', true); } },
    { label: 'Светлая тема', icon: 'fa-sun', sub: 'включить светлый режим', run: function () { document.documentElement.setAttribute('data-theme', 'light'); try { localStorage.setItem('aether_theme', 'light'); } catch (e) {} } },
    { label: 'Тёмная тема', icon: 'fa-moon', sub: 'включить тёмный режим', run: function () { document.documentElement.setAttribute('data-theme', 'dark'); try { localStorage.setItem('aether_theme', 'dark'); } catch (e) {} } },
    { label: 'Скопировать ссылку страницы', icon: 'fa-link', sub: 'в буфер обмена', run: function () {
      var done = function () { window.showToast('Ссылка скопирована', true); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(window.location.href).then(done, function () {});
      else done();
    } },
    { label: 'Журнал: выгрузка CSV', icon: 'fa-file-csv', sub: 'последние 7 дней', run: function () { window.open('/logs/export?days=7', '_self'); } },
    { label: 'Отчёт модерации: CSV', icon: 'fa-file-csv', sub: 'статистика команды', run: function () { window.open('/api/mod-report.csv?days=7', '_self'); } },
    { label: 'Досье участника', icon: 'fa-id-card', sub: 'аналитика рисков по ID', run: function () { window.location.href = '/mod-insights'; } },
    { label: 'Центр безопасности', icon: 'fa-shield-halved', sub: 'политики и лаборатория', run: function () { window.location.href = '/security'; } }
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
    var sysClock = doc.getElementById('sysClock');
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

    function loadNotifs() {
      var body = doc.getElementById('notifBody');
      if (!body) return;
      var sysP = fetch('/api/notifications/poll').then(function (r) { return r.json(); }).catch(function () { return { notifications: [], unread: 0 }; });
      var ownP = fetch('/api/my-notifications').then(function (r) { return r.json(); }).catch(function () { return []; });
      Promise.all([sysP, ownP]).then(function (both) {
        var sys = both[0].notifications || [];
        var own = Array.isArray(both[1]) ? both[1] : [];
        var sysItems = sys.map(function (n) {
          return { title: n.title, body: n.body, icon: notifIcon(n), ts: n.ts, kind: 'system' };
        });
        var ownItems = own.map(function (n) {
          return {
            title: n.title || n.action || 'Уведомление',
            body: n.body || n.detail || '',
            icon: /^fa-/.test(n.icon || '') ? n.icon : 'fa-bell',
            ts: n.ts || n.created_at || n.timestamp || 0,
            kind: 'personal'
          };
        });
        var all = sysItems.concat(ownItems).sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); });
        var list = notifTab === 'system' ? sysItems : notifTab === 'personal' ? ownItems : all;
        if (!list.length) {
          body.innerHTML = '<div class="empty"><i class="fas fa-bell-slash"></i><span>Уведомлений нет</span></div>';
        } else {
          body.innerHTML = list.slice(0, 30).map(function (n) {
            var t = n.ts ? timeAgo(n.ts) : '';
            return '<div class="feed-item">' +
              '<div class="feed-item-icon"><i class="fas ' + esc(n.icon) + '"></i></div>' +
              '<div style="min-width:0"><div class="feed-item-title">' + esc(n.title || '') + '</div>' +
              (n.body ? '<div class="feed-item-sub">' + esc(n.body) + '</div>' : '') +
              '<div class="feed-item-time">' +
                (n.kind === 'personal'
                  ? '<span class="badge neutral" style="font-size:9px;padding:0 6px">личное</span> '
                  : '<span class="badge security" style="font-size:9px;padding:0 6px">система</span> ') +
                esc(t) + '</div></div></div>';
          }).join('');
        }
        var unread = both[0].unread || 0;
        if (unread > 0 && badge && !drawer.classList.contains('open')) {
          badge.textContent = unread > 99 ? '99+' : unread;
          badge.style.display = 'grid';
        }
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
      ws.on('stats_update', function (d) {
        if (typeof window.handleStatsUpdate === 'function') window.handleStatsUpdate(d);
        try { doc.dispatchEvent(new CustomEvent('aether:live', { detail: d || {} })); } catch (e) {}
      });
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
    pageTransitions();
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
// AETHER PREMIUM KIT — счётчики, сортировка таблиц, графики
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
  window.AetherChart = {
    sparkline: function (el, values, opts) {
      opts = opts || {};
      if (!el) return;
      var data = (values || []).map(function (x) { return Number(x) || 0; });
      var w = 260, h = Number(opts.height) || 64, pad = 8;
      var color = opts.color || cssVar('--ac', '#4f46e5');
      if (!data.length) { el.innerHTML = '<span class="muted" style="font-size:11px">нет данных</span>'; return; }
      var pts = numPath(data, w, h, pad);
      var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
      var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (h - pad) + ' L' + pts[0][0].toFixed(1) + ' ' + (h - pad) + ' Z';
      var svg = svgEl('svg', { viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none', style: 'width:100%;height:' + h + 'px' });
      svg.appendChild(svgEl('path', { d: area, fill: colorWithAlpha(color, 0.16), 'class': 'area-fill' }));
      svg.appendChild(svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': '2.5', 'class': 'line-path' }));
      var last = pts[pts.length - 1];
      svg.appendChild(svgEl('circle', { cx: last[0], cy: last[1], r: 4, fill: color, 'class': 'last-dot' }));
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
      [0.25, 0.5, 0.75].forEach(function (f) {
        var y = pad + (h - pad * 2) * f;
        svg.appendChild(svgEl('line', { x1: pad, y1: y.toFixed(1), x2: w - pad, y2: y.toFixed(1), 'class': 'grid-line' }));
      });
      svg.appendChild(svgEl('path', { d: area, fill: colorWithAlpha(color, 0.16), 'class': 'area-fill' }));
      var linePath = svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': '2.5', 'class': 'line-path' });
      svg.appendChild(linePath);
      pts.forEach(function (p, i) {
        var dot = svgEl('circle', { cx: p[0], cy: p[1], r: 3, fill: color, opacity: i === pts.length - 1 ? 1 : 0.55 });
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
// AETHER PREMIUM KIT 2 — кольца, теплокарта, CSV, акценты
// ============================================================
(function () {
  'use strict';
  var doc = document;

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
  window.AetherRing = function (el, segments, opts) {
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
      var dash = frac * c - 1.5; // зазор между сегментами
      if (dash < 0) dash = 0;
      var circle = svgEl('circle', {
        cx: size / 2, cy: size / 2, r: r, fill: 'none',
        stroke: seg.color || '#4f46e5',
        'stroke-width': stroke,
        'stroke-dasharray': dash + ' ' + (c - dash),
        'stroke-dashoffset': -(off * c),
        'stroke-linecap': 'butt'
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
  };

  /* ── Тепловая карта (24 часа) ────────────────────────── */
  window.AetherHeat = function (el, values, opts) {
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
      try { cur = localStorage.getItem('aether_accent') || '#4f46e5'; } catch (e) {}
      cur = String(cur).toLowerCase();
      Array.prototype.forEach.call(grid.children, function (sw, i) {
        sw.classList.toggle('active', ACCENTS[i].hex.toLowerCase() === cur);
      });
    }
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
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
        var userPill = doc.querySelector('.user-pill.open');
        if (userPill) userPill.classList.remove('open');
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
// AETHER PREMIUM KIT 3 — тултипы, tilt, ripple
// ============================================================
(function () {
  'use strict';
  var doc = document;

  function reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ── Тултип для площадных графиков ───────────────────────
     Вызывается из AetherChart.area при opts.tooltip !== false. */
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
// AETHER PREMIUM KIT 4 — 3D-tilt и ripple
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
// AETHER PREMIUM KIT 5 — курсор-прожектор (свечение за мышкой)
// ============================================================
(function () {
  'use strict';
  var doc = document;
  if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) return;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) return;

  var SEL = '.panel, .card, .kpi, .stat-box, .cc-tile, .member-card, .g-card, .auth-card';
  var current = null;

  doc.addEventListener('mousemove', function (e) {
    var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
    if (el !== current) {
      if (current) current.classList.remove('spot-on');
      current = el;
      if (el) el.classList.add('spot-on');
    }
    if (el) {
      var r = el.getBoundingClientRect();
      el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      el.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }
  });

  doc.addEventListener('mouseleave', function () {
    if (current) { current.classList.remove('spot-on'); current = null; }
  });
})();

// ============================================================
// AETHER FX KIT — частицы, курсор-свечение, сплэш, вспышки,
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
    for (var i = 0; i < N; i++) {
      pts.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.3 + 0.5
      });
    }
    var LINK = 110;
    function step() {
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
      requestAnimationFrame(step);
    }
    step();
  }

  /* ── 2. Мягкое свечение за курсором ────────────────────── */
  function fxCursorGlow() {
    var glow = doc.getElementById('fxCursor');
    if (!glow || reduced || coarse) return;
    var tx = window.innerWidth / 2, ty = window.innerHeight / 3;
    var x = tx, y = ty;
    doc.addEventListener('mousemove', function (e) {
      tx = e.clientX; ty = e.clientY;
    }, { passive: true });
    function loop() {
      x += (tx - x) * 0.09;
      y += (ty - y) * 0.09;
      glow.style.transform = 'translate(' + x + 'px,' + y + 'px)';
      requestAnimationFrame(loop);
    }
    loop();
  }

  /* ── 3. Загрузочный сплэш ──────────────────────────────── */
  function fxBoot() {
    var el = doc.getElementById('bootSplash');
    if (!el) return;
    if (reduced) { el.remove(); return; }
    setTimeout(function () {
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 620);
    }, 950);
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

  /* ── 5. Параллакс aurora-фона при прокрутке ────────────── */
  function fxParallax() {
    var bg = doc.querySelector('.bg-aurora');
    if (!bg || reduced) return;
    var ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        bg.style.transform = 'translateY(' + (window.scrollY * -0.04) + 'px)';
        ticking = false;
      });
    }, { passive: true });
  }

  /* ── Старт ────────────────────────────────────────────── */
  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    fxBoot();
    fxParticles();
    fxCursorGlow();
    fxValueFlash();
    fxParallax();
  });
})();
