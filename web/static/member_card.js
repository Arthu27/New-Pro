/* Карточка участника 360° — общий рендер досье.
   Подключается на страницах:
   - /member-card (полноценная страница с поиском);
   - /users (перетаскиваемое окно из списка участников).
   Рендерит по стандартным ID: mcKpis, mcProfile, mcActivity, mcKarma,
   mcWarns, mcEvents, mcLinks — страница обязана иметь этот каркас. */
(function () {
  'use strict';

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m100 >= 11 && m100 <= 19) return many;
    if (m10 === 1) return one;
    if (m10 >= 2 && m10 <= 4) return few;
    return many;
  }

  function fmtNum(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

  function fmtVoice(s) {  // 1:1 с _fmt_t карточки бота
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h ? h + 'ч ' + m + 'м' : m + 'м';
  }

  function kpi(icon, num, label) {
    return '<div class="mc-kpi"><i class="fas ' + icon + '"></i><div><b>' + num + '</b> <span>' + esc(label) + '</span></div></div>';
  }

  var SRC_LABELS = {discord: 'ник с сервера', audit: 'из журнала аудита', birthday: 'из календаря ДР'};

  function $(id) { return document.getElementById(id); }
  function put(id, html) { var el = $(id); if (el) el.innerHTML = html; }

  function renderCard(c) {
    var a = c.activity, eco = c.economy, km = c.karma;
    put('mcKpis',
      kpi('fa-arrow-trend-up', a.level, 'уровень') +
      kpi('fa-comments', fmtNum(a.messages), plural(a.messages, 'сообщение', 'сообщения', 'сообщений')) +
      kpi('fa-microphone', fmtVoice(a.voice_seconds), 'в голосовых') +
      kpi('fa-coins', fmtNum(eco.total), 'монет всего') +
      kpi('fa-hand-holding-heart', fmtNum(km.score), plural(km.score, 'очко кармы', 'очка кармы', 'очков кармы')) +
      kpi('fa-triangle-exclamation', c.warns.count, plural(c.warns.count, 'варн', 'варна', 'варнов')));

    var m = c.member;
    var ava = m && m.avatar_url
      ? '<img src="' + esc(m.avatar_url) + '" alt="">'
      : (c.name ? esc(c.name.charAt(0).toUpperCase()) : '?');
    put('mcProfile',
      '<div class="mc-head">' +
        '<div class="mc-ava">' + ava + '</div>' +
        '<div><b>' + (c.name ? esc(c.name) : 'ID ' + esc(c.user_id)) + '</b>' +
        '<small>ID ' + esc(c.user_id) + (c.name_source ? ' · имя ' + (SRC_LABELS[c.name_source] || '') : '') + '</small></div>' +
        (m && m.booster ? '<span class="mc-boost"><i class="fas fa-gem"></i> бустер</span>' : '') +
      '</div>' +
      '<div class="mc-row"><span>Уровень ' + a.level + '</span><span class="num">' + fmtNum(a.xp) + ' XP</span></div>' +
      '<div class="mc-track"><div class="mc-fill" style="width:' + Math.min(100, Math.round(a.xp * 100 / (a.xp_needed || 1))) + '%"></div></div>' +
      '<div class="mc-xp">' + fmtNum(a.xp) + ' из ' + fmtNum(a.xp_needed) + ' XP до следующего уровня</div>' +
      (m ? '<div class="mc-chips">' +
        (m.joined_at ? '<span class="mc-chip"><i class="fas fa-door-open"></i> на сервере с ' + esc(m.joined_at) + '</span>' : '') +
        '<span class="mc-chip"><i class="fas fa-user-tag"></i> ' + m.roles + ' ' + plural(m.roles, 'роль', 'роли', 'ролей') + '</span>' +
        (m.top_role && m.top_role !== '@everyone' ? '<span class="mc-chip"><i class="fas fa-crown"></i> ' + esc(m.top_role) + '</span>' : '') +
      '</div>' : '<div class="mc-xp" style="margin-top:8px">Бот офлайн — дата входа и роли недоступны.</div>'));

    put('mcActivity',
      '<div class="mc-row"><span>Сообщения<small>за всё время по таблице лидеров</small></span><span class="num">' + fmtNum(a.messages) + '</span></div>' +
      '<div class="mc-row"><span>Голосовые<small>суммарно, трекер + наследие</small></span><span class="num">' + fmtVoice(a.voice_seconds) + '</span></div>' +
      '<div class="mc-row"><span>Баланс экономики<small>кошелёк ' + fmtNum(eco.balance) + ' + банк ' + fmtNum(eco.bank) + '</small></span><span class="num">' + fmtNum(eco.total) + '</span></div>' +
      '<div class="mc-chips">' +
        '<span class="mc-chip"><i class="fas fa-comments"></i> по сообщениям <b>#' + a.rank_messages + '</b></span>' +
        '<span class="mc-chip"><i class="fas fa-microphone"></i> по голосу <b>#' + a.rank_voice + '</b></span>' +
        '<span class="mc-chip"><i class="fas fa-coins"></i> по богатству <b>#' + a.rank_balance + '</b></span>' +
      '</div>');

    put('mcKarma',
      '<div class="mc-row"><span>Очки кармы<small>место в топе: ' + (km.rank ? '#' + km.rank : 'вне топа (0 очков)') + '</small></span><span class="num">' + fmtNum(km.score) + '</span></div>' +
      '<div class="mc-row"><span>Благодарностей получено<small>по журналу (хвост 200 записей)</small></span><span class="num">' + km.received + '</span></div>' +
      '<div class="mc-row"><span>Благодарностей отправлено<small>по журналу</small></span><span class="num">' + km.given + '</span></div>');

    var w = c.warns;
    var wh = '<div class="mc-row"><span>Всего предупреждений</span><span class="num">' + w.count + '</span></div>';
    if (!w.recent.length) {
      wh += '<div class="mc-row"><span style="color:var(--text-3)">Чисто — варнов нет.</span></div>';
    }
    w.recent.forEach(function (it) {
      wh += '<div class="mc-row"><span>#' + esc(it.id) + ' ' + esc(it.reason) +
        '<small>' + esc(it.date) + ' · ' + esc(it.mod) + '</small></span></div>';
    });
    put('mcWarns', wh);

    var b = c.birthday;
    var eh = '';
    if (b) {
      eh += '<div class="mc-row"><span>День рождения<small>' + esc(b.date) + (b.age != null ? ' · исполнится ' + b.age : '') + '</small></span>' +
        '<span class="mc-tag ' + (b.today ? 'ok' : 'warn') + '">' + (b.today ? 'сегодня' : 'через ' + b.days_until + ' ' + plural(b.days_until, 'день', 'дня', 'дней')) + '</span></div>';
    } else {
      eh += '<div class="mc-row"><span style="color:var(--text-3)">День рождения не записан в календаре.</span></div>';
    }
    if (c.member && c.member.joined_at) {
      eh += '<div class="mc-row"><span>На сервере с</span><span class="num" style="font-size:12px">' + esc(c.member.joined_at) + '</span></div>';
    }
    put('mcEvents', eh);

    put('mcLinks', c.links.map(function (l) {
      return '<a class="mc-link" href="' + esc(l.path) + '"><i class="fas ' + esc(l.icon) + '"></i> ' + esc(l.label) + '</a>';
    }).join(''));
  }

  window.MemberCard = {
    esc: esc,
    plural: plural,
    fmtNum: fmtNum,
    fmtVoice: fmtVoice,
    renderCard: renderCard
  };
})();
