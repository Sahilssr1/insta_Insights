import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { clearJwt, getJwt, ig, setJwt, type User } from '../api/client';

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Guest mode: testers never see a login screen. Resume the previous
      // guest session when it is still valid; otherwise silently provision a
      // fresh anonymous guest account (also recovers from a wiped server DB).
      if (getJwt()) {
        try {
          const u = await ig.me();
          if (!cancelled) setUser(u);
          return;
        } catch {
          clearJwt(); // stale session → fall through to a fresh guest
        }
      }
      const id = crypto.randomUUID().replace(/-/g, '');
      const res = await ig.register('Guest', `guest-${id}@insightboard.app`, id);
      setJwt(res.access_token);
      if (!cancelled) setUser(await ig.me());
    })()
      .catch(() => {
        /* backend unreachable — user stays null, UI shows a retry hint */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await ig.login(email, password);
    setJwt(res.access_token);
    setUser(await ig.me());
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await ig.register(name, email, password);
    setJwt(res.access_token);
    setUser(await ig.me());
  }, []);

  const logout = useCallback(() => {
    clearJwt();
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
