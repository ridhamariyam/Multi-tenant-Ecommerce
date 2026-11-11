'use client';

import { useTransition } from 'react';

import { logout } from '@/lib/auth/actions';

/** Ends the session, revoking the refresh token server-side as well. */
export default function SignOutButton({ className = 'myorderFilterButton' }: { className?: string }) {
  const [pending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => startTransition(() => logout())}
      className={className}>
      {pending ? 'Signing out...' : 'Sign out'}
    </button>
  );
}
