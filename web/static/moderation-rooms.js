/* Moderation Rooms v5 — compact actions, explicit state controls and stable live UI. */
(function () {
  'use strict';

  var utility = document.querySelector('[data-mod-utility]');
  var workspace = document.querySelector('[data-mod-workspace]');
  if (!utility || !workspace) return;

  var LIVE_KEY = 'aether_mod_live_paused_v1';
  var DENSITY_KEY = 'aether_mod_density_v1';
  var liveButton = utility.querySelector('[data-room-live]');
  var densityButton = utility.querySelector('[data-room-density]');
  var copyButton = utility.querySelector('[data-room-copy]');
  var refreshButton = utility.querySelector('[data-room-refresh]');

  // v4 focus mode changed the page geometry and could hide navigation context.
  // Remove its old persisted value and guarantee the normal layout.
  document.body.classList.remove('mod-focus-workspace');
  try { localStorage.removeItem('aether_mod_focus_v1'); } catch (_) {}

  function read(key) {
    try { return localStorage.getItem(key) === '1'; } catch (_) { return false; }
  }

  function write(key, value) {
    try { localStorage.setItem(key, value ? '1' : '0'); } catch (_) {}
  }

  function applyLive(paused) {
    const wasPaused = Boolean(window.__modLivePaused);
    window.__modLivePaused = paused;
    document.body.classList.toggle('mod-live-paused', paused);
    liveButton.setAttribute('aria-pressed', String(paused));
    liveButton.setAttribute('aria-label', paused ? 'Возобновить автообновление' : 'Приостановить автообновление');
    liveButton.textContent = paused ? 'Обновление на паузе' : 'Автообновление';
    write(LIVE_KEY, paused);
    if (wasPaused && !paused) {
      document.dispatchEvent(new CustomEvent('moderation:live-resume'));
    }
  }

  function applyDensity(compact) {
    document.body.classList.toggle('mod-density-compact', compact);
    densityButton.setAttribute('aria-pressed', String(compact));
    densityButton.textContent = compact ? 'Обычный вид' : 'Компактный вид';
    write(DENSITY_KEY, compact);
  }

  function flash(button, text) {
    var previous = button.textContent;
    button.textContent = text;
    button.classList.add('is-confirmed');
    window.setTimeout(function () {
      button.textContent = previous;
      button.classList.remove('is-confirmed');
    }, 1500);
  }

  function jumpTo(selector, mode) {
    var target;
    try { target = document.querySelector(selector); } catch (_) { target = null; }
    if (!target) return false;
    if (mode === 'click' && typeof target.click === 'function') target.click();
    window.setTimeout(function () {
      target.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center'});
      if (mode === 'focus' && typeof target.focus === 'function') target.focus({preventScroll: true});
      else {
        target.classList.add('mod-jump-highlight');
        window.setTimeout(function () { target.classList.remove('mod-jump-highlight'); }, 1100);
      }
    }, mode === 'click' ? 40 : 0);
    return true;
  }

  Array.prototype.forEach.call(utility.querySelectorAll('[data-room-jump]'), function (button) {
    button.addEventListener('click', function () {
      var found = jumpTo(button.getAttribute('data-room-jump'), button.getAttribute('data-room-mode') || 'scroll');
      if (!found) flash(button, 'Недоступно для вашей роли');
    });
  });

  liveButton.addEventListener('click', function () {
    applyLive(!window.__modLivePaused);
  });

  densityButton.addEventListener('click', function () {
    applyDensity(!document.body.classList.contains('mod-density-compact'));
  });

  copyButton.addEventListener('click', function () {
    var done = function () { flash(copyButton, 'Ссылка скопирована'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(window.location.href).then(done).catch(function () {});
      return;
    }
    var input = document.createElement('textarea');
    input.value = window.location.href;
    input.style.position = 'fixed'; input.style.opacity = '0';
    document.body.appendChild(input); input.select();
    try { document.execCommand('copy'); done(); } catch (_) {}
    input.remove();
  });

  refreshButton.addEventListener('click', function () {
    refreshButton.disabled = true;
    refreshButton.textContent = 'Обновляем…';
    window.location.reload();
  });

  function stateIsOn(control) {
    if (control.matches('label.tj-switch')) {
      var input = control.querySelector('input');
      return !!(input && input.checked);
    }
    return control.classList.contains('on');
  }

  function describeSwitch(control) {
    var on = stateIsOn(control);
    if (!control.hasAttribute('role')) control.setAttribute('role', 'switch');
    control.setAttribute('aria-checked', String(on));
    control.setAttribute('data-state-label', on ? 'Активно' : 'На паузе');
    if (!control.getAttribute('aria-label')) {
      var card = control.closest('section, .af-tog, .tj-field, .sc-card');
      var title = card && card.querySelector('h3, h2, .l, .tj-field-label, .lab');
      control.setAttribute('aria-label', (title ? title.textContent.trim() + ': ' : '') + (on ? 'активно' : 'на паузе'));
    }
  }

  function syncStateControls(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.af-switch, .toggle, .af-sw, .sc-sw, label.tj-switch'), describeSwitch);
  }

  var observer = new MutationObserver(function (records) {
    records.forEach(function (record) {
      if (record.type === 'attributes' && record.target.matches && record.target.matches('.af-switch, .toggle, .af-sw, .sc-sw, label.tj-switch')) {
        describeSwitch(record.target);
      }
      Array.prototype.forEach.call(record.addedNodes || [], function (node) {
        if (node.nodeType === 1) syncStateControls(node);
      });
    });
  });
  observer.observe(workspace, {subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'checked']});
  workspace.addEventListener('change', function (event) {
    var label = event.target && event.target.closest ? event.target.closest('label.tj-switch') : null;
    if (label) describeSwitch(label);
  });

  document.addEventListener('keydown', function (event) {
    if (event.altKey && event.key.toLowerCase() === 'l') {
      event.preventDefault(); applyLive(!window.__modLivePaused);
    }
    if (event.altKey && event.key.toLowerCase() === 'd') {
      event.preventDefault(); applyDensity(!document.body.classList.contains('mod-density-compact'));
    }
  });

  applyLive(read(LIVE_KEY));
  applyDensity(read(DENSITY_KEY));
  syncStateControls(document);
})();
