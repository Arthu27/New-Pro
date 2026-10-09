/* Warn panel — live mode: без location.reload / form.submit */
(function () {
  'use strict';

  const root = document.getElementById('warnLiveRoot');
  if (!root) return;

  const cfg = window.__WARN_LIVE__ || {};
  const csrf = cfg.csrf || '';
  const reasons = cfg.reasons || {};
  let tab = cfg.tab || 'members';
  let busy = false;
  let liveCtrl = null;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  function toast(text, ok) {
    let el = document.getElementById('warnToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'warnToast';
      el.className = 'warn-toast';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.toggle('is-err', !ok);
    el.classList.add('on');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('on'), 2200);
  }

  function paramsFromForm() {
    const form = $('warnFilterForm');
    const p = new URLSearchParams();
    if (!form) {
      p.set('tab', tab);
      return p;
    }
    new FormData(form).forEach((v, k) => {
      if (v != null && String(v) !== '') p.set(k, String(v));
    });
    if (!p.get('tab')) p.set('tab', tab);
    return p;
  }

  async function liveRefresh(extra) {
    if (busy) return;
    const p = paramsFromForm();
    const keepPage = !!(extra && extra.keepPage);
    if (extra) {
      Object.keys(extra).forEach((k) => {
        if (k === 'keepPage') return;
        if (extra[k] == null || extra[k] === '') p.delete(k);
        else p.set(k, String(extra[k]));
      });
    }
    // смена фильтра/вкладки — на первую страницу
    if (!keepPage && !(extra && extra.page != null)) p.set('page', '1');
    busy = true;
    root.classList.add('is-live-loading');
    if (liveCtrl) try { liveCtrl.abort(); } catch (_) {}
    liveCtrl = new AbortController();
    try {
      const r = await fetch('/api/warns/live?' + p.toString(), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal: liveCtrl.signal,
      });
      const j = await r.json();
      if (!j.ok) {
        toast(j.error || 'Ошибка загрузки', false);
        return;
      }
      root.innerHTML = j.html || '';
      tab = j.tab || tab;
      if (cfg) cfg.tab = tab;
      if (j.url) history.replaceState({ warnLive: 1 }, '', j.url);
      bindAll();
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      toast('Сеть', false);
    } finally {
      busy = false;
      root.classList.remove('is-live-loading');
    }
  }

  function wireSuggest(input, box, onPick, staffOnly) {
    if (!input || !box) return;
    let t = null;
    let items = [];
    let active = -1;
    let req = 0;
    let ctrl = null;
    const clientCache = new Map();

    function hide() {
      box.hidden = true;
      box.innerHTML = '';
      active = -1;
    }

    function paint() {
      if (!items.length) {
        box.innerHTML = '<div class="warn-suggest__empty">Никого не найдено</div>';
        box.hidden = false;
        return;
      }
      box.innerHTML = items.map((it, i) => {
        const av = it.avatar
          ? `<img src="${esc(it.avatar)}" alt="">`
          : `<span class="warn-suggest__fb">${esc((it.name || '?')[0] || '?').toUpperCase()}</span>`;
        const handle = it.handle ? '@' + esc(it.handle) + ' · ' : '';
        const gone = it.in_guild ? '' : ' · вышел';
        const badge = it.role_badge || '';
        const wb = (it.warns != null)
          ? `<span class="wbadge w${it.warns >= 3 ? 3 : it.warns}">${it.warns}</span>` : '';
        return `<button type="button" class="warn-suggest__item${i === active ? ' is-active' : ''}" data-i="${i}">
          ${av}
          <span class="warn-suggest__meta">
            <strong>${esc(it.name || it.id)}</strong>
            <small>${handle}${esc(it.id)}${gone}</small>
          </span>
          <span class="warn-suggest__right">${badge}${wb}</span>
        </button>`;
      }).join('');
      box.hidden = false;
      box.querySelectorAll('.warn-suggest__item').forEach((btn) => {
        btn.addEventListener('mousedown', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const it = items[Number(btn.dataset.i)];
          if (it) onPick(it);
          hide();
        });
      });
    }

    async function run() {
      const q = (input.value || '').trim();
      const clearBtn = input.closest('.warn-search__box')?.querySelector('.warn-search__clear');
      if (clearBtn && clearBtn.id === 'wqClear') clearBtn.hidden = q.length < 1;
      if (q.length < 1) { hide(); return; }
      const cacheKey = q.toLowerCase() + '|' + staffOnly;
      if (clientCache.has(cacheKey)) {
        items = clientCache.get(cacheKey);
        active = items.length ? 0 : -1;
        paint();
        return;
      }
      const my = ++req;
      if (ctrl) try { ctrl.abort(); } catch (_) {}
      ctrl = new AbortController();
      const params = new URLSearchParams({ q, limit: '10' });
      if (staffOnly === true) params.set('staff', '1');
      if (staffOnly === false) params.set('staff', '0');
      try {
        const r = await fetch('/api/warns/search?' + params, {
          credentials: 'same-origin', signal: ctrl.signal,
        });
        const j = await r.json();
        if (my !== req) return;
        items = (j.items || []).slice(0, 10);
        clientCache.set(cacheKey, items);
        if (clientCache.size > 40) {
          const k = clientCache.keys().next().value;
          clientCache.delete(k);
        }
        active = items.length ? 0 : -1;
        paint();
      } catch (e) {
        if (e && e.name === 'AbortError') return;
        if (my === req) hide();
      }
    }

    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(run, 160);
    });
    input.addEventListener('keydown', (e) => {
      if (box.hidden || !items.length) {
        if (e.key === 'Enter' && (input.value || '').trim()) {
          e.preventDefault();
          onPick({ id: input.value.trim(), name: input.value.trim() });
          hide();
        }
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        active = (active + 1) % items.length;
        paint();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        active = (active - 1 + items.length) % items.length;
        paint();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (active >= 0 && items[active]) {
          onPick(items[active]);
          hide();
        }
      } else if (e.key === 'Escape') hide();
    });
    input.addEventListener('blur', () => {
      setTimeout(() => { if (document.activeElement !== input) hide(); }, 120);
    });
    input.addEventListener('focus', () => {
      if ((input.value || '').trim().length >= 1) run();
    });
  }

  function bindAll() {
    const form = $('warnFilterForm');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        liveRefresh();
      });
    }

    function clearQ() {
      if ($('wqHidden')) $('wqHidden').value = '';
      if ($('wq')) $('wq').value = '';
      $('wqSuggest') && ($('wqSuggest').hidden = true, $('wqSuggest').innerHTML = '');
      $('wqChip')?.remove();
      const btn = $('wqClear');
      if (btn) btn.hidden = true;
      liveRefresh({ q: '' });
    }
    function clearMod() {
      if ($('wmodHidden')) $('wmodHidden').value = '';
      if ($('wmod')) $('wmod').value = '';
      $('wmodSuggest') && ($('wmodSuggest').hidden = true, $('wmodSuggest').innerHTML = '');
      $('wmodChip')?.remove();
      liveRefresh({ mod: '' });
    }

    $('wqClear')?.addEventListener('click', (e) => { e.preventDefault(); clearQ(); });
    $('wqChipX')?.addEventListener('click', (e) => { e.preventDefault(); clearQ(); });
    $('wmodClear')?.addEventListener('click', (e) => { e.preventDefault(); clearMod(); });
    $('wmodChipX')?.addEventListener('click', (e) => { e.preventDefault(); clearMod(); });

    ['wScope', 'wBranch', 'wSort'].forEach((id) => {
      $(id)?.addEventListener('change', () => liveRefresh());
    });

    document.querySelectorAll('[data-live-tab]').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const t = a.getAttribute('data-live-tab');
        if ($('wTabHidden')) $('wTabHidden').value = t;
        tab = t;
        liveRefresh({ tab: t, branch: t === 'staff' ? (paramsFromForm().get('branch') || '') : '' });
      });
    });

    document.querySelectorAll('[data-live-page]').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        liveRefresh({ page: a.getAttribute('data-live-page'), keepPage: 1 });
      });
    });

    const staffFilter = tab === 'staff' ? true : (tab === 'members' ? false : null);
    if ($('wq') && $('wqSuggest')) {
      wireSuggest($('wq'), $('wqSuggest'), (it) => {
        $('wqHidden').value = it.id || it.name || '';
        $('wq').value = '';
        liveRefresh({ q: $('wqHidden').value });
      }, staffFilter);
    }
    if ($('wmod') && $('wmodSuggest')) {
      wireSuggest($('wmod'), $('wmodSuggest'), (it) => {
        $('wmodHidden').value = it.id || '';
        $('wmod').value = '';
        liveRefresh({ mod: $('wmodHidden').value });
      }, null);
    }

    $('btnResync')?.addEventListener('click', async () => {
      if (!confirm('Пересинхронизировать кэш участников, ролей и каналов?')) return;
      const btn = $('btnResync');
      btn.disabled = true;
      btn.textContent = '…';
      try {
        const r = await fetch('/api/warns/resync', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ csrf }),
        });
        const j = await r.json();
        if (!j.ok) { toast(j.error || 'Ошибка', false); return; }
        toast('Синк готов', true);
        await liveRefresh({ keepPage: 1 });
      } catch (_) { toast('Сеть', false); }
      finally {
        const b = $('btnResync');
        if (b) { b.disabled = false; b.textContent = 'Пересинхронизировать'; }
      }
    });

    document.querySelectorAll('.btn-extend').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm('Продлить варн #' + btn.dataset.wid + '?')) return;
        const r = await fetch('/api/warns/extend', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ warn_id: Number(btn.dataset.wid), csrf }),
        });
        const j = await r.json();
        if (!j.ok) { toast(j.error || 'Ошибка', false); return; }
        toast('Продлено', true);
        liveRefresh({ keepPage: 1 });
      });
    });

    // issue / remove — dialogs живут вне live root
    document.querySelectorAll('.btn-issue-row').forEach((btn) => {
      btn.addEventListener('click', () => openIssue(btn.dataset.uid, btn.dataset.kind, btn.dataset.name));
    });
    document.querySelectorAll('.btn-unwarn').forEach((btn) => {
      btn.addEventListener('click', () => {
        rmWid = Number(btn.dataset.wid);
        rmUid = btn.dataset.uid;
        $('rmReason').value = '';
        $('rmMsg').textContent = '';
        $('rmHint').textContent = 'Снять варн у ' + (btn.dataset.name || rmUid) + '?';
        rmDlg.showModal();
      });
    });

    $('btnIssueWarn')?.addEventListener('click', () => {
      openIssue('', tab === 'staff' ? 'staff' : 'member');
    });
  }

  // dialogs (stable, outside live root)
  const dlg = $('warnDlg');
  const codeSel = $('warnCode');
  const kindSel = $('warnKind');
  const msg = $('warnMsg');
  const rmDlg = $('rmDlg');
  let rmWid = 0;
  let rmUid = '';

  function fillCodes() {
    if (!codeSel || !kindSel) return;
    const list = reasons[kindSel.value] || [];
    codeSel.innerHTML = list.map((r) =>
      `<option value="${esc(r.code)}">${esc(r.code)} · ${esc(r.label)}</option>`
    ).join('');
  }

  function openIssue(uid, kind, name) {
    if (!dlg) return;
    msg.textContent = '';
    $('warnUid').value = uid || '';
    $('warnUidSearch').value = name || uid || '';
    $('warnPicked').textContent = uid ? (`Выбран: ${name || ''} · ${uid}`) : '';
    if (kind) { kindSel.value = kind; fillCodes(); }
    dlg.showModal();
    if (!uid) setTimeout(() => $('warnUidSearch')?.focus(), 40);
  }

  if (kindSel) {
    kindSel.addEventListener('change', fillCodes);
    fillCodes();
  }
  $('warnClose')?.addEventListener('click', () => dlg?.close());
  $('warnCancel')?.addEventListener('click', () => dlg?.close());
  $('rmClose')?.addEventListener('click', () => rmDlg?.close());
  $('rmCancel')?.addEventListener('click', () => rmDlg?.close());

  if ($('warnUidSearch') && $('warnUidSuggest')) {
    wireSuggest($('warnUidSearch'), $('warnUidSuggest'), (it) => {
      $('warnUid').value = it.id;
      $('warnUidSearch').value = it.name || it.id;
      $('warnPicked').textContent = `Выбран: ${it.name || ''} · ${it.id}`;
      kindSel.value = it.is_staff ? 'staff' : 'member';
      fillCodes();
    }, null);
  }

  $('warnGo')?.addEventListener('click', async () => {
    msg.textContent = '…';
    const body = {
      user_id: ($('warnUid').value.trim() || $('warnUidSearch').value.trim()),
      reason_type: kindSel.value,
      reason_code: codeSel.value,
      detail: $('warnDetail').value.trim(),
      csrf,
    };
    if (!body.user_id || !body.detail) {
      msg.textContent = 'Выбери человека и формулировку';
      return;
    }
    const r = await fetch('/api/warns/issue', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.ok) { msg.textContent = j.error || 'Ошибка'; return; }
    dlg.close();
    $('warnDetail').value = '';
    toast('Варн выдан', true);
    liveRefresh({ keepPage: 1 });
  });

  $('rmGo')?.addEventListener('click', async () => {
    $('rmMsg').textContent = '…';
    const r = await fetch('/api/warns/remove', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        warn_id: rmWid, user_id: rmUid,
        removed_reason: $('rmReason').value.trim(), csrf,
      }),
    });
    const j = await r.json();
    if (!j.ok) { $('rmMsg').textContent = j.error || 'Ошибка'; return; }
    rmDlg.close();
    toast('Снято', true);
    liveRefresh({ keepPage: 1 });
  });

  function onPop() {
    if (!root.isConnected) {
      window.removeEventListener('popstate', onPop);
      return;
    }
    const p = new URLSearchParams(location.search);
    liveRefresh({
      tab: p.get('tab') || 'members',
      q: p.get('q') || '',
      scope: p.get('scope') || 'active',
      branch: p.get('branch') || '',
      mod: p.get('mod') || '',
      sort: p.get('sort') || 'count_desc',
      page: p.get('page') || '1',
      keepPage: 1,
    });
  }
  if (window.__warnLivePop) {
    window.removeEventListener('popstate', window.__warnLivePop);
  }
  window.__warnLivePop = onPop;
  window.addEventListener('popstate', onPop);

  bindAll();
  window.__warnLiveRefresh = liveRefresh;
})();
