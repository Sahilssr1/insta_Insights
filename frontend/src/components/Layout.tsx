import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { ig, type SyncStatus } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { Badge, Button, Toasts, timeAgo, useToasts } from './ui';

const NAV = [
  { to: '/', label: 'Overview', icon: '📈' },
  { to: '/content', label: 'Content', icon: '🎬' },
  { to: '/audience', label: 'Audience', icon: '👥' },
  { to: '/connect', label: 'Connect', icon: '🔗' },
];

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [toasts, push] = useToasts();
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadStatus = () => ig.syncStatus().then(setSyncStatus).catch(() => setSyncStatus(null));
  useEffect(() => { loadStatus(); }, []);

  const doSync = async () => {
    setSyncing(true);
    try {
      const res = await ig.sync();
      if (res.status === 'success') {
        push(`Synced ${res.records_synced ?? 0} records`, 'success');
      } else if (res.status === 'throttled') {
        push(res.message || 'Sync throttled — please wait', '');
      } else {
        push(res.message || 'Sync failed', 'error');
      }
      await loadStatus();
      window.dispatchEvent(new CustomEvent('insightboard:synced'));
    } catch (e: any) {
      push(e.message || 'Sync failed', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const onLogout = () => { logout(); navigate('/login'); };

  const syncBadge = syncStatus?.last_synced_at ? (
    <Badge tone={syncStatus.last_status === 'success' ? 'ok' : syncStatus.last_status === 'running' ? 'warn' : 'err'}>
      {syncing || syncStatus.syncing ? 'Syncing…' : `Synced ${timeAgo(syncStatus.last_synced_at)}`}
    </Badge>
  ) : null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">◈</div>
          <div>
            <div className="brand-name">InsightBoard</div>
            <div className="brand-sub">Instagram Analytics</div>
          </div>
        </div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="icon">{n.icon}</span>{n.label}
          </NavLink>
        ))}
        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {syncBadge}
          <Button size="sm" onClick={doSync} disabled={syncing}>{syncing ? 'Syncing…' : '↻ Sync now'}</Button>
          <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{user?.email}</div>
          <Button size="sm" onClick={onLogout}>Log out</Button>
        </div>
      </aside>

      <main className="main">
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginBottom: 14 }}>
          {syncBadge}
          <Button size="sm" onClick={doSync} disabled={syncing}>{syncing ? 'Syncing…' : '↻ Sync now'}</Button>
        </div>
        {children}
      </main>

      <nav className="bottom-nav">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="icon">{n.icon}</span>{n.label}
          </NavLink>
        ))}
      </nav>
      <Toasts toasts={toasts} />
    </div>
  );
}
