/* Typed API client. The JWT lives in localStorage; Instagram tokens never reach the frontend. */

export interface ApiError extends Error {
  status: number;
  code?: string;
}

const TOKEN_KEY = 'insightboard_jwt';

// Base URL of the backend API. Empty in local dev (Vite proxies /api to
// localhost:8000); set VITE_API_URL to the deployed backend origin
// (e.g. https://insightboard-api.onrender.com) for hosted frontends.
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export function getJwt(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setJwt(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearJwt() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const jwt = getJwt();
  if (jwt) headers['Authorization'] = `Bearer ${jwt}`;
  // ngrok's free tunnels show a "Visit Site" interstitial to browser requests;
  // this header tells ngrok to skip it for API (fetch) calls. Harmless for
  // non-ngrok backends, which simply ignore unknown headers.
  if (API_BASE.includes('ngrok')) headers['ngrok-skip-browser-warning'] = 'true';
  if (init.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`) as ApiError;
    err.status = res.status;
    err.code = data?.code;
    if (res.status === 401) {
      clearJwt();
      if (window.location.pathname !== '/login') window.location.href = '/login';
    }
    throw err;
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

/* ---------- types ---------- */

export interface User {
  id: number;
  name: string;
  email: string;
}
export interface InstagramAccount {
  id: number;
  instagram_user_id: string;
  username: string;
  account_type: string | null;
  profile_picture_url: string | null;
  followers_count: number | null;
  connected_at: string;
  token: { connected: boolean; expired: boolean; expires_at: string | null; scopes: string[] };
}
export interface Summary {
  range_days: number;
  totals: Record<string, number | null>;
  deltas: Record<string, number | null>;
  followers: number | null;
}
export interface TimeSeries {
  metric_names: string[];
  points: { date: string; values: Record<string, number | null> }[];
}
export interface MediaItem {
  id: number;
  instagram_media_id: string;
  media_type: string | null;
  media_product_type: string | null;
  caption: string | null;
  permalink: string | null;
  thumbnail_url: string | null;
  media_url?: string | null;
  posted_at: string | null;
  metrics: Record<string, number | null>;
}
export interface MediaList {
  items: MediaItem[];
  total: number;
}
export interface SyncStatus {
  last_synced_at: string | null;
  last_status: string | null;
  syncing: boolean;
}
export interface SyncResult {
  status: string;
  message?: string | null;
  records_synced?: number | null;
  synced_at?: string | null;
  last_synced_at?: string | null;
}
export interface Audience {
  breakdown: string;
  timeframe: string;
  buckets: { dimensions: Record<string, string>; value: number }[];
  note: string | null;
}
export interface CommentItem {
  comment_id: string;
  text: string | null;
  username: string | null;
  timestamp: string | null;
  like_count: number | null;
  hidden: boolean;
}
export interface MetaInfo {
  available: string[];
  unavailable: { metric: string; reason: string }[];
  provider: string;
  data_delay_note: string;
}

export const ig = {
  me: () => api.get<User>('/api/auth/me'),
  register: (name: string, email: string, password: string) =>
    api.post<{ access_token: string }>('/api/auth/register', { name, email, password }),
  login: (email: string, password: string) =>
    api.post<{ access_token: string }>('/api/auth/login', { email, password }),

  connect: () => api.get<{ authorize_url: string; note: string }>('/api/instagram/connect'),
  account: () => api.get<InstagramAccount>('/api/instagram/account'),
  disconnect: () => api.post<{ ok: boolean }>('/api/instagram/disconnect'),
  meta: () => api.get<MetaInfo>('/api/instagram/meta'),
  sync: (force = false) => api.post<SyncResult>(`/api/instagram/sync?force=${force}`),
  syncStatus: () => api.get<SyncStatus>('/api/instagram/sync/status'),

  summary: (days: number) => api.get<Summary>(`/api/instagram/insights/summary?days=${days}`),
  timeseries: (days: number, metrics: string[]) =>
    api.get<TimeSeries>(`/api/instagram/insights/timeseries?days=${days}&metrics=${metrics.join(',')}`),
  media: (sort = 'latest', limit = 25) =>
    api.get<MediaList>(`/api/instagram/media?sort=${sort}&limit=${limit}`),
  mediaDetail: (id: number) => api.get<MediaItem>(`/api/instagram/media/${id}`),
  audience: (breakdown: string, timeframe: string) =>
    api.get<Audience>(`/api/instagram/audience?breakdown=${breakdown}&timeframe=${timeframe}`),
  comments: (mediaId: number) => api.get<{ media_id: number; items: CommentItem[] }>(`/api/instagram/media/${mediaId}/comments`),
  replyComment: (commentId: string, message: string) =>
    api.post<CommentItem>(`/api/instagram/comments/${commentId}/replies`, { message }),
  hideComment: (commentId: string, hide: boolean) =>
    api.post<{ ok: boolean }>(`/api/instagram/comments/${commentId}/hide?hide=${hide}`),
  deleteComment: (commentId: string) => api.delete<{ ok: boolean }>(`/api/instagram/comments/${commentId}`),
};
