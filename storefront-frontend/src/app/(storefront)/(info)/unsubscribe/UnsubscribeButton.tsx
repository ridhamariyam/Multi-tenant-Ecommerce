'use client';

import { useState } from 'react';

import { unsubscribeFromMarketing } from '@/lib/marketing/actions';

export default function UnsubscribeButton({ userId, token }: { userId: string; token: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle');
  const [message, setMessage] = useState<string | null>(null);

  if (state === 'done') return <p role="status">Done. You won&apos;t get marketing email from us any more.</p>;
  return (
    <div>
      <button
        type="button"
        className="btn btn-dark"
        disabled={state === 'busy'}
        onClick={async () => {
          setState('busy');
          const result = await unsubscribeFromMarketing(userId, token);
          setState(result.ok ? 'done' : 'error');
          setMessage(result.message);
        }}>
        {state === 'busy' ? 'Saving…' : 'Unsubscribe'}
      </button>
      {state === 'error' && <p role="alert">{message}</p>}
    </div>
  );
}
