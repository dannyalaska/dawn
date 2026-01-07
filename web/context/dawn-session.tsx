'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from 'react';
import type { DawnUser } from '@/lib/types';
import { DEFAULT_API_BASE } from '@/lib/config';

interface DawnSessionContextValue {
  token: string | null;
  user: DawnUser | null;
  ready: boolean;
  apiBase: string;
  setSession: (payload: { token: string | null; user: DawnUser | null }) => void;
  logout: () => void;
}

const DawnSessionContext = createContext<DawnSessionContextValue | undefined>(undefined);
const STORAGE_KEY = 'dawn.session';

export function DawnSessionProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<DawnUser | null>(null);
  const [ready, setReady] = useState(false);
  const apiBase = DEFAULT_API_BASE;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        setReady(true);
        return;
      }
      const parsed = JSON.parse(raw);
      setToken(parsed.token ?? null);
      setUser(parsed.user ?? null);
    } catch (err) {
      console.warn('Failed to parse stored session', err);
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setReady(true);
    }
  }, []);

  const persist = useCallback((nextToken: string | null, nextUser: DawnUser | null) => {
    if (typeof window === 'undefined') return;
    if (!nextToken) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: nextToken, user: nextUser })
    );
  }, []);

  const setSession = useCallback(
    (payload: { token: string | null; user: DawnUser | null }) => {
      setToken(payload.token);
      setUser(payload.user);
      persist(payload.token, payload.user);
    },
    [persist]
  );

  const logout = useCallback(() => {
    setSession({ token: null, user: null });
  }, [setSession]);

  const value = useMemo(
    () => ({ token, user, ready, apiBase, setSession, logout }),
    [token, user, ready, apiBase, setSession, logout]
  );

  return <DawnSessionContext.Provider value={value}>{children}</DawnSessionContext.Provider>;
}

export function useDawnSession() {
  const ctx = useContext(DawnSessionContext);
  if (!ctx) {
    throw new Error('useDawnSession must be used inside DawnSessionProvider');
  }
  return ctx;
}
