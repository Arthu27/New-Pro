import { SectionHead, Btn, Pill, Row } from '../components/ui';
import { toast } from '../components/Toast';

export default function MemberPortal() {
  const user = localStorage.getItem('pb_auth_user') || '@member';
  const rooms = [
    { icon: '🏆', title: 'My Rank', desc: 'XP, уровень, место в leaderboard и следующая награда.', action: 'Rank card', msg: 'Rank sistemi backend bağlantısı gerektirir' },
    { icon: '🎫', title: 'Tickets', desc: 'Открыть обращение, посмотреть историю и статус ответов.', action: 'Open ticket', msg: 'Ticket sistemi yakında aktif olacak' },
    { icon: '🎭', title: 'Role Selection', desc: 'Выбрать роли уведомлений, игр, цветов и интересов.', action: 'Choose roles', msg: 'Rol seçimi Discord bot bağlantısı gerektirir' },
    { icon: '📜', title: 'Server Rules', desc: 'Правила сервера, onboarding и подтверждение ознакомления.', action: 'Read rules', msg: 'Kurallar sayfası yakında' },
    { icon: '🎁', title: 'Giveaways', desc: 'Активные розыгрыши, требования и твои участия.', action: 'View events', msg: 'Çekiliş sistemi geliştiriliyor' },
    { icon: '👤', title: 'My Profile', desc: 'Твоя активность, предупреждения и история на сервере.', action: 'Open profile', msg: 'Profil sayfası yakında' },
    { icon: '💰', title: 'Economy', desc: 'Баланс, daily reward, inventory и магазин сервера.', action: 'Open wallet', msg: 'Ekonomi sistemi geliştiriliyor' },
    { icon: '📣', title: 'Announcements', desc: 'Важные новости сервера и персональные уведомления.', action: 'View news', msg: 'Duyuru sistemi yakında' },
  ];
  return (
    <div>
      <section className="memberPortalHero card">
        <div><Pill>Member Portal</Pill><h1>Добро пожаловать, {user}</h1><p>Это твоя личная панель сервера. Здесь не админка — только полезные комнаты для участника.</p></div>
        <div className="memberHeroStat"><b>Level 24</b><span>68% до следующей награды</span><div><i style={{ width: '68%' }}></i></div></div>
      </section>
      <section className="portalRoomsGrid">
        {rooms.map(r => (
          <article key={r.title} className="card memberRoom">
            <div className="roomIcon">{r.icon}</div><h3>{r.title}</h3><p>{r.desc}</p>
            <Btn secondary onClick={() => toast(r.msg)}>{r.action}</Btn>
          </article>
        ))}
      </section>
      <section className="grid two">
        <div className="card"><SectionHead title="Последняя активность" sub="Будет заполняться из API после подключения логов." /><div className="denseList"><Row label="Rules accepted" tag={{ text: 'verified', variant: 'good' }} /><Row label="Next reward" value="Level 25" /><Row label="Open tickets" value="0" /></div></div>
        <div className="card"><SectionHead title="Быстрые действия" sub="Доступные участнику действия." /><div className="memberQuick"><Btn onClick={() => toast('Ticket sistemi yakında')}>Open ticket</Btn><Btn secondary onClick={() => toast('Rol seçimi yakında')}>Select roles</Btn><Btn secondary onClick={() => toast('Rank sistemi yakında')}>View rank</Btn></div></div>
      </section>
    </div>
  );
}
