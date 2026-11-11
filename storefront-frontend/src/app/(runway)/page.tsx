import type { Metadata } from 'next';

import { AuthProvider } from '@/context/AuthContext';
import { SignInModalProvider } from '@/context/SignInModalContext';
import { getCurrentUser } from '@/lib/auth/current-user';
import { getCart } from '@/lib/cart/read';

import RunwayClient from './_runway/RunwayClient';
import { loadRunwayLooks } from './_runway/load';
import { renderRunwayMarkup } from './_runway/markup';

export const metadata: Metadata = {
  title: 'Try the Look — CliQ.',
  description: 'Six looks, styled head to toe. Explore the runway, isolate a look, and tap a pin to see the piece.',
  other: { 'theme-color': '#ffffff' },
};

/** The cart badge and account link are per visitor, so this page is never statically cached. */
export const dynamic = 'force-dynamic';

export default async function RunwayHome() {
  const [looks, cart, user] = await Promise.all([
    loadRunwayLooks(),
    getCart().catch(() => null),
    getCurrentUser().catch(() => null),
  ]);
  const first = looks[0]?.model.src;

  return (
    <div className="cliq">
      {first ? <link rel="preload" as="image" href={first} fetchPriority="high" /> : null}
      {/* Sign-in redirects land on /?signin=1, so the modal has to live on this page too. */}
      <AuthProvider user={user}>
        <SignInModalProvider>
          <RunwayClient initialCount={cart?.item_count ?? 0} />
        </SignInModalProvider>
      </AuthProvider>
      <main dangerouslySetInnerHTML={{ __html: renderRunwayMarkup(looks) }} />
    </div>
  );
}
