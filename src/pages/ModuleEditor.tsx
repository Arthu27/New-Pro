import { useState } from 'react';
import { settingsSchema, channels, roles, type ModuleItem } from '../data/dashData';
import { config, pending, readinessScore, defaultFieldValue, saveModuleDraft, setPending, resetModule } from '../data/store';
import { SectionHead, Btn, ModeBanner, ExplainBox, Tag } from '../components/ui';
import { toast } from '../components/Toast';
const channelFields=['primaryChannel','logChannel','errorChannel','fallbackChannel'];
const roleFields=['adminRole','staffRole','memberRole','quarantineRole'];
const staticSelects:Record<string,string[]>={mode:['manual','automatic','template'],preset:['enterprise','community','security','support','gaming'],enabled:['true','false'],dryRun:['true','false'],autoCreateMissing:['yes','no','ask'],action:['delete','warn','mute','kick','ban'],auditLevel:['minimal','standard','full'],debug:['true','false']};
const textareaFields=['jsonOverrides','payload','variables','excludedChannels','bypassRoles'];
const stepHints:Record<string,string>={setup:'mode & preset',channels:'where it works',roles:'who can use',messages:'embed text',rules:'limits/actions',test:'safe check',advanced:'developer options'};
interface Props{module:ModuleItem;apiConnected:boolean;onOpenApply:(id:string)=>void;onOpenJson:(id:string)=>void;onRefresh:()=>void;}
export default function ModuleEditor({module:mod,apiConnected,onOpenApply,onOpenJson,onRefresh}:Props){
  const[modId,modName,modDesc,modType]=mod;const[activeTab,setActiveTab]=useState('setup');const tabs=Object.keys(settingsSchema);const score=readinessScore(modId);const cfg=config[modId]||{};const fields=settingsSchema[activeTab]||[];
  const merged={...(config[modId]||{}),...(pending[modId]||{})};
  const renderField=(f:string)=>{const val=cfg[f]||defaultFieldValue(f);
    if(channelFields.includes(f))return<div key={f} className="field"><label>{f}</label><select defaultValue={val} onChange={e=>setPending(modId,f,e.target.value)}>{channels.length===0?<option disabled>Каналы из API</option>:channels.map(c=><option key={c}>{c}</option>)}</select></div>;
    if(roleFields.includes(f))return<div key={f} className="field"><label>{f}</label><select defaultValue={val} onChange={e=>setPending(modId,f,e.target.value)}>{roles.length===0?<option disabled>Роли из API</option>:roles.map(r=><option key={r}>{r}</option>)}</select></div>;
    if(staticSelects[f])return<div key={f} className="field"><label>{f}</label><select defaultValue={val} onChange={e=>setPending(modId,f,e.target.value)}>{staticSelects[f].map(o=><option key={o}>{o}</option>)}</select></div>;
    if(textareaFields.includes(f))return<div key={f} className="field full"><label>{f}</label><textarea defaultValue={val||'{}'} onChange={e=>setPending(modId,f,e.target.value)}/></div>;
    return<div key={f} className="field"><label>{f}</label><input className="input" defaultValue={val} onChange={e=>setPending(modId,f,e.target.value)}/></div>;
  };
  return(<div><ModeBanner connected={apiConnected}/><ExplainBox title="Настройка модуля" text={`${modName} настраивается как builder.`} next="заполни поля, сохрани draft и открой Apply Preview"/>
    <div className="builderShell">
      <aside className="builderNav card"><div className="builderModuleTitle"><span className="moduleType">{modType}</span><h2>{modName}</h2><p>{modDesc}</p></div>
        <div className="builderSteps">{tabs.map((t,i)=><button key={t} className={`builderStep ${activeTab===t?'active':''}`} onClick={()=>setActiveTab(t)}><span>{i+1}</span><div><b>{t}</b><small>{stepHints[t]}</small></div></button>)}</div></aside>
      <section className="builderMain card"><SectionHead title={`${modName} / ${activeTab}`} right={<><Btn onClick={()=>onOpenApply(modId)}>Apply</Btn><Btn secondary onClick={()=>onOpenJson(modId)}>JSON</Btn></>}/>
        <div className="formGrid">{fields.map(f=>renderField(f))}</div><br/><div className="toolbar"><Btn onClick={()=>{saveModuleDraft(modId);onRefresh();toast('Draft saved');}}>Save Draft</Btn><Btn secondary onClick={()=>onOpenApply(modId)}>Apply Module</Btn><Btn secondary onClick={()=>{resetModule(modId);onRefresh();toast('Reset done');}}>Reset</Btn></div></section>
      <aside className="builderPreview card"><div className="sectionHead"><div><h3>Preview</h3></div><Tag variant={score>70?'good':score>35?'warn':'bad'}>{score}%</Tag></div>
        <div className="previewStack">{[['enabled',merged.enabled||'false'],['channel',merged.primaryChannel||'missing'],['log',merged.logChannel||'missing'],['staff role',merged.staffRole||'missing'],['action',merged.action||'not set'],['draft changes',String(Object.keys(pending[modId]||{}).length)]].map(r=><div key={r[0]} className="previewItem"><span>{r[0]}</span><b>{r[1]}</b></div>)}</div>
        <div className="previewNote">Apply сначала покажет preview. Без API это safe dry-run.</div></aside>
    </div></div>);
}
