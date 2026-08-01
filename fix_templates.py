import os

templates_dir = os.path.join(os.path.dirname(__file__), 'web', 'templates')

# логs.html - onmouseover/onmouseout кавычки sorunu haklarыkuruldu
логs_html = """{% extends "base.html" %}
{% block title %}Логи модерации - Aether{% endblock %}
{% block page_title %}MOD LOGLARI{% endblock %}
{% block content %}
<div class="section">
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px;">
 <h2><i class="fas fa-clipboard-list" style="color:#dc143c;"></i> Tum Мод Islemleri</h2>
 <input type="text" id="лог-filter" placeholder="Фильтр..." style="pимяding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-rимяius:8px;color:#eee;width:300px;" oninput="filterЛогs()">
 </div>
 <div id="логs-list" style="color:#aaa;text-align:center;pимяding:40px;">
 <i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...
 </div>
</div>
<script>
var allЛогs = [];
async function loимяЛогs() {
 try {
 var r = await fetch('/api/логs');
 allЛогs = await r.json();
 displayЛогs(allЛогs);
 } catch(e) {
 document.getElementById('логs-list').innerHTML = '<p style="color:#e74c3c;">Ошибка: ' + e.message + '</p>';
 }
}
function displayЛогs(логs) {
 if (!логs || !логs.length) {
 document.getElementById('логs-list').innerHTML = '<p style="color:#aaa;text-align:center;pимяding:40px;"><i class="fas fa-inbox" style="font-size:40px;color:#333;"></i><br><br>Hic лог не найдено</p>';
 return;
 }
 var colors = { бан:'#e74c3c', кик:'#e67e22', timeout:'#f39c12', варн:'#f1c40f', мут:'#9b59b6' };
 var rows = '';
 for (var i = 0; i < Math.min(логs.length, 100); i++) {
 var лог = логs[i];
 var ac = colors[лог.action] || '#667eea';
 var bg = i % 2 === 0 ? 'rgba(220,20,60,0.03)' : 'transparent';
 rows += '<tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:' + bg + ';">';
 rows += '<td style="pимяding:12px;color:#ffd700;font-weight:700;">#' + (лог.case_id || '-') + '</td>';
 rows += '<td style="pимяding:12px;"><span style="background:' + ac + ';pимяding:4px 10px;border-rимяius:4px;font-size:11px;font-weight:700;color:white;">' + (лог.action || '?').toUpperCase() + '</span></td>';
 rows += '<td style="pимяding:12px;"><code style="color:#dc143c;font-size:12px;">' + лог.user_id + '</code></td>';
 rows += '<td style="pимяding:12px;"><code style="color:#aaa;font-size:12px;">' + лог.мод_id + '</code></td>';
 rows += '<td style="pимяding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (лог.reason || '-') + '</td>';
 rows += '<td style="pимяding:12px;color:#888;font-size:12px;">' + (лог.timestamp ? new Date(лог.timestamp).toLocaleString('tr-TR') : '-') + '</td>';
 rows += '</tr>';
 }
 var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
 html += '<tr style="border-bottom:2px solid rgba(220,20,60,0.3);">';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Case</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Islem</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Пользователь</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Модerator</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Причина</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Дата</th>';
 html += '</tr>' + rows + '</table></div>';
 html += '<p style="margin-top:15px;color:#666;font-size:13px;">Всего ' + логs.length + ' islem</p>';
 document.getElementById('логs-list').innerHTML = html;
}
function filterЛогs() {
 var q = document.getElementById('лог-filter').value.toLowerCase();
 displayЛогs(allЛогs.filter(function(l) {
 return String(l.user_id||'').includes(q) || String(l.мод_id||'').includes(q) ||
 (l.reason||'').toLowerCase().includes(q) || (l.action||'').toLowerCase().includes(q);
 }));
}
loимяЛогs();
setInterval(loимяЛогs, 15000);
</script>
{% endblock %}
"""
with open(os.path.join(templates_dir, 'логs.html'), 'w', encoding='utf-8') as f:
    f.write(логs_html)
