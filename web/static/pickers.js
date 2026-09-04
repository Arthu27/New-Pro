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
  var _mpdPanels = []; /* все body-панели выбора участника (для закрытия чужих) */

  window.pickerLoad = function (gid) {
    /* Пустой gid (модуль не сообщил гильдию) — не оставляем пикеры пустыми:
       берём глобальные списки панели /api/channels и /api/roles. */
    if (!gid) gid = '_main';
    if (!_cache[gid]) {
      var warm = (gid === '_main' && window.__warmLists) || null;  // прогрев из base.html
      var chP = (warm && warm.channels ? Promise.resolve(warm.channels)
        : fetch(gid === '_main' ? '/api/channels' : '/api/guild/' + gid + '/channels')
          .then(function (r) { return r.json(); }))
        .then(function (d) {
          if (Array.isArray(d)) return { list: d, online: true };
          return { list: (d && d.channels) || [], online: false };
        })
        .catch(function () { return { list: [], online: false }; });
      var roP = (warm && warm.roles ? Promise.resolve(warm.roles)
        : fetch(gid === '_main' ? '/api/roles' : '/api/guild/' + gid + '/roles')
          .then(function (r) { return r.json(); }))
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


  /* ═══ п.4: кастомные select-меню (selectSuite) ══════════════════════════
     Красивый, единый вид для всех select панели: закрытая таблетка с
     текущим значением, всплываш с поиском (pickerNorm), строки с хитом
     одним кликом (mousedown → commit, без случайных соседей), клавиши
     (стрелки/Enter/Esc), плавные анимации через .sshd.open, корректное
     сужение под родителя на узких экранах. Вызов один раз на элемент —
     нативный select остаётся источником данных (скрыт визуально), все
     обработчики `change` страницы продолжают работать (мы ДИСПАТЧИМ change
     при выборе человека — ровно как нативный select). */

  function sshdEnhance(sel, opts) {
    if (!sel || sel._sshd) return sel && (sel._sshd ? sel._sshd._sshdCtl : null);
    opts = opts || {};
    var host = sel.parentNode;
    if (!host) return null;

    /* Структурная защита от дублей (sel._sshd теряется при пересоздании
       узла): если поле уже в .sshd или перед ним висит виджет — не строим
       второй; пустую осиротевшую обёртку от прежнего узла сносим. */
    if (host.classList && host.classList.contains('sshd') &&
        host.querySelector('select.sshd-src') === sel) {
      return sel._sshd ? sel._sshd._sshdCtl : null;
    }
    var prevSib = sel.previousElementSibling;
    if (prevSib && prevSib.classList && prevSib.classList.contains('sshd')) {
      var orphan = !prevSib.querySelector('select.sshd-src');
      if (orphan && prevSib.parentNode) prevSib.parentNode.removeChild(prevSib);
      else return prevSib._sshdCtl || null;
    }

    var root = document.createElement('div');
    root.className = 'sshd';
    if (sel.className) root.className += ' ' + sel.className.replace(/\s*form-select\s*/g, ' ');

    host.insertBefore(root, sel);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sshd-btn';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.setAttribute('aria-expanded', 'false');
    var btnLbl = document.createElement('span');
    btnLbl.className = 'sshd-lbl';
    var caret = document.createElement('i');
    caret.className = 'fas fa-chevron-down sshd-caret';
    btn.appendChild(btnLbl);
    btn.appendChild(caret);

    var pop = document.createElement('div');
    pop.className = 'sshd-pop';
    pop.hidden = true;
    var searchIp = null;
    if (opts.search) {
      searchIp = document.createElement('input');
      searchIp.type = 'search';
      searchIp.className = 'sshd-search';
      searchIp.placeholder = opts.searchPlaceholder || 'Поиск…';
      searchIp.setAttribute('aria-label', 'Поиск в списке');
      searchIp.autocomplete = 'off';
      pop.appendChild(searchIp);
    }
    var list = document.createElement('div');
    list.className = 'sshd-list';
    list.setAttribute('role', 'listbox');
    pop.appendChild(list);

    root.appendChild(btn);
    root.appendChild(sel);   // sel живёт внутри root, невидим — источник истины
    sel.classList.add('sshd-src');
    /* Попап монтируем в <body> и позиционируем fixed по координатам кнопки:
       панели формы имеют .panel{overflow:hidden}, и абсолютный список
       внутри поля обрезался бы границей панели («уезжает/не видно/клики
       мимо»). В body список ничем не клипуется и открывается в любую сторону. */
    pop.classList.add('sshd-pop-float');

    var state = { open: false, active: -1 };
    sel._sshd = root;
    sel._sshdCtl = { refresh: refresh, syncLabel: syncLabel };

    /* ── позиционирование в пределах экрана ─────────────────────────
       Список каналов/ролей бывает длинным, а поле — внизу страницы или
       модалки: если открыть строго вниз, всплывашка уходит за край и
       «выбирать невозможно» (клики попадают мимо). Считаем свободное
       место (и в прокручиваемом контейнере — его границы) и открываем
       ВВЕРХ или ограничиваем высоту списка. */
    function placePop() {
      var r = btn.getBoundingClientRect();
      var vw = window.innerWidth, vh = window.innerHeight;
      var w = r.width || 220;
      var below = vh - r.bottom - 12, above = r.top - 12;
      var up = below < 220 && above > below;
      root.classList.toggle('up', up);
      pop.classList.toggle('sshd-pop-up', up);
      var space = (up ? above : below);
      list.style.maxHeight = Math.max(120, Math.min(280, space < 120 ? 120 : space)) + 'px';
      pop.style.left = Math.min(Math.max(8, r.left), vw - w - 8) + 'px';
      pop.style.width = w + 'px';
      pop.style.top = up ? 'auto' : (r.bottom + 6) + 'px';
      pop.style.bottom = up ? (vh - r.top + 6) + 'px' : 'auto';
      var cur = list.querySelector('.sshd-row.cur'); // без подпрыгивания страницы
      if (cur && list.scrollTop === 0 && cur.offsetTop > list.clientHeight) {
        list.scrollTop = Math.max(0, cur.offsetTop - 8);
      }
    }

    /* Список в body+fixed: при прокрутке/ресайзе переставляем его к кнопке
       (клики не промахиваются). Прокрутка внутри списка не двигает страницу. */
    function moveOnScroll(e) {
      if (!state.open) return;
      var t = e && e.target;
      if (t && t.nodeType === 1 && (pop === t || pop.contains(t))) return;
      placePop();
    }
    window.addEventListener('scroll', moveOnScroll, true);
    window.addEventListener('resize', moveOnScroll, true);

    function options() {
      return Array.prototype.slice.call(sel.options || []);
    }
    function currentOpt() {
      var v = String(sel.value);
      var opts2 = options();
      for (var i = 0; i < opts2.length; i++) if (String(opts2[i].value) === v) return opts2[i];
      return null;
    }
    function syncLabel() {
      var cur = currentOpt();
      btnLbl.textContent = cur ? cur.textContent : '—';
      root.classList.toggle('empty', !cur || !cur.value);
    }

    var q = '';
    function matches(o) {
      if (!q) return true;
      return window.pickerNorm(o.textContent).indexOf(window.pickerNorm(q)) !== -1;
    }

    function renderList() {
      list.innerHTML = '';
      var cur = String(sel.value);
      var curVisible = false;
      options().forEach(function (o) {
        if (!matches(o) && String(o.value) !== cur) return;
        if (String(o.value) === cur) curVisible = true;
        var row = document.createElement('div');
        row.className = 'sshd-row' + (String(o.value) === cur ? ' cur' : '');
        row.setAttribute('role', 'option');
        row.setAttribute('data-v', String(o.value));
        row.setAttribute('aria-selected', String(o.value) === cur ? 'true' : 'false');
        row.textContent = o.textContent;
        /* mousedown, НЕ click: commit сразу, пока фокус у поля поиска —
           клик с первого раза, промахи по соседям исключены (ряд 36px) */
        row.addEventListener('mousedown', function (e) {
          e.preventDefault();
          if (e.stopPropagation) e.stopPropagation();
          commit(row.getAttribute('data-v'));
        });
        row.addEventListener('mousemove', function () { markActive(row); });
        list.appendChild(row);
      });
      if (!list.children || !list.children.length) {
        var emp = document.createElement('div');
        emp.className = 'sshd-empty';
        emp.textContent = 'Ничего не найдено';
        list.appendChild(emp);
      }
      state.active = curVisible ? -1 : -1;
    }

    function markActive(row) {
      Array.prototype.forEach.call(list.querySelectorAll('.sshd-row'), function (r) {
        r.classList.toggle('active', r === row);
      });
    }

    function openPop() {
      if (state.open) return;
      state.open = true;
      root.classList.add('open');
      // в body — чтобы не обрезалось overflow панели/модалки
      if (pop.parentNode !== document.body) document.body.appendChild(pop);
      pop.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      q = '';
      if (searchIp) { searchIp.value = ''; setTimeout(function () { searchIp.focus(); }, 30); }
      renderList();
      setTimeout(placePop, 0);
    }
    function closePop() {
      if (!state.open) return;
      state.open = false;
      root.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
      pop.hidden = true;
      if (pop.parentNode === document.body) {
        var parent = pop.parentNode;
        if (typeof pop.remove === 'function') pop.remove();
        else if (parent && typeof parent.removeChild === 'function') parent.removeChild(pop);
      }
    }
    function commit(v) {
      closePop();
      if (String(sel.value) !== String(v)) {
        sel.value = String(v);
        /* человеческий выбор == нативный change: все обработчики форм живут */
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
      syncLabel();
    }

    // disabled нативного селекта -> кнопка пикера тоже заблокирована
    function syncDisabled() {
      var off = !!sel.disabled;
      btn.disabled = off;
      btn.classList.toggle('sshd-btn-disabled', off);
      btn.setAttribute('aria-disabled', off ? 'true' : 'false');
      if (off && state.open) closePop();
    }
    if (typeof MutationObserver === 'function') {
      new MutationObserver(syncDisabled).observe(sel, { attributes: true, attributeFilter: ['disabled'] });
    }
    syncDisabled();

    btn.addEventListener('click', function () { if (sel.disabled) return; state.open ? closePop() : openPop(); });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        if (sel.disabled) return;
        e.preventDefault(); openPop();
      }
    });
    if (searchIp) {
      searchIp.addEventListener('input', function () { q = searchIp.value; renderList(); });
    }
    pop.addEventListener('keydown', function (e) {
      var rows = list.querySelectorAll('.sshd-row');
      if (e.key === 'Escape') { closePop(); btn.focus(); e.stopPropagation(); }
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!rows.length) return;
        state.active = e.key === 'ArrowDown'
          ? (state.active + 1) % rows.length
          : (state.active - 1 + rows.length) % rows.length;
        markActive(rows[state.active]);
        rows[state.active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && state.active >= 0 && rows[state.active]) {
        e.preventDefault();
        commit(rows[state.active].getAttribute('data-v'));
      }
    });
    document.addEventListener('mousedown', function (e) {
      if (state.open && !root.contains(e.target) && !pop.contains(e.target)) closePop();
    });
    /* внешний код поменял select.value и dispatch'нул change — обновляем ярлык */
    sel.addEventListener('change', syncLabel);

    function refresh() { syncLabel(); if (state.open) renderList(); }
    syncLabel();
    return sel._sshdCtl;
  }

  /* Полюбовное применение ко всем select на странице (кроме multiple и
     явно выключенных data-sshd-no); большие списки — с поиском. */
  window.sshdEnhance = sshdEnhance;

  function _rm(n) { if (!n) return; if (typeof n.remove === 'function') n.remove(); else if (n.parentNode) n.parentNode.removeChild(n); }
  function sshdPruneOrphans(scope) {
    var root = scope || document;
    if (!root.querySelectorAll) return;
    /* Здоровая обёртка содержит живой select, прикреплённый к документу и
       ссылающийся именно на неё (s._sshd === wrap). Иначе — осиротевший
       дубль от innerHTML (пустая кнопка или обёртка с заменённым select). */
    Array.prototype.forEach.call(root.querySelectorAll('.sshd'), function (wrap) {
      var ok = false;
      Array.prototype.forEach.call(wrap.querySelectorAll('select'), function (s) {
        if (s._sshd === wrap && document.contains(s)) ok = true;
      });
      if (!ok) _rm(wrap);
    });
    /* бесхозный видимый попап в body (виджет закрыт/удалён, а список висит) */
    if (scope === document || scope === document.body) {
      Array.prototype.forEach.call(document.querySelectorAll('.sshd-pop-float'), function (p) {
        if (!p.hidden && !document.querySelector('.sshd.open')) _rm(p);
      });
    }
  }
  window.sshdPruneOrphans = sshdPruneOrphans;

  function sshdAll(rootEl) {
    var scope = rootEl || document;
    if (!scope.querySelectorAll) return;
    sshdPruneOrphans(scope === document ? document : scope);
    Array.prototype.forEach.call(
      scope.querySelectorAll('select:not([multiple]):not([data-sshd-no]):not(.sshd-src)'),
      function (sel) {
        if (sel._sshd) return;
        var needsSearch = (sel.options || []).length > 8 || sel.hasAttribute('data-sshd-search');
        sshdEnhance(sel, { search: needsSearch });
      });
  }
  window.sshdAll = sshdAll;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { sshdAll(document); });
  } else {
    sshdAll(document);
  }
  /* динамически добавленные селекты (списки заполняются после загрузки) */
  var _sshdTimer = null;
  if (typeof MutationObserver === 'function' && document.body) {
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        if (muts[i].addedNodes && muts[i].addedNodes.length) {
          clearTimeout(_sshdTimer);
          _sshdTimer = setTimeout(function () { sshdAll(document.body); }, 120);
          break;
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  /* server-driven пикер канала/роли: заполняет <select> одноимёнными
     сущностями с сервера и подключает кастомный контрол (п.4). */
  window.attachSelectPicker = function (sel, opts) {
    if (!sel) return null;
    opts = opts || {};
    var kind = opts.kind || 'text';
    var gid = opts.gid;
    var noneValue = opts.noneValue == null ? '' : String(opts.noneValue);
    var noneLabel = opts.noneLabel || '— не выбрано —';
    sshdEnhance(sel, { search: opts.search !== false,
                       searchPlaceholder: opts.searchPlaceholder });

    function source(data) {
      if (kind === 'role') return data.roles;
      return (data.channels || []).filter(function (c) { return c.type === kind; });
    }

    function refreshCtl() {
      if (sel._pickerSearchApply) sel._pickerSearchApply();
      if (sel._sshdCtl) sel._sshdCtl.refresh();
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
      refreshCtl();
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
    /* повторный вызов на том же поле — обновляем контекст, без дублей */
    input._mpdSetCtx = function (o) {
      if (o && o.gid) gid = o.gid;
      if (o && o.statusEl) statusEl = o.statusEl;
      if (o && o.onPick) opts.onPick = o.onPick;
      curQ = '';
    };
    if (input._mpdAttached) { input._mpdSetCtx(opts); return input; }
    input._mpdAttached = true;
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
      /* Попап в <body> с fixed-координатами — не обрезается overflow формы. */
      panel.classList.add('mpd-floating');
      document.body.appendChild(panel);
      _mpdPanels.push(panel);
      function place() {
        if (panel.hidden) return;
        var r = input.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
        var w = Math.max(r.width, 240);
        var below = vh - r.bottom - 12, above = r.top - 12;
        var up = below < 220 && above > below; // вверх, только если внизу тесно
        panel.classList.toggle('up', up);
        panel.style.left = Math.min(Math.max(8, r.left), vw - w - 8) + 'px';
        panel.style.width = w + 'px';
        panel.style.top = up ? 'auto' : (r.bottom + 6) + 'px';
        panel.style.bottom = up ? (vh - r.top + 6) + 'px' : 'auto';
        var space = (up ? above : below);
        listBox.style.maxHeight = Math.max(120, Math.min(300, space < 120 ? 120 : space)) + 'px';
      }
      panel._place = place;
  // прокрутка/ресайз держат попап у поля; прокрутка внутри списка не закрывает
      window.addEventListener('scroll', function () { if (!panel.hidden) place(); }, true);
      window.addEventListener('resize', function () { if (!panel.hidden) place(); }, true);
      document.addEventListener('mousedown', function (e) {
        if (panel.hidden) return;
        if (e.target === input || panel.contains(e.target)) return;
        closePanel();
      });
    }
    // прокрутка/ресайз двигают панель вместе с полем; закрытие — клик мимо/Esc

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
          if (e.stopPropagation) e.stopPropagation();
          commit(row.getAttribute('data-uid'));
        });
        row.addEventListener('mousemove', function () { setActive(row); });
      });
      // на страницах с несколькими полями (доказательства) открыта может
      // быть только одна панель — гасим остальные
      _mpdPanels.forEach(function (p) { if (p !== panel) p.hidden = true; });
      panel.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      if (panel._place) setTimeout(panel._place, 0);
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
        found.forEach(function (m) { if (String(m.user_id) === String(uid)) hit = m; });
      }
      input.value = String(uid);
      closePanel();
      paint();
      /* опциональный колбэк: кто именно выбран (имя/аватарка) — например,
         страница доказательств берёт отсюда user_name, не подсматривая в DOM */
      if (typeof opts.onPick === 'function') {
        try { opts.onPick(String(uid), hit); } catch (e) {}
      }
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
