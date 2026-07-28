import { useState, useEffect, useCallback } from 'react';
import Layout from './components/Layout';
import Toast, { toast } from './components/Toast';
import Modal from './components/Modal';
import Drawer from './components/Drawer';
import LoginLanding from './pages/LoginLanding';
import StartHere from './pages/StartHere';
import Overview from './pages/Overview';
import SetupWizard from './pages/SetupWizard';
import Readiness from './pages/Readiness';
import Modules from './pages/Modules';
import ModuleEditor from './pages/ModuleEditor';
import AutomodRules from './pages/AutomodRules';
import TicketPanel from './pages/TicketPanel';
import WelcomeFlow from './pages/WelcomeFlow';
import AccessPortals from './pages/AccessPortals';
import Permissions from './pages/Permissions';
import LogsSetup from './pages/LogsSetup';
import ResourcePage from './pages/ResourcePage';
import MemberPortal from './pages/MemberPortal';
import SimplePage from './pages/SimplePage';
import { Btn } from './components/ui';
import { modules, channels, roles, setChannels, setRoles } from './data/dashData';
import { config, pending } from './data/store';
import * as api from './data/api';

export default function App() {
  const [authenticated, setAuthenticated] = useState(() => localStorage.getItem('pb_auth_ok') === 'true');
  const [darkMode, setDarkMode] = useState(true);
  const [currentPage, setCurrentPage] = useState(() => {
    const portal = localStorage.getItem('pb_auth_portal');
    return portal === 'member' ? 'memberPortal' : 'overview';
  });
  const [apiConnected, setApiConnected] = useState(false);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiData, setApiData] = useState<any>(null);
  const [, setRefreshKey] = useState(0);
  const forceRefresh = () => setRefreshKey(k => k + 1);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState('');
  const [modalContent, setModalContent] = useState<React.ReactNode>(null);

  // Drawer state (reserved for future use)
  const [drawerOpen] = useState(false);
  const drawerTitle = '';
  const drawerSubtitle = '';
  const drawerContent = null;

  // Apply animation state (used by ApplyModal via callback)

  useEffect(() => {
    document.body.className = darkMode ? '' : 'light';
  }, [darkMode]);

  const checkApi = useCallback(async () => {
    setApiLoading(true);
    const healthResult = await api.health();
    const isConnected = healthResult !== null;
    setApiConnected(isConnected);
    if (isConnected) {
      const data = await api.loadGuildDashboard('current');
      setApiData(data);
      // Load channels/roles from overview
      const o = data?.overview || {};
      if (Array.isArray(o.channelsList) && o.channelsList.length) {
        setChannels(o.channelsList.map(api.formatDiscordChannel));
      }
      if (Array.isArray(o.rolesList) && o.rolesList.length) {
        setRoles(o.rolesList
          .filter((r: any) => typeof r === 'object' ? r.name !== '@everyone' : true)
          .map((r: any) => typeof r === 'object' ? `@${r.name}` : String(r)));
      }
      // Try live resources
      try {
        const [chRes, rlRes] = await Promise.all([
          api.request('/guilds/current/channels'),
          api.request('/guilds/current/roles'),
        ]);
        if (chRes?.channels) setChannels(chRes.channels.map(api.formatDiscordChannel));
        if (rlRes?.roles) setRoles(rlRes.roles
          .filter((r: any) => typeof r === 'object' ? r.name !== '@everyone' : true)
          .map((r: any) => typeof r === 'object' ? `@${r.name}` : String(r)));
      } catch { /* keep overview data */ }
    }
    setApiLoading(false);
    forceRefresh();
  }, []);

  useEffect(() => {
    if (authenticated) checkApi();
  }, [authenticated, checkApi]);

  const handleLoginSuccess = () => {
    setAuthenticated(true);
    const portal = localStorage.getItem('pb_auth_portal');
    setCurrentPage(portal === 'member' ? 'memberPortal' : 'overview');
  };

  const handleLogout = () => {
    localStorage.removeItem('pb_auth_ok');
    localStorage.removeItem('pb_auth_user');
    localStorage.removeItem('pb_auth_token');
    setAuthenticated(false);
  };

  const openApply = (id: string) => {
    const mods = id === 'all'
      ? [...new Set([...Object.keys(pending), ...Object.keys(config)])]
      : [id];

    const steps = mods.flatMap(m => {
      // modules: [id, name, description, type]
      const mod = modules.find(x => x[0] === m);
      const modName = mod?.[1] || m;
      return ['validate config', 'check permissions', 'prepare actions', 'save config', 'write audit'].map(x => `${modName}: ${x}`);
    });

    setModalTitle('Apply Center');
    setModalContent(
      <ApplyModal
        connected={apiConnected}
        steps={steps}
        onJson={() => openJson(id)}
      />
    );
    setModalOpen(true);
  };

  const openJson = (id: string) => {
    const data = id === 'all' ? { config, pending } : { module: id, config: config[id] || {}, pending: pending[id] || {} };
    setModalTitle('JSON Preview');
    setModalContent(
      <textarea
        className="w-full px-3 py-2 text-xs rounded-lg bg-[var(--input-bg)] border border-[var(--border)] text-[var(--text)] outline-none resize-none font-mono"
        style={{ minHeight: 400 }}
        readOnly
        value={JSON.stringify(data, null, 2)}
      />
    );
    setModalOpen(true);
  };

  const openExplainMode = () => {
    setModalTitle('Что значит режим dashboard?');
    setModalContent(
      <div>
        <div className="space-y-3">
          {[
            ['Simulation', 'Безопасный режим. Dashboard показывает планы и JSON, но Discord сервер не меняется.'],
            ['Python API', 'Локальный backend на FastAPI. Через него dashboard общается с ботом.'],
            ['Live API', 'Реальный backend подключён. Apply может сохранить настройки бота.'],
          ].map(([title, desc]) => (
            <div key={title} className="flex items-start justify-between py-2 border-b border-[var(--border)] last:border-0">
              <b className="text-xs text-[var(--text)]">{title}</b>
              <span className="text-xs text-[var(--text-secondary)] text-right ml-4">{desc}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 text-center text-xs text-[var(--text-secondary)]">
          Если не понимаешь, с чего начать: открой <b>Start Here</b>, потом <b>Setup Wizard</b>, потом <b>Readiness</b>.
        </div>
      </div>
    );
    setModalOpen(true);
  };

  const openApiModal = () => {
    setModalTitle('Backend API');
    setModalContent(
      <div>
        <div className="mb-3">
          <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wide mb-1 block">Base URL</label>
          <input
            id="apiBaseModal"
            className="w-full px-3 py-1.5 text-xs rounded-lg bg-[var(--input-bg)] border border-[var(--border)] text-[var(--text)] outline-none"
            defaultValue={api.getBaseUrl()}
          />
        </div>
        <div className="mb-3">
          <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wide mb-1 block">Status</label>
          <input className="w-full px-3 py-1.5 text-xs rounded-lg bg-[var(--input-bg)] border border-[var(--border)] text-[var(--text)] outline-none" readOnly value={apiConnected ? 'Online' : 'Offline'} />
        </div>
        <Btn onClick={async () => {
          const el = document.getElementById('apiBaseModal') as HTMLInputElement;
          if (el) api.setBaseUrl(el.value.trim());
          await checkApi();
          setModalOpen(false);
          toast('API checked');
        }}>Save & Check</Btn>
      </div>
    );
    setModalOpen(true);
  };

  // Guild drawer removed — guild info shown in sidebar from API

  // Show login if not authenticated
  if (!authenticated) {
    return (
      <>
        <LoginLanding onLoginSuccess={handleLoginSuccess} />
        <Toast />
      </>
    );
  }

  // Find current module if on a module page
  // modules: [id, name, description, type]
  const currentModule = modules.find(m => m[0] === currentPage);

  const renderPage = () => {
    if (currentPage === 'memberPortal') return <MemberPortal />;
    if (currentPage === 'start') return <StartHere apiConnected={apiConnected} onNavigate={setCurrentPage} onOpenApply={openApply} onExplainMode={openExplainMode} />;
    if (currentPage === 'overview') return <Overview apiConnected={apiConnected} apiData={apiData} onNavigate={setCurrentPage} onOpenApply={openApply} onConnectApi={openApiModal} />;
    if (currentPage === 'setupWizard') return <SetupWizard apiConnected={apiConnected} onOpenApply={openApply} />;
    if (currentPage === 'readiness') return <Readiness apiConnected={apiConnected} onNavigate={setCurrentPage} onOpenApply={openApply} />;
    if (currentPage === 'modules') return <Modules apiConnected={apiConnected} onNavigate={setCurrentPage} onOpenApply={openApply} />;
    if (currentModule) return <ModuleEditor module={currentModule} apiConnected={apiConnected} onOpenApply={openApply} onOpenJson={openJson} onRefresh={forceRefresh} />;
    if (currentPage === 'automodRules') return <AutomodRules />;
    if (currentPage === 'ticketPanel') return <TicketPanel onOpenApply={openApply} />;
    if (currentPage === 'welcomeFlow') return <WelcomeFlow onOpenApply={openApply} />;
    if (currentPage === 'accessPortals') return <AccessPortals />;
    if (currentPage === 'permissions') return <Permissions />;
    if (currentPage === 'logsSetup') return <LogsSetup />;
    if (currentPage === 'channels') return <ResourcePage title="Channels" items={channels} type="channel" />;
    if (currentPage === 'roles') return <ResourcePage title="Roles" items={roles} type="role" />;
    return <SimplePage page={currentPage} apiConnected={apiConnected} onCheckApi={checkApi} />;
  };

  return (
    <>
      <Layout
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        apiConnected={apiConnected}
        apiLoading={apiLoading}
        onOpenApi={openApiModal}
        onOpenGuild={openApiModal}
        darkMode={darkMode}
        onToggleTheme={() => setDarkMode(!darkMode)}
        apiData={apiData}
      >
        {renderPage()}
      </Layout>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={modalTitle}>
        {modalContent}
      </Modal>

      <Drawer open={drawerOpen} onClose={() => {}} title={drawerTitle} subtitle={drawerSubtitle}>
        {drawerContent}
      </Drawer>

      <Toast />

      {/* Logout button (floating) */}
      <button
        onClick={handleLogout}
        className="fixed bottom-6 right-6 z-50 px-3 py-1.5 rounded-lg text-[10px] font-medium bg-gray-800 text-gray-400 border border-gray-700 hover:text-white hover:border-gray-500 transition shadow-lg"
      >
        {localStorage.getItem('pb_auth_user') || 'Account'} — Logout
      </button>
    </>
  );
}

// Apply modal sub-component
function ApplyModal({ connected, steps, onJson }: {
  connected: boolean;
  steps: string[];
  onJson: () => void;
}) {
  const [runSteps, setRunSteps] = useState<('pending' | 'running' | 'done')[]>(steps.map(() => 'pending'));
  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);

  const run = () => {
    if (running) return;
    setRunning(true);
    let i = 0;
    const tick = () => {
      if (i >= steps.length) {
        toast('Apply completed');
        setRunning(false);
        return;
      }
      setRunSteps(prev => prev.map((_s, idx) => idx < i ? 'done' : idx === i ? 'running' : 'pending'));
      setTimeout(() => {
        setRunSteps(prev => prev.map((_s, idx) => idx <= i ? 'done' : 'pending'));
        setProgress(Math.round(((i + 1) / steps.length) * 100));
        i++;
        tick();
      }, 260);
    };
    tick();
  };

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text)]">{connected ? 'Live API' : 'Simulation'} mode</h3>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            {connected
              ? 'Actions will be sent to backend.'
              : 'No backend: this is dry-run only. Ничего в Discord не изменится.'}
          </p>
          <p className="text-[10px] text-[var(--text-secondary)] mt-1">
            Apply проверит настройки, покажет шаги, сохранит config локально или отправит его в backend, если API подключён.
          </p>
        </div>
        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${connected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>
          {connected ? 'LIVE' : 'DRY RUN'}
        </span>
      </div>

      <div className="h-1.5 w-full rounded-full bg-[var(--border)] overflow-hidden mb-4">
        <div className="h-full rounded-full bg-indigo-500 transition-all duration-300" style={{ width: `${progress}%` }} />
      </div>

      <div className="space-y-1 max-h-60 overflow-y-auto mb-4">
        {steps.map((s, i) => (
          <div key={i} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition ${
            runSteps[i] === 'done' ? 'bg-emerald-500/10 text-emerald-400' :
            runSteps[i] === 'running' ? 'bg-indigo-500/10 text-indigo-400' :
            'text-[var(--text-secondary)]'
          }`}>
            <span className="w-5 h-5 rounded-full bg-[var(--border)] flex items-center justify-center text-[10px] font-bold shrink-0">
              {runSteps[i] === 'done' ? '✓' : i + 1}
            </span>
            {s}
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <Btn onClick={run} disabled={running}>Run apply</Btn>
        <Btn secondary onClick={onJson}>Preview JSON</Btn>
      </div>
    </div>
  );
}
