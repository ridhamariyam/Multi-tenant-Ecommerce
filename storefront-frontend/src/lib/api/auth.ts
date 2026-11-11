import { apiRequest } from '@/lib/api/client';
import type { Tenant, TokenPair, UserProfile } from '@/types/auth';

export const authApi = {
  /** Exchange the MSG91 widget's verified token for a CliQ session. */
  widgetLogin(accessToken: string): Promise<TokenPair> {
    return apiRequest<TokenPair>('/auth/widget/login', {
      method: 'POST',
      body: { access_token: accessToken },
      cache: 'no-store',
    });
  },

  googleLogin(credential: string): Promise<TokenPair> {
    return apiRequest<TokenPair>('/auth/google/login', {
      method: 'POST',
      body: { credential },
      cache: 'no-store',
    });
  },

  /** Rotate a refresh token. Reusing a revoked one revokes every session. */
  /** `host`: the storefront domain, for callers (middleware) that cannot read request headers. */
  refresh(refreshToken: string, host?: string | null): Promise<TokenPair> {
    return apiRequest<TokenPair>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      cache: 'no-store',
      ...(host ? { headers: { 'X-Forwarded-Host': host } } : {}),
    });
  },

  logout(refreshToken: string): Promise<null> {
    return apiRequest<null>('/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      cache: 'no-store',
    });
  },

  me(token: string): Promise<UserProfile> {
    return apiRequest<UserProfile>('/auth/me', { token, cache: 'no-store' });
  },

  updateMe(token: string, body: { marketing_opt_in?: boolean; email?: string | null }): Promise<UserProfile> {
    return apiRequest<UserProfile>('/auth/me', { method: 'PATCH', token, body, cache: 'no-store' });
  },

  /** Erase the account. Past orders survive, stripped of the person. */
  deleteAccount(token: string): Promise<null> {
    return apiRequest<null>('/auth/me', { method: 'DELETE', token, cache: 'no-store' });
  },

  /** The storefront this API host serves. Other tenants are never listed. */
  currentTenant(): Promise<Tenant> {
    return apiRequest<Tenant>('/auth/tenant', { cache: 'no-store' });
  },
};
