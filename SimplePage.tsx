import { useState, useEffect } from 'react';
import { SectionHead, Btn } from '../components/ui';
import { endpoints } from '../data/dashData';
import * as api from '../data/api';
import { toast } from '../components/Toast';

interface Props { page: string; apiConnected: boolean; onCheckApi: () => void; }

export default function SimplePage({ page, apiConnected, onCheckApi }: Props) {
  const [logs, setLogs] = useState<any[]>([]);
  const [logFilter, setLogFilter] = useState('');

  useEffect(() => {
    if (page === 'logs' && apiConnected) {
      api.request('/guilds/current/logs?limit=50').then(r => {
        if (r?.logs) setLogs(r.logs);
      }).catch(() => {});
    }
  }, [page, apiConnected]);

  if (page === 'activity') return (
    <div>
      <SectionHead title="Activity" sub="Backend event stream." />
      <div className="empty">{apiConnected ? 'Bağlı — event stream yakında.' : 'API bağlantısı gerekli.'}</div>
    </div>
  );

  if (page === 'logs') {
    const filtered = logs.filter(l => !logFilter || (l.action || '').toLowerCase().includes(logFilter.toLowerCase()));
    return (
      <div>
        <SectionHead title="Logs" sub="Audit log viewer." right={<Btn secondary onClick={() => toast('Export yakında')}>Export</Btn>} />
        <div className="card">
          <div className="toolbar">
            <select onChange={e => setLogFilter(e.target.value)}>
              <option value="">All events</option>
              <option value="module">Module changes</option>
              <option value="login">Logins</option>
              <option value="permission">Permissions</option>
              <option value="apply">Apply actions</option>
            </select>
            <input className="input" placeholder="Search logs..." value={logFilter} onChange={e => setLogFilter(e.target.value)} style={{ maxWidth: 300 }} />
          </div>
          {filtered.length > 0 ? (
            <table className="table">
              <thead><tr><th>Action</th><th>Actor</th><th>Time</th></tr></thead>
              <tbody>
                {filtered.map((l, i) => (
                  <tr key={i}>
                    <td><b>{l.action}</b></td>
                    <td>{l.actor_id || 'system'}</td>
                    <td>{new Date((l.created_at || 0) * 1000).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">{apiConnected ? 'Henüz log yok. Bir işlem yapınca burada görünecek.' : 'API bağlantısı gerekli. Settings → API sayfasından bağlan.'}</div>
          )}
        </div>
      </div>
    );
  }

  if (page === 'settings') return (
    <div>
      <SectionHead title="Settings" sub="Console preferences and backend connection." />
      <div className="grid two">
        <div className="card">
          <h3>API Connection</h3>
          <div style={{ marginTop: 10 }}>
            <div className="row" style={{ marginBottom: 8 }}>
              <b>Status</b>
              <span className={`tag ${apiConnected ? 'good' : 'bad'}`}>{apiConnected ? 'Connected' : 'Offline'}</span>
            </div>
          </div>
          <div className="formGrid" style={{ gridTemplateColumns: '1fr' }}>
            <div className="field full">
              <label>Base URL</label>
              <input id="apiBaseInput" className="input" defaultValue={api.getBaseUrl()} />
            </div>
          </div>
          <br />
          <Btn onClick={() => { const el = document.getElementById('apiBaseInput') as HTMLInputElement; if (el) api.setBaseUrl(el.value.trim()); onCheckApi(); toast('API checked'); }}>Save & Check</Btn>
        </div>
        <div className="card">
          <h3>API Endpoints</h3>
          <div className="denseList" style={{ marginTop: 10 }}>
            {endpoints.map(e => <div key={e} className="row"><b>{e}</b><span className={`tag ${apiConnected ? 'good' : 'warn'}`}>{apiConnected ? 'ok' : 'required'}</span></div>)}
          </div>
        </div>
      </div>
    </div>
  );

  return <div className="empty">Page "{page}" not found.</div>;
}
