import { useState, useRef, useCallback } from 'react';
import { toast } from '../components/Toast';
import * as api from '../data/api';

interface Props { onLoginSuccess: () => void; }
type LoginStep = 'idle' | 'find' | 'code';
const KNOWN_USERS = ['артур', 'artur', 'arthur'];
function delay(ms: number) { return new Promise(r => setTimeout(r, ms)); }

const NAV = [
  { icon: '🏆', label: 'Rank', desc: 'XP, leaderboard, награды за уровни', color: '#f5b544' },
  { icon: '🎫', label: 'Tickets', desc: 'Открой обращение, отслеживай статус', color: '#60a5fa' },
  { icon: '🎭', label: 'Roles', desc: 'Уведомления, игры, цвета', color: '#a78bfa' },
  { icon: '🎁', label: 'Events', desc: 'Giveaways, конкурсы, активности', color: '#37d99e' },
  { icon: '💰', label: 'Economy', desc: 'Баланс, магазин, daily rewards', color: '#22d3ee' },
  { icon: '📜', label: 'Rules', desc: 'Правила, onboarding, FAQ', color: '#fb7185' },
];

const FEATURES = [
  { icon: '🏆', title: 'Rank & XP System', desc: 'Зарабатывай XP за сообщения и голос. Получай роли за уровни, соревнуйся в leaderboard и следи за прогрессом в реальном времени.', stat: 'Level 24', statSub: '68% до награды' },
  { icon: '🎫', title: 'Ticket System', desc: 'Открывай тикеты в один клик — поддержка, репорт, предложение. Staff получает уведомление, ты видишь статус и историю.', stat: '2 тикета', statSub: 'в истории' },
  { icon: '🎭', title: 'Role Selection', desc: 'Выбирай роли без команд — уведомления, интересы, игры, цвета. Меняй в любой момент через красивое меню.', stat: '5 ролей', statSub: 'выбрано' },
  { icon: '🎁', title: 'Giveaways & Events', desc: 'Участвуй в розыгрышах, получай бонусные шансы за активность, следи за результатами и условиями.', stat: '3 active', statSub: 'события' },
  { icon: '💰', title: 'Economy & Shop', desc: 'Зарабатывай валюту сервера, покупай кастомные роли, бейджи и эксклюзивный контент в магазине.', stat: '12,400', statSub: 'монет' },
  { icon: '👤', title: 'Profile & History', desc: 'Вся твоя активность — предупреждения, участие в ивентах, голосовое время и текстовая статистика.', stat: '142 дня', statSub: 'на сервере' },
];

// Stats будут загружены из API, пока пустые

