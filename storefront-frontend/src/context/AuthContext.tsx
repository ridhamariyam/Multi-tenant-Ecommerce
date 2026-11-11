'use client';

import { createContext, useContext } from 'react';

import { logout as logoutAction } from '@/lib/auth/actions';
import type { UserProfile } from '@/types/auth';

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  /** Kept for the components that already read it. Same value as isAuthenticated. */
  isSignedIn: boolean;
  /**
   * Always false, and structurally so.
   *
   * There is no client-side sign-in bootstrap to wait for: the layout has
   * already resolved the session against /auth/me on the server, so the
   * first render the browser sees is the settled answer. Components can
   * still branch on it without having to know that.
   */
  loading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

/**
 * The signed-in user, resolved on the server.
 *
 * Tokens live in httpOnly cookies, so nothing here can read them -- the
 * layout calls /auth/me while rendering and passes the profile down. There
 * is no client-side sign-in call to make: the OTP form posts to a server
 * action, which sets the cookies and refreshes the tree, and middleware
 * rotates an expired access token before any of this runs. That is the
 * whole of the session's lifecycle, and it deliberately has no second copy
 * in browser state to fall out of step with the cookies.
 */
export function AuthProvider({ user, children }: { user: UserProfile | null; children: React.ReactNode }) {
  const isAuthenticated = user !== null;

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isSignedIn: isAuthenticated,
        loading: false,
        logout: logoutAction,
      }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }

  return context;
}
