import os

templates_dir = os.path.join(os.path.dirname(__file__), 'web', 'templates')
os.maкотrs(templates_dir, exist_ok=True)

# ============================================================
# commands.html
# ============================================================
commands_html = '''{% extends "base.html" %}
{% block title %}Команды - Aether{% endblock %}
{% block page_title %}КОМАНДА MERKEZИ{% endblock %}
{% block content %}
<style>
.cmd-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:20px; margin-top:20px; }
.cmd-card { background:linear-grимяient(135deg,#1a0a0a,#2a1010); border:1px solid rgba(220,20,60,0.4); border-rимяius:15px; pимяding:25px; cursor:pointer; transition:all 0.3s; position:relative; overflow:hidden; }
.cmd-card:hover { transform:translateY(-8px); border-color:#dc143c; box-shимяow:0 15px 40px rgba(220,20,60,0.4); }
.cmd-card::before { content:''; position:absolute; top:-50%; left:-50%; width:200%; height:200%; background:linear-grимяient(45deg,transparent,rgba(220,20,60,0.05),transparent); transform:rotate(45deg); transition:0.5s; }
.cmd-card:hover::before { left:100%; }
.cmd-card h3 { color:#dc143c; margin-bottom:8px; font-size:18px; }
.cmd-card p { color:#aaa; font-size:13px; }
.cmd-icon { font-size:36px; margin-bottom:15px; }
.модal-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:9999; justify-content:center; align-items:center; }
.модal-box { background:linear-grимяient(135deg,#1a1a1a,#2a2a2a); border:2px solid #dc143c; border-rимяius:20px; pимяding:35px; max-width:500px; width:90%; position:relative; box-shимяow:0 20px 60px rgba(220,20,60,0.5); }
.модal-box h2 { color:#dc143c; margin-bottom:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:#ccc; margin-bottom:6px; font-size:13px; text-transform:uppercase; letter-spacing:1px; }
.form-group input, .form-group select, .form-group textarea { width:100%; pимяding:10px 14px; background:#0a0a0a; border:2px solid rgba(220,20,60,0.3); border-rимяius:8px; color:#eee; font-size:14px; transition:border-color 0.3s; box-sizing:border-box; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:#dc143c; }
.btn-exec { background:linear-grимяient(135deg,#dc143c,#ff1744); color:white; pимяding:12px 28px; border:none; border-rимяius:8px; cursor:pointer; font-size:15px; font-weight:700; margin-right:10px; transition:all 0.3s; }
.btn-exec:hover { box-shимяow:0 5px 20px rgba(220,20,60,0.5); transform:translateY(-2px); }
.btn-cancel { background:#333; color:#ccc; pимяding:12px 28px; border:none; border-rимяius:8px; cursor:pointer; font-size:15px; }
#result-msg { margin-top:15px; pимяding:12px; border-rимяius:8px; display:none; }
</style>

<div class="cmd-grid">
 <div class="cmd-card" onclick="openCmd(\'бан\')">
 <div class="cmd-icon">🔨</div>
 <h3><i class="fas fa-бан"></i> Бан</h3>
 <p>Пользователя с сервера постоянный как забанить</p>
 </div>
 <div class="cmd-card" onclick="openCmd(\'кик\')">
 <div class="cmd-icon">👢</div>
 <h3><i class="fas fa-user-slash"></i> Кик</h3>
 <p>Исключить (кикнуть) пользователя с сервера</p>
 </div>
 <div class="cmd-card" onclick="openCmd(\'timeout\')">
 <div class="cmd-icon">⏱️</div>
 <h3><i class="fas fa-clock"></i> Мут</h3>
 <p>Пользователя geчici как sustur</p>
 </div>
 <div class="cmd-card" onclick="openCmd(\'варн\')">
 <div class="cmd-icon">⚠️</div>
 <h3><i class="fas fa-exclamation-triangle"></i> Предупреждение</h3>
 <p>Выдать предупреждение пользователю</p>
 </div>
 <div class="cmd-card" onclick="openCmd(\'clear\')">
 <div class="cmd-icon">🗑️</div>
 <h3><i class="fas fa-trash"></i> Сообщение Очистить</h3>
 <p>Канал toplu message удалить</p>
 </div>
 <div class="cmd-card" onclick="openCmd(\'роли\')">
 <div class="cmd-icon">🏷️</div>
 <h3><i class="fas fa-user-tag"></i> Роли Ver/Al</h3>
 <p>Пользователю роли имяd или удалить</p>
 </div>
</div>

<div id="cmdМодal" class="модal-overlay">
 <div class="модal-box">
 <button onclick="closeCmd()" style="position:absolute;top:15px;right:20px;background:none;border:none;color:#dc143c;font-size:26px;cursor:pointer;">&times;</button>
 <h2 id="cmdTitle">Команда</h2>
 <div id="cmdForm"></div>
 <div id="result-msg"></div>
 </div>
</div>

<script>
var guilds = [];
var currentCmd = '';

async function loимяGuilds() {
 var r = await fetch('/api/guilds');
 guilds = await r.json();
}

function guildOptions() {
 return guilds.map(function(g) { return '<option value="'+g.id+'">'+g.name+'</option>'; }).join('');
}

async function loимяChannels(selId) {
 var gid = document.getElementById('guild-sel').value;
 if (!gid) return;
 var r = await fetch('/api/guild/'+gid+'/channels');
 var chs = await r.json();
 if (!Array.isArray(chs)) chs = chs.channels || [];
 var sel = document.getElementById(selId);
 sel.innerHTML = chs.filter(function(c){return c.type==='text';}).map(function(c){return '<option value="'+c.id+'">#'+c.name+'</option>';}).join('');
}

async function loимяРольes(selId) {
 var gid = document.getElementById('guild-sel').value;
 if (!gid) return;
 var r = await fetch('/api/guild/'+gid+'/роли');
 var рольe = await r.json();
 if (!Array.isArray(рольes)) рольe = [];
 var sel = document.getElementById(selId);
 sel.innerHTML = рольes.map(function(ro){return '<option value="'+ro.id+'">'+ro.name+'</option>';}).join('');
}

function openCmd(cmd) {
 currentCmd = cmd;
 document.getElementById('cmdTitle').textContent = cmd.toUpperCase();
 document.getElementById('result-msg').style.display = 'none';
 var forms = {
 бан: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Бан причина"></div><button class="btn-exec" onclick="execCmd()">BAN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 кик: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Кик причина"></div><button class="btn-exec" onclick="execCmd()">KICK</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 timeout: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Sure (dakika)</label><input type="number" id="duration" value="60"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Мут причина"></div><button class="btn-exec" onclick="execCmd()">TIMEOUT</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 варн: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Предупреждение причина"></div><button class="btn-exec" onclick="execCmd()">WARN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 clear: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe" onchange="loимяChannels(\'channel-sel\')">'+guildOptions()+'</select></div><div class="form-group"><label>Канал</label><select id="channel-sel" class="form-contрольe"><option>Once сервер secin</option></select></div><div class="form-group"><label>Сообщение Количество</label><input type="number" id="amount" value="10"></div><button class="btn-exec" onclick="execCmd()">TEMИZLE</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 роли: '<div class="form-group"><label>Сервер</label><select id="guild-sel" class="form-contрольe" onchange="loимяРольes(\'роли-sel\')">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Роль</label><select id="роли-sel" class="form-contрольe"><option>Once сервер secin</option></select></div><button class="btn-exec" onclick="execCmd()">ПРИМЕН</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>'
 };
 document.getElementById('cmdForm').innerHTML = forms[cmd];
 document.getElementById('cmdМодal').style.display = 'flex';
 if (cmd === 'clear') loимяChannels('channel-sel');
 if (cmd === 'рольe') loимяРольes('рольe-sel');
}

function closeCmd() { document.getElementById('cmdМодal').style.display = 'none'; }

async function execCmd() {
 var data = { command: currentCmd, guild_id: document.getElementById('guild-sel').value };
 var uid = document.getElementById('user_id'); if (uid) data.user_id = uid.value;
 var rsn = document.getElementById('reason'); if (rsn) data.reason = rsn.value;
 var dur = document.getElementById('duration'); if (dur) data.duration = dur.value;
 var amt = document.getElementById('amount'); if (amt) data.amount = amt.value;
 var chs = document.getElementById('channel-sel'); if (chs) data.channel_id = chs.value;
 var rls = document.getElementById('роли-sel'); if (rls) data.рольe_id = rls.value;

 var r = await fetch('/api/execute-command', { method:'POST', heимяers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
 var res = await r.json();
 var msg = document.getElementById('result-msg');
 msg.style.display = 'block';
 if (res.success) {
 msg.style.background = 'rgba(46,204,113,0.2)'; msg.style.border = '1px solid #2ecc71'; msg.style.color = '#2ecc71';
 msg.textContent = '✅ Команда успешно calistirildi!';
 setTimeout(closeCmd, 2000);
 } else {
 msg.style.background = 'rgba(220,20,60,0.2)'; msg.style.border = '1px solid #dc143c'; msg.style.color = '#ff6b6b';
 msg.textContent = '❌ Ошибка: ' + res.error;
 }
}

document.getElementById('cmdМодal').имяdEventListener('click', function(e) { if (e.target === this) closeCmd(); });
loимяGuilds();
</script>
{% endblock %}
'''
with open(os.path.join(templates_dir, 'commands.html'), 'w', encoding='utf-8') as f:
    f.write(commands_html)
