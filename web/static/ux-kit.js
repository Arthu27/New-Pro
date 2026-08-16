/* ═══ UX-kit — навигация и полировка панели ═══
 *
 * 1. Палитра Ctrl+K: страницы (из сайдбара) + глубокий поиск /api/ux/search
 *    (участники, транскрипты, триггеры, объявления), единая навигация стрелками.
 * 2. Хоткеи: g+d/g+t/g+r/… переходы, «/» — палитра, «?» — справка-модал.
 * 3. Избранное: звёздочка на пунктах меню, закреплённые страницы наверху.
 * 4. Плотные таблицы: переключатель в навбаре (body.compact).
 * 5. Личные prefs на сервере: тема/акцент/плотность следуют за учёткой.
 * 6. window.uxUndo(label, undoFn) — тост с кнопкой «Отменить» (6.5 сек).
 *
 * Всё безвредно при отсутствии элементов: каждый блок проверяет DOM.
 */
(function () {
  'use strict';
  if (window.__uxKitInstalled) return;
  window.__uxKitInstalled = true;

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function isTyping() {
    var t = (document.activeElement && document.activeElement.tagName) || '';
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT'
      || (document.activeElement && document.activeElement.isContentEditable);
  }

  /* ── 5. Личные prefs: сервер поверх localStorage ─────────────────────── */
  var prefsSaveTimer = null;
  function pushPrefs(patch) {
    clearTimeout(prefsSaveTimer);
    prefsSaveTimer = setTimeout(function () {
      try {
        fetch('/api/ux/prefs', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch), guardSilent: true
        });
      } catch (e) { /* prefs — фон, не критично */ }
    }, 400);
  }
  function pullPrefs() {
    try {
      fetch('/api/ux/prefs', { guardSilent: true })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d || !d.prefs) return;
          var p = d.prefs;
          if (p.theme && p.theme !== localStorage.getItem('aether_theme')) {
            document.documentElement.setAttribute('data-theme', p.theme);
            try { localStorage.setItem('aether_theme', p.theme); } catch (e) {}
          }
          if (p.accent && p.accent !== localStorage.getItem('aether_accent')) {
            if (typeof window.applyAccent === 'function') window.applyAccent(p.accent);
            try { localStorage.setItem('aether_accent', p.accent); } catch (e) {}
          }
          if (typeof p.compact === 'boolean') applyCompact(p.compact, true);
        }).catch(function () {});
    } catch (e) { /* нет сети — живём на localStorage */ }
  }

  // Тема: ловим клик по существующему переключателю (обработчик base.html уже
  // поменял data-theme — читаем итог и кладём на сервер).
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('#themeToggle') : null;
    if (t) pushPrefs({ theme: document.documentElement.getAttribute('data-theme') || 'dark' });
  });
  // Акцент: оборачиваем applyAccent — страница темы зовёт её при выборе цвета.
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.applyAccent === 'function' && !window.applyAccent.__uxWrapped) {
      var orig = window.applyAccent;
      var wrapped = function (hex) {
        orig(hex);
        if (hex) pushPrefs({ accent: String(hex).replace('#', '').length === 6
          ? '#' + String(hex).replace('#', '').toLowerCase() : hex });
      };
      wrapped.__uxWrapped = true;
      window.applyAccent = wrapped;
    }
    pullPrefs();
  });

  /* ── 1. Палитра Ctrl+K: страницы + глубокий поиск ────────────────────── */
  var palette = document.getElementById('kbdPalette');
  var input = document.getElementById('kbdPaletteInput');
  var results = document.getElementById('kbdPaletteResults');

  function getPages() {
    var items = [];
    document.querySelectorAll('.sidebar-nav .nav-link').forEach(function (a) {
      var href = a.getAttribute('href');
      if (!href || href === '#' || href.indexOf('javascript') === 0) return;
      if (a.closest('.nav-favs')) return; // избранное — дубли основных пунктов
      var span = a.querySelector('span');
      var title = span ? span.textContent.trim() : a.textContent.trim();
      var icon = a.querySelector('i');
      var groupEl = a.closest('.nav-group');
      var groupTitle = '';
      if (groupEl) {
        var gt = groupEl.querySelector('.nav-group-title .nav-group-label');
        if (gt) groupTitle = gt.textContent.trim();
      }
      items.push({ href: href, title: title, group: groupTitle || 'Страница',
                   icon: icon ? icon.className : 'fas fa-circle' });
    });
    return items;
  }

  if (palette && input && results) {
    var flat = [];          // плоский список для стрелок: {href, ...}
    var activeIdx = 0;
    var searchTimer = null;
    var searchAbort = null;
    var lastRequestQ = '';

    function itemHtml(p, idx) {
      return '<div class="kbd-palette-item' + (idx === activeIdx ? ' active' : '') +
        '" data-idx="' + idx + '">' +
        '<div class="kbd-palette-icon"><i class="' + esc(p.icon) + '"></i></div>' +
        '<div class="kbd-palette-text">' +
          '<div class="kbd-palette-title">' + esc(p.title) + '</div>' +
          '<div class="kbd-palette-group">' + esc(p.sub || p.group || '') + '</div>' +
        '</div>' +
        (p.type === 'page' ? '' : '<span class="kbd-palette-go"><i class="fas fa-arrow-right"></i></span>') +
      '</div>';
    }

    function render(localPages, remoteGroups) {
      flat = [];
      var html = '';
      if (localPages.length) {
        html += '<div class="palette-sec">Страницы</div>';
        localPages.forEach(function (p) { html += itemHtml(p, flat.length); flat.push(p); });
      }
      (remoteGroups || []).forEach(function (g) {
        html += '<div class="palette-sec">' + esc(g.title) + '</div>';
        g.items.forEach(function (p) { html += itemHtml(p, flat.length); flat.push(p); });
      });
      if (!flat.length) {
        results.innerHTML = '<div class="empty-state"><i class="fas fa-search"></i>' +
          '<p>Ничего не найдено</p><p class="empty-tip">Пробуйте название страницы, ник участника или текст триггера</p></div>';
        return;
      }
      results.innerHTML = html;
      results.querySelectorAll('.kbd-palette-item').forEach(function (el) {
        el.addEventListener('click', function () {
          var p = flat[parseInt(el.getAttribute('data-idx'), 10)];
          if (p) window.location.href = p.href;
        });
      });
      var act = results.querySelector('.kbd-palette-item.active');
      if (act) act.scrollIntoView({ block: 'nearest' });
    }

    function filterPages(q) {
      var pages = getPages();
      if (!q) return pages;
      var lq = q.toLowerCase();
      return pages.filter(function (p) {
        return p.title.toLowerCase().indexOf(lq) !== -1 ||
               p.group.toLowerCase().indexOf(lq) !== -1 ||
               p.href.toLowerCase().indexOf(lq) !== -1;
      });
    }

    function refresh() {
      var q = input.value.trim();
      activeIdx = 0;
      render(filterPages(q), null);
      clearTimeout(searchTimer);
      if (searchAbort) { searchAbort.abort(); searchAbort = null; }
      if (q.length < 2) { lastRequestQ = ''; return; }
      searchTimer = setTimeout(function () {
        lastRequestQ = q;
        searchAbort = new AbortController();
        fetch('/api/ux/search?q=' + encodeURIComponent(q), {
          guardSilent: true, signal: searchAbort.signal
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (d) {
            if (!d || input.value.trim() !== lastRequestQ) return;
            render(filterPages(input.value.trim()), d.groups || []);
          }).catch(function () { /* офлайн/abort — остаются страницы */ });
      }, 250);
    }

    function open() {
      palette.classList.add('open');
      input.value = '';
      input.focus();
      refresh();
    }
    function close() {
      palette.classList.remove('open');
      input.blur();
    }
    window.uxPaletteOpen = open;

    input.addEventListener('input', refresh);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') {
        e.preventDefault(); activeIdx = Math.min(activeIdx + 1, flat.length - 1);
        results.querySelectorAll('.kbd-palette-item').forEach(function (el) {
          el.classList.toggle('active', parseInt(el.getAttribute('data-idx'), 10) === activeIdx);
        });
        var act = results.querySelector('.kbd-palette-item.active');
        if (act) act.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0);
        results.querySelectorAll('.kbd-palette-item').forEach(function (el) {
          el.classList.toggle('active', parseInt(el.getAttribute('data-idx'), 10) === activeIdx);
        });
        var act2 = results.querySelector('.kbd-palette-item.active');
        if (act2) act2.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var p = flat[activeIdx];
        if (p) window.location.href = p.href;
      } else if (e.key === 'Escape') {
        e.preventDefault(); close();
      }
    });
    palette.addEventListener('click', function (e) { if (e.target === palette) close(); });

    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K' || e.key === 'л' || e.key === 'Л')) {
        e.preventDefault();
        if (palette.classList.contains('open')) close(); else open();
      } else if (e.key === '/' && !palette.classList.contains('open') && !isTyping()
                 && !e.metaKey && !e.ctrlKey) {
        e.preventDefault(); open();
      }
    });
    var gsBtn = document.getElementById('globalSearchBtn');
    if (gsBtn) gsBtn.addEventListener('click', function () { open(); });
  }

  /* ── 2. Хоткеи g+<клавиша> + справка по «?» ──────────────────────────── */
  var G_MAP = {
    'd': ['/', 'Обзор'], 'g': ['/guilds', 'Серверы'], 'a': ['/analytics', 'Аналитика'],
    's': ['/bot-stats', 'Статистика бота'], 'l': ['/logs', 'Логи'],
    'w': ['/warnings', 'Предупреждения'], 'u': ['/users', 'Пользователи'],
    'm': ['/mod-history', 'История модерации'], 'c': ['/commands', 'Команды'],
    't': ['/ticket-search', 'Тикеты'], 'r': ['/transcripts', 'Транскрипты'],
    'n': ['/announcements', 'Объявления'], 'o': ['/automation', 'Автоматика'],
    'e': ['/economy', 'Экономика'], 'p': ['/polls', 'Опросы']
  };
  var gArmed = false;
  var gTimer = null;

  function helpModal() {
    var m = document.getElementById('hkHelp');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'hkHelp';
    m.className = 'hk-modal';
    var rows = Object.keys(G_MAP).map(function (k) {
      return '<div class="hk-row"><span class="hk-keys"><kbd>G</kbd><kbd>' + esc(k.toUpperCase()) + '</kbd></span><span>' + esc(G_MAP[k][1]) + '</span></div>';
    }).join('');
    m.innerHTML =
      '<div class="hk-panel" role="dialog" aria-label="Горячие клавиши">' +
        '<div class="hk-head"><i class="fas fa-keyboard"></i> Горячие клавиши' +
          '<button type="button" class="hk-close" aria-label="Закрыть"><i class="fas fa-times"></i></button></div>' +
        '<div class="hk-body">' +
          '<div class="hk-row"><span class="hk-keys"><kbd>Ctrl</kbd><kbd>K</kbd></span><span>Глобальный поиск: страницы, участники, транскрипты</span></div>' +
          '<div class="hk-row"><span class="hk-keys"><kbd>/</kbd></span><span>Тоже открывает поиск</span></div>' +
          rows +
          '<div class="hk-row"><span class="hk-keys"><kbd>?</kbd></span><span>Эта справка</span></div>' +
          '<div class="hk-row"><span class="hk-keys"><kbd>Esc</kbd></span><span>Закрыть окно/поиск</span></div>' +
        '</div>' +
        '<div class="hk-foot">Хоткеи не срабатывают, когда курсор в поле ввода</div>' +
      '</div>';
    document.body.appendChild(m);
    m.addEventListener('click', function (e) {
      if (e.target === m || e.target.closest('.hk-close')) m.classList.remove('open');
    });
    return m;
  }

  document.addEventListener('keydown', function (e) {
    if (isTyping() || e.metaKey || e.ctrlKey || e.altKey) return;
    var palOpen = palette && palette.classList.contains('open');
    if (e.key === '?' || (e.shiftKey && e.code === 'Slash')) {
      if (!palOpen) { e.preventDefault(); helpModal().classList.toggle('open'); }
      return;
    }
    if (palOpen) return;
    if (gArmed) {
      gArmed = false;
      clearTimeout(gTimer);
      var hit = G_MAP[e.key.toLowerCase()];
      if (hit) { e.preventDefault(); window.location.href = hit[0]; }
      return;
    }
    if (e.key === 'g' || e.key === 'G' || e.key === 'п' || e.key === 'П') {
      gArmed = true;
      clearTimeout(gTimer);
      gTimer = setTimeout(function () { gArmed = false; }, 1200);
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var m = document.getElementById('hkHelp');
      if (m && m.classList.contains('open')) m.classList.remove('open');
    }
  });

  /* ── 3. Избранное в сайдбаре ──────────────────────────────────────────── */
  var FAV_KEY = 'aether_favs';
  function favsGet() {
    try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]'); } catch (e) { return []; }
  }
  function favsSet(list) {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(list.slice(0, 20))); } catch (e) {}
  }
  function favsBlock() {
    var favs = favsGet();
    var old = document.querySelector('.nav-favs');
    if (old) old.remove();
    if (!favs.length) return;
    var nav = document.getElementById('sidebarNav');
    if (!nav) return;
    var box = document.createElement('div');
    box.className = 'nav-group nav-favs';
    var html = '<div class="nav-group-title nav-favs-title"><span class="nav-group-icon"><i class="fas fa-star"></i></span><span class="nav-group-label">Избранное</span></div><div class="nav-favs-items">';
    favs.forEach(function (path) {
      var src = null;
      document.querySelectorAll('.sidebar-nav .nav-link').forEach(function (x) {
        if (!src && x.getAttribute('href') === path && !x.closest('.nav-favs')) src = x;
      });
      if (!src) return;
      var icon = src.querySelector('i');
      var span = src.querySelector('span');
      html += '<a href="' + esc(path) + '" class="nav-link"><i class="' + (icon ? esc(icon.className) : 'fas fa-circle') + '"></i> <span>' + esc(span ? span.textContent : path) + '</span></a>';
    });
    box.innerHTML = html + '</div>';
    nav.insertBefore(box, nav.firstChild);
  }
  function favsInit() {
    document.querySelectorAll('.sidebar-nav .nav-link').forEach(function (a) {
      var href = a.getAttribute('href') || '';
      if (!href || href === '#') return;
      var star = document.createElement('span');
      star.className = 'fav-star' + (favsGet().indexOf(href) !== -1 ? ' on' : '');
      star.title = 'В избранное';
      star.setAttribute('aria-label', 'В избранное');
      star.innerHTML = '<i class="fas fa-star"></i>';
      star.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var favs = favsGet();
        if (favs.indexOf(href) !== -1) favs = favs.filter(function (x) { return x !== href; });
        else favs.unshift(href);
        favsSet(favs);
        document.querySelectorAll('.sidebar-nav .nav-link').forEach(function (x) {
          if (x.getAttribute('href') === href) {
            var st = x.querySelector('.fav-star');
            if (st) st.classList.toggle('on', favs.indexOf(href) !== -1);
          }
        });
        favsBlock();
      });
      a.appendChild(star);
    });
    favsBlock();
  }
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(favsInit, 0); // после отрисовки сайдбара base.html
  });

  /* ── 4. Плотные таблицы ───────────────────────────────────────────────── */
  function applyCompact(on, silent) {
    document.body.classList.toggle('compact', !!on);
    try { localStorage.setItem('aether_compact', on ? '1' : '0'); } catch (e) {}
    var b = document.getElementById('compactToggle');
    if (b) b.classList.toggle('active', !!on);
    if (!silent && typeof window.showToast === 'function') {
      window.showToast(on ? 'Плотные таблицы включены' : 'Обычные таблицы', true);
    }
  }
  window.applyCompact = applyCompact;
  document.addEventListener('DOMContentLoaded', function () {
    var nav = document.querySelector('.navbar-right');
    if (!nav || document.getElementById('compactToggle')) return;
    var btn = document.createElement('button');
    btn.id = 'compactToggle';
    btn.className = 'nav-icon-btn';
    btn.title = 'Плотные таблицы';
    btn.setAttribute('aria-label', 'Плотные таблицы');
    btn.innerHTML = '<i class="fas fa-compress-alt"></i>';
    btn.addEventListener('click', function () {
      var on = !document.body.classList.contains('compact');
      applyCompact(on);
      pushPrefs({ compact: on });
    });
    var fs = document.getElementById('fullscreenBtn');
    if (fs && fs.parentNode) fs.parentNode.insertBefore(btn, fs);
    else nav.insertBefore(btn, nav.firstChild);
    if (localStorage.getItem('aether_compact') === '1') applyCompact(true, true);
  });

  /* ── 6. Undo-тост: действие с отменой (6.5 сек) ──────────────────────── */
  window.uxUndo = function (label, undoFn) {
    var host = document.getElementById('toastHost');
    if (!host) { if (typeof undoFn === 'function') { /* некуда показать — отмены нет */ } return; }
    var el = document.createElement('div');
    el.className = 'ux-undo';
    el.innerHTML = '<span class="ux-undo-msg">' + esc(label) + '</span>' +
      '<button type="button" class="ux-undo-btn"><i class="fas fa-rotate-left"></i> Отменить</button>' +
      '<span class="ux-undo-bar"></span>';
    var done = false;
    var kill = setTimeout(function () { done = true; el.classList.add('out'); setTimeout(function () { el.remove(); }, 300); }, 6500);
    el.querySelector('.ux-undo-btn').addEventListener('click', function () {
      if (done) return;
      done = true;
      clearTimeout(kill);
      if (typeof undoFn === 'function') {
        try { undoFn(); } catch (e) { /* отмена — лучшая попытка */ }
      }
      if (typeof window.showToast === 'function') window.showToast('Отменено', true);
      el.remove();
    });
    host.appendChild(el);
  };

  window.UX = { esc: esc, undo: window.uxUndo, openPalette: window.uxPaletteOpen };
})();
