/* Hakumo · Aurora FX — v16 (progressive enhancement, ничего не ломает)
 *
 * Две маленькие фичи для web/static/panel-aurora.css, работают на ЛЮБОЙ
 * странице панели без правки шаблонов:
 *   1. Курсор-прожектор: --mx/--my на .panel/.card под курсором.
 *   2. Каскад появления: --av-i по порядку карточек на странице.
 *
 * Полностью пассивно — если что-то пошло не так, просто нет эффекта
 * (никаких window.* переопределений, никаких обязательных зависимостей).
 */
(function () {
  'use strict';

  var reduced = false;
  try {
    reduced = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) { reduced = false; }

  function indexCards() {
    var nodes = document.querySelectorAll(
      '.main-content .panel, .main-content .card, .main-content .kpi, ' +
      '.main-content .stat-box, .main-content .mt-kpi');
    for (var i = 0; i < nodes.length; i++) {
      if (i < 24) nodes[i].style.setProperty('--av-i', String(i));
    }
  }

  if (reduced) {
    // Каскад отключён CSS-медиа-запросом; курсор-прожектор не подключаем.
    return;
  }

  var hoverCapable = true;
  try {
    hoverCapable = window.matchMedia && window.matchMedia('(hover: hover)').matches;
  } catch (e) { hoverCapable = true; }

  function attachSpotlight() {
    if (!hoverCapable) return;
    var current = null;

    function onMove(e) {
      var el = e.target && e.target.closest
        ? e.target.closest('.panel, .card')
        : null;
      if (el !== current) {
        if (current) current.classList.remove('av-hot');
        current = el;
        if (current) current.classList.add('av-hot');
      }
      if (!el) return;
      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var x = ((e.clientX - r.left) / r.width) * 100;
      var y = ((e.clientY - r.top) / r.height) * 100;
      el.style.setProperty('--mx', x.toFixed(1) + '%');
      el.style.setProperty('--my', y.toFixed(1) + '%');
    }

    function onLeave() {
      if (current) current.classList.remove('av-hot');
      current = null;
    }

    document.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerleave', onLeave, true);
  }

  function boot() {
    indexCards();
    attachSpotlight();
    // Панель подгружает часть карточек ajax'ом после DOMContentLoaded —
    // переиндексируем разок чуть позже, без бесконечного observer'а.
    setTimeout(indexCards, 900);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
