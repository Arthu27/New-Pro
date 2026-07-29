import os

templates_dir = os.path.join(os.path.dirname(__file__), 'web', 'templates')

# logs.html - onmouseover/onmouseout tırnak sorunu исправлено
logs_html = """{% extends "base.html" %}
{% block title %}Mod Логиi - Aether{% endblock %}
{% block page_title %}MOD LOGLARI{% endblock %}
{% block content %}
<div class="section">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-ботtom:20px;flex-wrap:wrap;gap:10px;">
    <h2><i class="fas fa-clipboard-list" style="color:#dc143c;"></i> Tum Mod Islemleri</h2>
    <input type="text" id="log-filter" placeholder="Filtrele..." style="padding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-radius:8px;color:#eee;width:300px;" oninput="filterLogs()">
  </div>
  <div id="logs-list" style="color:#aaa;text-align:center;padding:40px;">
    <i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...
  </div>
</div>
<script>
var allLogs = [];
async function loadLogs() {
  try {
    var r = await fetch('/api/logs');
    allLogs = await r.json();
    displayLogs(allLogs);
  } catch(e) {
    document.getElementById('logs-list').innerHTML = '<p style="color:#e74c3c;">Ошибка: ' + e.message + '</p>';
  }
}
function displayLogs(logs) {
  if (!logs || !logs.length) {
    document.getElementById('logs-list').innerHTML = '<p style="color:#aaa;text-align:center;padding:40px;"><i class="fas fa-inbox" style="font-size:40px;color:#333;"></i><br><br>Hic log bulunamadi</p>';
    return;
  }
  var colors = { ban:'#e74c3c', kick:'#e67e22', timeout:'#f39c12', warn:'#f1c40f', mute:'#9b59b6' };
  var rows = '';
  for (var i = 0; i < Math.min(logs.length, 100); i++) {
    var log = logs[i];
    var ac = colors[log.action] || '#667eea';
    var bg = i % 2 === 0 ? 'rgba(220,20,60,0.03)' : 'transparent';
    rows += '<tr style="border-ботtom:1px solid rgba(255,255,255,0.05);background:' + bg + ';">';
    rows += '<td style="padding:12px;color:#ffd700;font-weight:700;">#' + (log.case_id || '-') + '</td>';
    rows += '<td style="padding:12px;"><span style="background:' + ac + ';padding:4px 10px;border-radius:4px;font-size:11px;font-weight:700;color:white;">' + (log.action || '?').toUpperCase() + '</span></td>';
    rows += '<td style="padding:12px;"><code style="color:#dc143c;font-size:12px;">' + log.user_id + '</code></td>';
    rows += '<td style="padding:12px;"><code style="color:#aaa;font-size:12px;">' + log.mod_id + '</code></td>';
    rows += '<td style="padding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (log.reason || '-') + '</td>';
    rows += '<td style="padding:12px;color:#888;font-size:12px;">' + (log.timestamp ? new Date(log.timestamp).toLocaleString('tr-TR') : '-') + '</td>';
    rows += '</tr>';
  }
  var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
  html += '<tr style="border-ботtom:2px solid rgba(220,20,60,0.3);">';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Case</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Islem</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Kullanici</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Moderator</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Причина</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Дата</th>';
  html += '</tr>' + rows + '</table></div>';
  html += '<p style="margin-top:15px;color:#666;font-size:13px;">Всего ' + logs.length + ' islem</p>';
  document.getElementById('logs-list').innerHTML = html;
}
function filterLogs() {
  var q = document.getElementById('log-filter').value.toLowerCase();
  displayLogs(allLogs.filter(function(l) {
    return String(l.user_id||'').includes(q) || String(l.mod_id||'').includes(q) ||
           (l.reason||'').toLowerCase().includes(q) || (l.action||'').toLowerCase().includes(q);
  }));
}
loadLogs();
setInterval(loadLogs, 15000);
</script>
{% endblock %}
"""

with open(os.path.join(templates_dir, 'logs.html'), 'w', encoding='utf-8') as f:
    f.write(logs_html)
print("logs.html duzeltildi")

# warnings.html
warnings_html = """{% extends "base.html" %}
{% block title %}Uyarilar - Aether{% endblock %}
{% block page_title %}UYARI SİSTEMİ{% endblock %}
{% block content %}
<div class="section">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-ботtom:20px;flex-wrap:wrap;gap:10px;">
    <h2><i class="fas fa-exclamation-triangle" style="color:#dc143c;"></i> Tum Uyarilar</h2>
    <input type="text" id="warn-filter" placeholder="Filtrele..." style="padding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-radius:8px;color:#eee;width:300px;" oninput="filterWarnings()">
  </div>
  <div id="warnings-list" style="color:#aaa;text-align:center;padding:40px;">
    <i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...
  </div>
</div>
<script>
var allWarnings = [];
async function loadWarnings() {
  try {
    var r = await fetch('/api/warnings');
    allWarnings = await r.json();
    displayWarnings(allWarnings);
  } catch(e) {
    document.getElementById('warnings-list').innerHTML = '<p style="color:#e74c3c;">Ошибка: ' + e.message + '</p>';
  }
}
function displayWarnings(warns) {
  if (!warns || !warns.length) {
    document.getElementById('warnings-list').innerHTML = '<p style="color:#aaa;text-align:center;padding:40px;"><i class="fas fa-inbox" style="font-size:40px;color:#333;"></i><br><br>Hic uyari bulunamadi</p>';
    return;
  }
  var rows = '';
  for (var i = 0; i < Math.min(warns.length, 100); i++) {
    var w = warns[i];
    var bg = i % 2 === 0 ? 'rgba(220,20,60,0.03)' : 'transparent';
    rows += '<tr style="border-ботtom:1px solid rgba(255,255,255,0.05);background:' + bg + ';">';
    rows += '<td style="padding:12px;"><code style="color:#dc143c;font-size:12px;">' + w.user_id + '</code></td>';
    rows += '<td style="padding:12px;color:#ffd700;">' + (w.moderator || '-') + '</td>';
    rows += '<td style="padding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (w.reason || '-') + '</td>';
    rows += '<td style="padding:12px;color:#888;font-size:12px;">' + (w.timestamp ? new Date(w.timestamp).toLocaleString('tr-TR') : '-') + '</td>';
    rows += '<td style="padding:12px;"><code style="color:#aaa;font-size:11px;">' + w.guild_id + '</code></td>';
    rows += '</tr>';
  }
  var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
  html += '<tr style="border-ботtom:2px solid rgba(220,20,60,0.3);">';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Kullanici ID</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Moderator</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Причина</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Дата</th>';
  html += '<th style="padding:12px;text-align:left;color:#dc143c;">Сервер</th>';
  html += '</tr>' + rows + '</table></div>';
  html += '<p style="margin-top:15px;color:#666;font-size:13px;">Всего ' + warns.length + ' uyari</p>';
  document.getElementById('warnings-list').innerHTML = html;
}
function filterWarnings() {
  var q = document.getElementById('warn-filter').value.toLowerCase();
  displayWarnings(allWarnings.filter(function(w) {
    return String(w.user_id||'').includes(q) || (w.moderator||'').toLowerCase().includes(q) ||
           (w.reason||'').toLowerCase().includes(q);
  }));
}
loadWarnings();
setInterval(loadWarnings, 15000);
</script>
{% endblock %}
"""

with open(os.path.join(templates_dir, 'warnings.html'), 'w', encoding='utf-8') as f:
    f.write(warnings_html)
print("warnings.html duzeltildi")
print("Завершено!")
