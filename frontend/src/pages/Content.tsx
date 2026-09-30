import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ig, type MediaItem, type MediaList } from '../api/client';
import { EmptyState, ErrorState, Skeleton, Tabs, formatNum } from '../components/ui';

const SORTS = [
  { key: 'latest', label: 'Latest' },
  { key: 'views', label: 'Views' },
  { key: 'likes', label: 'Likes' },
  { key: 'comments', label: 'Comments' },
  { key: 'shares', label: 'Shares' },
  { key: 'saves', label: 'Saves' },
];

const STAT_KEYS = ['views', 'likes', 'comments', 'shares', 'saved', 'reach'] as const;

function MediaCard({ item, onOpen }: { item: MediaItem; onOpen: () => void }) {
  const caption = item.caption?.trim() || '(no caption)';
  const date = item.posted_at ? new Date(item.posted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
  return (
    <div className="media-card" onClick={onOpen} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onOpen()}>
      <div className="media-thumb">
        {item.thumbnail_url
          ? <img src={item.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
          : <span>{item.media_product_type === 'REELS' ? '🎬 Reel' : item.media_type === 'CAROUSEL_ALBUM' ? '🖼️ Carousel' : '📷 Post'}</span>}
      </div>
      <div className="media-body">
        <p className="media-caption">{caption}</p>
        <div className="media-date">{date}{item.media_product_type ? ` · ${item.media_product_type}` : ''}</div>
        <div className="media-stats">
          {STAT_KEYS.map((k) => (
            <div className="media-stat" key={k}>
              <div className="k">{k === 'saved' ? 'saves' : k}</div>
              <div className="v">{formatNum(item.metrics[k])}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Content() {
  const navigate = useNavigate();
  const [sort, setSort] = useState('latest');
  const [data, setData] = useState<MediaList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await ig.media(sort, 48));
    } catch (e: any) {
      setError(e.message || 'Could not load content');
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const fn = () => load();
    window.addEventListener('insightboard:synced', fn);
    return () => window.removeEventListener('insightboard:synced', fn);
  }, [load]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Content</h1>
          <div className="page-sub">{data ? `${data.total} posts & reels` : 'Your posts and reels'}</div>
        </div>
      </div>
      <Tabs tabs={SORTS.map((s) => s.label)} active={SORTS.find((s) => s.key === sort)!.label}
        onChange={(label) => setSort(SORTS.find((s) => s.label === label)!.key)} />
      {loading ? (
        <div className="media-grid">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={280} />)}</div>
      ) : error ? (
        <ErrorState text={error} onRetry={load} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState icon="🎬" title="No content yet" text="Sync your account to load posts and reels." />
      ) : (
        <div className="media-grid">
          {data.items.map((m) => (
            <MediaCard key={m.id} item={m} onOpen={() => navigate(`/content/${m.id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}