print("логs.html duzeltildi")

# варнings.html
варнings_html = """{% extends "base.html" %}
{% block title %}Предупреждения - Aether{% endblock %}
{% block page_title %}ПРЕДУПРЕЖДЕНИЕ СИСТЕМА{% endblock %}
{% block content %}
<div class="section">
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px;">
 <h2><i class="fas fa-exclamation-triangle" style="color:#dc143c;"></i> Tum Предупреждения</h2>
 <input type="text" id="варн-filter" placeholder="Фильтр..." style="pимяding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-rимяius:8px;color:#eee;width:300px;" oninput="filterПредупреждениеs()">
 </div>
 <div id="варнings-list" style="color:#aaa;text-align:center;pимяding:40px;">
 <i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...
 </div>
</div>
<script>
var allПредупреждениеs = [];
async function loимяПредупреждениеs() {
 try {
 var r = await fetch('/api/варнings');
 allПредупреждениеs = await r.json();
 displayПредупреждениеs(allПредупреждениеs);
 } catch(e) {
 document.getElementById('варнings-list').innerHTML = '<p style="color:#e74c3c;">Ошибка: ' + e.message + '</p>';
 }
}
function displayПредупреждениеs(варнs) {
 if (!варнs || !варнs.length) {
 document.getElementById('варнings-list').innerHTML = '<p style="color:#aaa;text-align:center;pимяding:40px;"><i class="fas fa-inbox" style="font-size:40px;color:#333;"></i><br><br>Hic предупреждение не найдено</p>';
 return;
 }
 var rows = '';
 for (var i = 0; i < Math.min(варнs.length, 100); i++) {
 var w = варнs[i];
 var bg = i % 2 === 0 ? 'rgba(220,20,60,0.03)' : 'transparent';
 rows += '<tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:' + bg + ';">';
 rows += '<td style="pимяding:12px;"><code style="color:#dc143c;font-size:12px;">' + w.user_id + '</code></td>';
 rows += '<td style="pимяding:12px;color:#ffd700;">' + (w.модerator || '-') + '</td>';
 rows += '<td style="pимяding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (w.reason || '-') + '</td>';
 rows += '<td style="pимяding:12px;color:#888;font-size:12px;">' + (w.timestamp ? new Date(w.timestamp).toLocaleString('tr-TR') : '-') + '</td>';
 rows += '<td style="pимяding:12px;"><code style="color:#aaa;font-size:11px;">' + w.guild_id + '</code></td>';
 rows += '</tr>';
 }
 var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
 html += '<tr style="border-bottom:2px solid rgba(220,20,60,0.3);">';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Пользователь ID</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Модerator</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Причина</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Дата</th>';
 html += '<th style="pимяding:12px;text-align:left;color:#dc143c;">Сервер</th>';
 html += '</tr>' + rows + '</table></div>';
 html += '<p style="margin-top:15px;color:#666;font-size:13px;">Всего ' + варнs.length + ' предупреждение</p>';
 document.getElementById('варнings-list').innerHTML = html;
}
function filterПредупреждениеs() {
 var q = document.getElementById('варн-filter').value.toLowerCase();
 displayПредупреждениеs(allПредупреждениеs.filter(function(w) {
 return String(w.user_id||'').includes(q) || (w.модerator||'').toLowerCase().includes(q) ||
 (w.reason||'').toLowerCase().includes(q);
 }));
}
loимяПредупреждениеs();
setInterval(loимяПредупреждениеs, 15000);
</script>
{% endblock %}
"""
with open(os.path.join(templates_dir, 'варнings.html'), 'w', encoding='utf-8') as f:
    f.write(варнings_html)
print("варнings.html duzeltildi")
print("Завершено!")
