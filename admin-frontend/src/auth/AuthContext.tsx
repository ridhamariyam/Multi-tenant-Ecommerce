import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getMe, login as loginRequest, logout as logoutRequest } from "../api/auth";
import type { LoginRole } from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";
import { getMerchant, loginMerchant, logoutMerchant, registerMerchant, switchBrand } from "../api/platform";
import type { MerchantAccount } from "../types/platform";
import type { UserProfile } from "../types/user";
import {
  clearAllSessions,
  clearBrandSession,
  getBrandId,
  getPlatformRefreshToken,
  getPlatformToken,
  getRefreshToken,
  getToken,
  savePlatformTokens,
  saveTokens,
  setBrandId,
} from "../utils/storage";

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
  /** Signed in with a merchant account (may own several brands). */
  merchant: MerchantAccount | null;
  /** The brand open in merchant mode; null in a per-store login or before one is chosen. */
  brandId: string | null;
  checking: boolean;
  notice: string | null;
  login: (role: LoginRole, identifier: string, password: string) => Promise<void>;
  merchantLogin: (email: string, password: string) => Promise<void>;
  merchantRegister: (data: { name: string; email: string; password: string; phone?: string | null }) => Promise<void>;
  /** Open one of the merchant's brands; every admin screen then works on it. */
  openBrand: (brandId: string, token?: string) => Promise<void>;
  /** Close the open brand and go back to the brand list. */
  leaveBrand: () => void;
  logout: (notice?: string) => void;
  can: (permission: string) => boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [merchant, setMerchant] = useState<MerchantAccount | null>(null);
  const [brandId, setBrand] = useState<string | null>(() => getBrandId());
  const [checking, setChecking] = useState(() => getToken() !== null || getPlatformToken() !== null);
  const [notice, setNotice] = useState<string | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const logout = useCallback((message?: string) => {
    const refresh = getRefreshToken();
    if (refresh) logoutRequest(refresh).catch(() => undefined);
    const platformRefresh = getPlatformRefreshToken();
    if (platformRefresh) logoutMerchant(platformRefresh).catch(() => undefined);
    clearAllSessions();
    setUser(null);
    setMerchant(null);
    setBrand(null);
    setNotice(message ?? null);
  }, []);

  // Restore the session after a page reload: the merchant account, then the open brand's user.
  useEffect(() => {
    if (!getToken() && !getPlatformToken()) return;
    (async () => {
      if (getPlatformToken()) {
        const me = await getMerchant().catch(() => null);
        if (me) setMerchant(me.data);
      }
      if (getToken()) {
        const response = await getMe().catch(() => null);
        if (response && PANEL_ROLES.has(response.data.role)) setUser(response.data);
        else if (response) logout(NOT_A_PANEL_ACCOUNT);
      }
    })().finally(() => setChecking(false));
  }, [logout]);

  const openBrand = useCallback(async (id: string, token?: string) => {
    const access = token ?? (await switchBrand(id)).data.access_token;
    saveTokens(access, null);
    setBrandId(id);
    setBrand(id);
    const me = await getMe();
    setUser(me.data);
  }, []);

  const leaveBrand = useCallback(() => {
    clearBrandSession();
    setBrand(null);
    setUser(null);
  }, []);

  const startMerchantSession = useCallback((session: { access_token: string; refresh_token: string; account: MerchantAccount }) => {
    clearBrandSession();
    savePlatformTokens(session.access_token, session.refresh_token);
    setMerchant(session.account);
    setUser(null);
    setBrand(null);
    setNotice(null);
  }, []);

  const merchantLogin = useCallback(async (email: string, password: string) => {
    startMerchantSession((await loginMerchant(email, password)).data);
  }, [startMerchantSession]);

  const merchantRegister = useCallback(async (data: { name: string; email: string; password: string; phone?: string | null }) => {
    startMerchantSession((await registerMerchant(data)).data);
  }, [startMerchantSession]);

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
    clearAllSessions();
    setMerchant(null);
    setBrand(null);
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
      merchant,
      brandId,
      checking,
      notice,
      login,
      merchantLogin,
      merchantRegister,
      openBrand,
      leaveBrand,
      logout,
      can: (permission) => !!user && user.permissions.includes(permission),
      isAdmin: user?.role === "ADMIN",
    }),
    [user, merchant, brandId, checking, notice, login, merchantLogin, merchantRegister, openBrand, leaveBrand, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