print("commands.html написано")

# ============================================================
# execute_command.html - base.html extend eden версий
# ============================================================
execute_html = '''{% extends "base.html" %}
{% block title %}Команда Calistir - Aether{% endblock %}
{% block page_title %}КОМАНДА ЧALIШTIR{% endblock %}
{% block content %}
<style>
.cmd-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:20px; margin-top:20px; }
.cmd-card { background:linear-grимяient(135deg,#1a0a0a,#2a1010); border:1px solid rgba(220,20,60,0.4); border-rимяius:15px; pимяding:25px; cursor:pointer; transition:all 0.3s; position:relative; overflow:hidden; }
.cmd-card:hover { transform:translateY(-8px); border-color:#dc143c; box-shимяow:0 15px 40px rgba(220,20,60,0.4); }
.cmd-icon { font-size:36px; margin-bottom:15px; }
.cmd-card h3 { color:#dc143c; margin-bottom:8px; font-size:18px; }
.cmd-card p { color:#aaa; font-size:13px; }
.модal-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:9999; justify-content:center; align-items:center; }
.модal-box { background:linear-grимяient(135deg,#1a1a1a,#2a2a2a); border:2px solid #dc143c; border-rимяius:20px; pимяding:35px; max-width:500px; width:90%; position:relative; box-shимяow:0 20px 60px rgba(220,20,60,0.5); }
.модal-box h2 { color:#dc143c; margin-bottom:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:#ccc; margin-bottom:6px; font-size:13px; text-transform:uppercase; letter-spacing:1px; }
.form-group input, .form-group select { width:100%; pимяding:10px 14px; background:#0a0a0a; border:2px solid rgba(220,20,60,0.3); border-rимяius:8px; color:#eee; font-size:14px; box-sizing:border-box; transition:border-color 0.3s; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:#dc143c; }
.btn-exec { background:linear-grимяient(135deg,#dc143c,#ff1744); color:white; pимяding:12px 28px; border:none; border-rимяius:8px; cursor:pointer; font-size:15px; font-weight:700; margin-right:10px; transition:all 0.3s; }
.btn-exec:hover { box-shимяow:0 5px 20px rgba(220,20,60,0.5); transform:translateY(-2px); }
.btn-cancel { background:#333; color:#ccc; pимяding:12px 28px; border:none; border-rимяius:8px; cursor:pointer; font-size:15px; }
#exec-result { margin-top:15px; pимяding:12px; border-rимяius:8px; display:none; }
</style>

<div class="cmd-grid">
 <div class="cmd-card" onclick="openCmd(\'бан\')"><div class="cmd-icon">🔨</div><h3><i class="fas fa-бан"></i> Бан</h3><p>Пользователя постоянный забанить</p></div>
 <div class="cmd-card" onclick="openCmd(\'кик\')"><div class="cmd-icon">👢</div><h3><i class="fas fa-user-slash"></i> Кик</h3><p>Пользователя с сервера at</p></div>
 <div class="cmd-card" onclick="openCmd(\'timeout\')"><div class="cmd-icon">⏱️</div><h3><i class="fas fa-clock"></i> Мут</h3><p>Gecici sustur</p></div>
 <div class="cmd-card" onclick="openCmd(\'варн\')"><div class="cmd-icon">⚠️</div><h3><i class="fas fa-exclamation-triangle"></i> Предупреждение</h3><p>Предупреждение ver</p></div>
 <div class="cmd-card" onclick="openCmd(\'clear\')"><div class="cmd-icon">🗑️</div><h3><i class="fas fa-trash"></i> Очистить</h3><p>Массовая message удалить</p></div>
 <div class="cmd-card" onclick="openCmd(\'роли\')"><div class="cmd-icon">🏷️</div><h3><i class="fas fa-user-tag"></i> Роли Ver/Al</h3><p>Роли имяd или cыkar</p></div>
</div>

<div id="execМодal" class="модal-overlay">
 <div class="модal-box">
 <button onclick="closeCmd()" style="position:absolute;top:15px;right:20px;background:none;border:none;color:#dc143c;font-size:26px;cursor:pointer;">&times;</button>
 <h2 id="execTitle">Команда</h2>
 <div id="execForm"></div>
 <div id="exec-result"></div>
 </div>
</div>

<script>
var guilds = [];
var currentCmd = '';

async function loимяGuilds() {
 var r = await fetch('/api/guilds');
 guilds = await r.json();
}

function guildOptions() {
 return guilds.map(function(g){return '<option value="'+g.id+'">'+g.name+'</option>';}).join('');
}

async function loимяChannels(selId) {
 var gid = document.getElementById('guild-sel').value;
 if (!gid) return;
 var r = await fetch('/api/guild/'+gid+'/channels');
 var data = await r.json();
 var chs = Array.isArray(data) ? data : (data.channels || []);
 var sel = document.getElementById(selId);
 sel.innerHTML = chs.filter(function(c){return c.type==='text';}).map(function(c){return '<option value="'+c.id+'">#'+c.name+'</option>';}).join('');
}

async function loимяРольes(selId) {
 var gid = document.getElementById('guild-sel').value;
 if (!gid) return;
 var r = await fetch('/api/guild/'+gid+'/роли');
 var рольe = await r.json();
 if (!Array.isArray(рольes)) рольe = [];
 var sel = document.getElementById(selId);
 sel.innerHTML = рольes.map(function(ro){return '<option value="'+ro.id+'">'+ro.name+'</option>';}).join('');
}

function openCmd(cmd) {
 currentCmd = cmd;
 document.getElementById('execTitle').textContent = cmd.toUpperCase();
 document.getElementById('exec-result').style.display = 'none';
 var forms = {
 бан: '<div class="form-group"><label>Сервер</label><select id="guild-sel">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Бан причина"></div><button class="btn-exec" onclick="execCmd()">BAN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 кик: '<div class="form-group"><label>Сервер</label><select id="guild-sel">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Кик причина"></div><button class="btn-exec" onclick="execCmd()">KICK</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 timeout: '<div class="form-group"><label>Сервер</label><select id="guild-sel">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Sure (dakika)</label><input type="number" id="duration" value="60"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Мут причина"></div><button class="btn-exec" onclick="execCmd()">TIMEOUT</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 варн: '<div class="form-group"><label>Сервер</label><select id="guild-sel">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Предупреждение причина"></div><button class="btn-exec" onclick="execCmd()">WARN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 clear: '<div class="form-group"><label>Сервер</label><select id="guild-sel" onchange="loимяChannels(\'channel-sel\')">'+guildOptions()+'</select></div><div class="form-group"><label>Канал</label><select id="channel-sel"><option>Once сервер secin</option></select></div><div class="form-group"><label>Сообщение Количество</label><input type="number" id="amount" value="10"></div><button class="btn-exec" onclick="execCmd()">TEMИZLE</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>',
 роли: '<div class="form-group"><label>Сервер</label><select id="guild-sel" onchange="loимяРольes(\'роли-sel\')">'+guildOptions()+'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Роль</label><select id="роли-sel"><option>Once сервер secin</option></select></div><button class="btn-exec" onclick="execCmd()">ПРИМЕН</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>'
 };
 document.getElementById('execForm').innerHTML = forms[cmd];
 document.getElementById('execМодal').style.display = 'flex';
 if (cmd === 'clear') loимяChannels('channel-sel');
 if (cmd === 'рольe') loимяРольes('рольe-sel');
}

function closeCmd() { document.getElementById('execМодal').style.display = 'none'; }

async function execCmd() {
 var data = { command: currentCmd, guild_id: document.getElementById('guild-sel').value };
 var uid = document.getElementById('user_id'); if (uid) data.user_id = uid.value;
 var rsn = document.getElementById('reason'); if (rsn) data.reason = rsn.value;
 var dur = document.getElementById('duration'); if (dur) data.duration = dur.value;
 var amt = document.getElementById('amount'); if (amt) data.amount = amt.value;
 var chs = document.getElementById('channel-sel'); if (chs) data.channel_id = chs.value;
 var rls = document.getElementById('роли-sel'); if (rls) data.рольe_id = rls.value;

 var r = await fetch('/api/execute-command', { method:'POST', heимяers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
 var res = await r.json();
 var msg = document.getElementById('exec-result');
 msg.style.display = 'block';
 if (res.success) {
 msg.style.cssText = 'display:block;background:rgba(46,204,113,0.2);border:1px solid #2ecc71;color:#2ecc71;pимяding:12px;border-rимяius:8px;margin-top:15px;';
 msg.textContent = '✅ Команда успешно calistirildi!';
 setTimeout(closeCmd, 2000);
 } else {
 msg.style.cssText = 'display:block;background:rgba(220,20,60,0.2);border:1px solid #dc143c;color:#ff6b6b;pимяding:12px;border-rимяius:8px;margin-top:15px;';
 msg.textContent = '❌ Ошибка: ' + res.error;
 }
}

document.getElementById('execМодal').имяdEventListener('click', function(e) { if (e.target === this) closeCmd(); });
loимяGuilds();
</script>
{% endblock %}
'''
with open(os.path.join(templates_dir, 'execute_command.html'), 'w', encoding='utf-8') as f:
    f.write(execute_html)
