import { modules } from '../data/dashData';
import { config } from '../data/store';
import { ModeBanner, ExplainBox, SectionHead, Btn, Tag } from '../components/ui';
import { toast } from '../components/Toast';
interface Props { apiConnected: boolean; onNavigate: (p: string) => void; onOpenApply: (id: string) => void; }
export default function Modules({ apiConnected, onNavigate, onOpenApply }: Props) {
  return (<div><ModeBanner connected={apiConnected} /><ExplainBox title="Что такое Modules?" text="Это список всех функций бота. Нажми Configure, чтобы настроить конкретный модуль." next="начни с AutoMod, Tickets или Welcome" />
    <SectionHead title="Modules" sub="Все функции бота." right={<Btn onClick={() => onOpenApply('all')}>Apply All</Btn>} />
    <div className="grid moduleGrid">{modules.map(m => { const [id,name,desc,type]=m; const enabled=config[id]?.enabled==='true'; return (
      <div key={id} className="card moduleCard"><div className="moduleTop"><span className="moduleType">{type}</span><Tag variant={enabled?'good':'warn'}>{enabled?'enabled':'draft'}</Tag></div><h3>{name}</h3><p>{desc}</p>
        <div className="moduleActions"><Btn mini onClick={() => onNavigate(id)}>Configure</Btn><Btn mini secondary onClick={() => toast(`Quick: ${name}`)}>Quick</Btn></div></div>);})}</div></div>);
}
