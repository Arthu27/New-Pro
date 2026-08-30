/* Числовой заменитель Chart.js (политика заказа, п.2 «без линий/графиков»):
   подменяет window.Chart после загрузки vendor, и каждый график
   превращается в ряд числовых сводок (сумма · первое · последнее · максимум
   на каждый набор данных). Canvas прячется без перерисовки вёрстки. */
(function () {
  'use strict';

  /* Объект, самосоздающий вложенные уровни при чтении — присваивания
     вида Chart.defaults.font.family = 'Inter' всегда проходят. */
  function _autoObj() {
    return new Proxy({}, {
      get: function (t, k) {
        if (typeof k !== 'string') return undefined;
        if (!(k in t)) t[k] = _autoObj();
        return t[k];
      },
      set: function (t, k, v) { t[k] = v; return true; }
    });
  }

  function fmt(v) {
    var n = Number(v) || 0;
    var r = Math.abs(n - Math.round(n)) < 0.05 ? Math.round(n) : Math.round(n * 10) / 10;
    return String(r).replace('.', ',');
  }

  /* Рисует ряд сводок вместо canvas: по одному чипу на набор данных */
  function renderNums(canvas, cfg) {
    var data = (cfg && cfg.data) || {};
    var datasets = data.datasets || [];
    var host = canvas && canvas.parentNode;
    if (!host) return null;
    var old = host.querySelector('.hc-numwrap');
    if (old) old.remove();
    canvas.style.display = 'none';
    var wrap = document.createElement('div');
    wrap.className = 'hc-numwrap hc-stats';
    if (!datasets.length) {
      wrap.innerHTML = '<span class="hc-empty muted" style="font-size:12px">нет данных</span>';
    } else {
      var html = '';
      datasets.forEach(function (ds) {
        var vals = (ds.data || []).map(function (x) { return Number(x) || 0; });
        var total = 0, mx = -Infinity, mn = Infinity;
        vals.forEach(function (v) { total += v; if (v > mx) mx = v; if (v < mn) mn = v; });
        if (!vals.length) { mx = mn = 0; }
        var name = ds.label ? String(ds.label) : 'ряд';
        html += '<div class="hc-stat"><span class="hc-k">' + name + '</span>' +
          '<b class="hc-v">' + fmt(total) + '</b>' +
          '<small class="hc-sub muted">последнего: ' + fmt(vals.length ? vals[vals.length - 1] : 0) +
          ' · макс: ' + fmt(mx) + ' · мин: ' + fmt(mn) + '</small></div>';
      });
      wrap.innerHTML = html;
    }
    canvas.insertAdjacentElement('afterend', wrap);
    return wrap;
  }

  /* Конструктор-шим с API Chart.js (destroy/update) */
  function NumChart(target, cfg) {
    if (!(this instanceof NumChart)) return new NumChart(target, cfg);
    var canvas = target;
    // Chart.js иногда получает контекст — возвращаемся к элементу
    if (canvas && canvas.canvas) canvas = canvas.canvas;
    this._el = canvas;
    this._cfg = cfg;
    this._wrap = renderNums(canvas, cfg);
  }
  NumChart.prototype.destroy = function () {
    if (this._wrap && this._wrap.remove) this._wrap.remove();
    this._wrap = null;
    if (this._el) this._el.style.display = 'none';
  };
  NumChart.prototype.update = function () {
    if (this._wrap) this._wrap.remove();
    this._wrap = renderNums(this._el, this._cfg);
  };
  NumChart.prototype.resize = function () {};
  NumChart.prototype.toBase64Image = function () { return ''; };
  /* defaults — толерантная структура: страницы настраивают Chart.defaults
     (color, font.family, plugins.legend…) — заглушка обязана принимать
     любые вложенные присваивания, иначе страница падает целиком
     (баг 29.08.2026: analytics вешался на font.family). */
  NumChart.defaults = _autoObj();
  NumChart.register = function () {};
  NumChart.version = 'nums-1.0';

  window.Chart = NumChart;
})();
