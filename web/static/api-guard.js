/* ═══ API Guard — единый показ ошибок HTTP-запросов панели ═══
 * Оборачивает window.fetch один раз: любой не-OK ответ показывает тост
 * «МЕТОД /путь · HTTP код — текст ошибки сервера». Больше не надо
 * открывать консоль, чтобы понять, что скрывалось за «400 BAD REQUEST».
 *
 * Отключить для конкретного вызова:
 *   fetch(url, { guardSilent: true })              — опция
 *   fetch(url, { headers: { 'X-Guard-Silent': '1' } }) — или заголовок
 *
 * Ответ возвращается вызывающему коду без изменений (парсим клон).
 */
(function () {
  'use strict';
  if (window.__apiGuardInstalled) return;
  window.__apiGuardInstalled = true;

  var DEDUP_MS = 3000;   // одинаковый тост не спамим чаще раза в 3 секунды
  var MAX_ERR_LEN = 160; // хвост длинной ошибки режем
  var _lastMsg = '';
  var _lastAt = 0;
  var _original = window.fetch.bind(window);

  function describe(input, init) {
    var method = (init && init.method) || (input && input.method) || 'GET';
    var path = '';
    try {
      var raw = typeof input === 'string' ? input : (input && input.url) || '';
      path = new URL(raw, window.location.origin).pathname;
    } catch (e) { /* exotic input — label без пути */ }
    return String(method).toUpperCase() + ' ' + (path || '(?)');
  }

  function isSilent(init) {
    try {
      if (init && init.guardSilent) return true;
      var h = init && init.headers;
      if (h) {
        if (typeof h.get === 'function' && h.get('X-Guard-Silent')) return true;
        if (h['X-Guard-Silent']) return true;
      }
    } catch (e) { /* чужеродные headers — не молчим */ }
    return false;
  }

  function toast(text) {
    var now = Date.now();
    if (text === _lastMsg && now - _lastAt < DEDUP_MS) return;
    _lastMsg = text;
    _lastAt = now;
    try {
      if (typeof window.showToast === 'function') {
        window.showToast(text, false);
        return;
      }
    } catch (e) { /* тост недоступен — падаем в консоль */ }
    console.warn('[API Guard] ' + text);
  }

  window.fetch = function (input, init) {
    var silent = isSilent(init);
    var label = describe(input, init);
    return _original(input, init).then(function (resp) {
      if (!silent && resp && !resp.ok) {
        var status = resp.status;
        try {
          resp.clone().json().then(function (data) {
            var reason = (data && (data.error || data.message)) || '';
            if (reason.length > MAX_ERR_LEN) reason = reason.slice(0, MAX_ERR_LEN) + '…';
            toast(label + ' · HTTP ' + status + (reason ? ' — ' + reason : ''));
          }).catch(function () {
            toast(label + ' · HTTP ' + status);
          });
        } catch (e) {
          toast(label + ' · HTTP ' + status);
        }
      }
      return resp;
    }).catch(function (err) {
      if (!silent) toast(label + ' · сеть недоступна — сервер не ответил');
      throw err;
    });
  };
})();
