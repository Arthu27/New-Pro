import { ModeBanner, SectionHead, Btn, Row, Pill } from '../components/ui';

interface Props { apiConnected: boolean; onNavigate: (p: string) => void; onOpenApply: (id: string) => void; onExplainMode: () => void; }

export default function StartHere({ apiConnected, onNavigate, onOpenApply, onExplainMode }: Props) {
  return (
    <div>
      <ModeBanner connected={apiConnected} />
      <div className="startHero card"><div><Pill>START HERE</Pill><h1>Сначала разберёмся, что здесь происходит</h1><p>Это dashboard для настройки Discord бота. Пока backend API не подключён, он работает в безопасном режиме: показывает формы, планы и JSON, но не меняет сервер.</p></div></div>
      <div className="grid three" style={{ marginTop: 14 }}>
        {[
          { n: 1, t: 'Понять режим', d: 'Simulation значит: можно нажимать кнопки, но Discord сервер не изменится.', btn: 'Объяснить режим', act: () => onExplainMode(), sec: true },
          { n: 2, t: 'Подключить Python API', d: 'Запусти backend через START.bat или run_api.bat, затем dashboard получит реальные данные.', btn: 'API Settings', act: () => onNavigate('settings') },
          { n: 3, t: 'Пройти Wizard', d: 'Wizard создаёт понятный план: какие каналы, роли и модули нужны.', btn: 'Открыть Wizard', act: () => onNavigate('setupWizard') },
          { n: 4, t: 'Проверить Readiness', d: 'Readiness показывает, какие модули готовы, а где не хватает настроек.', btn: 'Проверить', act: () => onNavigate('readiness') },
          { n: 5, t: 'Настроить модуль', d: 'Открой AutoMod/Tickets/Welcome и заполни вкладки по порядку.', btn: 'AutoMod', act: () => onNavigate('automod') },
          { n: 6, t: 'Нажать Apply', d: 'Apply покажет, что будет сделано. Без API это безопасная симуляция.', btn: 'Посмотреть Apply', act: () => onOpenApply('all'), sec: true },
        ].map(s => (
          <div key={s.n} className="card stepCard">
            <span>{s.n}</span><h3>{s.t}</h3><p>{s.d}</p>
            <Btn onClick={s.act} secondary={s.sec}>{s.btn}</Btn>
          </div>
        ))}
      </div>
      <br />
      <div className="grid two">
        <div className="card"><SectionHead title="Простая карта dashboard" sub="Куда нажимать и зачем." />
          <div className="denseList">
            <Row label="Setup Wizard" value="создаёт первый план настройки" />
            <Row label="Readiness" value="показывает, что не настроено" />
            <Row label="Modules" value="список всех функций бота" />
            <Row label="AutoMod / Tickets / Welcome" value="конкретные настройки модулей" />
            <Row label="Settings → API" value="подключение backend" />
          </div>
        </div>
        <div className="card"><SectionHead title="Что НЕ происходит без backend" sub="Чтобы не было путаницы." />
          <div className="denseList">
            <Row label="Не создаются каналы" tag={{ text: 'dry-run', variant: 'warn' }} />
            <Row label="Не создаются роли" tag={{ text: 'dry-run', variant: 'warn' }} />
            <Row label="Не меняется Discord сервер" tag={{ text: 'safe', variant: 'warn' }} />
            <Row label="Не показываются fake live данные" tag={{ text: 'honest', variant: 'good' }} />
          </div>
        </div>
      </div>
    </div>
  );
}
