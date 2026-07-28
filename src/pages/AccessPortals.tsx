import { useState, useEffect } from 'react';
import { roles } from '../data/dashData';
import { portalConfig, save } from '../data/store';
import { SectionHead, Btn, Tag } from '../components/ui';
import { toast } from '../components/Toast';
import * as api from '../data/api';
const KEYS = ['owner','admin','moderator','member'] as const;
export default function AccessPortals() {
  const [,setR]=useState(0); const [saving,setSaving]=useState(false);
  const refresh=()=>setR(x=>x+1);
  useEffect(()=>{api.getAccessPortals('current').then(r=>{if(r?.config&&Object.keys(r.config).length){Object.assign(portalConfig,r.config);save();refresh();}}).catch(()=>{});},[]);
  const saveApi=async()=>{setSaving(true);try{await api.saveAccessPortals('current',portalConfig);save();toast('Saved to server');}catch{save();toast('Saved locally');}setSaving(false);};
  const toggleRole=(k:typeof KEYS[number],r:string)=>{const p=portalConfig[k];p.roles=p.roles.includes(r)?p.roles.filter(x=>x!==r):[...p.roles,r];save();refresh();};
  const addUser=(k:typeof KEYS[number])=>{const u=prompt('Discord username:');if(u&&!portalConfig[k].users.includes(u)){portalConfig[k].users.push(u);save();refresh();}};
  const removeUser=(k:typeof KEYS[number],u:string)=>{portalConfig[k].users=portalConfig[k].users.filter(x=>x!==u);save();refresh();};
  return(<div><SectionHead title="Access Portals" sub="Настрой уровни доступа к dashboard." right={<Btn onClick={saveApi} disabled={saving}>{saving?'Saving...':'Save All'}</Btn>}/>
    <div className="grid two">{KEYS.map(k=>{const p=portalConfig[k];return(<div key={k} className="card">
      <div className="sectionHead"><h3 style={{textTransform:'capitalize'}}>{k}</h3><Tag variant={k==='owner'?'warn':k==='admin'?'warn':'good'}>{k}</Tag></div>
      <div style={{marginBottom:10}}><label className="field" style={{gap:4}}><b style={{fontSize:11,color:'var(--muted)'}}>Sections</b></label><div style={{display:'flex',flexWrap:'wrap',gap:4}}>{p.sections.map(s=><span key={s} className="pill">{s}</span>)}</div></div>
      <div style={{marginBottom:10}}><b style={{fontSize:11,color:'var(--muted)'}}>Roles</b>{roles.length?<div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:6}}>{roles.map(r=><button key={r} onClick={()=>toggleRole(k,r)} className={`btn mini ${p.roles.includes(r)?'':'secondary'}`}>{r}</button>)}</div>:<p style={{fontSize:11,color:'var(--muted)'}}>Roles from API</p>}</div>
      <div><b style={{fontSize:11,color:'var(--muted)'}}>Users</b><div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:6}}>{p.users.map(u=><span key={u} className="pill">{u} <button onClick={()=>removeUser(k,u)} style={{border:0,background:'transparent',color:'var(--bad)',fontWeight:900}}>×</button></span>)}</div><Btn mini secondary onClick={()=>addUser(k)}>Add user</Btn></div>
    </div>);})}</div></div>);
}
