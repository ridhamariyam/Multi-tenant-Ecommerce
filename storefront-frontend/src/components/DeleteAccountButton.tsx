'use client';

import { useTransition } from 'react';

import { deleteAccount } from '@/lib/auth/actions';


export default function DeleteAccountButton() {
  const [pending, startTransition] = useTransition();

  function handleClick() {
    const confirmed = window.confirm(
      'Delete your account? Your past orders stay on record, but your profile and addresses are gone for good. This cannot be undone.',
    );
    if (!confirmed) return;

    startTransition(() => deleteAccount());
  }

  return (
    <button
      type="button"
      disabled={pending}
      onClick={handleClick}
      className="myorderFilterButton"
      style={{ color: '#cc0d39', borderColor: '#cc0d39' }}>
      {pending ? 'Deleting...' : 'Delete account'}
    </button>
  );
}
