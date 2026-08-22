/* Aether Music — встроенная активность Discord.
   Подключается к голосовому каналу через Embedded App SDK и управляет
   плеером бота через /api/activity/music/*. */
(function () {
  'use strict';

  var DiscordSDK = (window.DiscordSDKBundle && window.DiscordSDKBundle.DiscordSDK) || null;
  var app = document.getElementById('app');

  var state = {
    token: null,
    guildId: null,
    channelId: null,
    clientId: '',
    redirectUri: '',
    demo: false,
    payload: null,
    authUser: null,
  };

  /* ── иконки (inline SVG, без внешних библиотек) ── */
  var ICONS = {
    music: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 3v10.55A4 4 0 1 0 11 17V7h8V3H9z"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    skip: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6l8 6-8 6V6zm10 0v12h2V6h-2z"/></svg>',
    shuffle: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 7h12l-1 14H7L6 7zm3-3h6l1 2H8l1-2zm-2 5v9h2V9H7zm4 0v9h2V9h-2zm4 0v9h2V9h-2z"/></svg>',
    leave: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 3h-2v10h2V3zm-8.17 6.59L6 11.41 1.59 7 6 2.59 7.83 4.42 5.25 7H14v2H5.25l2.58 2.59zM20 19h-2v-4h-2v6h4v-2z"/></svg>',
    vol: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8.5v7a4.5 4.5 0 0 0 2.5-3.5zM14 3.2v2.06a7 7 0 0 1 0 13.48v2.06a9 9 0 0 0 0-17.6z"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2 1 21h22L12 2zm1 14h-2v2h2v-2zm0-6h-2v4h2v-4z"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.65 6.35A8 8 0 1 0 19 12h-2a6 6 0 1 1-1.76-4.24L12 11h7V4l-1.35 2.35z"/></svg>',
  };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function banner(icon, html, isErr) {
    return '<div class="banner' + (isErr ? ' err' : '') + '">' + icon + '<div>' + html + '</div></div>';
  }

  function loading(html) {
    return '<section class="state-loading"><div class="spinner"></div><p>' + html + '</p></section>';
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (state.token) opts.headers['Authorization'] = 'Bearer ' + state.token;
    if (opts.body && typeof opts.body === 'object') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    return fetch(path, opts).then(function (r) { return r.json(); });
  }

  /* ── конфиг ── */
  function loadConfig() {
    return api('/api/activity/music/config')
      .then(function (cfg) {
        state.clientId = (cfg && cfg.client_id) || '';
        state.redirectUri = (cfg && cfg.redirect_uri) || '';
        state.demo = !!(cfg && cfg.demo);
      })
      .catch(function () {});
  }

  /* ── подключение к Discord ── */
  async function connectDiscord() {
    await loadConfig();

    if (state.demo) {
      state.token = 'demo';
      state.guildId = 'demo';
      state.channelId = 'demo';
      state.authUser = { username: 'демо' };
      return;
    }

    if (!DiscordSDK) {
      throw new Error('SDK не загружен');
    }
    if (!state.clientId) {
      throw new Error('Не задан ACTIVITY_CLIENT_ID — см. docs/EMBEDDED_APP.md');
    }

    var sdk = new DiscordSDK(state.clientId);
    await sdk.ready();

    var auth = await sdk.commands.authorize({
      client_id: state.clientId,
      response_type: 'code',
      state: '',
      prompt: 'none',
      scope: ['identify'],
    });

    var tokenResp = await api('/api/activity/music/token', {
      method: 'POST',
      body: { code: auth.code, redirect_uri: state.redirectUri },
    });
    if (!tokenResp.success || !tokenResp.access_token) {
      throw new Error(tokenResp.error || 'Не удалось получить токен');
    }
    state.token = tokenResp.access_token;

    var authResult = await sdk.commands.authenticate({ access_token: state.token });
    state.authUser = authResult.user || {};
    state.guildId = authResult.guild_id || null;
    state.channelId = authResult.channel_id || null;
  }

  /* ── рендер ── */
  function render() {
    var p = state.payload;
    if (!p) {
      app.innerHTML = loading('Загружаем плеер…');
      return;
    }
    if (p.offline) {
      app.innerHTML =
        banner(ICONS.warn, 'Бот офлайн или музыкальный модуль выключен. Запустите бота с музыкой (профиль <b>BOT_SLIM=1</b>).', true);
      return;
    }

    var headPill = p.connected
      ? '<span class="head-pill live"><span class="dot"></span> В канале</span>'
      : '<span class="head-pill off"><span class="dot"></span> Не подключён</span>';

    var cur = p.current;
    var playing = p.playing && !p.paused;

    var nowBlock = cur
      ? '<div class="now">'
        + '<div class="now-art">' + ICONS.music + '</div>'
        + '<div class="now-copy">'
        + '<div class="now-track">' + esc(cur.query) + '</div>'
        + '<div class="now-req">заказал: ' + esc(cur.requester || '—') + '</div>'
        + '<div class="now-state">' + (p.paused ? 'на паузе' : (p.playing ? 'играет' : 'стоп')) + '</div>'
        + '</div>'
        + '<div class="now-controls">'
        + '<button class="btn round primary" data-act="' + (playing ? 'pause' : 'resume') + '" title="' + (playing ? 'Пауза' : 'Играть') + '">' + (playing ? ICONS.pause : ICONS.play) + '</button>'
        + '<button class="btn round" data-act="skip" title="Следующий">' + ICONS.skip + '</button>'
        + '</div>'
        + '</div>'
      : '<div class="empty">Сейчас ничего не играет — добавьте треки командой бота.</div>';

    var queue = (p.queue || []);
    var queueBlock = queue.length
      ? '<div class="queue">' + queue.map(function (s) {
          return '<div class="q-item' + (s.n === 1 ? ' current' : '') + '">'
            + '<span class="q-num">' + s.n + '</span>'
            + '<span class="q-track">' + esc(s.query) + '</span>'
            + '<span class="q-req">' + esc(s.requester || '') + '</span>'
            + '</div>';
        }).join('') + '</div>'
      : '<div class="empty">Очередь пуста.</div>';

    var vol = (p.volume == null ? 100 : p.volume);
    var volBlock =
      '<div class="volume">' + ICONS.vol
      + '<input type="range" min="0" max="' + (p.volume_max || 200) + '" value="' + vol + '" data-role="volume">'
      + '<span class="vol-num">' + vol + '%</span></div>';

    var toolbar =
      '<div class="card" style="padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap">'
      + '<button class="btn" data-act="shuffle">' + ICONS.shuffle + ' Перемешать</button>'
      + '<button class="btn" data-act="clear">' + ICONS.trash + ' Очистить</button>'
      + '<button class="btn danger" data-act="leave">' + ICONS.leave + ' Отключить</button>'
      + '<button class="btn" data-role="refresh" style="margin-left:auto">' + ICONS.refresh + '</button>'
      + '</div>';

    app.innerHTML =
      '<div class="head">'
      + '<div class="head-ico">' + ICONS.music + '</div>'
      + '<div><div class="head-title">Музыка сервера</div>'
      + '<div class="head-sub">' + esc(p.channel || 'голосовой канал') + (state.authUser ? ' · вы: ' + esc(state.authUser.username || state.authUser.global_name || '') : '') + '</div></div>'
      + headPill
      + '</div>'
      + '<div class="card">' + nowBlock + '</div>'
      + '<div class="card">'
      + '<div class="sec-title">Очередь <span class="count">' + p.total + ' треков</span></div>'
      + queueBlock
      + volBlock
      + '</div>'
      + toolbar
      + '<div class="footer">Aether Music · управление ботом в голосовом канале</div>';
  }

  function refresh() {
    var q = state.guildId ? ('?guild_id=' + encodeURIComponent(state.guildId)) : '';
    return api('/api/activity/music/state' + q)
      .then(function (p) {
        state.payload = p;
        render();
      })
      .catch(function () {
        state.payload = { success: false, offline: true, error: 'Сеть' };
        render();
      });
  }

  function control(action, extra) {
    var body = { action: action, guild_id: state.guildId };
    if (extra) for (var k in extra) body[k] = extra[k];
    return api('/api/activity/music/control', { method: 'POST', body: body })
      .then(function (p) {
        if (p && p.success) { state.payload = p; render(); }
        else renderError(p && p.error);
      })
      .catch(function () { renderError('Ошибка соединения'); });
  }

  function renderError(msg) {
    var b = banner(ICONS.warn, esc(msg || 'Ошибка'), true);
    app.insertAdjacentHTML('beforeend', b);
  }

  /* ── события ── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-act]');
    if (btn) { control(btn.getAttribute('data-act')); return; }
    if (e.target.closest('[data-role="refresh"]')) { refresh(); }
  });

  var volTimer = null;
  document.addEventListener('input', function (e) {
    if (e.target && e.target.getAttribute('data-role') === 'volume') {
      var n = e.target.parentElement.querySelector('.vol-num');
      if (n) n.textContent = e.target.value + '%';
      clearTimeout(volTimer);
      volTimer = setTimeout(function () {
        control('volume', { volume: parseInt(e.target.value, 10) });
      }, 250);
    }
  });

  /* ── старт ── */
  app.innerHTML = loading('Подключаемся к голосовому каналу…');
  connectDiscord()
    .then(function () { return refresh(); })
    .then(function () {
      if (window.setInterval) {
        setInterval(function () {
          if (state.token) refresh();
        }, 6000);
      }
    })
    .catch(function (err) {
      var msg = err && err.message ? err.message : String(err);
      app.innerHTML =
        banner(ICONS.info, 'Эту панель нужно открывать как <b>Активность</b> в голосовом канале Discord. '
          + 'Вне Discord она показывает только заглушку.' + (msg ? '<br>' + esc(msg) : ''), true);
      state.token = 'demo';
      state.guildId = 'demo';
      api('/api/activity/music/state?guild_id=demo').then(function (p) {
        if (p && p.success) { state.payload = p; render(); }
      }).catch(function () {});
    });
})();
