import { ImageResponse } from 'next/og';

import { SITE_NAME } from '@/lib/seo';

/** The default share card (1200x630) for pages without an image of their own. */
export function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          background: '#0f1238',
          color: '#f3ead8',
        }}
      >
        <div style={{ fontSize: 168, fontWeight: 700, letterSpacing: -6 }}>{SITE_NAME}</div>
        <div style={{ fontSize: 40, marginTop: 12, opacity: 0.85 }}>Complete looks, styled head to toe.</div>
      </div>
    ),
    { width: 1200, height: 630, headers: { 'Cache-Control': 'public, max-age=86400, immutable' } },
  );
}
