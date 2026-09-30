import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ig, type CommentItem, type MediaItem } from '../api/client';
import {
  Button, Card, EmptyState, ErrorState, Modal, Skeleton, Toasts, formatNum, timeAgo, useToasts,
} from '../components/ui';

const PERF_KEYS = [
  ['views', 'Views'], ['reach', 'Reach'], ['likes', 'Likes'], ['comments', 'Comments'],
  ['saved', 'Saves'], ['shares', 'Shares'], ['total_interactions', 'Engagement'],
  ['reposts', 'Reposts'], ['follows', 'Follows'], ['profile_visits', 'Profile visits'],
  ['profile_activity', 'Profile activity'],
] as const;

export function MediaDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [toasts, push] = useToasts();
  const [media, setMedia] = useState<MediaItem | null>(null);
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [commentsError, setCommentsError] = useState('');
  const [replyTo, setReplyTo] = useState<CommentItem | null>(null);
  const [replyText, setReplyText] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      setMedia(await ig.mediaDetail(Number(id)));
    } catch (e: any) {
      setError(e.message || 'Could not load media');
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadComments = useCallback(async () => {
    if (!id) return;
    setCommentsError('');
    try {
      const res = await ig.comments(Number(id));
      setComments(res.items);
    } catch (e: any) {
      setCommentsError(e.message || 'Could not load comments');
    }
  }, [id]);

  useEffect(() => { load(); loadComments(); }, [load, loadComments]);

  const doReply = async () => {
    if (!replyTo || !replyText.trim()) return;
    setBusy(true);
    try {
      await ig.replyComment(replyTo.comment_id, replyText.trim());
      push('Reply posted', 'success');
      setReplyTo(null);
      setReplyText('');
      loadComments();
    } catch (e: any) {
      push(e.message || 'Could not post reply', 'error');
    } finally {
      setBusy(false);
    }
  };

  const doHide = async (c: CommentItem, hide: boolean) => {
    try {
      await ig.hideComment(c.comment_id, hide);
      push(hide ? 'Comment hidden' : 'Comment unhidden', 'success');
      loadComments();
    } catch (e: any) {
      push(e.message || 'Action failed', 'error');
    }
  };

  const doDelete = async (c: CommentItem) => {
    if (!window.confirm('Delete this comment? This only works for comments you posted.')) return;
    try {
      await ig.deleteComment(c.comment_id);
      push('Comment deleted', 'success');
      loadComments();
    } catch (e: any) {
      push(e.message || 'Could not delete comment', 'error');
    }
  };

  if (loading) return <div><Skeleton height={30} width="50%" /><div style={{ height: 16 }} /><Skeleton height={300} /></div>;
  if (error || !media) return <ErrorState text={error} onRetry={load} />;

  const caption = media.caption?.trim() || '(no caption)';
  const date = media.posted_at ? new Date(media.posted_at).toLocaleString() : '';

  return (
    <div>
      <div className="page-head">
        <div>
          <Button size="sm" onClick={() => navigate('/content')}>← Back to content</Button>
          <h1 className="page-title" style={{ marginTop: 12 }}>
            {media.media_product_type === 'REELS' ? 'Reel' : media.media_type === 'CAROUSEL_ALBUM' ? 'Carousel' : 'Post'}
          </h1>
          <div className="page-sub">{date}</div>
        </div>
        {media.permalink && <a href={media.permalink} target="_blank" rel="noreferrer"><Button size="sm">Open on Instagram ↗</Button></a>}
      </div>

      <div className="grid-2">
        <Card>
          <div className="media-thumb" style={{ borderRadius: 10, marginBottom: 14 }}>
            {media.thumbnail_url
              ? <img src={media.thumbnail_url} alt="" referrerPolicy="no-referrer" />
              : <span>📷</span>}
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{caption}</p>
        </Card>
        <Card>
          <div className="card-title-row"><h3>Performance</h3></div>
          <div className="row-list">
            {PERF_KEYS.map(([k, label]) => (
              <div className="row-item" key={k}>
                <span className="k">{label}</span>
                <span className="v">{media.metrics[k] !== null && media.metrics[k] !== undefined ? formatNum(media.metrics[k]) : <span style={{ color: 'var(--text-faint)', fontWeight: 500, fontSize: 12.5 }}>Data unavailable</span>}</span>
              </div>
            ))}
          </div>
          {media.metrics.ig_reels_avg_watch_time ? (
            <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 12 }}>
              Avg. watch time: {Number(media.metrics.ig_reels_avg_watch_time).toFixed(1)}s
            </p>
          ) : null}
        </Card>
      </div>

      <Card className="mt-24">
        <div className="card-title-row"><h3>Comments</h3><span className="badge">{comments.length}</span></div>
        {commentsError ? (
          <ErrorState title="Could not load comments" text={commentsError} onRetry={loadComments} />
        ) : comments.length === 0 ? (
          <EmptyState icon="💬" title="No comments" text="Comments on this post will appear here." />
        ) : (
          comments.map((c) => (
            <div className="comment" key={c.comment_id}>
              <div className="comment-head">
                <span className="comment-user">@{c.username || 'unknown'}</span>
                <span className="comment-time">{c.timestamp ? timeAgo(c.timestamp) : ''}{c.like_count ? ` · ♥ ${c.like_count}` : ''}</span>
              </div>
              <div className="comment-text">{c.text}</div>
              <div className="comment-actions">
                <Button size="sm" onClick={() => setReplyTo(c)}>Reply</Button>
                <Button size="sm" onClick={() => doHide(c, !c.hidden)}>{c.hidden ? 'Unhide' : 'Hide'}</Button>
                <Button size="sm" variant="danger" onClick={() => doDelete(c)}>Delete</Button>
              </div>
            </div>
          ))
        )}
      </Card>

      {replyTo && (
        <Modal title={`Reply to @${replyTo.username}`} onClose={() => setReplyTo(null)}>
          <p style={{ fontSize: 13.5, color: 'var(--text-dim)', marginTop: 0 }}>"{replyTo.text}"</p>
          <div className="field">
            <label>Your reply</label>
            <input className="input" value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Write a reply…" maxLength={1000} />
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <Button onClick={() => setReplyTo(null)}>Cancel</Button>
            <Button variant="primary" onClick={doReply} disabled={busy || !replyText.trim()}>
              {busy ? 'Posting…' : 'Post reply'}
            </Button>
          </div>
        </Modal>
      )}
      <Toasts toasts={toasts} />
    </div>
  );
}
