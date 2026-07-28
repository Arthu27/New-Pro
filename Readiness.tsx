import { modules } from '../data/dashData';
import { readinessScore, config } from '../data/store';
import { ModeBanner, ExplainBox, SectionHead, Btn, Tag, Row } from '../components/ui';
interface Props { apiConnected: boolean; onNavigate: (p: string) => void; onOpenApply: (id: string) => void; }
export default function Readiness({ apiConnected, onNavigate, onOpenApply }: Props) {
  return (<div><ModeBanner connected={apiConnected} /><ExplainBox title="Что такое Readiness?" text="Это процент готовности модуля." next="открой модуль с низким процентом" />
    <SectionHead title="Module Readiness" sub="Показывает, какие модули готовы к применению." right={<Btn secondary onClick={() => onNavigate('modules')}>Open modules</Btn>} />
    <div className="grid moduleGrid">{modules.map(m => { const [id,name,desc,type]=m; const score=readinessScore(id); const c=config[id]||{}; return (
      <div key={id} className="card moduleCard"><div className="moduleTop"><span className="moduleType">{type}</span><Tag variant={score>75?'good':score>35?'warn':'bad'}>{score}%</Tag></div><h3>{name}</h3><p>{desc}</p>
        <div className="progress"><i style={{width:`${score}%`}}/></div>
        <div className="denseList"><Row label="Channel" value={c.primaryChannel||'missing'}/><Row label="Staff role" value={c.staffRole||'missing'}/></div>
        <div className="moduleActions"><Btn mini onClick={() => onNavigate(id)}>Fix</Btn><Btn mini secondary onClick={() => onOpenApply(id)}>Apply</Btn></div></div>);})}</div></div>);
}
