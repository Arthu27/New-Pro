#!/usr/bin/env python3
# Помощь sayfasini yeniden написатьar
content = r"""{% extends "base.html" %}
{% block title %}Команда Руководство — Aether{% endblock %}
{% block page_title %}{% endblock %}
{% block content %}
<style>
:root{
  --r:#ff4757;--r2:rgba(255,71,87,0.15);--r-glow:rgba(255,71,87,0.3);
  --g:#2ed573;--g2:rgba(46,213,115,0.15);--g-glow:rgba(46,213,115,0.3);
  --b:#5352ed;--b2:rgba(83,82,237,0.15);--b-glow:rgba(83,82,237,0.3);
  --y:#ffa502;--y2:rgba(255,165,2,0.15);--y-glow:rgba(255,165,2,0.3);
  --p:#ff6b81;--p2:rgba(255,107,129,0.15);
  --гол:#ffd700;--gold2:rgba(255,215,0,0.15);
  --cy:#00f5ff;
  --glass:rgba(10,8,4,0.75);--border-base:rgba(212,168,67,0.1);
}
.yr-orb{position:fixed;border-radius:50%;pointer-events:none;z-index:0;filter:blur(100px);opacity:0.07;}
.yr-orb-1{width:500px;height:500px;background:#ff4757;top:-150px;right:-100px;animation:orbFloat 8s ease-in-out infinite;}
.yr-orb-2{width:400px;height:400px;background:#5352ed;bottom:-100px;left:-80px;animation:orbFloat 10s ease-in-out infinite reverse;}
.yr-orb-3{width:300px;height:300px;background:#2ed573;top:40%;left:40%;animation:orbFloat 12s ease-in-out infinite 2s;}
@keyframes orbFloat{0%,100%{transform:translate(0,0) scale(1);}33%{transform:translate(30px,-20px) scale(1.05);}66%{transform:translate(-20px,30px) scale(0.95);}}
.yr-каждый{text-align:center;padding:32px 20px 28px;position:relative;z-index:1;}
.yr-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(212,168,67,0.08);border:1px solid rgba(212,168,67,0.2);border-radius:99px;padding:5px 16px;font-size:11px;font-weight:700;color:#c8922a;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:18px;}
.yr-badge::before{content:'';width:6px;height:6px;border-radius:50%;background:#c8922a;animation:blink 1.5s ease-in-out infinite;}
@keyframes blink{0%,100%{opacity:1;box-shadow:0 0 6px #c8922a;}50%{opacity:0.3;box-shadow:none;}}
.yr-каждый h1{font-size:clamp(28px,4vw,48px);font-weight:900;letter-spacing:-0.04em;line-height:1;margin-bottom:10px;background:linear-gradient(135deg,#f0e8d0 0%,#c8922a 40%,#f0e8d0 70%,#e0a830 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;background-size:200% 200%;animation:shimmer 4s ease-in-out infinite;}
@keyframes shimmer{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
.yr-каждый-sub{font-size:13px;color:rgba(240,232,208,0.35);margin-bottom:24px;}
.yr-stats{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-bottom:28px;position:relative;z-index:1;}
.yr-stat{display:flex;align-items:center;gap:10px;background:var(--glass);border:1px solid var(--border-base);border-radius:12px;padding:12px 20px;backdrop-filter:blur(20px);transition:border-color 0.2s,box-shadow 0.2s,transform 0.2s;cursor:default;}
.yr-stat:hover{transform:translateY(-2px);}
.yr-stat-icon{font-size:18px;}
.yr-stat-val{font-size:20px;font-weight:800;color:#f0e8d0;letter-spacing:-0.03em;line-height:1;}
.yr-stat-lbl{font-size:10px;color:rgba(240,232,208,0.35);text-transform:uppercase;letter-spacing:0.08em;margin-top:2px;}
.yr-stat.s-гол{border-color:rgba(255,215,0,0.2);}
.yr-stat.s-гол:hover{border-color:var(--гол);box-shadow:0 0 20px var(--gold2);}
.yr-stat.s-green{border-color:rgba(46,213,115,0.2);}
.yr-stat.s-green:hover{border-color:var(--g);box-shadow:0 0 20px var(--g2);}
.yr-stat.s-blue{border-color:rgba(83,82,237,0.2);}
.yr-stat.s-blue:hover{border-color:var(--b);box-shadow:0 0 20px var(--b2);}
.yr-stat.s-red{border-color:rgba(255,71,87,0.2);}
.yr-stat.s-red:hover{border-color:var(--r);box-shadow:0 0 20px var(--r2);}
.yr-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:24px;position:relative;z-index:1;}
.yr-search-wrap{position:relative;flex:1;min-width:220px;}
.yr-search-wrap i{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:rgba(212,168,67,0.4);font-size:12px;pointer-events:none;}
.yr-search{width:100%;padding:11px 14px 11px 38px;background:var(--glass);border:1px solid var(--border-base);border-radius:12px;color:#f0e8d0;font-size:13px;font-family:Inter,sans-serif;backdrop-filter:blur(20px);transition:border-color 0.2s,box-shadow 0.2s;margin:0;}
.yr-search:focus{outline:none;border-color:rgba(212,168,67,0.45);box-shadow:0 0 0 3px rgba(212,168,67,0.08);}
.yr-search::placeholder{color:rgba(240,232,208,0.2);}
.yr-tabs{display:flex;gap:6px;flex-wrap:wrap;}
.yr-tab{display:flex;align-items:center;gap:6px;padding:8px 16px;background:var(--glass);border:1px solid var(--border-base);border-radius:99px;color:rgba(240,232,208,0.4);font-size:11px;font-weight:700;cursor:pointer;font-family:Inter,sans-serif;transition:all 0.18s;white-space:nowrap;backdrop-filter:blur(12px);}
.yr-tab:hover{color:#f0e8d0;border-color:rgba(212,168,67,0.3);background:rgba(212,168,67,0.06);}
.yr-tab.active{color:#c8922a;border-color:rgba(212,168,67,0.4);background:rgba(212,168,67,0.1);box-shadow:0 0 16px rgba(212,168,67,0.15);}
.yr-tab[data-c="r"].active{color:var(--r);border-color:var(--r);background:var(--r2);box-shadow:0 0 16px var(--r-glow);}
.yr-tab[data-c="g"].active{color:var(--g);border-color:var(--g);background:var(--g2);box-shadow:0 0 16px var(--g-glow);}
.yr-tab[data-c="b"].active{color:var(--b);border-color:var(--b);background:var(--b2);box-shadow:0 0 16px var(--b-glow);}
.yr-tab[data-c="y"].active{color:var(--y);border-color:var(--y);background:var(--y2);box-shadow:0 0 16px var(--y-glow);}
.yr-tab[data-c="p"].active{color:var(--p);border-color:var(--p);background:var(--p2);}
.yr-tab[data-c="гол"].active{color:var(--гол);border-color:var(--гол);background:var(--gold2);}
.yr-section{position:relative;z-index:1;margin-bottom:28px;}
.yr-section-hdr{display:flex;align-items:center;gap:10px;margin-bottom:12px;}
.yr-section-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.14em;white-space:nowrap;}
.yr-section-line{flex:1;height:1px;}
.yr-section-count{font-size:10px;color:rgba(240,232,208,0.3);border:1px solid rgba(212,168,67,0.1);border-radius:99px;padding:2px 8px;background:rgba(212,168,67,0.05);}
.yr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;}
.yr-card{background:var(--glass);border:1px solid rgba(212,168,67,0.08);border-radius:12px;padding:16px 18px;cursor:default;transition:all 0.22s;backdrop-filter:blur(20px);position:relative;overflow:hidden;}
.yr-card::after{content:'';position:absolute;top:0;left:-100%;width:60%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.03),transparent);transition:left 0.5s;}
.yr-card:hover::after{left:150%;}
.yr-card:hover{transform:translateY(-2px);}
.yr-card[data-c="r"]:hover{border-color:var(--r);box-shadow:0 0 20px var(--r2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card[data-c="g"]:hover{border-color:var(--g);box-shadow:0 0 20px var(--g2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card[data-c="b"]:hover{border-color:var(--b);box-shadow:0 0 20px var(--b2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card[data-c="y"]:hover{border-color:var(--y);box-shadow:0 0 20px var(--y2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card[data-c="p"]:hover{border-color:var(--p);box-shadow:0 0 20px var(--p2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card[data-c="гол"]:hover{border-color:var(--гол);box-shadow:0 0 20px var(--gold2),0 4px 20px rgba(0,0,0,0.4);}
.yr-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;}
.yr-cmd-name{font-size:13px;font-weight:700;font-family:'Courier New',monospace;letter-spacing:0.02em;}
.yr-cmd-desc{font-size:11px;color:rgba(240,232,208,0.5);line-height:1.5;}
.yr-cmd-usage{font-size:10px;color:rgba(240,232,208,0.22);margin-top:4px;font-family:'Courier New',monospace;}
.pb{font-size:9px;font-weight:700;padding:2px 7px;border-radius:99px;text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap;flex-shrink:0;}
.pb-all{background:rgba(46,213,115,0.1);color:var(--g);border:1px solid rgba(46,213,115,0.25);}
.pb-mod{background:rgba(255,165,2,0.1);color:var(--y);border:1px solid rgba(255,165,2,0.25);}
.pb-админ{background:rgba(255,71,87,0.1);color:var(--r);border:1px solid rgba(255,71,87,0.25);}
.yr-empty{text-align:center;padding:60px 20px;color:rgba(240,232,208,0.2);font-size:13px;position:relative;z-index:1;}
.yr-empty i{font-size:32px;margin-bottom:12px;display:block;opacity:0.3;}
@media(max-width:768px){.yr-grid{grid-template-columns:1fr;}.yr-stats{flex-direction:column;}}
</style>

<div class="yr-orb yr-orb-1"></div>
<div class="yr-orb yr-orb-2"></div>
<div class="yr-orb yr-orb-3"></div>

<div class="yr-каждый">
  <div class="yr-badge">Aether Bot</div>
  <h1>Команда Руководство</h1>
  <p class="yr-каждый-sub">Tum команды, kategoriler ve izin уровеньleri</p>
</div>

<div class="yr-stats">
  <div class="yr-stat s-гол">
    <div class="yr-stat-icon">&#9889;</div>
    <div><div class="yr-stat-val" id="total-cmds">-</div><div class="yr-stat-lbl">Всего Команда</div></div>
  </div>
  <div class="yr-stat s-blue">
    <div class="yr-stat-icon">&#128194;</div>
    <div><div class="yr-stat-val">6</div><div class="yr-stat-lbl">Kategori</div></div>
  </div>
  <div class="yr-stat s-green">
    <div class="yr-stat-icon">&#128065;</div>
    <div><div class="yr-stat-val" id="filtered-count">-</div><div class="yr-stat-lbl">Gosterilen</div></div>
  </div>
  <div class="yr-stat s-red">
    <div class="yr-stat-icon">&#128172;</div>
    <div><div class="yr-stat-val">/помощь</div><div class="yr-stat-lbl">Discord Команда</div></div>
  </div>
</div>

<div class="yr-toolbar">
  <div class="yr-search-wrap">
    <i class="fas fa-search"></i>
    <input class="yr-search" type="text" id="cmd-search" placeholder="Команда или aciklama ara..." oninput="yrFilter()">
  </div>
  <div class="yr-tabs" id="yr-tabs">
    <button class="yr-tab active" data-c="" onclick="yrTab('all',this)">Tumu</button>
    <button class="yr-tab" data-c="r" onclick="yrTab('мод',this)">Мод</button>
    <button class="yr-tab" data-c="y" onclick="yrTab('варн',this)">Предупреждение</button>
    <button class="yr-tab" data-c="g" onclick="yrTab('music',this)">Muzik</button>
    <button class="yr-tab" data-c="p" onclick="yrTab('fun',this)">Игра</button>
    <button class="yr-tab" data-c="гол" onclick="yrTab('eco',this)">Ekonomi</button>
    <button class="yr-tab" data-c="b" onclick="yrTab('util',this)">Aramaclar</button>
  </div>
</div>

<div id="yr-container"></div>

<script>
var YR_CATS=[
  {id:'мод',color:'r',title:'Moderasyon',cmds:[
    {n:'/moderate бан',d:'Пользователя постоянный запретla',u:'/moderate бан @user причина',p:'админ'},
    {n:'/moderate кик',d:'С сервера at',u:'/moderate кик @user причина',p:'админ'},
    {n:'/moderate timeout',d:'Gecici sustur',u:'/moderate timeout @user 10m',p:'админ'},
    {n:'/moderate untimeout',d:'Susturmayi удалить',u:'/moderate untimeout @user',p:'админ'},
    {n:'/moderate unban',d:'Bani удалить',u:'/moderate unban user_id',p:'админ'},
    {n:'/utility clear',d:'Toplu message удалить',u:'/utility clear 50',p:'админ'},
    {n:'/utility lock',d:'Канал заблокировать',u:'/utility lock',p:'мод'},
    {n:'/utility unlock',d:'Канал замокni удалить',u:'/utility unlock',p:'мод'},
    {n:'/utility userinfo',d:'Пользователь infosi',u:'/utility userinfo @user',p:'мод'},
    {n:'/роли',d:'Роли ver / al',u:'/роли @user @роли',p:'админ'},
  ]},
  {id:'варн',color:'y',title:'Предупреждение Система',cmds:[
    {n:'/варн',d:'Предупреждение ver',u:'/варн @user причина',p:'мод'},
    {n:'/warnings',d:'Предупреждения listele',u:'/warnings @user',p:'мод'},
    {n:'/clearwarns',d:'Tum предупреждения clear',u:'/clearwarns @user',p:'админ'},
  ]},
  {id:'music',color:'g',title:'Muzik',cmds:[
    {n:'/cal',d:"YouTube'dan muzik cal",u:'/cal lofi hip hop',p:'all'},
    {n:'/dur',d:'Duraklat / devam',u:'/dur',p:'all'},
    {n:'/atla',d:'Sarkхорошо atla',u:'/atla',p:'all'},
    {n:'/kuyruk',d:'Kuyrugu goster',u:'/kuyruk',p:'all'},
    {n:'/ses',d:'Ses уровеньsi (0-100)',u:'/ses 80',p:'all'},
    {n:'/clear-kuyruk',d:'Kuyrugu clear',u:'/clear-kuyruk',p:'all'},
    {n:'/ayril',d:'Ses из канала cik',u:'/ayril',p:'all'},
    {n:'/join',d:'Ses в канал katil',u:'/join',p:'all'},
  ]},
  {id:'fun',color:'p',title:'Eglence ve Игра',cmds:[
    {n:'/текст',d:'Текст орёл at',u:'/текст',p:'all'},
    {n:'/кубик-at',d:'Бросить кубик (1-5 adet)',u:'/кубик-at 2',p:'all'},
    {n:'/tas-kagit-ножницы',d:'Tas kagit ножницы',u:'/tas-kagit-ножницы',p:'all'},
    {n:'/игра-baslat',d:'Число tahmin играu',u:'/игра-baslat',p:'all'},
    {n:'/игра-tahmin',d:'Tahmin et',u:'/игра-tahmin 42',p:'all'},
    {n:'/sihirli-top',d:'Sihirli 8 top',u:'/sihirli-top soru',p:'all'},
    {n:'/игра-rastgele-uye',d:'Rastgele uye sec',u:'/игра-rastgele-uye',p:'all'},
  ]},
  {id:'eco',color:'гол',title:'Ekonomi ve Ozellikler',cmds:[
    {n:'/dogumgunu',d:'Dogum gununu сохранить',u:'/dogumgunu 15.03',p:'all'},
    {n:'/dogumgunleri',d:'Yaklasan dogum gunleri',u:'/dogumgunleri',p:'all'},
    {n:'/duty-panel',d:'Gorev panelini gonder',u:'/duty-panel #channel',p:'админ'},
    {n:'/duty-add',d:'Manuel ilerleme add',u:'/duty-add @user 10',p:'мод'},
    {n:'/ticket_panel',d:'Ticket panelini gonder',u:'/ticket_panel',p:'админ'},
    {n:'/webhook',d:'Webhook islemleri',u:'/webhook olustur',p:'админ'},
  ]},
  {id:'util',color:'b',title:'Помощник Aramaclar',cmds:[
    {n:'/modstats',d:'Moderator статистика',u:'/modstats',p:'мод'},
    {n:'/activemods',d:'En активен moderatorler',u:'/activemods',p:'мод'},
    {n:'/saglik',d:'Сервер saglik skoru',u:'/saglik',p:'all'},
    {n:'/channel-статистика',d:'Канал message istatistigi',u:'/channel-статистика',p:'all'},
    {n:'/duty-stats',d:'Gorev очки tablosu',u:'/duty-stats',p:'мод'},
    {n:'/verify-setup',d:'Dogrulama sistemini kur',u:'/verify-setup',p:'админ'},
  ]},
];
var CM={
  r:{t:'#ff4757',l:'rgba(255,71,87,0.4)'},
  g:{t:'#2ed573',l:'rgba(46,213,115,0.4)'},
  b:{t:'#5352ed',l:'rgba(83,82,237,0.4)'},
  y:{t:'#ffa502',l:'rgba(255,165,2,0.4)'},
  p:{t:'#ff6b81',l:'rgba(255,107,129,0.4)'},
  гол:{t:'#ffd700',l:'rgba(255,215,0,0.4)'},
};
var yrTab_='all',yrQ_='';
function pb(p){
  if(p==='админ')return '<span class="pb pb-админ">Иsminin</span>';
  if(p==='мод')return '<span class="pb pb-mod">Мод</span>';
  return '<span class="pb pb-all">Каждый</span>';
}
function yrFilter(){yrQ_=document.getElementById('cmd-search').value.toLowerCase().trim();yrRender();}
function yrTab(id,btn){
  yrTab_=id;
  document.querySelectorAll('.yr-tab').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
  yrRender();
}
function yrRender(){
  var c=document.getElementById('yr-container'),html='',shown=0;
  YR_CATS.forEach(function(cat){
    if(yrTab_!=='all'&&yrTab_!==cat.id)return;
    var f=cat.cmds.filter(function(x){
      if(!yrQ_)return true;
      return x.n.toLowerCase().includes(yrQ_)||x.d.toLowerCase().includes(yrQ_);
    });
    if(!f.length)return;
    shown+=f.length;
    var cm=CM[cat.color]||CM.b;
    html+='<div class="yr-section" data-cat="'+cat.id+'">';
    html+='<div class="yr-section-hdr">';
    html+='<span class="yr-section-title" style="color:'+cm.t+';text-shadow:0 0 10px '+cm.t+'40;">'+cat.title+'</span>';
    html+='<div class="yr-section-line" style="background:linear-gradient(90deg,'+cm.l+',transparent);"></div>';
    html+='<span class="yr-section-count">'+f.length+' команда</span>';
    html+='</div><div class="yr-grid">';
    f.forEach(function(x){
      html+='<div class="yr-card" data-c="'+cat.color+'">';
      html+='<div class="yr-card-top"><span class="yr-cmd-name" style="color:'+cm.t+';text-shadow:0 0 8px '+cm.t+'60;">'+x.n+'</span>'+pb(x.p)+'</div>';
      html+='<div class="yr-cmd-desc">'+x.d+'</div>';
      html+='<div class="yr-cmd-usage">'+x.u+'</div>';
      html+='</div>';
    });
    html+='</div></div>';
  });
  if(!html)html='<div class="yr-empty"><i class="fas fa-search"></i>В конецuч не найдено.</div>';
  c.innerHTML=html;
  document.getElementById('filtered-count').textContent=shown;
}
(function(){
  var t=YR_CATS.reduce(function(s,c){return s+c.cmds.length;},0);
  document.getElementById('total-cmds').textContent=t;
  yrRender();
})();
</script>
{% endblock %}
"""

with open('web/templates/помощь.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("OK - помощь.html написано")
