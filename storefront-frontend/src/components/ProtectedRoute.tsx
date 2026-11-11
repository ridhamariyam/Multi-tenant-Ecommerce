'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { useAuth } from '@/context/AuthContext';
import { signInUrl } from '@/lib/auth/sign-in-url';

/**
 * A second gate for pages that need a signed-in shopper.
 *
 * Middleware already redirects these routes, and the backend rejects the
 * calls behind them, so this exists to keep a stale client-side navigation
 * from flashing an empty page. There is no loading state: the session is
 * resolved on the server before the tree renders.
 *
 * The path is carried across so signing in returns the shopper to the page
 * they asked for, rather than dropping them on the account page.
 */
export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isSignedIn } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!isSignedIn) {
      router.replace(signInUrl(pathname));
    }
  }, [isSignedIn, pathname, router]);

  if (!isSignedIn) {
    return null;
  }

  return <>{children}</>;
}