print("execute_command.html написано")

# ============================================================
# логs.html
# ============================================================
логs_html = '''{% extends "base.html" %}
{% block title %}Логи модерации - Aether{% endblock %}
{% block page_title %}MOD LOGLARI{% endblock %}
{% block content %}
<div class="section">
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px;">
 <h2><i class="fas fa-clipboard-list" style="color:#dc143c;"></i> Tum Мод Islemleri</h2>
 <input type="text" id="лог-filter" placeholder="Filtrele (пользователь ID, причина, islem...)" style="pимяding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-rимяius:8px;color:#eee;width:300px;" oninput="filterЛогs()">
 </div>
 <div id="логs-list" style="color:#aaa;text-align:center;pимяding:40px;"><i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...</div>
</div>
<script>
var allЛогs = [];
async function loимяЛогs() {
 var r = await fetch('/api/логs');
 allЛогs = await r.json();
 displayЛогs(allЛогs);
}
function displayЛогs(логs) {
 if (!логs.length) {
 document.getElementById('логs-list').innerHTML = '<p style="color:#aaa;text-align:center;pимяding:40px;">Hic лог не найдено</p>';
 return;
 }
 var colors = { бан:'#e74c3c', кик:'#e67e22', timeout:'#f39c12', варн:'#f1c40f', мут:'#9b59b6' };
 var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
 html += '<tr style="border-bottom:2px solid rgba(220,20,60,0.3);"><th style="pимяding:12px;text-align:left;color:#dc143c;">Case</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Islem</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Пользователь</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Модerator</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Причина</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Дата</th></tr>';
 логs.slice(0,100).forEach(function(лог, i) {
 var bg = i%2===0 ? 'rgba(220,20,60,0.03)' : 'transparent';
 var ac = colors[лог.action] || '#667eea';
 html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:'+bg+';transition:background 0.2s;" onmouseover="this.style.background=\'rgba(220,20,60,0.08)\'" onmouseout="this.style.background=\''+bg+'\'">';
 html += '<td style="pимяding:12px;color:#ffd700;font-weight:700;">#'+лог.case_id+'</td>';
 html += '<td style="pимяding:12px;"><span style="background:'+ac+';pимяding:4px 10px;border-rимяius:4px;font-size:11px;font-weight:700;color:white;">'+лог.action.toUpperCase()+'</span></td>';
 html += '<td style="pимяding:12px;"><code style="color:#dc143c;font-size:12px;">'+лог.user_id+'</code></td>';
 html += '<td style="pимяding:12px;"><code style="color:#aaa;font-size:12px;">'+лог.мод_id+'</code></td>';
 html += '<td style="pимяding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+лог.reason+'</td>';
 html += '<td style="pимяding:12px;color:#888;font-size:12px;">'+new Date(лог.timestamp).toLocaleString("tr-TR")+'</td>';
 html += '</tr>';
 });
 html += '</table></div><p style="margin-top:15px;color:#666;font-size:13px;">Всего '+логs.length+' islem</p>';
 document.getElementById('логs-list').innerHTML = html;
}
function filterЛогs() {
 var q = document.getElementById('лог-filter').value.toLowerCase();
 displayЛогs(allЛогs.filter(function(l) {
 return String(l.user_id).includes(q) || String(l.мод_id).includes(q) || (l.reason||'').toLowerCase().includes(q) || (l.action||'').toLowerCase().includes(q);
 }));
}
loимяЛогs();
setInterval(loимяЛогs, 15000);
</script>
{% endblock %}
'''
with open(os.path.join(templates_dir, 'логs.html'), 'w', encoding='utf-8') as f:
    f.write(логs_html)
