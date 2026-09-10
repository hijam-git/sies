import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiClient, ApiError } from './api';
import type { Branch, User } from './api';
import { effectivePermissions, can as rawCan, canView as rawCanView } from './permissions';
import type { Action, Resource } from './permissions';
import { normalizeBdPhone } from './normalizeBdPhone';
import { useT } from './i18n';

interface AuthContextType {
  user: User | null;
  /** The permissions the app actually enforces on screen: the user's own list
   *  if it is set, otherwise their role's preset — never merged. See
   *  `lib/permissions.ts`. */
  permissions: string[];
  loading: boolean;
  error: string | null;
  clearError: () => void;
  /** 11-digit phone + password. There is no other way in. */
  login: (phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;

  // ── Branch switching, platform admin only ─────────────────────────────
  /** Every institution this user may look at. Empty until loaded, and only
   *  ever more than one entry for a platform admin. */
  branches: Branch[];
  /** The institution being viewed, or null for "all of them". Always null for
   *  a user tied to a branch — the backend ignores `?branch=` for them
   *  (`docs/02` §3), so letting the UI pretend otherwise would only mislead. */
  activeBranchId: number | null;
  setActiveBranchId: (id: number | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = (): AuthContextType => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};

/**
 * The permission check, bound to whoever is signed in.
 *
 * `canView('fees')` at the call site rather than threading a permission array
 * through every component — the sidebar alone would have to pass it to a dozen
 * places, and one forgotten argument is a nav item shown to somebody who
 * cannot open it.
 */
export function usePermissions() {
  const { permissions } = useAuth();
  return useMemo(
    () => ({
      permissions,
      can: (resource: Resource, action: Action) => rawCan(permissions, resource, action),
      canView: (resource: Resource) => rawCanView(permissions, resource),
    }),
    [permissions],
  );
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { setLang } = useT();
  const [user, setUser] = useState<User | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranchId, setActiveBranchIdState] = useState<number | null>(
    apiClient.getActiveBranchId(),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  /** The person's saved language wins over whatever this browser last used —
   *  a teacher who set Bangla on their own machine should not meet English on
   *  the office computer. */
  const adoptLanguage = useCallback((u: User) => {
    if (u.language === 'bn' || u.language === 'en') setLang(u.language);
  }, [setLang]);

  /** Only a platform admin has more than one institution to choose between, so
   *  only they pay for the extra request. */
  const loadBranches = useCallback(async (u: User) => {
    if (u.branch !== null) return;
    try {
      setBranches(await apiClient.getBranches());
    } catch {
      // The switcher is a convenience. Losing it must not cost the dashboard.
    }
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setBranches([]);
    setActiveBranchIdState(null);
    apiClient.setActiveBranchId(null);
  }, []);

  useEffect(() => {
    let alive = true;

    const initialise = async () => {
      if (!apiClient.isAuthenticated()) {
        setLoading(false);
        return;
      }

      // Paint from the stored copy first, then correct it. Waiting for the
      // network before rendering means a blank screen on every reload, and a
      // permission change since last login lands a moment later either way.
      const stored = apiClient.getStoredUser();
      if (stored && alive) {
        setUser(stored);
        adoptLanguage(stored);
      }

      const current = await apiClient.getCurrentUser();
      if (!alive) return;

      if (current) {
        setUser(current);
        adoptLanguage(current);
        void loadBranches(current);
      } else {
        // The token is gone or rejected. Clearing here rather than leaving the
        // stale user on screen is what sends them to /login instead of to a
        // dashboard where every request 401s.
        await apiClient.logout();
        clearSession();
      }
      setLoading(false);
    };

    void initialise();
    return () => { alive = false; };
  }, [adoptLanguage, clearSession, loadBranches]);

  const login = useCallback(async (phone: string, password: string): Promise<void> => {
    setError(null);
    // Canonicalised here as well as in the form: this is the last point before
    // the wire, and every caller has to send the same eleven digits the
    // account was created with.
    const canonical = normalizeBdPhone(phone);
    if (!canonical) {
      setError('invalid_phone');
      throw new ApiError(400, 'invalid_phone', { code: 'invalid_phone' });
    }

    try {
      const response = await apiClient.login(canonical, password);
      setUser(response.user);
      adoptLanguage(response.user);
      void loadBranches(response.user);
    } catch (err) {
      // The code, not a sentence: LoginPage renders it through the dictionary
      // so the message exists in both languages like every other string.
      setError(err instanceof ApiError ? (err.code ?? 'login_failed') : 'login_failed');
      throw err;
    }
  }, [adoptLanguage, loadBranches]);

  const logout = useCallback(async (): Promise<void> => {
    await apiClient.logout();
    clearSession();
    setError(null);
  }, [clearSession]);

  const setActiveBranchId = useCallback((id: number | null) => {
    apiClient.setActiveBranchId(id);
    setActiveBranchIdState(id);
    // Every list on screen was fetched for the old institution. A reload is
    // blunt but it is also complete — anything subtler leaves one stale panel
    // showing another institution's numbers, which is the one mistake this
    // screen must never make.
    window.location.reload();
  }, []);

  const permissions = useMemo(() => effectivePermissions(user), [user]);

  const value: AuthContextType = useMemo(() => ({
    user,
    permissions,
    loading,
    error,
    clearError,
    login,
    logout,
    isAuthenticated: !!user,
    branches,
    activeBranchId,
    setActiveBranchId,
  }), [user, permissions, loading, error, clearError, login, logout, branches, activeBranchId, setActiveBranchId]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
