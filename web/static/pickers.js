/* Aether — живые пикеры ID и мелкий UX (идеи #91-95).
 *
 * #91 pickerLoad/attachIdPicker — datalist-подсказки «#имя — id» из живых
 *     списков сервера (/api/guild/<gid>/channels, /roles), статус-чип под
 *     полем: нашёлся / не найден / бот офлайн.
 * #92 подключения — в шаблонах страниц с ID-полями.
 * #93 attachListFilter — клиентский поиск по длинным спискам.
 * #94 bindCopyId — клик по элементу с data-copy-id копирует ID.
 * #95 bindCtrlS — Ctrl+S сохраняет форму, не отправляя страницу.
 *
 * Без декоративных эмодзи — иконки Font Awesome.
 */
(function () {
  'use strict';
  var _cache = {};  /* gid -> Promise({channels, roles, online}) */

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* Живые списки сервера: каналы при ошибке приходят словарём с error —
     по нему отличаем «бот офлайн» от «пусто». */
  window.pickerLoad = function (gid) {
    if (!_cache[gid]) {
      var chP = fetch('/api/guild/' + gid + '/channels')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (Array.isArray(d)) return {list: d, online: true};
          return {list: (d && d.channels) || [], online: false};
        })
        .catch(function () { return {list: [], online: false}; });
      var roP = fetch('/api/guild/' + gid + '/roles')
        .then(function (r) { return r.json(); })
        .then(function (d) { return Array.isArray(d) ? d : []; })
        .catch(function () { return []; });
      _cache[gid] = Promise.all([chP, roP]).then(function (both) {
        return {channels: both[0].list, roles: both[1], online: both[0].online};
      });
    }
    return _cache[gid];
  };

  /* Цифры ID из вставленного '<#123>', '@роль (123)' и похожего. */
  window.pickerExtractId = function (raw) {
    var m = String(raw == null ? '' : raw).match(/(\d{5,24})/);
    return m ? m[1] : '';
  };

  /* datalist-подсказки + статус-чип. kind: 'text' | 'voice' | 'category' | 'role'. */
  window.attachIdPicker = function (input, opts) {
    opts = opts || {};
    var kind = opts.kind || 'text';
    var gid = opts.gid;
    var statusEl = opts.statusEl || null;
    var dl = document.createElement('datalist');
    dl.id = 'picker-dl-' + Math.random().toString(36).slice(2, 8);
    input.setAttribute('list', dl.id);
    input.parentNode.appendChild(dl);

    function source(data) {
      if (kind === 'role') return data.roles;
      return data.channels.filter(function (c) { return c.type === kind; });
    }

    function render(data) {
      dl.innerHTML = source(data).map(function (it) {
        var prefix = kind === 'role' ? '@' : '#';
        return '<option value="' + esc(it.id) + '">' + esc(prefix + it.name + ' — ' + it.id) + '</option>';
      }).join('');
      paint(data);
    }

    function paint(data) {
      if (!statusEl) return;
      var id = pickerExtractId(input.value);
      if (!id) { statusEl.innerHTML = ''; return; }
      if (!data.online) {
        statusEl.innerHTML = '<span class="picker-chip warn"><i class="fas fa-satellite-dish"></i> бот офлайн — не проверить</span>';
        return;
      }
      var hit = null;
      source(data).forEach(function (it) { if (String(it.id) === id) hit = it; });
      if (hit) {
        statusEl.innerHTML = '<span class="picker-chip ok"><i class="fas fa-circle-check"></i> ' + esc((kind === 'role' ? '@' : '#') + hit.name) + '</span>';
      } else {
        statusEl.innerHTML = '<span class="picker-chip bad"><i class="fas fa-triangle-exclamation"></i> не найдено на сервере</span>';
      }
    }

    pickerLoad(gid).then(render);
    input.addEventListener('input', function () { pickerLoad(gid).then(paint); });
    input.addEventListener('change', function () {
      var id = pickerExtractId(input.value);
      if (id) input.value = id;
      pickerLoad(gid).then(paint);
    });
  };

  /* Клиентский поиск по списку: прячет строки без совпадения с запросом. */
  window.attachListFilter = function (input, containerId, rowSelector) {
    var box = document.getElementById(containerId);
    if (!box) return;
    function apply() {
      var q = input.value.toLowerCase().trim();
      var rows = box.querySelectorAll(rowSelector);
      var visible = 0;
      rows.forEach(function (row) {
        var show = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
        row.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      var note = box.querySelector('[data-filter-empty]');
      if (note) note.remove();
      if (q && !visible && rows.length) {
        var div = document.createElement('div');
        div.className = 'empty-state';
        div.setAttribute('data-filter-empty', '1');
        div.innerHTML = '<i class="fas fa-search"></i><p>По запросу «' + esc(q) + '» никого нет</p>';
        box.appendChild(div);
      }
    }
    input.addEventListener('input', apply);
    input._pkApply = apply;
    /* строки подгружаются заново — перефильтровываем по текущему запросу */
    var mo = new MutationObserver(function () {
      if (String(input.value || '').trim()) apply();
    });
    mo.observe(box, {childList: true});
  };

  /* Клик по элементу с data-copy-id копирует ID в буфер. */
  window.bindCopyId = function (root) {
    (root || document).addEventListener('click', function (e) {
      var el = e.target.closest ? e.target.closest('[data-copy-id]') : null;
      if (!el) return;
      var id = el.getAttribute('data-copy-id');
      function done() {
        el.classList.add('copied');
        setTimeout(function () { el.classList.remove('copied'); }, 700);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(id).then(done, function () {});
      } else {
        var t = document.createElement('textarea');
        t.value = id;
        document.body.appendChild(t);
        t.select();
        try { document.execCommand('copy'); done(); } catch (err) {}
        t.remove();
      }
    });
  };

  /* Ctrl+S / Cmd+S — сохранить форму без перезагрузки страницы. */
  window.bindCtrlS = function (saveFn) {
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 's') {
        e.preventDefault();
        if (typeof saveFn === 'function') saveFn();
      }
    });
  };
})();