print("логs.html написано")

# ============================================================
# варнings.html
# ============================================================
варнings_html = '''{% extends "base.html" %}
{% block title %}Предупреждения - Aether{% endblock %}
{% block page_title %}ПРЕДУПРЕЖДЕНИЕ СИСТЕМА{% endblock %}
{% block content %}
<div class="section">
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px;">
 <h2><i class="fas fa-exclamation-triangle" style="color:#dc143c;"></i> Tum Предупреждения</h2>
 <input type="text" id="варн-filter" placeholder="Filtrele (пользователь ID, модerator, причина...)" style="pимяding:10px 15px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-rимяius:8px;color:#eee;width:300px;" oninput="filterПредупреждениеs()">
 </div>
 <div id="варнings-list" style="color:#aaa;text-align:center;pимяding:40px;"><i class="fas fa-spinner fa-spin" style="font-size:30px;color:#dc143c;"></i><br><br>Yukleniyor...</div>
</div>
<script>
var allПредупреждениеs = [];
async function loимяПредупреждениеs() {
 var r = await fetch('/api/варнings');
 allПредупреждениеs = await r.json();
 displayПредупреждениеs(allПредупреждениеs);
}
function displayПредупреждениеs(варнs) {
 if (!варнs.length) {
 document.getElementById('варнings-list').innerHTML = '<p style="color:#aaa;text-align:center;pимяding:40px;">Hic предупреждение не найдено</p>';
 return;
 }
 var html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">';
 html += '<tr style="border-bottom:2px solid rgba(220,20,60,0.3);"><th style="pимяding:12px;text-align:left;color:#dc143c;">Пользователь ID</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Модerator</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Причина</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Дата</th><th style="pимяding:12px;text-align:left;color:#dc143c;">Сервер</th></tr>';
 варнs.slice(0,100).forEach(function(w, i) {
 var bg = i%2===0 ? 'rgba(220,20,60,0.03)' : 'transparent';
 html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.05);background:'+bg+';transition:background 0.2s;" onmouseover="this.style.background=\'rgba(220,20,60,0.08)\'" onmouseout="this.style.background=\''+bg+'\'">';
 html += '<td style="pимяding:12px;"><code style="color:#dc143c;font-size:12px;">'+w.user_id+'</code></td>';
 html += '<td style="pимяding:12px;color:#ffd700;">'+w.модerator+'</td>';
 html += '<td style="pимяding:12px;color:#ccc;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+w.reason+'</td>';
 html += '<td style="pимяding:12px;color:#888;font-size:12px;">'+new Date(w.timestamp).toLocaleString("tr-TR")+'</td>';
 html += '<td style="pимяding:12px;"><code style="color:#aaa;font-size:11px;">'+w.guild_id+'</code></td>';
 html += '</tr>';
 });
 html += '</table></div><p style="margin-top:15px;color:#666;font-size:13px;">Всего '+варнs.length+' предупреждение</p>';
 document.getElementById('варнings-list').innerHTML = html;
}
function filterПредупреждениеs() {
 var q = document.getElementById('варн-filter').value.toLowerCase();
 displayПредупреждениеs(allПредупреждениеs.filter(function(w) {
 return String(w.user_id).includes(q) || (w.модerator||'').toLowerCase().includes(q) || (w.reason||'').toLowerCase().includes(q);
 }));
}
loимяПредупреждениеs();
setInterval(loимяПредупреждениеs, 15000);
</script>
{% endblock %}
'''
with open(os.path.join(templates_dir, 'варнings.html'), 'w', encoding='utf-8') as f:
    f.write(варнings_html)
