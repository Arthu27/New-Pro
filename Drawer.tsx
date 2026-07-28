import type { ReactNode } from 'react';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export default function Drawer({ open, onClose, title, subtitle, children }: DrawerProps) {
  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-[90]" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-80 z-[91] bg-[var(--card-bg)] border-l border-[var(--border)] shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)] shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">{title}</h2>
            {subtitle && <p className="text-[10px] text-[var(--text-secondary)]">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="text-[var(--text-secondary)] hover:text-[var(--text)] text-lg transition">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {children}
        </div>
      </div>
    </>
  );
}
