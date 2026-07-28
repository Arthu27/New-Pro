import { channels, roles } from '../data/dashData';
import { SectionHead, Btn } from '../components/ui';
interface Props{onOpenApply:(id:string)=>void;}
const steps=['User joins','Check account age','Send welcome embed','Send DM','Wait rules accept','Assign member role','Log to channel'];
const types=['trigger','condition','action','action','wait','action','audit'];
export default function WelcomeFlow({onOpenApply}:Props){
  return(<div><SectionHead title="Welcome Flow Builder" sub="Пошаговый onboarding flow: join → checks → messages → roles → logs." right={<Btn onClick={()=>onOpenApply('welcome')}>Apply flow</Btn>}/>
    <div className="flowBoard">{steps.map((s,i)=><div key={i} className="flowNode card"><span>{i+1}</span><b>{s}</b><small>{types[i]}</small></div>)}</div><br/>
    <div className="grid two"><div className="card"><h3>Flow settings</h3><div className="formGrid"><div className="field"><label>Welcome channel</label><select>{channels.length?channels.map(c=><option key={c}>{c}</option>):<option disabled>From API</option>}</select></div><div className="field"><label>Member role</label><select>{roles.length?roles.map(r=><option key={r}>{r}</option>):<option disabled>From API</option>}</select></div><div className="field"><label>Rules required</label><select><option>true</option><option>false</option></select></div><div className="field"><label>DM welcome</label><select><option>true</option><option>false</option></select></div><div className="field full"><label>Welcome message</label><textarea defaultValue="Welcome {user} to {server}. Please read rules."/></div></div></div>
      <div className="card"><h3>Generated flow JSON</h3><textarea readOnly value={JSON.stringify({trigger:'guildMemberAdd',steps:steps.map((s,i)=>({order:i+1,name:s}))},null,2)}/></div></div></div>);
}