print("варнings.html написано")

# ============================================================
# settings.html
# ============================================================
settings_html = '''{% extends "base.html" %}
{% block title %}Настройки - Aether{% endblock %}
{% block page_title %}PANEL НАСТРОЙК{% endblock %}
{% block content %}
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:20px;">
 <div class="section">
 <h2><i class="fas fa-shield-alt" style="color:#dc143c;"></i> Роли Администратор</h2>
 <table style="width:100%;border-collapse:collapse;">
 <tr style="border-bottom:2px solid rgba(220,20,60,0.3);"><th style="pимяding:10px;text-align:left;color:#dc143c;">Роль</th><th style="pимяding:10px;text-align:left;color:#dc143c;">Уровень</th><th style="pимяding:10px;text-align:left;color:#dc143c;">Администратор</th></tr>
 <tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td style="pимяding:10px;color:#ffd700;font-weight:700;">Owner</td><td style="pимяding:10px;color:#dc143c;">3</td><td style="pимяding:10px;color:#ccc;">Tum администратор</td></tr>
 <tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td style="pимяding:10px;color:#e67e22;font-weight:700;">Иsminin</td><td style="pимяding:10px;color:#dc143c;">2</td><td style="pимяding:10px;color:#ccc;">Команды, пользователи, логlar</td></tr>
 <tr><td style="pимяding:10px;color:#3498db;font-weight:700;">Мод</td><td style="pимяding:10px;color:#dc143c;">1</td><td style="pимяding:10px;color:#ccc;">Сервера, логlar, предупреждения</td></tr>
 </table>
 </div>
 <div class="section">
 <h2><i class="fas fa-users-cog" style="color:#dc143c;"></i> Panel Пользователь</h2>
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);border-rимяius:10px;pимяding:15px;margin-bottom:10px;">
 <div style="display:flex;justify-content:space-between;align-items:center;">
 <span style="color:#ffd700;font-weight:700;">owner</span>
 <span style="background:#dc143c;pимяding:3px 10px;border-rимяius:10px;font-size:12px;color:white;">OWNER</span>
 </div>
 <div style="color:#888;font-size:12px;margin-top:5px;">Sifre: owner123</div>
 </div>
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);border-rимяius:10px;pимяding:15px;margin-bottom:10px;">
 <div style="display:flex;justify-content:space-between;align-items:center;">
 <span style="color:#e67e22;font-weight:700;">админ</span>
 <span style="background:#e67e22;pимяding:3px 10px;border-rимяius:10px;font-size:12px;color:white;">ADMIN</span>
 </div>
 <div style="color:#888;font-size:12px;margin-top:5px;">Sifre: админ123</div>
 </div>
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.3);border-rимяius:10px;pимяding:15px;">
 <div style="display:flex;justify-content:space-between;align-items:center;">
 <span style="color:#3498db;font-weight:700;">мод</span>
 <span style="background:#3498db;pимяding:3px 10px;border-rимяius:10px;font-size:12px;color:white;">MOD</span>
 </div>
 <div style="color:#888;font-size:12px;margin-top:5px;">Sifre: мод123</div>
 </div>
 <div style="margin-top:15px;pимяding:12px;background:rgba(243,156,18,0.1);border:1px solid rgba(243,156,18,0.3);border-rимяius:8px;color:#f39c12;font-size:13px;">
 <i class="fas fa-exclamation-triangle"></i> Production ortaminda bu информация degistirin!
 </div>
 </div>
 <div class="section">
 <h2><i class="fas fa-robot" style="color:#dc143c;"></i> Bot Статистика</h2>
 <div id="bot-stats" style="color:#aaa;text-align:center;pимяding:20px;"><i class="fas fa-spinner fa-spin" style="color:#dc143c;"></i> Yukleniyor...</div>
 </div>
 <div class="section">
 <h2><i class="fas fa-info-circle" style="color:#dc143c;"></i> Система Информация</h2>
 <div style="display:grid;gap:10px;">
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;">
 <span style="color:#888;">Panel Versiyonu</span><span style="color:#ffd700;font-weight:700;">v2.0 Aether</span>
 </div>
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;">
 <span style="color:#888;">Framework</span><span style="color:#ccc;">Flask + Discord.py</span>
 </div>
 <div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;">
 <span style="color:#888;">Port</span><span style="color:#ccc;">5001</span>
 </div>
 </div>
 </div>
</div>
<script>
async function loимяStats() {
 var r = await fetch('/api/stats');
 var d = await r.json();
 if (d.error) { document.getElementById('bot-stats').innerHTML = '<p style="color:#e74c3c;">'+d.error+'</p>'; return; }
 document.getElementById('bot-stats').innerHTML =
 '<div style="display:grid;gap:10px;">' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;"><span style="color:#888;">Сервер Количество</span><span style="color:#ffd700;font-weight:700;">'+d.guilds+'</span></div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;"><span style="color:#888;">Пользователь Количество</span><span style="color:#ffd700;font-weight:700;">'+d.users+'</span></div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;"><span style="color:#888;">Ping</span><span style="color:#2ecc71;font-weight:700;">'+d.latency+'ms</span></div>' +
 '<div style="background:rgba(220,20,60,0.1);border:1px solid rgba(220,20,60,0.2);border-rимяius:8px;pимяding:12px;display:flex;justify-content:space-between;"><span style="color:#888;">Состояние</span><span style="color:#2ecc71;font-weight:700;">● ONLINE</span></div>' +
 '</div>';
}
loимяStats();
</script>
{% endblock %}
'''
with open(os.path.join(templates_dir, 'settings.html'), 'w', encoding='utf-8') as f:
    f.write(settings_html)
print("settings.html написано")

print("\nTum template'ler успешно написано!")
