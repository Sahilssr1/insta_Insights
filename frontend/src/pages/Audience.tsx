import { useCallback, useEffect, useState } from 'react';
import { ig, type Audience as AudienceData } from '../api/client';
import { Card, EmptyState, ErrorState, Skeleton, formatNum } from '../components/ui';

const BREAKDOWNS = [
  { key: 'age', label: 'Age' },
  { key: 'gender', label: 'Gender' },
  { key: 'city', label: 'City' },
  { key: 'country', label: 'Country' },
];
const TIMEFRAMES = [
  { key: 'last_14_days', label: '14 days' },
  { key: 'last_30_days', label: '30 days' },
  { key: 'last_90_days', label: '90 days' },
];

export function Audience() {
  const [breakdown, setBreakdown] = useState('age');
  const [timeframe, setTimeframe] = useState('last_30_days');
  const [data, setData] = useState<AudienceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await ig.audience(breakdown, timeframe));
    } catch (e: any) {
      setError(e.message || 'Could not load audience data');
    } finally {
      setLoading(false);
    }
  }, [breakdown, timeframe]);

  useEffect(() => { load(); }, [load]);

  const max = Math.max(1, ...(data?.buckets.map((b) => b.value) || [0]));

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Audience</h1>
          <div className="page-sub">Follower demographics from Instagram's official API</div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div className="seg" role="group" aria-label="Breakdown">
            {BREAKDOWNS.map((b) => (
              <button key={b.key} className={breakdown === b.key ? 'active' : ''} onClick={() => setBreakdown(b.key)}>
                {b.label}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Timeframe">
            {TIMEFRAMES.map((t) => (
              <button key={t.key} className={timeframe === t.key ? 'active' : ''} onClick={() => setTimeframe(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <Card><Skeleton height={16} /><div style={{ height: 12 }} /><Skeleton height={16} /><div style={{ height: 12 }} /><Skeleton height={16} /></Card>
      ) : error ? (
        <ErrorState text={error} onRetry={load} />
      ) : data?.note ? (
        <EmptyState icon="👥" title="Demographics unavailable" text={data.note} />
      ) : !data || data.buckets.length === 0 ? (
        <EmptyState icon="👥" title="No demographic data" text="Instagram currently does not provide this metric through the connected API." />
      ) : (
        <Card>
          <div className="card-title-row"><h3 style={{ textTransform: 'capitalize' }}>Followers by {breakdown}</h3></div>
          {data.buckets
            .slice()
            .sort((a, b) => b.value - a.value)
            .slice(0, 15)
            .map((b, i) => {
              const label = Object.values(b.dimensions).join(' · ') || 'Unknown';
              return (
                <div className="bar-row" key={i}>
                  <span className="bar-label">{label}</span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${(b.value / max) * 100}%` }} /></div>
                  <span className="bar-val">{formatNum(b.value)}</span>
                </div>
              );
            })}
          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: '14px 0 0' }}>
            Instagram returns the top entries only and requires at least 100 followers.
          </p>
        </Card>
      )}
    </div>
  );
}
