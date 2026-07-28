import { useState, type ReactNode } from 'react';
import { nav } from '../data/dashData';

interface LayoutProps {
  currentPage: string;
  onNavigate: (page: string) => void;
  apiConnected: boolean;
  apiLoading: boolean;
  onOpenApi: () => void;
  onOpenGuild: () => void;
  children: ReactNode;
  darkMode: boolean;
  onToggleTheme: () => void;
  apiData?: any;
}

const groupLabels: Record<string, string> = { main: 'Console', setup: 'Modules', builders: 'Builders', system: 'System' };

export default function Layout({ currentPage, onNavigate, apiConnected, apiLoading, onOpenApi, children, darkMode, onToggleTheme, apiData }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState('');

  // Guild bilgisi API'den
  const guildName = apiData?.overview?.guildName || 'Server';
  const guildInitials = guildName.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase();

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const q = search.toLowerCase();
      const found = nav.find(n => n[2].toLowerCase().includes(q) || n[1].includes(q));
      if (found) { onNavigate(found[1]); setSearch(''); }
    }
  };

  let lastGroup = '';

  return (
    <div className="appShell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brandMark">P</div>
          <div><b>ProBotum</b><span>Enterprise Console</span></div>
        </div>

        {/* Guild card — gerçek sunucu bilgisi */}
        <div className="guildCard">
          <span className="guildIcon">{guildInitials}</span>
          <span>
            <b>{guildName}</b>
            <small>{apiConnected ? '✅ API connected' : '⚠️ API offline'}</small>
          </span>
        </div>

        <nav className="nav">
          {nav.map(item => {
            const [group, id, label, icon] = item;
            const showGroup = group !== lastGroup;
            lastGroup = group;
            return (
              <div key={id}>
                {showGroup && <div className="navGroup">{groupLabels[group]}</div>}
                <button className={currentPage === id ? 'active' : ''} onClick={() => { onNavigate(id); setSidebarOpen(false); }}>
                  <i>{icon}</i>{label}
                </button>
              </div>
            );
          })}
        </nav>

        <div className="sideStatus">
          <div><span>Runtime</span><b>{apiConnected ? 'Live API' : 'Simulation'}</b></div>
          <div><span>Backend</span><b>{apiLoading ? 'Checking' : apiConnected ? 'Online' : 'Offline'}</b></div>
        </div>
      </aside>

      {sidebarOpen && <div className="overlay show" onClick={() => setSidebarOpen(false)} />}

      <main className="workspace">
        <header className="topbar">
          <button className="mobileBtn" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
          <div className="pageTitle">{nav.find(n => n[1] === currentPage)?.[2] || currentPage}</div>
          <div className="globalSearch">
            <span>⌘</span>
            <input placeholder="Search modules, settings, commands..." value={search} onChange={e => setSearch(e.target.value)} onKeyDown={handleSearch} />
          </div>
          <button className="topBtn" onClick={onOpenApi}>API</button>
          <button className="topBtn" onClick={onToggleTheme}>{darkMode ? '☀️' : '🌙'}</button>
          <button className="topBtn ownerBadge" onClick={() => { localStorage.removeItem('pb_auth_ok'); localStorage.removeItem('pb_auth_user'); localStorage.removeItem('pb_auth_token'); location.reload(); }}>
            {localStorage.getItem('pb_auth_user') || 'Account'}
          </button>
        </header>
        <section className="content">{children}</section>
      </main>
    </div>
  );
}
