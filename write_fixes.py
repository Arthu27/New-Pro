#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Все sorunlarы dюzeltir"""
import os

# ─── 1. logs.html ────────────────────────────────────────────────────────────
logs_html = r"""{% extends "base.html" %}
{% block title %}Denetim Kaydi - Aether{% endblock %}
{% block page_title %}DENETИM KAYDI{% endblock %}
{% block content %}
<style>
.filter-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:15px;align-items:center;}
.filter-bar input,.filter-bar select{padding:9px 13px;background:#0a0a0a;border:2px solid rgba(220,20,60,0.3);border-radius:8px;color:#eee;font-size:13px;}
.filter-bar input:focus,.filter-bar select:focus{outline:none;border-color:#dc143c;}
.filter-bar input{flex:1;min-width:180px;}
.cat-btn{padding:7px 13px;border-radius:20px;border:2px solid rgba(220,20,60,0.3);background:transparent;color:#aaa;cursor:pointer;font-size:11px;font-weight:700;transition:all 0.2s;white-space:nowrap;}
.cat-btn.active,.cat-btn:hover{border-color:#dc143c;color:white;background:rgba(220,20,60,0.2);}
.ev-row{display:flex;align-items:center;gap:10px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:10px 14px;transition:all 0.2s;}
.ev-row:hover{background:rgba(220,20,60,0.07);border-color:rgba(220,20,60,0.2);}
.ev-icon{font-size:18px;width:28px;text-align:center;flex-shrink:0;}
.ev-cat{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:2px 7px;border-radius:8px;flex-shrink:0;min-width:72px;text-align:center;}
.ev-action{color:white;font-weight:600;font-size:13px;flex-shrink:0;min-width:140px;}
.ev-detail{color:#666;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ev-time{color:#444;font-size:11px;flex-shrink:0;min-width:100px;text-align:right;}
.ev-btn{background:rgba(220,20,60,0.15);border:1px solid rgba(220,20,60,0.3);color:#dc143c;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px;flex-shrink:0;transition:all 0.2s;}
.ev-btn:hover{background:rgba(220,20,60,0.3);}
.stats-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px;}
.stat-chip{background:rgba(220,20,60,0.08);border:1px solid rgba(220,20,60,0.2);border-radius:10px;padding:8px 14px;text-align:center;min-width:80px;cursor:pointer;transition:all 0.2s;}
.stat-chip:hover{border-color:#dc143c;background:rgba(220,20,60,0.15);}
.stat-chip .num{font-size:18px;font-weight:700;}
.stat-chip .lbl{font-size:10px;color:#888;text-transform:uppercase;letter-spacing:1px;}
.detail-modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.88);z-index:9999;justify-content:center;align-items:center;}
.detail-box{background:linear-gradient(135deg,#1a1a1a,#2a2a2a);border:2px solid #dc143c;border-radius:18px;padding:30px;max-width:560px;width:92%;max-height:85vh;overflow-y:auto;position:relative;box-shadow:0 20px 60px rgba(220,20,60,0.4);}
.detail-row{display:flex;gap:10px;margin-bottom:12px;align-items:flex-start;}
.detail-label{color:#888;font-size:11px;text-transform:uppercase;letter-spacing:1px;min-width:120px;flex-shrink:0;padding-top:2px;}
.detail-value{color:#eee;font-size:13px;flex:1;word-break:break-word;}
.msg-box{background:#0a0a0a;border:1px solid rgba(220,20,60,0.2);border-radius:8px;padding:12px;color:#ccc;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word;margin-top:6px;}
.msg-box.deleted{border-color:rgba(231,76,60,0.5);background:rgba(231,76,60,0.06);}
.msg-box.before{border-color:rgba(243,156,18,0.4);background:rgba(243,156,18,0.04);}
.msg-box.after{border-color:rgba(46,204,113,0.4);background:rgba(46,204,113,0.04);}
.msg-label{font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-top:15px;margin-bottom:4px;}
</style>

<div class="stats-bar" id="stats-bar"></div>
<div class="section" style="overflow:visible;">
  <div class="filter-bar">
    <input type="text" id="search" placeholder="Пользователь, channel, message ara..." oninput="applyFilters()">
    <select id="guild-filter" onchange="applyFilters()"><option value="">Tum Сервера</option></select>
  </div>
  <div class="filter-bar" id="cat-buttons" style="margin-bottom:15px;"></div>
  <div id="event-list" style="display:flex;flex-direction:column;gap:5px;">
    <div style="text-align:center;padding:50px;color:#555;">
      <i class="fas fa-spinner fa-spin" style="font-size:28px;color:#dc143c;"></i><br><br>Yukleniyor...
    </div>
  </div>
  <div id="load-more-wrap" style="text-align:center;margin-top:15px;display:none;">
    <button id="load-more-btn" style="background:rgba(220,20,60,0.15);border:2px solid rgba(220,20,60,0.4);color:#dc143c;padding:9px 28px;border-radius:8px;cursor:pointer;font-size:13px;">Более Fazla Yukle</button>
  </div>
</div>

<!-- Detail Modal -->
<div id="detailModal" class="detail-modal" onclick="if(event.target===this)closeDetail()">
  <div class="detail-box">
    <button onclick="closeDetail()" style="position:absolute;top:12px;right:16px;background:none;border:none;color:#dc143c;font-size:24px;cursor:pointer;z-index:1;">&times;</button>
    <div id="detailContent"></div>
  </div>
</div>

<script>
var allEvents=[], filtered=[], currentCat='', shown=0, PAGE=100;

var CATS={
  мод:    {icon:'🔨',label:'Мод',    bg:'rgba(231,76,60,0.2)',  border:'rgba(231,76,60,0.5)',  text:'#e74c3c'},
  member: {icon:'👤',label:'Uye',    bg:'rgba(46,204,113,0.2)', border:'rgba(46,204,113,0.5)', text:'#2ecc71'},
  message:{icon:'💬',label:'Сообщение',  bg:'rgba(52,152,219,0.2)', border:'rgba(52,152,219,0.5)', text:'#3498db'},
  роли:   {icon:'🎭',label:'Роль',    bg:'rgba(155,89,182,0.2)', border:'rgba(155,89,182,0.5)', text:'#9b59b6'},
  channel:{icon:'📺',label:'Канал',  bg:'rgba(243,156,18,0.2)', border:'rgba(243,156,18,0.5)', text:'#f39c12'},
  voice:  {icon:'🔊',label:'Ses',    bg:'rgba(26,188,156,0.2)', border:'rgba(26,188,156,0.5)', text:'#1abc9c'},
  сервер: {icon:'🏰',label:'Сервер', bg:'rgba(230,126,34,0.2)', border:'rgba(230,126,34,0.5)', text:'#e67e22'},
  automod:{icon:'🤖',label:'AutoMod',bg:'rgba(231,76,60,0.2)',  border:'rgba(231,76,60,0.5)',  text:'#e74c3c'},
  invite: {icon:'📨',label:'Приглашение',  bg:'rgba(149,165,166,0.2)',border:'rgba(149,165,166,0.5)',text:'#95a5a6'}
};

function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function buildCatButtons(){
  var w=document.getElementById('cat-buttons');
  var h='<button class="cat-btn active" data-cat="">Tumu</button> ';
  Object.keys(CATS).forEach(function(k){
    h+='<button class="cat-btn" data-cat="'+k+'">'+CATS[k].icon+' '+CATS[k].label+'</button> ';
  });
  w.innerHTML=h;
  w.querySelectorAll('.cat-btn').forEach(function(b){
    b.addEventListener('click',function(){
      w.querySelectorAll('.cat-btn').forEach(function(x){x.classList.remove('active');});
      this.classList.add('active');
      currentCat=this.getAttribute('data-cat');
      applyFilters();
    });
  });
}

function shortDetail(ev){
  var p=[];
  if(ev.user_name) p.push('<span style="color:#dc143c;">@'+esc(ev.user_name)+'</span>');
  if(ev.channel) p.push('<span style="color:#3498db;">#'+esc(ev.channel)+'</span>');
  if(ev.content) p.push('<span style="color:#888;">'+esc(String(ev.content).substring(0,60))+(ev.content.length>60?'...':'')+'</span>');
  if(ev.before) p.push('<span style="color:#888;">'+esc(String(ev.before).substring(0,50))+'...</span>');
  if(ev.old_name&&ev.new_name) p.push(esc(ev.old_name)+' → <b style="color:white;">'+esc(ev.new_name)+'</b>');
  if(ev.added_roles&&ev.added_roles.length) p.push('➕ '+esc(ev.added_roles.join(', ')));
  if(ev.removed_roles&&ev.removed_roles.length) p.push('➖ '+esc(ev.removed_roles.join(', ')));
  if(ev.reason) p.push('<span style="color:#f39c12;">'+esc(String(ev.reason).substring(0,60))+'</span>');
  if(ev.code) p.push('discord.gg/'+esc(ev.code));
  return p.join(' · ') || '<span style="color:#333;">-</span>';
}

function formatTime(ts){
  if(!ts) return '-';
  var d=new Date(ts+'Z'), diff=Math.floor((Date.now()-d)/1000);
  if(isNaN(diff)||diff<0) { d=new Date(ts); diff=Math.floor((Date.now()-d)/1000); }
  if(diff<60) return diff+'s once';
  if(diff<3600) return Math.floor(diff/60)+'dk once';
  if(diff<86400) return Math.floor(diff/3600)+'sa once';
  return d.toLocaleDateString('tr-TR')+' '+d.toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'});
}

function fullTime(ts){
  if(!ts) return '-';
  var d=new Date(ts+'Z');
  if(isNaN(d)) d=new Date(ts);
  return d.toLocaleDateString('tr-TR',{weekday:'long',year:'numeric',month:'long',day:'numeric'})+' '+d.toLocaleTimeString('tr-TR');
}

function renderEvents(){
  var list=document.getElementById('event-list');
  var lmw=document.getElementById('load-more-wrap');
  if(!filtered.length){
    list.innerHTML='<div style="text-align:center;padding:50px;color:#555;"><i class="fas fa-search" style="font-size:32px;"></i><br><br>В конецuч не найдено</div>';
    lmw.style.display='none'; return;
  }
  var slice=filtered.slice(0,shown), html='';
  for(var i=0;i<slice.length;i++){
    var ev=slice[i], cat=ev.category||'мод', c=CATS[cat]||CATS.mod;
    html+='<div class="ev-row">';
    html+='<div class="ev-icon">'+c.icon+'</div>';
    html+='<div class="ev-cat" style="background:'+c.bg+';border:1px solid '+c.border+';color:'+c.text+'">'+c.label+'</div>';
    html+='<div class="ev-action">'+esc(ev.action||'-')+'</div>';
    html+='<div class="ev-detail">'+shortDetail(ev)+'</div>';
    html+='<div class="ev-time">'+formatTime(ev.timestamp)+'</div>';
    html+='<button class="ev-btn" data-idx="'+i+'">Детали</button>';
    html+='</div>';
  }
  list.innerHTML=html;
  list.querySelectorAll('.ev-btn').forEach(function(btn){
    btn.addEventListener('click',function(e){
      e.stopPropagation();
      showDetail(parseInt(this.getAttribute('data-idx')));
    });
  });
  lmw.style.display=shown<filtered.length?'block':'none';
}

function closeDetail(){
  document.getElementById('detailModal').style.display='none';
}

function showDetail(idx){
  var ev=filtered[idx];
  if(!ev) return;
  var cat=ev.category||'мод', c=CATS[cat]||CATS.mod;
  var h='';
  // Заголовок
  h+='<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;padding-bottom:15px;border-bottom:1px solid rgba(220,20,60,0.2);">';
  h+='<span style="font-size:32px;">'+c.icon+'</span>';
  h+='<div><div style="color:#dc143c;font-size:18px;font-weight:700;">'+esc(ev.action||'-')+'</div>';
  h+='<div style="color:#888;font-size:12px;">'+c.label+' · '+fullTime(ev.timestamp)+'</div></div></div>';

  function row(label,val){
    if(val===undefined||val===null||val==='') return '';
    return '<div class="detail-row"><div class="detail-label">'+label+'</div><div class="detail-value">'+val+'</div></div>';
  }

  // Пользователь информация
  if(ev.user_name) h+=row('Пользователь','<span style="color:#dc143c;font-weight:700;">@'+esc(ev.user_name)+'</span>');
  if(ev.user_id)   h+=row('Пользователь ID','<code style="color:#aaa;font-size:12px;">'+esc(ev.user_id)+'</code>');
  if(ev.channel)   h+=row('Канал','<span style="color:#3498db;">#'+esc(ev.channel)+'</span>');
  if(ev.channel_id)h+=row('Канал ID','<code style="color:#aaa;font-size:12px;">'+esc(ev.channel_id)+'</code>');
  if(ev.guild_id)  h+=row('Сервер ID','<code style="color:#aaa;font-size:12px;">'+esc(ev.guild_id)+'</code>');
  if(ev.mod_id)    h+=row('Moderator ID','<code style="color:#aaa;font-size:12px;">'+esc(ev.mod_id)+'</code>');
  if(ev.reason)    h+=row('Причина','<span style="color:#f39c12;">'+esc(ev.reason)+'</span>');
  if(ev.message_id)h+=row('Сообщение ID','<code style="color:#aaa;font-size:12px;">'+esc(ev.message_id)+'</code>');
  if(ev.account_age_days!==undefined) h+=row('Hesap Yasi',ev.account_age_days+' gun');
  if(ev.roles&&ev.roles.length)         h+=row('Роли',esc(ev.roles.join(', ')));
  if(ev.added_roles&&ev.added_roles.length)   h+=row('Добавл Роли','<span style="color:#2ecc71;">'+esc(ev.added_roles.join(', '))+'</span>');
  if(ev.removed_roles&&ev.removed_roles.length) h+=row('Удален Роли','<span style="color:#e74c3c;">'+esc(ev.removed_roles.join(', '))+'</span>');
  if(ev.old_name)  h+=row('Старый Isim','<span style="color:#e74c3c;">'+esc(ev.old_name)+'</span>');
  if(ev.new_name)  h+=row('Новый Isim','<span style="color:#2ecc71;">'+esc(ev.new_name)+'</span>');
  if(ev.old_nick)  h+=row('Старый Nick','<span style="color:#e74c3c;">'+esc(ev.old_nick)+'</span>');
  if(ev.new_nick)  h+=row('Новый Nick','<span style="color:#2ecc71;">'+esc(ev.new_nick)+'</span>');
  if(ev.max_uses)  h+=row('Maks Использование',esc(String(ev.max_uses)));
  if(ev.code)      h+=row('Приглашение Kodu','discord.gg/'+esc(ev.code));
  if(ev.channel_type) h+=row('Канал Tipi',esc(ev.channel_type));

  // Сообщение содержимое - action'a по показать
  var action = ev.action || '';
  if(action.indexOf('Написано') !== -1 || action.indexOf('Metinldы') !== -1) {
    if(ev.content){
      h+='<div class="msg-label" style="color:#3498db;">💬 Сообщение Содержимое</div>';
      h+='<div class="msg-box">'+esc(ev.content)+'</div>';
    }
  }
  if(action.indexOf('Удалено') !== -1) {
    if(ev.content){
      h+='<div class="msg-label" style="color:#e74c3c;">🗑️ Удален Сообщение</div>';
      h+='<div class="msg-box deleted">'+esc(ev.content)+'</div>';
    }
  }
  if(action.indexOf('Duzenlendi') !== -1 || action.indexOf('Редактироватьndi') !== -1) {
    if(ev.before){
      h+='<div class="msg-label" style="color:#f39c12;">✏️ Назад Сообщение</div>';
      h+='<div class="msg-box before">'+esc(ev.before)+'</div>';
    }
    if(ev.after){
      h+='<div class="msg-label" style="color:#2ecc71;">✅ Новый Сообщение</div>';
      h+='<div class="msg-box after">'+esc(ev.after)+'</div>';
    }
  }

  document.getElementById('detailContent').innerHTML=h;
  document.getElementById('detailModal').style.display='flex';
}

function applyFilters(){
  var q=(document.getElementById('search').value||'').toLowerCase();
  var gid=document.getElementById('guild-filter').value;
  filtered=allEvents.filter(function(ev){
    if(currentCat&&ev.category!==currentCat) return false;
    if(gid&&ev.guild_id!==gid) return false;
    if(q&&!JSON.stringify(ev).toLowerCase().includes(q)) return false;
    return true;
  });
  shown=PAGE; renderEvents(); buildStats();
}

function buildStats(){
  var counts={};
  allEvents.forEach(function(ev){var c=ev.category||'мод';counts[c]=(counts[c]||0)+1;});
  var h='<div class="stat-chip" data-cat=""><div class="num" style="color:#dc143c;">'+allEvents.length+'</div><div class="lbl">Всего</div></div>';
  Object.keys(CATS).forEach(function(k){
    if(!counts[k]) return;
    var c=CATS[k];
    h+='<div class="stat-chip" data-cat="'+k+'" style="border-color:'+c.border+';"><div class="num" style="color:'+c.text+'">'+counts[k]+'</div><div class="lbl">'+c.icon+' '+c.label+'</div></div>';
  });
  var bar=document.getElementById('stats-bar');
  bar.innerHTML=h;
  bar.querySelectorAll('.stat-chip').forEach(function(chip){
    chip.addEventListener('click',function(){
      var cat=this.getAttribute('data-cat');
      var btn=document.querySelector('.cat-btn[data-cat="'+cat+'"]');
      if(btn) btn.click();
    });
  });
}

function populateGuilds(){
  var guilds={};
  allEvents.forEach(function(ev){if(ev.guild_id) guilds[ev.guild_id]=true;});
  var sel=document.getElementById('guild-filter');
  sel.innerHTML='<option value="">Tum Сервера</option>';
  Object.keys(guilds).forEach(function(gid){
    sel.innerHTML+='<option value="'+gid+'">'+gid+'</option>';
  });
}

document.getElementById('load-more-btn').addEventListener('click',function(){shown+=PAGE;renderEvents();});

async function loadLogs(){
  try{
    var r=await fetch('/api/logs');
    if(!r.ok) throw new Error('HTTP '+r.status);
    var data=await r.json();
    if(!Array.isArray(data)) data=[];
    allEvents=data;
    populateGuilds(); applyFilters();
  }catch(e){
    document.getElementById('event-list').innerHTML='<p style="color:#e74c3c;text-align:center;padding:40px;">Ошибка: '+e.message+'</p>';
  }
}

buildCatButtons(); loadLogs(); setInterval(loadLogs,15000);
</script>
{% endblock %}
"""

# ─── 2. style.css - section hover удалить (клик блокliyor) ──────────────
# section:hover transform удален, pointer-events dюzeltilecek

os.makedirs("discord_bot/web/templates", exist_ok=True)

with open("discord_bot/web/templates/logs.html", "w", encoding="utf-8") as f:
    f.write(logs_html)
print("✅ logs.html написано")

# ─── 3. style.css fix - section hover transform удалить ───────────────────────
css_path = "web/static/style.css"
with open(css_path, "r", encoding="utf-8") as f:
    css = f.read()

# section hover transform удалить - клик блокliyor
old = """.section:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 35px rgba(220, 20, 60, 0.3);
}"""
new = """.section:hover {
    box-shadow: 0 12px 35px rgba(220, 20, 60, 0.3);
}"""
if old in css:
    css = css.replace(old, new)
    print("✅ section hover transform удалено")
else:
    print("⚠️ section hover zaten dюzeltilmiш или разница")

with open(css_path, "w", encoding="utf-8") as f:
    f.write(css)
print("✅ style.css написано")

print("\n✅ Все dюzeltmeler завершено!")
