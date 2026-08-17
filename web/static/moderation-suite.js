/* Aether Moderation Suite
 * UX для 18 инструментов: секции sidebar, навигатор, поиск, recent и Alt+M.
 */
(function () {
  'use strict';

  var SECTION_KEY = 'aether_mod_sections_v1';
  var RECENT_KEY = 'aether_mod_recent_v1';

  function readJSON(key, fallback) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || 'null');
      return value == null ? fallback : value;
    } catch (e) {
      return fallback;
    }
  }

  function saveJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function normalise(value) {
    return String(value || '').toLocaleLowerCase('ru-RU').replace(/\s+/g, ' ').trim();
  }

  function setupSidebarSections() {
    var sections = Array.prototype.slice.call(document.querySelectorAll('[data-mod-section]'));
    if (!sections.length) return;
    var state = readJSON(SECTION_KEY, {});

    function setOpen(section, open, persist) {
      var key = section.getAttribute('data-mod-section');
      var button = section.querySelector('.nav-subgroup-title');
      section.classList.toggle('open', open);
      if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (persist && key) {
        state[key] = open;
        saveJSON(SECTION_KEY, state);
      }
    }

    sections.forEach(function (section, index) {
      var key = section.getAttribute('data-mod-section');
      var hasActive = section.classList.contains('has-active');
      var open = hasActive || state[key] === true || (state[key] === undefined && index === 0);
      setOpen(section, open, false);
      var button = section.querySelector('.nav-subgroup-title');
      if (button) {
        button.addEventListener('click', function (event) {
          event.preventDefault();
          event.stopPropagation();
          setOpen(section, !section.classList.contains('open'), true);
        });
      }
    });

    // Общий поиск sidebar уже фильтрует ссылки. Здесь раскрываем только секции,
    // где есть совпадение, а после очистки возвращаем сохранённое состояние.
    var search = document.getElementById('sidebarSearch');
    if (search) {
      search.addEventListener('input', function () {
        var query = normalise(search.value);
        sections.forEach(function (section, index) {
          if (query) {
            var matches = Array.prototype.some.call(
              section.querySelectorAll('.nav-link'),
              function (link) { return normalise(link.textContent).indexOf(query) !== -1; }
            );
            section.style.display = matches ? '' : 'none';
            setOpen(section, matches, false);
          } else {
            section.style.display = '';
            var key = section.getAttribute('data-mod-section');
            var open = section.classList.contains('has-active') || state[key] === true ||
              (state[key] === undefined && index === 0);
            setOpen(section, open, false);
          }
        });
      });
    }
  }

  function setupSuite() {
    var bar = document.querySelector('[data-mod-suite]');
    var overlay = document.querySelector('[data-mod-overlay]');
    if (!bar || !overlay) return;

    var dialog = overlay.querySelector('.mod-suite-dialog');
    var openButton = bar.querySelector('[data-mod-open]');
    var closeButton = overlay.querySelector('[data-mod-close]');
    var search = overlay.querySelector('[data-mod-search]');
    var count = overlay.querySelector('[data-mod-result-count]');
    var empty = overlay.querySelector('[data-mod-empty]');
    var recentBox = overlay.querySelector('[data-mod-recent]');
    var cards = Array.prototype.slice.call(overlay.querySelectorAll('[data-mod-card]'));
    var sections = Array.prototype.slice.call(overlay.querySelectorAll('[data-mod-dialog-section]'));
    var currentPath = bar.getAttribute('data-current-path') || window.location.pathname;
    var enterButton = bar.querySelector('[data-mod-enter]');
    var workspace = document.querySelector('[data-mod-workspace]');
    var previousFocus = null;

    function enterWorkspace() {
      if (!workspace) return;
      var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      workspace.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
      var target = workspace.querySelector('input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),a[href]');
      if (target) window.setTimeout(function () { target.focus({ preventScroll: true }); }, 350);
    }

    function rememberCurrent() {
      var current = cards.filter(function (card) {
        return card.getAttribute('data-mod-card-path') === currentPath;
      })[0];
      if (!current) return;
      var recent = readJSON(RECENT_KEY, []);
      if (!Array.isArray(recent)) recent = [];
      recent = recent.filter(function (path) { return path !== currentPath; });
      recent.unshift(currentPath);
      saveJSON(RECENT_KEY, recent.slice(0, 5));
    }

    function renderRecent() {
      if (!recentBox) return;
      recentBox.textContent = '';
      var recent = readJSON(RECENT_KEY, []);
      if (!Array.isArray(recent)) recent = [];
      var byPath = {};
      cards.forEach(function (card) {
        byPath[card.getAttribute('data-mod-card-path')] = card;
      });
      var paths = recent.filter(function (path) { return byPath[path]; }).slice(0, 4);
      if (!paths.length) {
        recentBox.hidden = true;
        return;
      }
      var label = document.createElement('span');
      label.textContent = 'Недавно';
      recentBox.appendChild(label);
      paths.forEach(function (path) {
        var source = byPath[path];
        var link = document.createElement('a');
        link.href = path;
        link.textContent = source.getAttribute('data-mod-card-label') || path;
        if (path === currentPath) link.setAttribute('aria-current', 'page');
        recentBox.appendChild(link);
      });
      recentBox.hidden = false;
    }

    function filterCards() {
      var query = normalise(search && search.value);
      var visible = 0;
      cards.forEach(function (card) {
        var haystack = normalise(card.getAttribute('data-mod-search-text'));
        var show = !query || haystack.indexOf(query) !== -1;
        card.hidden = !show;
        if (show) visible += 1;
      });
      sections.forEach(function (section) {
        section.hidden = !section.querySelector('[data-mod-card]:not([hidden])');
      });
      if (count) count.textContent = String(visible);
      if (empty) empty.hidden = visible !== 0;
      if (recentBox) recentBox.hidden = !!query || !recentBox.children.length;
    }

    function focusable() {
      return Array.prototype.slice.call(dialog.querySelectorAll(
        'a[href]:not([hidden]), button:not([disabled]), input:not([disabled])'
      )).filter(function (element) {
        return element.offsetParent !== null && !element.closest('[hidden]');
      });
    }

    function openSuite() {
      if (!overlay.hidden) return;
      previousFocus = document.activeElement;
      overlay.hidden = false;
      document.body.classList.add('mod-suite-open');
      renderRecent();
      if (search) {
        search.value = '';
        filterCards();
        window.setTimeout(function () { search.focus(); }, 30);
      }
    }

    function closeSuite() {
      if (overlay.hidden) return;
      overlay.hidden = true;
      document.body.classList.remove('mod-suite-open');
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
    }

    function setupSteps() {
      var index = cards.findIndex(function (card) {
        return card.getAttribute('data-mod-card-path') === currentPath;
      });
      if (index < 0 || !cards.length) return;
      var prev = cards[(index - 1 + cards.length) % cards.length];
      var next = cards[(index + 1) % cards.length];
      var prevLink = bar.querySelector('[data-mod-prev]');
      var nextLink = bar.querySelector('[data-mod-next]');
      if (prevLink) {
        prevLink.href = prev.getAttribute('href');
        prevLink.title = 'Назад: ' + (prev.getAttribute('data-mod-card-label') || 'инструмент');
      }
      if (nextLink) {
        nextLink.href = next.getAttribute('href');
        nextLink.title = 'Далее: ' + (next.getAttribute('data-mod-card-label') || 'инструмент');
      }
    }

    if (openButton) openButton.addEventListener('click', openSuite);
    if (enterButton) enterButton.addEventListener('click', enterWorkspace);
    if (closeButton) closeButton.addEventListener('click', closeSuite);
    if (search) search.addEventListener('input', filterCards);
    overlay.addEventListener('mousedown', function (event) {
      if (event.target === overlay) closeSuite();
    });

    document.addEventListener('keydown', function (event) {
      if (event.altKey && !event.ctrlKey && !event.metaKey && normalise(event.key) === 'm') {
        event.preventDefault();
        if (overlay.hidden) openSuite(); else closeSuite();
        return;
      }
      if (overlay.hidden) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closeSuite();
        return;
      }
      if (event.key === '/' && document.activeElement !== search) {
        event.preventDefault();
        if (search) search.focus();
        return;
      }
      // Фокус не уходит под модальное окно.
      if (event.key === 'Tab') {
        var items = focusable();
        if (!items.length) return;
        var first = items[0];
        var last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    rememberCurrent();
    renderRecent();
    setupSteps();
    filterCards();
  }

  function init() {
    setupSidebarSections();
    setupSuite();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