/* ── #96-100: фокус, черновики, свежесть, «наверх» ──────────────
 * bindSlashFocus — клавиша «/» фокусирует поиск списка (как GitHub).
 * dirtyTrack — сторож незакрытых черновиков: beforeunload + reset после
 *   удачного сохранения.
 * freshStamp — чип «обновлено HH:MM:SS» у списка после каждой загрузки.
 * initScrollTop — плавающая кнопка «наверх» на длинных страницах.
 */
(function () {
  'use strict';

  window.bindSlashFocus = function (input) {
    if (!input) return;
    document.addEventListener('keydown', function (e) {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      var t = e.target;
      var tag = (t && t.tagName) ? t.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select'
          || (t && t.isContentEditable)) return;
      e.preventDefault();
      input.focus();
      input.select();
    });
  };

  /* fields — список полей формы; возвращает {is(), reset()}. */
  window.dirtyTrack = function (fields) {
    var dirty = false;
    function mark() { dirty = true; }
    fields.forEach(function (el) {
      if (!el) return;
      el.addEventListener('input', mark);
      el.addEventListener('change', mark);
    });
    window.addEventListener('beforeunload', function (e) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
    return {
      is: function () { return dirty; },
      reset: function () { dirty = false; }
    };
  };

  window.freshStamp = function (el) {
    if (!el) return;
    var d = new Date();
    var p = function (v) { return String(v).padStart(2, '0'); };
    el.innerHTML = '<i class="fas fa-rotate"></i> обновлено ' +
      p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('scrollTopBtn')) return;
    var btn = document.createElement('button');
    btn.id = 'scrollTopBtn';
    btn.type = 'button';
    btn.className = 'scroll-top-btn';
    btn.title = 'Наверх';
    btn.setAttribute('aria-label', 'Наверх');
    btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    document.body.appendChild(btn);
    function paint() {
      btn.classList.toggle('show', window.scrollY > 600);
    }
    window.addEventListener('scroll', paint, {passive: true});
    btn.addEventListener('click', function () {
      window.scrollTo({top: 0, behavior: 'smooth'});
    });
    paint();
  });
})();
