import { ModeBanner, SectionHead, Btn, Row } from '../components/ui';

interface Props { apiConnected: boolean; apiData: any; onNavigate: (p: string) => void; onOpenApply: (id: string) => void; onConnectApi: () => void; }

function fmt(v: any): string { if (v === null || v === undefined || v === '') return 'N/A'; if (typeof v === 'number') return v.toLocaleString('ru-RU'); return String(v); }

export default function Overview({ apiConnected, apiData, onNavigate, onOpenApply, onConnectApi }: Props) {
  const o = apiData?.overview || {};
  const metrics = [
    ['Server', o.guildName || 'N/A', 'Discord guild'],['Members', fmt(o.members), 'from Discord API'],['Online', fmt(o.online), 'presence count'],['Channels', fmt(o.channels), 'real channel count'],
    ['Roles', fmt(o.roles), 'real role count'],['Configured modules', fmt(o.modulesConfigured), 'stored in SQLite'],['Audit events', fmt(o.auditEvents), 'backend audit logs'],['Backend', apiConnected ? 'Online' : 'Offline', apiConnected ? 'FastAPI connected' : 'API not connected'],
  ];
  return (
    <div>
      <ModeBanner connected={apiConnected} />
      {!apiConnected && <div className="card apiNotice sectionHead"><div><h3>Backend API не подключён</h3><p>Dashboard не показывает fake-цифры. Подключи API, чтобы заполнить реальные данные сервера.</p></div><Btn secondary onClick={onConnectApi}>Connect API</Btn></div>}
      <SectionHead title="Enterprise Bot Console" sub="Dashboard подключён к Python API. Реальные данные Discord появляются здесь." right={<><Btn onClick={() => onOpenApply('all')}>Apply Queue</Btn><Btn secondary onClick={() => onNavigate('modules')}>Modules</Btn></>} />
      {o.warning && <div className="card apiNotice"><b>Discord API warning</b><p>{o.warning}</p></div>}
      <div className="grid four">{metrics.map(m => <div key={m[0]} className="card metric"><label>{m[0]}</label><strong>{m[1]}</strong><small>{m[2]}</small></div>)}</div>
      <br />
      <div className="grid two">
        <div className="card"><SectionHead title="Operational readiness" sub="Что нужно для настоящего запуска." /><div className="denseList">
          {[['Python API', apiConnected ? 'ok' : 'missing'],['Discord token', o.warning ? 'check' : 'ok'],['Channels loaded', o.channels ? 'ok' : 'check'],['Roles loaded', o.roles ? 'ok' : 'check'],['Live actions', o.liveDiscordActions ? 'enabled' : 'dry-run'],['Bot gateway', 'check terminal']].map(x => <Row key={x[0]} label={x[0]} tag={{ text: x[1], variant: (x[1] === 'ok' || x[1] === 'enabled') ? 'good' : x[1] === 'missing' ? 'bad' : 'warn' }} />)}
        </div></div>
        <div className="card"><SectionHead title="Recent audit" sub="Последние backend события." />
          {(o.recentAudit || []).length ? <table className="table"><tbody>{o.recentAudit.map((l: any, i: number) => <tr key={i}><td><b>{l.action || 'event'}</b></td><td>{l.actor_id || 'system'}</td><td>{new Date((l.created_at || 0) * 1000).toLocaleString()}</td></tr>)}</tbody></table> : <div className="empty">Пока нет audit events.</div>}
        </div>
      </div>
    </div>
  );
}
