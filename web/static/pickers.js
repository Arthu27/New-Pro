/* ============================================================
   Hakumo Panel — Picker Kit (Light Edition)
   Живые пикеры ID и мелкий UX для страниц с ID-полями:
   - pickerLoad / attachIdPicker — datalist-подсказки «#имя — id»
   - attachListFilter — клиентский поиск по длинным спискам
   - bindCopyId — клик по data-copy-id копирует ID
   - bindCtrlS — Ctrl+S сохраняет форму без перезагрузки
   - bindSlashFocus, dirtyTrack, freshStamp, кнопка «наверх»
   ============================================================ */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── Живые списки сервера ─────────────────────────────── */
  var _cache = {}; /* gid -> Promise({channels, roles, online}) */

  window.pickerLoad = function (gid) {
    if (!_cache[gid]) {
      var chP = fetch('/api/guild/' + gid + '/channels')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (Array.isArray(d)) return { list: d, online: true };
          return { list: (d && d.channels) || [], online: false };
        })
        .catch(function () { return { list: [], online: false }; });
      var roP = fetch('/api/guild/' + gid + '/roles')
        .then(function (r) { return r.json(); })
        .then(function (d) { return Array.isArray(d) ? d : []; })
        .catch(function () { return []; });
      _cache[gid] = Promise.all([chP, roP]).then(function (both) {
        return { channels: both[0].list, roles: both[1], online: both[0].online };
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
      var id = window.pickerExtractId(input.value);
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

    window.pickerLoad(gid).then(render);
    input.addEventListener('input', function () { window.pickerLoad(gid).then(paint); });
    input.addEventListener('change', function () {
      var id = window.pickerExtractId(input.value);
      if (id) input.value = id;
      window.pickerLoad(gid).then(paint);
    });
  };

  /* Полноценный выпадающий выбор — политика владельца «никакого ручного
     ввода ID»: только интерактивный выбор из списка. Заполняет <select>
     каналами/ролями сервера; value — строка id, «ничего» = noneValue ('').
     Если выбранный ранее id удалён с сервера — добавляет его меткой
     «(удалён)» и не теряет значение. */
  /* Нормализация для поиска: регистр, эмодзи и лишние пробелы не мешают
     («Мой #Чат*» ищется как «мой чат», «MyChat», «мой  чат»). */
  function pickerNorm(s) {
    return String(s || '').toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, ' ')
      .replace(/\s+/g, ' ').trim();
  }
  window.pickerNorm = pickerNorm;  // для тестов и нестандартных поисков

  /* Поиск внутри длинного <select>: строка поиска над списком. Выбранный
     вариант и «none» видны всегда; ФИЛЬТР НИКОГДА не меняет значение —
     никаких случайных выборов (пункт 5.1) и сбросов других полей (5.2). */
  window.attachSelectSearch = function (sel, input) {
    if (!sel || !input) return null;
    function apply() {
      var q = pickerNorm(input.value);
      var cur = String(sel.value || '');
      Array.prototype.forEach.call(sel.options, function (opt) {
        var isNone = opt === sel.options[0];
        var keep = opt.value === cur;
        if (isNone || keep || !q) { opt.hidden = false; return; }
        opt.hidden = pickerNorm(opt.textContent).indexOf(q) === -1;
      });
      input.classList.toggle('active', !!q);
    }
    input.addEventListener('input', apply);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { input.value = ''; apply(); }
    });
    sel.addEventListener('focus', function () {
      if (input.value) { input.value = ''; apply(); }
    });
    sel._pickerSearchApply = apply;  // attachSelectPicker вызывает после fill
    return input;
  };

  window.attachSelectPicker = function (sel, opts) {
    if (!sel) return null;
    opts = opts || {};
    var kind = opts.kind || 'text';
    var gid = opts.gid;
    var noneValue = opts.noneValue == null ? '' : String(opts.noneValue);
    var noneLabel = opts.noneLabel || '— не выбрано —';
    /* opts.value: явное начальное значение (для селектов, созданных пустыми
       и заполняемых хелпером — у пустого <select> собственного value нет) */

    function source(data) {
      if (kind === 'role') return data.roles;
      return (data.channels || []).filter(function (c) { return c.type === kind; });
    }

    /* opts.search: над длинным списком — строка поиска (регистр/эмодзи/пробелы
       не важны, значение фильтром никогда не меняется) */
    var searchInput = null;
    if (opts.search && !sel._pickerSearchAttached) {
      sel._pickerSearchAttached = true;
      searchInput = document.createElement('input');
      searchInput.type = 'search';
      searchInput.className = 'picker-search';
      searchInput.placeholder = opts.searchPlaceholder || 'Поиск по названию…';
      searchInput.setAttribute('aria-label',
        opts.searchAria || 'Поиск по названию в списке');
      searchInput.autocomplete = 'off';
      sel.parentNode.insertBefore(searchInput, sel);
      window.attachSelectSearch(sel, searchInput);
    } else {
      searchInput = sel.previousElementSibling && sel.previousElementSibling.classList
        && sel.previousElementSibling.classList.contains('picker-search')
        ? sel.previousElementSibling : null;
    }

    window.pickerLoad(gid).then(function (data) {
      var keep = String(opts.value != null ? opts.value : (sel.value || ''));
      var list = source(data);
      var has = false;
      var html = '<option value="' + esc(noneValue) + '">' + esc(noneLabel) + '</option>';
      html += list.map(function (it) {
        if (String(it.id) === keep && keep) has = true;
        var prefix = kind === 'role' ? '@ ' : '# ';
        return '<option value="' + esc(it.id) + '">' + esc(prefix + it.name) + '</option>';
      }).join('');
      if (keep && keep !== noneValue && keep !== '0' && !has) {
        html += '<option value="' + esc(keep) + '" selected>' +
          esc(opts.deletedLabel || 'ранее выбрано (удалено с сервера)') + '</option>';
        has = true;
      }
      sel.innerHTML = html;
      sel.value = has && keep ? keep : String(noneValue);
      if (sel._pickerSearchApply) {  // повторный прогон фильтра по свежим опциям
        sel._pickerSearchApply();
      }
    }).catch(function () {
      /* бот офлайн/сеть: оставляем как есть, пикер не ломает страницу */
    });
    return sel;
  };

  /* Подсказки по УЧАСТНИКАМ: вводим ник/имя — варианты из живого поиска
     панели (member-card suggest), выбор по клику; в value остаётся id. */
  /* ── Богатый выбор участника (п.3): аватарки, поиск, клавиши, пагинация ──
     API прежний: input.value = user_id, statusEl-чип, opts {gid, statusEl}.
     Панель: строки с аватаркой/именем/ID, «Показать ещё» (offset-пагинация),
     стрелки + Enter + Esc, сортировка: совпадения с начала имени — первыми.
     Всё через серверный suggest → быстро и на сервере с тысячами людей. */

  /* Сортировка: те, чьё имя НАЧИНАЕТСЯ с запроса — выше остальных. */
  window.pickRankMembers = function (list, q) {
    q = String(q || '').trim().toLowerCase();
    if (!q) return list || [];
    var head = [], tail = [];
    (list || []).forEach(function (m) {
      var nm = String(m.name || '').toLowerCase();
      if (nm.indexOf(q) === 0) head.push(m); else tail.push(m);
    });
    return head.concat(tail);
  };

  window.attachMemberPicker = function (input, opts) {
    if (!input) return null;
    opts = opts || {};
    var gid = opts.gid;
    var statusEl = opts.statusEl || null;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');

    var found = [];
    var timer = null;
    var panel = null, listBox = null, headEl = null, moreEl = null;
    var activeIdx = -1;
    var curQ = '';
    var offset = 0;
    var LIMIT = 25;
    var hasMore = false;

    function paint() {
      if (!statusEl) return;
      var id = window.pickerExtractId(input.value);
      if (!id || !/\d{5,24}/.test(id)) { statusEl.innerHTML = ''; return; }
      var hit = null;
      found.forEach(function (it) { if (String(it.user_id) === id) hit = it; });
      if (hit) {
        statusEl.innerHTML = '<span class="picker-chip ok"><i class="fas fa-circle-check"></i> ' + esc(hit.name) + '</span>';
      }
    }

    function suggest(q, off) {
      return fetch('/api/guild/' + gid + '/member-card/suggest?q=' + encodeURIComponent(q) +
                   (off ? '&offset=' + off : ''), { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : {}; })
        .then(function (d) { return (d && d.items) || []; })
        .catch(function () { return []; });
    }

    /* ── DOM панели (лениво, один раз) ────────────────────────────── */
    function ensurePanel() {
      if (panel) return;
      panel = document.createElement('div');
      panel.className = 'mpd';
      panel.hidden = true;
      headEl = document.createElement('div');
      headEl.className = 'mpd-head';
      listBox = document.createElement('div');
      listBox.className = 'mpd-list';
      moreEl = document.createElement('button');
      moreEl.type = 'button';
      moreEl.className = 'mpd-more';
      moreEl.textContent = 'Показать ещё…';
      moreEl.addEventListener('mousedown', function (e) { e.preventDefault(); });
      moreEl.addEventListener('click', function () {
        suggest(curQ, offset).then(function (items) {
          offset += items.length;
          hasMore = items.length === LIMIT;
          found = found.concat(items);
          renderList();
        });
      });
      panel.appendChild(headEl);
      panel.appendChild(listBox);
      panel.appendChild(moreEl);
      var host = input.parentNode;
      if (host && getComputedStyle(host).position === 'static') host.style.position = 'relative';
      host.appendChild(panel);
      document.addEventListener('mousedown', function (e) {
        if (panel.hidden) return;
        if (e.target === input || panel.contains(e.target)) return;
        closePanel();
      });
    }

    function avatarHtml(m) {
      var av = String(m.avatar || '');
      if (av) return '<img class="mpd-av" src="' + esc(av) + '" alt="" loading="lazy">';
      var ch = (String(m.name || '?').trim()[0] || '?').toUpperCase();
      return '<span class="mpd-av mpd-av-letter">' + esc(ch) + '</span>';
    }

    function rowHtml(m, q) {
      var name = String(m.name || '?');
      var bot = m.bot ? '<span class="mpd-bot">бот</span>' : '';
      return '<div class="mpd-row" data-uid="' + esc(m.user_id) + '">' + avatarHtml(m) +
        '<div class="mpd-txt"><div class="mpd-name">' + esc(name) + bot + '</div>' +
        '<div class="mpd-id">' + esc(m.user_id) + '</div></div></div>';
    }

    function renderList() {
      var ranked = window.pickRankMembers(found, curQ);
      headEl.textContent = found.length
        ? 'Найдено: ' + found.length + (hasMore ? '+' : '')
        : 'Ничего не найдено — проверьте написание';
      listBox.innerHTML = ranked.slice(0, 60).map(function (m) { return rowHtml(m, curQ); }).join('');
      moreEl.hidden = !hasMore;
      activeIdx = -1;
      Array.prototype.forEach.call(listBox.querySelectorAll('.mpd-row'), function (row) {
        row.addEventListener('mousedown', function (e) {
          e.preventDefault();
          commit(row.getAttribute('data-uid'));
        });
        row.addEventListener('mousemove', function () { setActive(row); });
      });
      panel.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function setActive(row) {
      Array.prototype.forEach.call(listBox.querySelectorAll('.mpd-row'), function (r) {
        r.classList.toggle('active', r === row);
      });
    }

    function commit(uid) {
      var hit = null;
      found.forEach(function (m) { if (String(m.user_id) === String(uid)) hit = m; });
      if (!hit && listBox.querySelector('.mpd-row')) {
        var r = listBox.querySelector('.mpd-row');
        uid = r.getAttribute('data-uid');
      }
      input.value = String(uid);
      closePanel();
      paint();
      /* выбор из списка должен сработать как обычное изменение поля */
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function closePanel() {
      if (panel) panel.hidden = true;
      input.setAttribute('aria-expanded', 'false');
    }

    function refresh() {
      if (!curQ) { closePanel(); paint(); return; }
      suggest(curQ, 0).then(function (items) {
        offset = items.length;
        hasMore = items.length === LIMIT;
        found = items;
        renderList();
        paint();
      });
    }

    input.addEventListener('input', function () {
      ensurePanel();
      clearTimeout(timer);
      curQ = String(input.value || '').trim();
      timer = setTimeout(refresh, 180);
    });
    input.addEventListener('focus', function () {
      ensurePanel();
      clearTimeout(timer);
      curQ = String(input.value || '').trim() || '@';
      timer = setTimeout(refresh, 60);
    });
    input.addEventListener('keydown', function (e) {
      if (!panel || panel.hidden) return;
      var rows = listBox.querySelectorAll('.mpd-row');
      if (e.key === 'Escape') { closePanel(); e.stopPropagation(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!rows.length) return;
        activeIdx = e.key === 'ArrowDown'
          ? (activeIdx + 1) % rows.length
          : (activeIdx - 1 + rows.length) % rows.length;
        setActive(rows[activeIdx]);
        rows[activeIdx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && activeIdx >= 0 && rows[activeIdx]) {
        e.preventDefault();
        commit(rows[activeIdx].getAttribute('data-uid'));
      }
    });
    input.addEventListener('change', function () {
      var id = window.pickerExtractId(input.value);
      if (id) input.value = id;
      paint();
    });
    return input;
  };

  /* Клиентский поиск по списку. */
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
    var mo = new MutationObserver(function () {
      if (String(input.value || '').trim()) apply();
    });
    mo.observe(box, { childList: true });
  };

  /* Клик по data-copy-id копирует ID. */
  window.bindCopyId = function (root) {
    (root || document).addEventListener('click', function (e) {
      var el = e.target && e.target.closest ? e.target.closest('[data-copy-id]') : null;
      if (!el) return;
      var id = el.getAttribute('data-copy-id');
      function done() {
        el.classList.add('copied');
        setTimeout(function () { el.classList.remove('copied'); }, 700);
        if (typeof window.showToast === 'function') window.showToast('ID скопирован', true);
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

  /* Ctrl+S / Cmd+S — сохранить форму. */
  window.bindCtrlS = function (saveFn) {
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 's') {
        e.preventDefault();
        if (typeof saveFn === 'function') saveFn();
      }
    });
  };

  /* Клавиша «/» фокусирует поиск списка. */
  window.bindSlashFocus = function (input) {
    if (!input) return;
    document.addEventListener('keydown', function (e) {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      var t = e.target;
      var tag = (t && t.tagName) ? t.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
      e.preventDefault();
      input.focus();
      input.select();
    });
  };

  /* Сторож незакрытых черновиков. */
  window.dirtyTrack = function (fields) {
    var dirty = false;
    function mark() { dirty = true; }
    fields.forEach(function (el) {
      if (!el) return;
      el.addEventListener('input', mark);
      el.addEventListener('change', mark);
    });
    window.addEventListener('beforeunload', function (e) {
      if (dirty) { e.preventDefault(); e.returnValue = ''; }
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
    function paint() { btn.classList.toggle('show', window.scrollY > 600); }
    window.addEventListener('scroll', paint, { passive: true });
    btn.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    paint();
  });
})();
