'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { createContext, Suspense, useCallback, useContext, useEffect, useState } from 'react';

import SignInModal from '@/components/SignInModal';
import { useAuth } from '@/context/AuthContext';
import { SIGN_IN_PARAM } from '@/lib/auth/sign-in-url';

interface SignInModalContextType {
  /** Open sign-in over the current page. `next` defaults to that page. */
  openSignIn: (next?: string) => void;
  closeSignIn: () => void;
}

const SignInModalContext = createContext<SignInModalContextType | null>(null);

function currentLocation(): string {
  return `${window.location.pathname}${window.location.search}`;
}

/**
 * Opens the modal when a server redirect asked for it with `?signin=1`,
 * then strips the flag so a refresh or a close does not bring it back.
 * Split out because reading search params needs its own Suspense boundary.
 */
function SignInParamWatcher({ onRequest }: { onRequest: (next: string | null) => void }) {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (searchParams.get(SIGN_IN_PARAM) !== '1') return;

    onRequest(searchParams.get('next'));

    const rest = new URLSearchParams(searchParams.toString());
    rest.delete(SIGN_IN_PARAM);
    rest.delete('next');
    const query = rest.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [onRequest, pathname, router, searchParams]);

  return null;
}

/**
 * Sign-in as a modal over whatever page the shopper is on.
 *
 * It lives in the shell, above every page, so it survives the navigation a
 * successful sign-in triggers; it closes itself once the server-resolved
 * user arrives rather than relying on the action resolving, which it does
 * not do when it redirects.
 */
export function SignInModalProvider({ children }: { children: React.ReactNode }) {
  const { isSignedIn } = useAuth();
  const [next, setNext] = useState<string | null>(null);

  const openSignIn = useCallback((target?: string) => setNext(target || currentLocation()), []);
  const closeSignIn = useCallback(() => setNext(null), []);
  const onRequest = useCallback((target: string | null) => setNext(target || '/'), []);

  useEffect(() => {
    if (isSignedIn) setNext(null);
  }, [isSignedIn]);

  return (
    <SignInModalContext.Provider value={{ openSignIn, closeSignIn }}>
      {children}
      <Suspense>
        <SignInParamWatcher onRequest={onRequest} />
      </Suspense>
      {next !== null && !isSignedIn && <SignInModal next={next} onClose={closeSignIn} />}
    </SignInModalContext.Provider>
  );
}

export function useSignInModal() {
  const context = useContext(SignInModalContext);

  if (!context) {
    throw new Error('useSignInModal must be used inside SignInModalProvider');
  }

  return context;
}
