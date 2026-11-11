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
  refresh(refreshToken: string): Promise<TokenPair> {
    return apiRequest<TokenPair>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      cache: 'no-store',
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

  /** Erase the account. Past orders survive, stripped of the person. */
  deleteAccount(token: string): Promise<null> {
    return apiRequest<null>('/auth/me', { method: 'DELETE', token, cache: 'no-store' });
  },

  /** The storefront this API host serves. Other tenants are never listed. */
  currentTenant(): Promise<Tenant> {
    return apiRequest<Tenant>('/auth/tenant', { cache: 'no-store' });
  },
};
