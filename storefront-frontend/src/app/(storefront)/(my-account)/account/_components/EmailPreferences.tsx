'use client';

import { useState } from 'react';

import { setMarketingConsent } from '@/lib/auth/actions';

/** Marketing email consent. Order emails are sent regardless. */
export default function EmailPreferences({ initial, hasEmail }: { initial: boolean; hasEmail: boolean }) {
  const [optIn, setOptIn] = useState(initial);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function change(next: boolean) {
    if (next && !hasEmail && !/^\S+@\S+\.\S+$/.test(email.trim())) {
      setMessage('Add your email first.');
      return;
    }
    setBusy(true);
    const result = await setMarketingConsent(next, hasEmail ? null : email.trim());
    setBusy(false);
    if (result.ok) setOptIn(next);
    setMessage(result.ok ? (next ? 'You will get new arrivals and offers by email.' : 'Marketing email turned off.') : result.message);
  }

  return (
    <div style={{ marginTop: 16 }}>
      {!hasEmail && !optIn && (
        <label style={{ display: 'block', marginBottom: 8 }}>
          Email
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        </label>
      )}
      <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={optIn} disabled={busy} onChange={e => change(e.target.checked)} />
        Email me new arrivals and offers
      </label>
      {message && <small role="status">{message}</small>}
    </div>
  );
}
