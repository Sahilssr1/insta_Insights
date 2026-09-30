import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ig, type InstagramAccount } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, Skeleton, Toasts, useToasts } from '../components/ui';

const OAUTH_ERRORS: Record<string, string> = {
  access_denied: 'You cancelled the Instagram authorization. No account was connected.',
  invalid_state: 'The authorization request was invalid. Please try connecting again.',
  state_expired: 'The authorization request expired. Please try connecting again.',
  state_reused: 'This authorization request was already used. Please try connecting again.',
  exchange_failed: 'Instagram did not complete the connection. Please try again.',
  not_configured: 'Instagram connection is not configured on this server yet (missing META_APP_ID / META_APP_SECRET).',
  account_taken: 'This Instagram account is already connected to a different user.',
};

export function Connect() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [toasts, push] = useToasts();
  const [account, setAccount] = useState<InstagramAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connecting, setConnecting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setAccount(await ig.account());
    } catch (e: any) {
      if (e.status === 404) setAccount(null);
      else setError(e.message || 'Could not load connection status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const err = params.get('error');
    if (params.get('connected') === '1') push('Instagram connected successfully', 'success');
    else if (err) push(OAUTH_ERRORS[err] || 'Instagram connection failed', 'error');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startConnect = async () => {
    setConnecting(true);
    try {
      const res = await ig.connect();
      window.location.href = res.authorize_url;
    } catch (e: any) {
      push(e.message || 'Could not start Instagram connection', 'error');
      setConnecting(false);
    }
  };

  const doDisconnect = async () => {
    if (!window.confirm('Disconnect your Instagram account? All synced analytics will be deleted.')) return;
    try {
      await ig.disconnect();
      setAccount(null);
      push('Instagram disconnected', 'success');
    } catch (e: any) {
      push(e.message || 'Could not disconnect', 'error');
    }
  };

  if (loading) {
    return (
      <div>
        <Skeleton height={30} width="40%" />
        <div style={{ height: 16 }} />
        <Skeleton height={180} />
      </div>
    );
  }
  if (error) return <ErrorState text={error} onRetry={load} />;

  if (!account) {
    return (
      <div className="connect-hero">
        <div className="logo-big">◈</div>
        <h1>Connect your Instagram</h1>
        <p>
          Connect your Instagram <strong>Professional</strong> (Business or Creator) account
          to view your reach, views, engagement and content performance — powered directly
          by Meta's official APIs.
        </p>
        <div style={{ margin: '28px 0' }}>
          <Button variant="primary" size="lg" onClick={startConnect} disabled={connecting}>
            {connecting ? 'Opening Instagram…' : 'Connect Instagram'}
          </Button>
        </div>
        <Card>
          <div className="privacy-list">
            <div className="row"><span className="tick">✓</span><span>You'll authorize on instagram.com — we <strong>never</strong> ask for your Instagram password.</span></div>
            <div className="row"><span className="tick">✓</span><span>Access tokens are encrypted and stored server-side; they never reach your browser.</span></div>
            <div className="row"><span className="tick">✓</span><span>Only analytics data is read — nothing is ever posted to your account.</span></div>
            <div className="row"><span className="tick">✓</span><span>Disconnect anytime; your synced data is deleted.</span></div>
          </div>
        </Card>
        <Toasts toasts={toasts} />
      </div>
    );
  }

  return (
    <div className="connect-hero">
      <div className="logo-big">✓</div>
      <h1>Instagram connected</h1>
      <p style={{ fontSize: 18 }}><strong>@{account.username}</strong></p>
      <p>
        {account.account_type && <Badge>{account.account_type}</Badge>}{' '}
        {account.followers_count !== null && <Badge>{account.followers_count?.toLocaleString()} followers</Badge>}{' '}
        {account.token.expired
          ? <Badge tone="err">Token expired — please reconnect</Badge>
          : <Badge tone="ok">Token active</Badge>}
      </p>
      <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 26, flexWrap: 'wrap' }}>
        <Button variant="primary" size="lg" onClick={() => navigate('/')}>View Insights</Button>
        <Button size="lg" variant="danger" onClick={doDisconnect}>Disconnect</Button>
      </div>
      {account.token.expires_at && (
        <p style={{ marginTop: 18, fontSize: 13, color: 'var(--text-faint)' }}>
          Token expires {new Date(account.token.expires_at).toLocaleDateString()} — it refreshes automatically on sync.
        </p>
      )}
      <Toasts toasts={toasts} />
    </div>
  );
}

export function RequireAccount({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [state, setState] = useState<'loading' | 'ok' | 'none'>('loading');
  useEffect(() => {
    ig.account()
      .then(() => setState('ok'))
      .catch((e: any) => setState(e.status === 404 ? 'none' : 'none'));
  }, []);
  if (state === 'loading') return <Skeleton height={200} />;
  if (state === 'none') {
    return (
      <EmptyState
        icon="🔗"
        title="No Instagram account connected"
        text="Connect your Instagram Professional account to see analytics."
        action={<Button variant="primary" onClick={() => navigate('/connect')}>Connect Instagram</Button>}
      />
    );
  }
  return <>{children}</>;
}