export default function LoginLanding({ onLoginSuccess }: Props) {
  const [loginOpen, setLoginOpen] = useState(false);
  const [hoveredNav, setHoveredNav] = useState<string | null>(null);
  const [step, setStep] = useState<LoginStep>('idle');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [devCode, setDevCode] = useState('');
  const [foundUser, setFoundUser] = useState('');
  const [processing, setProcessing] = useState(false);
  const [, setPipelineStage] = useState(0);
  const [pipelineStates, setPipelineStates] = useState<string[]>(Array(6).fill(''));
  const [suggestions, setSuggestions] = useState<{ id: string; name: string }[]>([]);
  const [selectedMember, setSelectedMember] = useState<{ id: string; name: string } | null>(null);
  const [loaderState, setLoaderState] = useState<'' | 'checking' | 'done'>('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const openLogin = () => { setLoginOpen(true); setStep('find'); setError(''); setCode(''); setDevCode(''); setFoundUser(''); setPipelineStage(0); setPipelineStates(Array(6).fill('')); setSelectedMember(null); setLoaderState(''); setTimeout(() => nameRef.current?.focus(), 100); };
  const setProgressState = (idx: number, state: string) => { setPipelineStates(prev => prev.map((s, i) => { if (i < idx - 1) return 'done'; if (i === idx - 1 && state) return state; return s; })); };
  const onNameInput = useCallback((value: string) => { setName(value); setSelectedMember(null); if (searchTimer.current) clearTimeout(searchTimer.current); if (value.trim().length < 2) { setSuggestions([]); return; } searchTimer.current = setTimeout(() => { const q = value.toLowerCase().replace(/^@/, ''); setSuggestions(['артур', 'Arthur', 'artur'].map((u, i) => ({ id: `local_${i}`, name: u })).filter(u => u.name.toLowerCase().includes(q)).slice(0, 6)); }, 220); }, []);

  const sendCode = async () => {
    const identifier = selectedMember?.name || name.trim(); const normalized = identifier.toLowerCase().replace(/^@/, '');
    if (!normalized) { setError('Введите Discord username или ID'); return; }
    setProcessing(true); setError(''); setPipelineStates(Array(6).fill('')); setPipelineStage(1); setLoaderState('checking'); setFoundUser(''); setDevCode('');
    try {
      setProgressState(2, 'loading'); const res = await api.request('/auth/request-code', { method: 'POST', body: JSON.stringify({ identifier, guildId: 'current' }) });
      setProgressState(2, 'done'); setPipelineStage(2); await delay(550); setProgressState(3, 'loading'); await delay(650); setProgressState(3, 'done'); setPipelineStage(3); setProgressState(4, 'loading'); await delay(650); setProgressState(4, 'done'); setPipelineStage(4); setProgressState(5, 'loading'); await delay(650); setProgressState(5, 'done'); setPipelineStage(5);
      const display = res.username ? `@${res.username.replace(/^@/, '')}` : `@${normalized}`; setFoundUser(display);
      localStorage.setItem('pb_pending_login_user', display); localStorage.setItem('pb_pending_login_user_id', res.userId || ''); localStorage.setItem('pb_pending_login_portal', res.portal || 'member');
      setProgressState(6, 'loading'); await delay(850); setProgressState(6, 'done'); setPipelineStage(6);
      if (res.devCode) { setDevCode(`Dev: ${res.devCode}`); localStorage.setItem('pb_pending_login_code', res.devCode); } else { setDevCode('Код отправлен в Discord DM.'); localStorage.removeItem('pb_pending_login_code'); }
      setProcessing(false); setLoaderState('done'); setTimeout(() => setStep('code'), 900);
    } catch {
      setProgressState(2, 'loading'); await delay(650); setProgressState(2, 'done'); setPipelineStage(2); setProgressState(3, 'loading'); await delay(650);
      if (!KNOWN_USERS.includes(normalized) && !/^\d{15,22}$/.test(normalized)) { setLoaderState(''); setProgressState(3, 'fail'); setProcessing(false); setError('Пользователь не найден'); return; }
      setProgressState(3, 'done'); setPipelineStage(3); setProgressState(4, 'loading'); await delay(550); setProgressState(4, 'done'); setPipelineStage(4); setProgressState(5, 'loading'); await delay(550); setProgressState(5, 'done'); setPipelineStage(5);
      const display = selectedMember?.name || name.replace(/^@/, ''); setFoundUser(display);
      setProgressState(6, 'loading'); await delay(850); setProgressState(6, 'done'); setPipelineStage(6);
      const gc = String(Math.floor(100000 + Math.random() * 900000)); localStorage.setItem('pb_pending_login_user', display); localStorage.setItem('pb_pending_login_user_id', 'dev-user'); localStorage.setItem('pb_pending_login_portal', 'member'); localStorage.setItem('pb_pending_login_code', gc);
      setDevCode(`Dev: ${gc} (offline)`); setProcessing(false); setLoaderState('done'); setTimeout(() => setStep('code'), 900);
    }
  };

  const confirmCode = async () => {
    const expected = localStorage.getItem('pb_pending_login_code'); const user = localStorage.getItem('pb_pending_login_user') || '@user'; const userId = localStorage.getItem('pb_pending_login_user_id') || '';
    if (!code.trim()) { setError('Введите код из DM'); return; }
    try {
      if (userId && userId !== 'dev-user') { const res = await api.request('/auth/verify-code', { method: 'POST', body: JSON.stringify({ guildId: 'current', userId, username: user, code: code.trim() }) }); localStorage.setItem('pb_auth_token', res.token); api.setToken(res.token); localStorage.setItem('pb_auth_user', `@${String(res.user?.username || user).replace(/^@/, '')}`); localStorage.setItem('pb_auth_portal', res.user?.portal || 'member'); }
      else { if (code.trim() !== expected) { setError('Неверный код'); return; } localStorage.setItem('pb_auth_user', user); localStorage.setItem('pb_auth_portal', localStorage.getItem('pb_pending_login_portal') || 'member'); }
    } catch { if (expected && code.trim() === expected) { localStorage.setItem('pb_auth_user', user); localStorage.setItem('pb_auth_portal', localStorage.getItem('pb_pending_login_portal') || 'member'); } else { setError('Неверный или просроченный код'); return; } }
    localStorage.setItem('pb_auth_ok', 'true'); localStorage.removeItem('pb_pending_login_code'); toast(`Добро пожаловать, ${localStorage.getItem('pb_auth_user') || user}`); onLoginSuccess();
  };

  return (
    <div className="welcomeLanding">
      <div className="welcomeGrid" />
      <div className="welcomeGlow purple" />
      <div className="welcomeGlow cyan" />

      {/* ═══════════ TOP NAV ═══════════ */}
      <header className="welcomeTop">
        <div className="welcomeBrand">
          <div className="welcomeLogo">P</div>
          <div><b>ProBotum</b><span>Community Portal</span></div>
        </div>

        <nav className="welcomeNav">
          {NAV.map(item => (
            <div key={item.label} style={{ position: 'relative' }} onMouseEnter={() => setHoveredNav(item.label)} onMouseLeave={() => setHoveredNav(null)}>
              <button className={`welcomeNavItem ${hoveredNav === item.label ? 'active' : ''}`} onClick={openLogin}>
                <span>{item.icon}</span>{item.label}
              </button>
              {hoveredNav === item.label && (
                <div style={{
                  position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)', marginTop: 8, width: 220,
                  background: 'linear-gradient(180deg, rgba(13,18,28,.98), rgba(7,10,16,.98))', border: '1px solid rgba(124,92,255,.25)',
                  borderRadius: 16, padding: 14, boxShadow: '0 20px 60px rgba(0,0,0,.5)', zIndex: 50, animation: 'contentFade .15s ease both',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <span style={{ fontSize: 24 }}>{item.icon}</span>
                    <b style={{ fontSize: 15 }}>{item.label}</b>
                  </div>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>{item.desc}</p>
                  <button className="btn mini" style={{ marginTop: 10, width: '100%' }} onClick={openLogin}>Войти →</button>
                </div>
              )}
            </div>
          ))}
        </nav>

        <button className="welcomeLoginBtn" onClick={openLogin}>🔐 Войти</button>
      </header>

      {/* ═══════════ HERO ═══════════ */}
      <main className="welcomeHero">
        <section className="welcomeCopy">
          <span className="welcomeBadge">✨ COMMUNITY PORTAL</span>
          <h1>Всё для участника. В одном месте.</h1>
          <p>Ранг, тикеты, роли, розыгрыши, экономика, профиль — красивый портал для твоего Discord сервера без хаоса в каналах.</p>
          <div className="welcomeActions">
            <button className="welcomePrimary" onClick={openLogin}>🚀 Войти в портал</button>
            <button className="welcomeSecondary" onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}>📖 Возможности</button>
          </div>

          {/* Stats bar — bilgi yok ise gösterme */}
        </section>

        {/* Preview window */}
        <section className="welcomePreview">
          <div className="welcomeWindow">
            <div className="welcomeWindowTop">
              <span className="welcomeWindowDot" style={{ background: '#7c5cff' }} />
              <span className="welcomeWindowDot" style={{ background: '#22d3ee' }} />
              <span className="welcomeWindowDot" style={{ background: '#a78bfa' }} />
              <b>member.portal</b>
            </div>
            <div className="welcomeWindowBody">
              <aside className="welcomeSidebar">
                <div className="welcomeAvatar">A</div>
                <b>@артур</b><span>Server Member</span>
                <div className="welcomeLevel"><small>Level 24</small><div><i style={{ width: '68%' }} /></div></div>
              </aside>
              <main className="welcomeMain">
                <div className="welcomeCard"><div><span>Welcome back</span><h2>Community Hub</h2></div><b>68%</b></div>
                <div className="welcomeTiles">
                  {[{ i: '🏆', t: 'My Rank', s: 'XP, level, leaderboard' }, { i: '🎫', t: 'Open Ticket', s: 'Support & reports' }, { i: '🎭', t: 'Role Select', s: 'Games, colors' }, { i: '🎁', t: 'Giveaways', s: 'Active events' }].map(c => (
                    <div key={c.t} className="welcomeTile"><span>{c.i}</span><b>{c.t}</b><small>{c.s}</small></div>
                  ))}
                </div>
                <div className="welcomeFeed"><div><b>Rules accepted</b><span>Verified ✓</span></div><div><b>Next reward</b><span>Level 25 · VIP</span></div></div>
              </main>
            </div>
          </div>
          <div className="welcomeFloat" style={{ left: -28, top: 92 }}><b>🏆 Rank #12</b><span>this week</span></div>
          <div className="welcomeFloat" style={{ right: -26, top: 230, animationDelay: '-1.4s' }}><b>🎫 2 tickets</b><span>resolved</span></div>
          <div className="welcomeFloat" style={{ left: 60, bottom: -18, animationDelay: '-2.6s' }}><b>🎭 5 roles</b><span>selected</span></div>
        </section>
      </main>

      {/* ═══════════ FEATURE CARDS ═══════════ */}
      <section id="features" style={{ position: 'relative', zIndex: 2, maxWidth: 1380, margin: '60px auto 0', padding: '0 30px' }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <span className="welcomeBadge">🎯 ВОЗМОЖНОСТИ ПОРТАЛА</span>
          <h2 style={{ fontSize: 'clamp(28px, 4vw, 44px)', letterSpacing: '-.06em', margin: '16px 0 10px' }}>Всё что нужно участнику</h2>
          <p style={{ color: '#94a3b8', fontSize: 16, maxWidth: 600, margin: '0 auto', lineHeight: 1.6 }}>Каждая функция доступна через красивый интерфейс — без команд, без поиска каналов.</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
          {FEATURES.map(f => (
            <div key={f.title} className="card" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 14, cursor: 'pointer' }} onClick={openLogin}>
              <div>
                <div style={{ fontSize: 28, marginBottom: 10 }}>{f.icon}</div>
                <h3 style={{ margin: '0 0 8px', fontSize: 17 }}>{f.title}</h3>
                <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.5, fontSize: 13 }}>{f.desc}</p>
              </div>
              <div style={{ textAlign: 'right', paddingTop: 8 }}>
                <b style={{ display: 'block', fontSize: 22, letterSpacing: '-.04em', color: '#c7d2fe' }}>{f.stat}</b>
                <span style={{ color: '#64748b', fontSize: 11, fontWeight: 800 }}>{f.statSub}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ═══════════ BOTTOM STRIP ═══════════ */}
      <footer className="welcomeBottom" style={{ marginTop: 40 }}>
        {NAV.map(n => (
          <div key={n.label} className="welcomeFeature" onClick={openLogin} style={{ cursor: 'pointer' }}>
            <b>{n.icon} {n.label}</b>
            <span>{n.desc}</span>
          </div>
        ))}
      </footer>

      {/* ═══════════ LOGIN POPUP ═══════════ */}
      {loginOpen && (
        <div className="loginOverlay" onClick={e => { if (e.target === e.currentTarget) setLoginOpen(false); }}>
          <div className="loginBox" onClick={e => e.stopPropagation()}>
            <button className="loginClose" onClick={() => setLoginOpen(false)}>×</button>
            <div className="loginProgress">
              {pipelineStates.map((state, i) => <div key={i} className={`loginProgressStep ${state || (i === 0 ? 'done' : '')}`} />)}
            </div>

            {step === 'find' && (
              <div style={{ animation: 'contentFade .22s ease both' }}>
                <div className="loginHead">
                  <div className={`loaderIcon ${loaderState}`} />
                  <div><h2>Введите ник или ID</h2><p>Проверим сервер и найдём пользователя.</p></div>
                </div>
                <div className="loginField">
                  <label>Discord username veya ID</label>
                  <input ref={nameRef} placeholder="@username veya 123456789..." value={name} onChange={e => onNameInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') sendCode(); }} />
                </div>
                {suggestions.length > 0 && !selectedMember && (
                  <div className="suggestBox">{suggestions.map(s => (
                    <button key={s.id} className="suggestItem" onClick={() => { setSelectedMember(s); setName(s.name); setSuggestions([]); }}>
                      <span className="suggestAvatar">{s.name.charAt(0).toUpperCase()}</span><b>{s.name}</b>
                    </button>
                  ))}</div>
                )}
                {foundUser && <div className="foundOk">Найден: <b>{foundUser}</b></div>}
                {devCode && <div className="devHint">{devCode}</div>}
                <button className="loginSubmitBtn" onClick={sendCode} disabled={processing}>{processing ? 'Проверяем...' : '🔍 Начать проверку'}</button>
              </div>
            )}

            {step === 'code' && (
              <div style={{ animation: 'contentFade .22s ease both' }}>
                <div className="loginHead">
                  <div className="loaderIcon done" />
                  <div><h2>Код отправлен</h2><p>Введите 6-значный код из Discord DM.</p></div>
                </div>
                {foundUser && <div className="foundOk" style={{ marginBottom: 12 }}>Аккаунт: <b>{foundUser}</b></div>}
                {devCode && <div className="devHint" style={{ marginBottom: 12 }}>{devCode}</div>}
                <div className="loginField">
                  <label>Код из DM</label>
                  <input placeholder="000000" inputMode="numeric" maxLength={6} value={code} onChange={e => setCode(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') confirmCode(); }} style={{ fontFamily: 'ui-monospace, monospace', letterSpacing: '.2em', textAlign: 'center' }} />
                </div>
                <button className="loginSubmitBtn" onClick={confirmCode}>✅ Подтвердить и войти</button>
                <button className="loginBackBtn" onClick={() => { setStep('find'); setPipelineStates(Array(6).fill('')); setLoaderState(''); }}>← изменить пользователя</button>
              </div>
            )}

            {error && <div className="loginError">{error}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
