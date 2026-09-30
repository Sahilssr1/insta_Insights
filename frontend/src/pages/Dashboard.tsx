import { useCallback, useEffect, useMemo, useState } from 'react';
import { ig, type InstagramAccount, type MetaInfo, type Summary, type TimeSeries } from '../api/client';
import { TimeChart, type Series } from '../components/Chart';
import {
  Card, DateRangePicker, EmptyState, ErrorState, MetricCard, SkeletonCards, Toasts, formatNum, useToasts,
} from '../components/ui';

const KPI_DEFS: { key: string; label: string }[] = [
  { key: 'views', label: 'Views' },
  { key: 'reach', label: 'Reach' },
  { key: 'likes', label: 'Likes' },
  { key: 'comments', label: 'Comments' },
  { key: 'shares', label: 'Shares' },
  { key: 'saves', label: 'Saves' },
  { key: 'total_interactions', label: 'Engagement' },
  { key: 'accounts_engaged', label: 'Accounts engaged' },
];

const CHART_METRICS = [
  { key: 'views', label: 'Views' },
  { key: 'reach', label: 'Reach' },
  { key: 'total_interactions', label: 'Engagement' },
];

const METRIC_LABELS: Record<string, string> = {
  views: 'Views', reach: 'Reach', likes: 'Likes', comments: 'Comments',
  shares: 'Shares', saves: 'Saves', total_interactions: 'Engagement',
  accounts_engaged: 'Accounts engaged', replies: 'Replies', reposts: 'Reposts',
  follows_and_unfollows: 'Follows', profile_links_taps: 'Profile taps', follower_count: 'Follower change',
};

export function Dashboard() {
  const [toasts, push] = useToasts();
  const [days, setDays] = useState(30);
  const [chartMetric, setChartMetric] = useState('views');
  const [account, setAccount] = useState<InstagramAccount | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [series, setSeries] = useState<TimeSeries | null>(null);
  const [meta, setMeta] = useState<MetaInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [acct, sum, ts, m] = await Promise.all([
        ig.account(),
        ig.summary(days),
        ig.timeseries(days, CHART_METRICS.map((c) => c.key)),
        ig.meta(),
      ]);
      setAccount(acct);
      setSummary(sum);
      setSeries(ts);
      setMeta(m);
    } catch (e: any) {
      setError(e.message || 'Could not load insights');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const fn = () => { load(); push('Dashboard refreshed', 'success'); };
    window.addEventListener('insightboard:synced', fn);
    return () => window.removeEventListener('insightboard:synced', fn);
  }, [load, push]);

  const chartSeries: Series[] = useMemo(() => {
    if (!series) return [];
    const s = series.points;
    return CHART_METRICS.filter((c) => c.key === chartMetric || chartMetric === 'all').map((c, i) => ({
      name: c.label,
      color: ['#6c8cff', '#34d399', '#fbbf24'][i % 3],
      points: s.map((p) => ({ x: p.date, y: p.values[c.key] ?? null })),
    }));
  }, [series, chartMetric]);

  const hasData = summary && Object.values(summary.totals).some((v) => (v || 0) > 0);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Insights</h1>
          <div className="page-sub">
            {account ? (
              <>Account <strong>@{account.username}</strong>{account.account_type ? ` · ${account.account_type}` : ''} · last {days} days</>
            ) : 'Your Instagram analytics'}
          </div>
        </div>
        <DateRangePicker value={days} onChange={setDays} />
      </div>

      {loading ? (
        <><SkeletonCards count={8} /><div style={{ height: 16 }} /><Card><div style={{ height: 260 }} /></Card></>
      ) : error ? (
        <ErrorState text={error} onRetry={load} />
      ) : !hasData ? (
        <EmptyState
          icon="📊"
          title="No insights data yet"
          text="Sync your Instagram data to populate this dashboard. Insights can take up to 48 hours to appear for very new accounts."
        />
      ) : (
        <>
          <div className="kpi-grid">
            {KPI_DEFS.map((k) => (
              <MetricCard
                key={k.key}
                label={k.label}
                value={summary!.totals[k.key]}
                delta={summary!.deltas[k.key]}
              />
            ))}
            <MetricCard label="Followers" value={summary!.followers} note="Current follower count" />
          </div>

          <Card className="chart-card mt-24">
            <div className="card-title-row">
              <h3>Performance over time</h3>
              <div className="seg" role="group" aria-label="Chart metric">
                {CHART_METRICS.map((c) => (
                  <button key={c.key} className={chartMetric === c.key ? 'active' : ''} onClick={() => setChartMetric(c.key)}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
            <TimeChart series={chartSeries} />
          </Card>

          {meta && meta.unavailable.length > 0 && (
            <Card className="mt-24">
              <div className="card-title-row"><h3>Metric availability</h3></div>
              <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: '0 0 12px' }}>
                These metrics appear in the Instagram app but are <strong>not provided by Meta's official API</strong>,
                so we show them as unavailable instead of guessing:
              </p>
              <div className="row-list">
                {meta.unavailable.map((u) => (
                  <div className="row-item" key={u.metric}>
                    <span className="k" style={{ textTransform: 'capitalize' }}>{u.metric.replace(/_/g, ' ')}</span>
                    <span className="v" style={{ fontWeight: 500, fontSize: 12.5, color: 'var(--text-faint)', maxWidth: '60%', textAlign: 'right' }}>{u.reason}</span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '12px 0 0' }}>{meta.data_delay_note}</p>
            </Card>
          )}
        </>
      )}
      <Toasts toasts={toasts} />
    </div>
  );
}

export { METRIC_LABELS, formatNum };
