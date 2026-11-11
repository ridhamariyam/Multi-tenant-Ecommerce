import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { NO_INDEX } from '@/lib/seo';

/** Personal pages: never indexed, whatever the page itself sets. */
export const metadata: Metadata = { title: 'Order confirmed', robots: NO_INDEX };

export default function PrivateLayout({ children }: { children: ReactNode }) {
  return children;
}
