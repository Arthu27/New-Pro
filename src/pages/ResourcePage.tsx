import { modules } from '../data/dashData';
import { SectionHead, Btn, Tag } from '../components/ui';
import { toast } from '../components/Toast';
interface Props{title:string;items:string[];type:string;}
export default function ResourcePage({title,items,type}:Props){
  return(<div><SectionHead title={title} sub="API-ready resource inventory." right={<Btn secondary onClick={()=>toast('Sync requires API')}>Sync from API</Btn>}/>
    <div className="card">{items.length?<table className="table"><thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Linked modules</th><th></th></tr></thead><tbody>{items.map((x,i)=><tr key={i}><td><b>{x}</b></td><td>{type}</td><td><Tag variant={i%4===0?'warn':'good'}>{i%4===0?'review':'ready'}</Tag></td><td>{modules[i%modules.length][1]}</td><td><Btn mini secondary onClick={()=>toast(`Inspect: ${x}`)}>Inspect</Btn></td></tr>)}</tbody></table>:<div className="empty">No {type}s loaded. Connect API.</div>}</div></div>);
}
