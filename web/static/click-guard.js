/* click-guard.js — самолечение кликов по всей панели.
   Симптом: «кнопки работают, только если листнуть страницу вниз» —
   где-то над первым экраном лежит невидимый элемент и перехватывает тапы.
   Здесь: если точка тапа попала НЕ в интерактив, смотрим весь стек слоёв
   под пальцем и пробрасываем клик ближайшей живой кнопке/ссылке.
   Гард НЕ срабатывает, когда открыто осмысленное модальное окно/дровер —
   там бэкдроп перекрывает страницу намеренно. */
(function () {
  var INTER = 'button, a, [role="button"], [role="option"], input, select, textarea, label,' +
              ' summary, .switch, .nav-link, [data-bs-toggle], [onclick], .aes-opt';

  function overlayIntentional(x, y) {
    /* Открытые оверлеи: модалка, дровер, палитра, сплэш — не лечим.
       .aes-panel.open — открытый кастомный дропдаун (HakumoSelect): клики
       по его опциям — законные клики в интерактив, а не «промах».
       Без этого гарда пробрасывала тап по опции на кнопку ПОД панелью —
       открывался чужой селект («настройки переключаются сами»). */
    var open = document.querySelector('.modal-overlay.open, .drawer.open, .kbd-palette:not([hidden]), .aes-panel.open, .sidebar-backdrop.show, .fab.backdrop.show, .chat-drawer-backdrop.show, .tour-mask.show');
    if (open) return true;
    var boot = document.getElementById('bootSplash');
    return !!(boot && !boot.classList.contains('out'));
  }

  document.addEventListener('pointerdown', function (e) {
    try {
      if (e.button && e.button !== 0) return;                 /* только основная кнопка */
      if (e.target && e.target.closest && e.target.closest(INTER)) return; /* попали честно */
      if (overlayIntentional(e.clientX, e.clientY)) return;
      if (typeof document.elementsFromPoint !== 'function') return;
      var stack = document.elementsFromPoint(e.clientX, e.clientY) || [];
      for (var i = 0; i < stack.length; i++) {
        var el = stack[i];
        if (!el || !el.closest) continue;
        var ok = el.closest(INTER);
        if (ok && !ok.disabled && ok.getAttribute('aria-disabled') !== 'true') {
          e.preventDefault();
          e.stopPropagation();
          if (window.console && console.warn) {
            console.warn('[click-guard] клик перехвачен элементом %o — проброшен на %o', e.target, ok);
          }
          ok.click();
          return;
        }
      }
    } catch (err) { /* гард обязан быть тихим */ }
  }, true);
})();
