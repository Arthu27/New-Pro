/* Aether Quality Suite
 * Сквозная доводка всех страниц без вмешательства в их доменную логику.
 */
(function () {
  'use strict';
  if (window.__qualitySuiteInstalled) return;
  window.__qualitySuiteInstalled = true;

  var progress = document.getElementById('routeProgress');
  var connection = document.getElementById('qualityConnection');
  var sysConnection = document.getElementById('sysConnection');
  var progressTimer = null;
  var finishTimer = null;
  var activeRequests = 0;
  var syncTimer = null;

  function progressStart() {
    if (!progress) return;
    clearTimeout(finishTimer);
    progress.classList.remove('is-done');
    progress.classList.add('is-active');
    progress.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-navigating');
  }

  function progressDone() {
    if (!progress) return;
    clearTimeout(progressTimer);
    progress.classList.remove('is-active');
    progress.classList.add('is-done');
    document.body.classList.remove('is-navigating');
    finishTimer = window.setTimeout(function () {
      progress.classList.remove('is-done');
      progress.setAttribute('aria-hidden', 'true');
    }, 240);
  }

  function setConnection(state, label) {
    var online = state !== 'offline';
    if (connection) {
      connection.classList.remove('is-online', 'is-syncing', 'is-offline');
      connection.classList.add('is-' + state);
      var text = connection.querySelector('.quality-connection-label');
      if (text) text.textContent = label;
      connection.title = state === 'offline'
        ? 'Нет соединения. Изменения могут не сохраниться.'
        : state === 'syncing' ? 'Обмен данными с сервером' : 'Соединение с панелью установлено';
    }
    if (sysConnection) {
      sysConnection.textContent = online ? (state === 'syncing' ? 'Sync' : 'Online') : 'Offline';
      sysConnection.style.color = online ? '' : 'var(--err)';
    }
  }

  function requestStarted() {
    activeRequests += 1;
    clearTimeout(syncTimer);
    syncTimer = window.setTimeout(function () {
      if (activeRequests > 0 && navigator.onLine !== false) setConnection('syncing', 'Синхронизация');
    }, 500);
  }

  function requestFinished(networkFailed) {
    activeRequests = Math.max(0, activeRequests - 1);
    if (networkFailed || navigator.onLine === false) {
      setConnection('offline', 'Нет сети');
      return;
    }
    if (activeRequests === 0) {
      clearTimeout(syncTimer);
      setConnection('online', 'В сети');
    }
  }

  function setupFetchHealth() {
    if (!window.fetch || window.fetch.__qualityWrapped) return;
    var original = window.fetch.bind(window);
    var wrapped = function () {
      requestStarted();
      return original.apply(null, arguments).then(function (response) {
        requestFinished(false);
        return response;
      }, function (error) {
        requestFinished(true);
        throw error;
      });
    };
    wrapped.__qualityWrapped = true;
    window.fetch = wrapped;
  }

  function samePageHash(url) {
    return url.pathname === window.location.pathname &&
      url.search === window.location.search && !!url.hash;
  }

  function setupNavigationProgress() {
    document.addEventListener('click', function (event) {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
          event.shiftKey || event.altKey) return;
      var link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
      if (!link || link.hasAttribute('download') || link.target === '_blank') return;
      var href = link.getAttribute('href') || '';
      if (!href || href === '#' || href.indexOf('javascript:') === 0) return;
      try {
        var url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || samePageHash(url)) return;
        progressTimer = window.setTimeout(function () {
          if (!event.defaultPrevented) progressStart();
        }, 70);
      } catch (e) {}
    }, true);

    document.addEventListener('submit', function (event) {
      progressTimer = window.setTimeout(function () {
        if (!event.defaultPrevented) progressStart();
      }, 70);
    });
    window.addEventListener('beforeunload', progressStart);
    window.addEventListener('pageshow', progressDone);
    window.addEventListener('load', progressDone);
  }

  function iconLabel(button) {
    return button.getAttribute('title') || button.getAttribute('data-tooltip') ||
      button.getAttribute('data-label') || '';
  }

  function enhanceImage(image) {
    if (!image.hasAttribute('alt')) image.setAttribute('alt', '');
    if (!image.hasAttribute('decoding')) image.setAttribute('decoding', 'async');
    if (image.dataset.qualityImage === '1') return;
    image.dataset.qualityImage = '1';
    image.addEventListener('error', function () {
      image.dataset.qualityBroken = 'true';
    });
    image.addEventListener('load', function () {
      delete image.dataset.qualityBroken;
    });
  }

  function enhanceButton(button) {
    if (!button.hasAttribute('type') && !button.closest('form')) button.type = 'button';
    var visibleText = String(button.textContent || '').replace(/\s+/g, ' ').trim();
    if (!visibleText && !button.getAttribute('aria-label')) {
      var label = iconLabel(button);
      if (label) button.setAttribute('aria-label', label);
    }
    if (!visibleText && button.querySelector('i, svg')) button.dataset.qualityIconOnly = 'true';
  }

  function updateTableEdges(shell) {
    var overflow = shell.scrollWidth > shell.clientWidth + 2;
    shell.classList.toggle('is-overflowing', overflow);
    shell.classList.toggle('is-at-start', !overflow || shell.scrollLeft <= 2);
    shell.classList.toggle('is-at-end', !overflow ||
      shell.scrollLeft + shell.clientWidth >= shell.scrollWidth - 2);
  }

  function enhanceTable(table) {
    if (table.dataset.qualityTable === '1') return;
    table.dataset.qualityTable = '1';
    var parent = table.parentElement;
    var shell = null;
    if (parent && /(?:table|scroll|responsive|overflow)/i.test(parent.className || '')) {
      shell = parent;
      shell.classList.add('quality-table-shell');
    } else if (parent) {
      shell = document.createElement('div');
      shell.className = 'quality-table-shell';
      parent.insertBefore(shell, table);
      shell.appendChild(table);
    }
    if (!shell) return;
    if (!shell.hasAttribute('tabindex')) shell.tabIndex = 0;
    if (!shell.getAttribute('aria-label')) shell.setAttribute('aria-label', 'Прокручиваемая таблица');
    shell.addEventListener('scroll', function () { updateTableEdges(shell); }, { passive: true });
    window.requestAnimationFrame(function () { updateTableEdges(shell); });
  }

  function enhanceStatus(element) {
    if (!element.hasAttribute('role')) element.setAttribute('role', 'status');
    if (!element.hasAttribute('aria-live')) element.setAttribute('aria-live', 'polite');
  }

  function enhanceRoot(root) {
    if (!root || !root.querySelectorAll) return;
    var select = function (selector) {
      var result = Array.prototype.slice.call(root.querySelectorAll(selector));
      if (root.matches && root.matches(selector)) result.unshift(root);
      return result;
    };
    select('img').forEach(enhanceImage);
    select('button').forEach(enhanceButton);
    select('table').forEach(enhanceTable);
    select('.msg, .result, .status-msg, .form-result').forEach(enhanceStatus);
    select('.empty-state').forEach(function (element) {
      element.classList.add('quality-empty-upgraded');
      if (!element.hasAttribute('role')) element.setAttribute('role', 'status');
    });
    select('a[target="_blank"]').forEach(function (link) {
      var rel = (link.getAttribute('rel') || '').split(/\s+/).filter(Boolean);
      if (rel.indexOf('noopener') === -1) rel.push('noopener');
      if (rel.indexOf('noreferrer') === -1) rel.push('noreferrer');
      link.setAttribute('rel', rel.join(' '));
    });
  }

  function setupDynamicEnhancement() {
    enhanceRoot(document);
    var queued = [];
    var scheduled = false;
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        Array.prototype.forEach.call(mutation.addedNodes || [], function (node) {
          if (node && node.nodeType === 1) queued.push(node);
        });
      });
      if (!scheduled && queued.length) {
        scheduled = true;
        window.requestAnimationFrame(function () {
          var batch = queued.splice(0, queued.length);
          scheduled = false;
          batch.forEach(enhanceRoot);
        });
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', function () {
      document.querySelectorAll('.quality-table-shell').forEach(updateTableEdges);
    }, { passive: true });
  }

  function setupKeyboardWidgets() {
    var userPill = document.querySelector('.user-pill');
    if (userPill) {
      userPill.tabIndex = 0;
      userPill.setAttribute('role', 'button');
      userPill.setAttribute('aria-haspopup', 'menu');
      userPill.setAttribute('aria-expanded', userPill.classList.contains('open') ? 'true' : 'false');
      userPill.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          userPill.click();
          userPill.setAttribute('aria-expanded', userPill.classList.contains('open') ? 'true' : 'false');
        } else if (event.key === 'Escape') {
          userPill.classList.remove('open');
          userPill.setAttribute('aria-expanded', 'false');
        }
      });
      userPill.addEventListener('click', function () {
        window.setTimeout(function () {
          userPill.setAttribute('aria-expanded', userPill.classList.contains('open') ? 'true' : 'false');
        }, 0);
      });
    }
  }

  window.qualitySetLoading = function (button, loading) {
    if (!button) return;
    button.classList.toggle('is-loading', !!loading);
    button.setAttribute('aria-busy', loading ? 'true' : 'false');
    if (loading) {
      button.dataset.qualityWasDisabled = button.disabled ? '1' : '0';
      button.disabled = true;
    } else {
      if (button.dataset.qualityWasDisabled !== '1') button.disabled = false;
      delete button.dataset.qualityWasDisabled;
    }
  };

  function init() {
    setupFetchHealth();
    setupNavigationProgress();
    setupDynamicEnhancement();
    setupKeyboardWidgets();
    setConnection(navigator.onLine === false ? 'offline' : 'online',
      navigator.onLine === false ? 'Нет сети' : 'В сети');
    progressDone();
  }

  window.addEventListener('online', function () { setConnection('online', 'В сети'); });
  window.addEventListener('offline', function () { setConnection('offline', 'Нет сети'); });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
