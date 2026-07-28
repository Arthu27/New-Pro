import type { ReactNode } from 'react';

export function esc(v: any): string {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c] || c));
}

export function ModeBanner({ connected }: { connected: boolean }) {
  return (
    <div className={`modeBanner ${connected ? 'live' : 'sim'}`}>
      <div>
        <b>Текущий режим: {connected ? 'Live API' : 'Simulation'}</b>
        <span>{connected ? 'Apply может отправлять запросы в backend.' : 'Сейчас dashboard ничего не меняет на Discord сервере. Все действия — только dry-run / preview.'}</span>
      </div>
    </div>
  );
}

export function ExplainBox({ title, text, next }: { title: string; text: string; next?: string }) {
  return (
    <div className="explainBox">
      <b>{title}</b>
      <p>{text}</p>
      {next && <small>Следующий шаг: {next}</small>}
    </div>
  );
}

export function SectionHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="sectionHead">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {right && <div style={{ display: 'flex', gap: 8 }}>{right}</div>}
    </div>
  );
}

export function Tag({ variant, children }: { variant: 'good' | 'warn' | 'bad'; children: ReactNode }) {
  return <span className={`tag ${variant}`}>{children}</span>;
}

export function Pill({ children }: { children: ReactNode }) {
  return <span className="pill">{children}</span>;
}

export function Btn({ children, onClick, secondary, mini, disabled }: { children: ReactNode; onClick?: () => void; secondary?: boolean; mini?: boolean; disabled?: boolean }) {
  return (
    <button className={`btn ${secondary ? 'secondary' : ''} ${mini ? 'mini' : ''}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function Row({ label, value, tag }: { label: string; value?: string; tag?: { text: string; variant: 'good' | 'warn' | 'bad' } }) {
  return (
    <div className="row">
      <b>{label}</b>
      {tag ? <Tag variant={tag.variant}>{tag.text}</Tag> : <span>{value}</span>}
    </div>
  );
}
