import { useCallback, useEffect, useState, type ReactNode } from 'react';

/* ---------- primitives ---------- */

export function Button({
  children, onClick, variant = 'default', size, disabled, type,
}: {
  children: ReactNode; onClick?: () => void; variant?: 'default' | 'primary' | 'danger';
  size?: 'sm' | 'lg'; disabled?: boolean; type?: 'button' | 'submit';
}) {
  const cls = ['btn', variant === 'primary' ? 'btn-primary' : variant === 'danger' ? 'btn-danger' : '',
    size === 'sm' ? 'btn-sm' : size === 'lg' ? 'btn-lg' : ''].join(' ');
  return <button type={type || 'button'} className={cls} onClick={onClick} disabled={disabled}>{children}</button>;
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function Badge({ children, tone }: { children: ReactNode; tone?: 'ok' | 'warn' | 'err' }) {
  return <span className={`badge ${tone ?? ''}`}>{children}</span>;
}

/* ---------- MetricCard ---------- */

export function formatNum(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const n = Math.round(v);
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  return n.toLocaleString();
}

export function MetricCard({
  label, value, delta, note, unavailable,
}: {
  label: string; value?: number | null; delta?: number | null; note?: string; unavailable?: boolean;
}) {
  let deltaEl: ReactNode = null;
  if (unavailable) {
    deltaEl = <div className="metric-note">Not available through Instagram API</div>;
  } else if (delta !== undefined && delta !== null) {
    const cls = Math.abs(delta) < 0.05 ? 'delta-flat' : delta > 0 ? 'delta-up' : 'delta-down';
    const arrow = Math.abs(delta) < 0.05 ? '→' : delta > 0 ? '▲' : '▼';
    deltaEl = <div className={`metric-delta ${cls}`}>{arrow} {Math.abs(delta).toFixed(1)}% vs prev</div>;
  }
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{unavailable ? '—' : formatNum(value)}</div>
      {deltaEl}
      {note && !unavailable && <div className="metric-note">{note}</div>}
    </div>
  );
}

/* ---------- Tabs ---------- */

export function Tabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (t: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t} role="tab" className={`tab ${t === active ? 'active' : ''}`} onClick={() => onChange(t)}>
          {t}
        </button>
      ))}
    </div>
  );
}

/* ---------- DateRangePicker (7 / 30 / 90 days) ---------- */

export function DateRangePicker({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  return (
    <div className="seg" role="group" aria-label="Date range">
      {[7, 30, 90].map((d) => (
        <button key={d} className={value === d ? 'active' : ''} onClick={() => onChange(d)}>
          {d}D
        </button>
      ))}
    </div>
  );
}

/* ---------- Modal ---------- */

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

/* ---------- Toast ---------- */

export interface ToastMsg { id: number; text: string; tone: 'success' | 'error' | '' }

export function Toasts({ toasts }: { toasts: ToastMsg[] }) {
  return (
    <div className="toast-wrap">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>
      ))}
    </div>
  );
}

let toastId = 1;
export function useToasts(): [ToastMsg[], (text: string, tone?: ToastMsg['tone']) => void] {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const push = useCallback((text: string, tone: ToastMsg['tone'] = '') => {
    const id = toastId++;
    setToasts((ts) => [...ts, { id, text, tone }]);
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 4200);
  }, []);
  return [toasts, push];
}

/* ---------- loading / empty / error ---------- */

export function Skeleton({ height = 18, width = '100%' }: { height?: number; width?: string | number }) {
  return <div className="skeleton" style={{ height, width }} />;
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="kpi-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="metric-card"><Skeleton height={12} width="60%" /><div style={{ height: 10 }} /><Skeleton height={28} width="80%" /></div>
      ))}
    </div>
  );
}

export function EmptyState({ icon = '📊', title, text, action }: { icon?: string; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <h3 style={{ margin: '0 0 8px' }}>{title}</h3>
      {text && <p style={{ margin: '0 0 16px', fontSize: 13.5 }}>{text}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', text, onRetry }: { title?: string; text?: string; onRetry?: () => void }) {
  return (
    <div className="error-state">
      <div className="big">⚠️</div>
      <h3 style={{ margin: '0 0 8px' }}>{title}</h3>
      {text && <p style={{ margin: '0 0 16px', fontSize: 13.5 }}>{text}</p>}
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/* ---------- misc ---------- */

export function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
