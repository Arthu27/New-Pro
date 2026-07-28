import { useState } from 'react';
import { channels, roles } from '../data/dashData';
import { SectionHead, Btn } from '../components/ui';
import { toast } from '../components/Toast';
interface Props{onOpenApply:(id:string)=>void;}
export default function TicketPanel({onOpenApply}:Props){const[title,setTitle]=useState('Open a support ticket');const[desc,setDesc]=useState('Choose a category below and describe your issue. Staff will respond soon.');
  return(<div><SectionHead title="Ticket Panel Builder" sub="Собери panel message, категории, формы, SLA и staff routing." right={<Btn onClick={()=>onOpenApply('tickets')}>Apply panel</Btn>}/>
    <div className="grid two"><div className="card"><div className="formGrid"><div className="field"><label>Panel channel</label><select>{channels.length?channels.map(c=><option key={c}>{c}</option>):<option disabled>Channels from API</option>}</select></div><div className="field"><label>Staff role</label><select>{roles.length?roles.map(r=><option key={r}>{r}</option>):<option disabled>Roles from API</option>}</select></div><div className="field"><label>SLA</label><input className="input" defaultValue="15m first response"/></div>
      <div className="field full"><label>Panel title</label><input className="input" value={title} onChange={e=>setTitle(e.target.value)}/></div><div className="field full"><label>Description</label><textarea value={desc} onChange={e=>setDesc(e.target.value)}/></div><div className="field full"><label>Categories</label><textarea defaultValue="Support, Purchase, Report, Partner, Bug"/></div></div></div>
      <div className="card"><h3>Discord preview</h3><div className="previewEmbed"><b>{title}</b><p>{desc}</p><div className="previewButtons"><button>Support</button><button>Purchase</button><button>Report</button></div></div><br/><Btn secondary onClick={()=>toast('JSON copied')}>Copy JSON</Btn></div></div></div>);
}
