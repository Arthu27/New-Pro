import { useState } from 'react';
import { roles } from '../data/dashData';
import { logsSetup, save } from '../data/store';
import { SectionHead, Btn, Tag } from '../components/ui';
import { toast } from '../components/Toast';
import * as api from '../data/api';
const types=[{key:'mod',label:'Moderation',icon:'🛡️'},{key:'message',label:'Messages',icon:'💬'},{key:'member',label:'Members',icon:'👤'},{key:'voice',label:'Voice',icon:'🔊'},{key:'ticket',label:'Tickets',icon:'🎫'},{key:'security',label:'Security',icon:'🔒'},{key:'bot',label:'Bot',icon:'🤖'}];
export default function LogsSetup(){const[,setR]=useState(0);const[creating,setCreating]=useState(false);const refresh=()=>setR(x=>x+1);
  const toggle=(k:string)=>{logsSetup.channels[k]=!logsSetup.channels[k];save();refresh();};
  const toggleRole=(r:string)=>{logsSetup.roles=logsSetup.roles.includes(r)?logsSetup.roles.filter(x=>x!==r):[...logsSetup.roles,r];save();refresh();};
  const createChannels=async()=>{setCreating(true);try{await api.createLogChannels('current',{category:logsSetup.category,channels:logsSetup.channels,roles:logsSetup.roles});toast('Preview complete');}catch{toast('API unavailable');}setCreating(false);};
  return(<div><SectionHead title="Logs Setup" sub="Настройка системы логирования." right={<><Btn onClick={()=>{save();toast('Saved');}}>Save</Btn><Btn secondary onClick={createChannels} disabled={creating}>{creating?'...':'Preview Apply'}</Btn></>}/>
    <div className="grid two"><div className="card">
      <div className="formGrid" style={{gridTemplateColumns:'1fr 1fr'}}><div className="field"><label>Mode</label><select value={logsSetup.mode} onChange={e=>{logsSetup.mode=e.target.value;save();refresh();}}><option>auto</option><option>manual</option><option>hybrid</option></select></div>
        <div className="field"><label>Category</label><input className="input" value={logsSetup.category} onChange={e=>{logsSetup.category=e.target.value;save();refresh();}}/></div></div>
      <h3 style={{margin:'14px 0 8px',fontSize:13,color:'var(--muted)'}}>Log channels</h3>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>{types.map(ch=><button key={ch.key} onClick={()=>toggle(ch.key)} className={`row`} style={logsSetup.channels[ch.key]?{borderColor:'rgba(55,217,158,.28)',background:'rgba(55,217,158,.065)'}:{}}><span>{ch.icon} {ch.label}</span><Tag variant={logsSetup.channels[ch.key]?'good':'warn'}>{logsSetup.channels[ch.key]?'on':'off'}</Tag></button>)}</div>
      <h3 style={{margin:'14px 0 8px',fontSize:13,color:'var(--muted)'}}>Access roles</h3>
      {roles.length?<div style={{display:'flex',flexWrap:'wrap',gap:6}}>{roles.map(r=><button key={r} className={`btn mini ${logsSetup.roles.includes(r)?'':'secondary'}`} onClick={()=>toggleRole(r)}>{r}</button>)}</div>:<p style={{color:'var(--muted)',fontSize:11}}>Роли из API</p>}
    </div><div className="card"><h3>Current config</h3>{types.map(ch=><div key={ch.key} className="row" style={{marginBottom:4}}><span>{ch.icon} {ch.label}</span><Tag variant={logsSetup.channels[ch.key]?'good':'warn'}>{logsSetup.channels[ch.key]?'on':'off'}</Tag></div>)}</div></div></div>);
}
