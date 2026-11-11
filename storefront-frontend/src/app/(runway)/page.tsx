import type { Metadata } from 'next';

import { getCart } from '@/lib/cart/read';

import RunwayClient from './_runway/RunwayClient';
import { loadRunwayLooks } from './_runway/load';
import { renderRunwayMarkup } from './_runway/markup';

export const metadata: Metadata = {
  title: 'Try the Look — CliQ.',
  description: 'Six looks, styled head to toe. Explore the runway, isolate a look, and tap a pin to see the piece.',
  other: { 'theme-color': '#ffffff' },
};

/** The cart badge is per visitor, so this page is never statically cached. */
export const dynamic = 'force-dynamic';

export default async function RunwayHome() {
  const [looks, cart] = await Promise.all([loadRunwayLooks(), getCart().catch(() => null)]);
  const first = looks[0]?.model.src;

  return (
    <div className="cliq">
      {first ? <link rel="preload" as="image" href={first} fetchPriority="high" /> : null}
      <RunwayClient initialCount={cart?.item_count ?? 0} />
      <main dangerouslySetInnerHTML={{ __html: renderRunwayMarkup(looks) }} />
    </div>
  );
}
