content = '''{% extends "base.html" %}
{% block title %}Команда Calistir - Aether{% endblock %}
{% block page_title %}КОМАНДА ÇALIŞTIR{% endblock %}
{% block content %}
<style>
.cmd-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:20px; margin-top:20px; }
.cmd-card { background:linear-gradient(135deg,#1a0a0a,#2a1010); border:1px solid rgba(220,20,60,0.4); border-radius:15px; padding:25px; cursor:pointer; transition:all 0.3s; position:relative; overflow:hidden; }
.cmd-card:hover { transform:translateY(-8px); border-color:#dc143c; box-shadow:0 15px 40px rgba(220,20,60,0.4); }
.cmd-icon { font-size:36px; margin-bottom:15px; }
.cmd-card h3 { color:#dc143c; margin-bottom:8px; font-size:18px; }
.cmd-card p { color:#aaa; font-size:13px; }
.modal-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:9999; justify-content:center; align-items:center; }
.modal-box { background:linear-gradient(135deg,#1a1a1a,#2a2a2a); border:2px solid #dc143c; border-radius:20px; padding:35px; max-width:500px; width:90%; position:relative; box-shadow:0 20px 60px rgba(220,20,60,0.5); }
.modal-box h2 { color:#dc143c; margin-bottom:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:#ccc; margin-bottom:6px; font-size:13px; text-transform:uppercase; letter-spacing:1px; }
.form-group input, .form-group select { width:100%; padding:10px 14px; background:#0a0a0a; border:2px solid rgba(220,20,60,0.3); border-radius:8px; color:#eee; font-size:14px; box-sizing:border-box; transition:border-color 0.3s; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:#dc143c; }
.btn-exec { background:linear-gradient(135deg,#dc143c,#ff1744); color:white; padding:12px 28px; border:none; border-radius:8px; cursor:pointer; font-size:15px; font-weight:700; margin-right:10px; transition:all 0.3s; }
.btn-exec:hover { box-shadow:0 5px 20px rgba(220,20,60,0.5); transform:translateY(-2px); }
.btn-cancel { background:#333; color:#ccc; padding:12px 28px; border:none; border-radius:8px; cursor:pointer; font-size:15px; }
#exec-result { margin-top:15px; padding:12px; border-radius:8px; display:none; }
</style>

<div class="cmd-grid">
 <div class="cmd-card" onclick="openCmd(\'ban\')"><div class="cmd-icon">🔨</div><h3><i class="fas fa-ban"></i> Ban</h3><p>Пользователя постоянный забанить</p></div>
 <div class="cmd-card" onclick="openCmd(\'kick\')"><div class="cmd-icon">👢</div><h3><i class="fas fa-user-slash"></i> Kick</h3><p>Пользователя с сервера at</p></div>
 <div class="cmd-card" onclick="openCmd(\'timeout\')"><div class="cmd-icon">⏱️</div><h3><i class="fas fa-clock"></i> Mute</h3><p>Gecici sustur</p></div>
 <div class="cmd-card" onclick="openCmd(\'warn\')"><div class="cmd-icon">⚠️</div><h3><i class="fas fa-exclamation-triangle"></i> Warning</h3><p>Warning ver</p></div>
 <div class="cmd-card" onclick="openCmd(\'clear\')"><div class="cmd-icon">🗑️</div><h3><i class="fas fa-trash"></i> Temizle</h3><p>Массовая message удалить</p></div>
 <div class="cmd-card" onclick="openCmd(\'роли\')"><div class="cmd-icon">🏷️</div><h3><i class="fas fa-user-tag"></i> Роли Ver/Al</h3><p>Роли add или cıkar</p></div>
</div>

<div id="execModal" class="modal-overlay">
 <div class="modal-box">
 <button onclick="closeCmd()" style="position:absolute;top:15px;right:20px;background:none;border:none;color:#dc143c;font-size:26px;cursor:pointer;">&times;</button>
 <h2 id="execTitle">Команда</h2>
 <div id="execForm"></div>
 <div id="exec-result"></div>
 </div>
</div>

<script>
var guilds = [];
var currentCmd = \'\';

async function loadGuilds() {
 var r = await fetch(\'/api/guilds\');
 guilds = await r.json();
}

function guildOptions() {
 return guilds.map(function(g){return \'<option value="\'+g.id+\'">\'+g.name+\'</option>\';}).join(\'\');
}

async function loadChannels(selId) {
 var gid = document.getElementById(\'guild-sel\').value;
 if (!gid) return;
 var r = await fetch(\'/api/guild/\'+gid+\'/channels\');
 var data = await r.json();
 var chs = Array.isArray(data) ? data : (data.channels || []);
 var sel = document.getElementById(selId);
 sel.innerHTML = chs.filter(function(c){return c.type===\'text\';}).map(function(c){return \'<option value="\'+c.id+\'">#\'+c.name+\'</option>\';}).join(\'\');
}

async function loadMembers(selId) {
 var gid = document.getElementById(\'guild-sel\').value;
 if (!gid) return;
 var r = await fetch(\'/api/guild/\'+gid+\'/members\');
 var members = await r.json();
 if (!Array.isArray(members)) members = [];
 var sel = document.getElementById(selId);
 sel.innerHTML = members.filter(function(m){return !m.bot;}).map(function(m){
 return \'<option value="\'+m.id+\'">\'+m.display_name+\' (\'+m.name+\')</option>\';
 }).join(\'\');
}

async function loadRoles(selId) {
 var gid = document.getElementById(\'guild-sel\').value;
 if (!gid) return;
 var r = await fetch(\'/api/guild/\'+gid+\'/роли\');
 var role = await r.json();
 if (!Array.isArray(roles)) role = [];
 var sel = document.getElementById(selId);
 sel.innerHTML = roles.map(function(ro){return \'<option value="\'+ro.id+\'">\'+ro.name+\'</option>\';}).join(\'\');
}

async function loadRolesAndMembers() {
 await Promise.all([loadRoles(\'роли-sel\'), loadMembers(\'member-sel\')]);
}

function openCmd(cmd) {
 currentCmd = cmd;
 document.getElementById(\'execTitle\').textContent = cmd.toUpperCase();
 document.getElementById(\'exec-result\').style.display = \'none\';
 var forms = {
 ban: \'<div class="form-group"><label>Сервер</label><select id="guild-sel">\'+guildOptions()+\'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Ban причина"></div><button class="btn-exec" onclick="execCmd()">BAN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\',
 kick: \'<div class="form-group"><label>Сервер</label><select id="guild-sel">\'+guildOptions()+\'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Kick причина"></div><button class="btn-exec" onclick="execCmd()">KICK</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\',
 timeout: \'<div class="form-group"><label>Сервер</label><select id="guild-sel">\'+guildOptions()+\'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Sure (dakika)</label><input type="number" id="duration" value="60"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Mute причина"></div><button class="btn-exec" onclick="execCmd()">TIMEOUT</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\',
 warn: \'<div class="form-group"><label>Сервер</label><select id="guild-sel">\'+guildOptions()+\'</select></div><div class="form-group"><label>Пользователь ID</label><input type="text" id="user_id" placeholder="123456789"></div><div class="form-group"><label>Причина</label><input type="text" id="reason" placeholder="Предупреждение причина"></div><button class="btn-exec" onclick="execCmd()">WARN</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\',
 clear: \'<div class="form-group"><label>Сервер</label><select id="guild-sel" onchange="loadChannels(&quot;channel-sel&quot;)">\'+guildOptions()+\'</select></div><div class="form-group"><label>Канал</label><select id="channel-sel"><option>Yukleniyor...</option></select></div><div class="form-group"><label>Сообщение Количество</label><input type="number" id="amount" value="10"></div><button class="btn-exec" onclick="execCmd()">TEMİZLE</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\',
 роли: \'<div class="form-group"><label>Сервер</label><select id="guild-sel" onchange="loadRolesAndMembers()">\'+guildOptions()+\'</select></div><div class="form-group"><label>Участник</label><select id="member-sel"><option>Загрузка...</option></select></div><div class="form-group"><label>Роль</label><select id="роли-sel"><option>Загрузка...</option></select></div><button class="btn-exec" onclick="execCmd()">ПРИМЕН</button><button class="btn-cancel" onclick="closeCmd()">Отмена</button>\'
 };
 document.getElementById(\'execForm\').innerHTML = forms[cmd];
 document.getElementById(\'execModal\').style.display = \'flex\';
 setTimeout(function() {
 if (cmd === \'clear\') loadChannels(\'channel-sel\');
 if (cmd === \'роли\') loadRolesAndMembers();
 }, 50);
}

function closeCmd() { document.getElementById(\'execModal\').style.display = \'none\'; }

async function execCmd() {
 var data = { command: currentCmd, guild_id: document.getElementById(\'guild-sel\').value };
 var uid = document.getElementById(\'user_id\'); if (uid) data.user_id = uid.value;
 var msel = document.getElementById(\'member-sel\'); if (msel) data.user_id = msel.value;
 var rsn = document.getElementById(\'reason\'); if (rsn) data.reason = rsn.value;
 var dur = document.getElementById(\'duration\'); if (dur) data.duration = dur.value;
 var amt = document.getElementById(\'amount\'); if (amt) data.amount = amt.value;
 var chs = document.getElementById(\'channel-sel\'); if (chs) data.channel_id = chs.value;
 var rls = document.getElementById(\'роли-sel\'); if (rls) data.role_id = rls.value;

 var r = await fetch(\'/api/execute-command\', { method:\'POST\', headers:{\'Content-Type\':\'application/json\'}, body:JSON.stringify(data) });
 var res = await r.json();
 var msg = document.getElementById(\'exec-result\');
 msg.style.display = \'block\';
 if (res.success) {
 msg.style.cssText = \'display:block;background:rgba(46,204,113,0.2);border:1px solid #2ecc71;color:#2ecc71;padding:12px;border-radius:8px;margin-top:15px;\';
 msg.textContent = \'✅ Команда успешно calistirildi!\';
 setTimeout(closeCmd, 2000);
 } else {
 msg.style.cssText = \'display:block;background:rgba(220,20,60,0.2);border:1px solid #dc143c;color:#ff6b6b;padding:12px;border-radius:8px;margin-top:15px;\';
 msg.textContent = \'❌ Ошибка: \' + res.error;
 }
}

document.getElementById(\'execModal\').addEventListener(\'click\', function(e) { if (e.target === this) closeCmd(); });
loadGuilds();
</script>
{% endblock %}
'''
with open('discord_bot/web/templates/execute_command.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("execute_command.html написано")
