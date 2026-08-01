content = """{% extends "base.html" %}
{% block title %}Пользователи - Aether{% endblock %}
{% block page_title %}ПОЛЬЗОВАТЕЛИ{% endblock %}
{% block content %}
<div class="section">
<h2><i class="fas fa-сервер"></i> Сервер Sec</h2>
<select id="guild-select" onchange="loимяMembers()" style="width:100%;pимяding:12px;background:#0a0a0a;border:2px solid #dc143c;border-rимяius:8px;color:#eee;font-size:15px;margin-bottom:10px;"><option value="">Сервер secin...</option></select>
<input type="text" id="search" placeholder="Uye ara..." oninput="filterMembers()" style="display:none;">
</div>
<div class="section" id="members-section" style="display:none;">
<h2><i class="fas fa-users"></i> Uyeler - <span id="member-count">0</span> kisi</h2>
<div id="members-list"></div>
</div>
<div id="модal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:9999;justify-content:center;align-items:center;">
<div style="background:linear-grимяient(135deg,#1a1a1a,#2a2a2a);border:2px solid #dc143c;border-rимяius:20px;pимяding:40px;max-width:550px;width:90%;position:relative;box-shимяow:0 20px 60px rgba(220,20,60,0.5);max-height:90vh;overflow-y:auto;">
<button onclick="closeМодal()" style="position:absolute;top:15px;right:20px;background:none;border:none;color:#dc143c;font-size:28px;cursor:pointer;">&times;</button>
<div id="модal-content"></div>
</div>
</div>
<script>
var allMembers = [];

async function loимяGuilds() {
 var res = await fetch('/api/guilds');
 var guilds = await res.json();
 var sel = document.getElementById('guild-select');
 guilds.forEach(function(g) {
 var opt = document.createElement('option');
 opt.value = g.id;
 opt.textContent = g.name;
 sel.appendChild(opt);
 });
}

async function loимяMembers() {
 var guildId = document.getElementById('guild-select').value;
 if (!guildId) return;
 document.getElementById('members-section').style.display = 'block';
 document.getElementById('search').style.display = 'block';
 document.getElementById('members-list').innerHTML = '<p style="text-align:center;color:#aaa;pимяding:40px;"><i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...</p>';
 var res = await fetch('/api/guild/' + guildId + '/members');
 allMembers = await res.json();
 document.getElementById('member-count').textContent = allMembers.length;
 renderMembers(allMembers);
}

function renderMembers(members) {
 if (!members.length) {
 document.getElementById('members-list').innerHTML = '<p style="color:#aaa;text-align:center;pимяding:40px;">Uye не найдено</p>';
 return;
 }
 var container = document.createElement('div');
 container.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:15px;';
 members.forEach(function(m, i) {
 var sc = m.status === 'online' ? '#2ecc71' : m.status === 'idle' ? '#f39c12' : m.status === 'dnd' ? '#e74c3c' : '#555';
 var card = document.createElement('div');
 card.style.cssText = 'background:linear-grимяient(135deg,#1a1a1a,#2a2a2a);border:1px solid rgba(220,20,60,0.3);border-rимяius:12px;pимяding:20px;cursor:pointer;text-align:center;transition:all 0.3s;';
 card.onmouseover = function() { this.style.borderColor = '#dc143c'; this.style.transform = 'translateY(-5px)'; };
 card.onmouseout = function() { this.style.borderColor = 'rgba(220,20,60,0.3)'; this.style.transform = 'none'; };
 card.onclick = function() { showDetail(i); };
 card.innerHTML = '<div style="position:relative;display:inline-block;margin-bottom:12px;">' +
 '<img src="' + m.avatar + '" style="width:60px;height:60px;border-rимяius:50%;border:3px solid #dc143c;">' +
 '<div style="position:absolute;bottom:2px;right:2px;width:14px;height:14px;background:' + sc + ';border-rимяius:50%;border:2px solid #1a1a1a;"></div>' +
 '</div>' +
 '<div style="font-weight:700;color:white;font-size:14px;margin-bottom:4px;">' + m.display_name + '</div>' +
 '<div style="color:#888;font-size:12px;">' + m.name + '</div>' +
 (m.bot ? '<span style="background:#dc143c;pимяding:2px 8px;border-rимяius:10px;font-size:10px;margin-top:6px;display:inline-block;">BOT</span>' : '');
 container.appendChild(card);
 });
 document.getElementById('members-list').innerHTML = '';
 document.getElementById('members-list').appendChild(container);
}

function showDetail(i) {
 var m = allMembers[i];
 var cr = new Date(m.created_at);
 var jo = m.joined_at ? new Date(m.joined_at) : null;
 var sc = m.status === 'online' ? '#2ecc71' : m.status === 'idle' ? '#f39c12' : m.status === 'dnd' ? '#e74c3c' : '#555';
 var st = m.status === 'online' ? 'Cevrimici' : m.status === 'idle' ? 'Bosta' : m.status === 'dnd' ? 'Rahatsiz Etme' : 'Cevrimdisi';
 var рольe = m.рольes.map(function(r) {
 return '<span style="background:rgba(220,20,60,0.2);border:1px solid rgba(220,20,60,0.4);pимяding:3px 10px;border-rимяius:10px;font-size:12px;margin:3px;display:inline-block;">' + r.name + '</span>';
 }).join('');
 var mc = document.getElementById('модal-content');
 mc.innerHTML = '';
 var h = document.createElement('div');
 h.innerHTML =
 '<div style="text-align:center;margin-bottom:20px;">' +
 '<img src="' + m.avatar + '" style="width:100px;height:100px;border-rимяius:50%;border:4px solid #dc143c;box-shимяow:0 0 20px rgba(220,20,60,0.5);margin-bottom:15px;">' +
 '<h2 style="color:white;margin-bottom:5px;">' + m.display_name + '</h2>' +
 (m.nick ? '<p style="color:#888;font-size:13px;">Nick: ' + m.nick + '</p>' : '') +
 '<p style="color:#888;margin-bottom:10px;">' + m.name + '</p>' +
 '<span style="background:' + sc + ';pимяding:4px 12px;border-rимяius:10px;font-size:12px;color:white;">' + st + '</span>' +
 (m.bot ? '<span style="background:#dc143c;pимяding:4px 12px;border-rимяius:10px;font-size:12px;color:white;margin-left:8px;">BOT</span>' : '') +
 '</div>' +
 '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0;">' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);pимяding:12px;border-rимяius:10px;text-align:center;"><i class="fas fa-id-card" style="color:#dc143c;"></i><br><small style="color:#888;">ID</small><br><code style="color:#dc143c;font-size:11px;">' + m.id + '</code></div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);pимяding:12px;border-rимяius:10px;text-align:center;"><i class="fas fa-calendar-plus" style="color:#dc143c;"></i><br><small style="color:#888;">Hesap Acildi</small><br><span style="color:white;font-size:13px;">' + cr.toLocaleDateString('tr-TR') + '</span><br><small style="color:#888;">' + cr.toLocaleTimeString('tr-TR') + '</small></div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);pимяding:12px;border-rимяius:10px;text-align:center;"><i class="fas fa-sign-in-alt" style="color:#dc143c;"></i><br><small style="color:#888;">На сервер Giris</small><br><span style="color:white;font-size:13px;">' + (jo ? jo.toLocaleDateString('tr-TR') : 'Bilinmiyor') + '</span>' + (jo ? '<br><small style="color:#888;">' + jo.toLocaleTimeString('tr-TR') + '</small>' : '') + '</div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);pимяding:12px;border-rимяius:10px;text-align:center;"><i class="fas fa-crown" style="color:#dc143c;"></i><br><small style="color:#888;">En Yuksek Роль</small><br><span style="color:white;font-size:13px;">' + (m.top_рольe || 'Yok') + '</span></div>' +
 '</div>' +
 (m.рольes.length ? '<div><small style="color:#888;text-transform:uppercase;letter-spacing:1px;">Роли (' + m.рольes.length + ')</small><br><br>' + роли + '</div>' : '');
 mc.appendChild(h);
 document.getElementById('модal').style.display = 'flex';
}

function closeМодal() { document.getElementById('модal').style.display = 'none'; }

function filterMembers() {
 var q = document.getElementById('search').value.toLowerCase();
 renderMembers(allMembers.filter(function(m) {
 return m.name.toLowerCase().includes(q) || m.display_name.toLowerCase().includes(q) || m.id.includes(q);
 }));
}

document.getElementById('модal').имяdEventListener('click', function(e) { if (e.target === this) closeМодal(); });
loимяGuilds();
</script>
{% endblock %}
"""
with open('web/templates/users.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
