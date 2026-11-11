import './_runway/runway.css';

import type { ReactNode } from 'react';

/**
 * The CliQ. runway homepage has its own header, so it sits outside the
 * (storefront) shell. app/layout.tsx still owns <html> and <body>.
 */
export default function RunwayLayout({ children }: { children: ReactNode }) {
  return children;
}
