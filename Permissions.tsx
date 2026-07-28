import { useState, useEffect } from 'react';
import { commands, roles } from '../data/dashData';
import { getDefaultPerm, save, permState } from '../data/store';
import { SectionHead, Btn, Tag, Row } from '../components/ui';
import { toast } from '../components/Toast';
import * as api from '../data/api';
export default function Permissions(){const[sel,setSel]=useState('/settings');const[q,setQ]=useState('');const[saving,setSaving]=useState(false);const[,setR]=useState(0);const refresh=()=>setR(x=>x+1);const perm=getDefaultPerm(sel);
  useEffect(()=>{api.getPermissions('current').then(r=>{if(r?.rules&&Array.isArray(r.rules)){for(const rule of r.rules){const cmd=rule.command_name||rule.command;if(!permState[cmd])permState[cmd]={mode:'restricted',roles:{},denyRoles:{},syncVisibility:false};if(rule.target_type==='role'){if(rule.effect==='allow')permState[cmd].roles[rule.target_id]='allow';else permState[cmd].denyRoles[rule.target_id]='deny';}}save();refresh();}}).catch(()=>{});},[]);
  const saveApi=async()=>{setSaving(true);try{const rules:any[]=[];for(const[cmd,p]of Object.entries(permState)){for(const[rid,eff]of Object.entries(p.roles))rules.push({command:cmd,targetType:'role',targetId:rid,effect:eff});for(const[rid,eff]of Object.entries(p.denyRoles))rules.push({command:cmd,targetType:'role',targetId:rid,effect:eff});}await api.savePermissions('current',rules);save();toast('Saved to server');}catch{save();toast('Saved locally');}setSaving(false);};
  const toggleRole=(r:string)=>{if(perm.roles[r]==='allow')delete perm.roles[r];else perm.roles[r]='allow';save();refresh();};
  return(<div><SectionHead title="Permissions Center" sub="Управление правами доступа к командам бота." right={<><Btn onClick={saveApi} disabled={saving}>{saving?'Saving...':'Save'}</Btn><Btn secondary onClick={()=>toast('Sync после API')}>Sync</Btn></>}/>
    <div className="grid two">
      <div className="card"><input className="input" placeholder="Search commands..." value={q} onChange={e=>setQ(e.target.value)} style={{marginBottom:10}}/>
        <div className="denseList">{commands.filter(c=>c.toLowerCase().includes(q.toLowerCase())).map(c=><button key={c} className={`row ${sel===c?'':''}`} onClick={()=>{setSel(c);refresh();}} style={sel===c?{borderColor:'rgba(83,177,253,.30)',background:'rgba(83,177,253,.10)'}:{}}><b>{c}</b>{permState[c]?.mode==='restricted'&&<Tag variant="warn">restricted</Tag>}</button>)}</div></div>
      <div className="card"><SectionHead title={sel}/>
        <div style={{display:'flex',gap:8,marginBottom:12}}>{['everyone','restricted','disabled'].map(m=><button key={m} className={`btn ${perm.mode===m?'':'secondary'}`} onClick={()=>{perm.mode=m;save();refresh();}}>{m}</button>)}</div>
        {perm.mode==='restricted'&&<div><div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>
          <Btn mini secondary onClick={()=>{if(!roles.length){toast('Роли не загружены');return;}perm.roles={};roles.filter(r=>/owner|admin/i.test(r)).forEach(r=>{perm.roles[r]='allow';});perm.denyRoles={};save();refresh();}}>Admins only</Btn>
          <Btn mini secondary onClick={()=>{if(!roles.length){toast('Роли не загружены');return;}perm.roles={};roles.filter(r=>/owner|admin|mod|staff/i.test(r)).forEach(r=>{perm.roles[r]='allow';});perm.denyRoles={};save();refresh();}}>Staff preset</Btn>
          <Btn mini secondary onClick={()=>{perm.roles={};perm.denyRoles={};save();refresh();}}>Clear</Btn></div>
          {roles.length?<div style={{display:'flex',flexWrap:'wrap',gap:6}}>{roles.map(r=><button key={r} className={`btn mini ${perm.roles[r]==='allow'?'':'secondary'}`} onClick={()=>toggleRole(r)}>{r}</button>)}</div>:<p style={{color:'var(--muted)',fontSize:11}}>Роли загрузятся из API</p>}</div>}
        {perm.mode==='disabled'&&<div className="empty">Команда отключена.</div>}
        <div style={{marginTop:14}}><Row label="Mode" tag={{text:perm.mode,variant:perm.mode==='everyone'?'good':perm.mode==='restricted'?'warn':'bad'}}/><Row label="Allowed roles" value={String(Object.keys(perm.roles).length)}/></div>
      </div></div></div>);
}
