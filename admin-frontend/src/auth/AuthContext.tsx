import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getMe, login as loginRequest, logout as logoutRequest } from "../api/auth";
import type { LoginRole } from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";
import type { UserProfile } from "../types/user";
import { clearToken, getRefreshToken, getToken, saveTokens } from "../utils/storage";

// Inactivity is separate from access-token expiry; active sessions renew through the API client.
const configuredIdleMinutes = Number(process.env.NEXT_PUBLIC_AUTH_IDLE_TIMEOUT_MINUTES ?? 60);
const idleMinutes = Number.isFinite(configuredIdleMinutes) && configuredIdleMinutes >= 1 ? configuredIdleMinutes : 60;
export const IDLE_TIMEOUT_MS = idleMinutes * 60 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "keydown", "scroll", "touchstart"] as const;

// Only these roles may hold a session here; anything else is signed straight out.
const PANEL_ROLES = new Set(["ADMIN", "STAFF"]);
const NOT_A_PANEL_ACCOUNT = "This account cannot use the admin panel.";

interface AuthState {
  user: UserProfile | null;
  checking: boolean;
  notice: string | null;
  login: (role: LoginRole, identifier: string, password: string) => Promise<void>;
  logout: (notice?: string) => void;
  can: (permission: string) => boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [checking, setChecking] = useState(() => getToken() !== null);
  const [notice, setNotice] = useState<string | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const logout = useCallback((message?: string) => {
    const refresh = getRefreshToken();
    if (refresh) logoutRequest(refresh).catch(() => undefined);
    clearToken();
    setUser(null);
    setNotice(message ?? null);
  }, []);

  // Restore the session after a page reload.
  useEffect(() => {
    if (!getToken()) return;
    getMe()
      .then((response) => {
        if (PANEL_ROLES.has(response.data.role)) setUser(response.data);
        else logout(NOT_A_PANEL_ACCOUNT);
      })
      .catch(() => undefined)
      .finally(() => setChecking(false));
  }, [logout]);

  useEffect(() => {
    setUnauthorizedHandler(() => logout("Your session has expired. Please sign in again."));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Idle timeout while signed in.
  useEffect(() => {
    if (!user) return;
    const reset = () => {
      if (idleTimer.current) clearTimeout(idleTimer.current);
      idleTimer.current = setTimeout(
        () => logout(`You were signed out after ${idleMinutes} minutes of inactivity.`),
        IDLE_TIMEOUT_MS
      );
    };
    reset();
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      if (idleTimer.current) clearTimeout(idleTimer.current);
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [user, logout]);

  const login = useCallback(async (role: LoginRole, identifier: string, password: string) => {
    const tokens = await loginRequest(role, identifier, password);
    saveTokens(tokens.data.access_token, tokens.data.refresh_token);
    const me = await getMe();
    if (!PANEL_ROLES.has(me.data.role)) {
      logout();
      throw new Error(NOT_A_PANEL_ACCOUNT);
    }
    setNotice(null);
    setUser(me.data);
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      checking,
      notice,
      login,
      logout,
      can: (permission) => !!user && user.permissions.includes(permission),
      isAdmin: user?.role === "ADMIN",
    }),
    [user, checking, notice, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
