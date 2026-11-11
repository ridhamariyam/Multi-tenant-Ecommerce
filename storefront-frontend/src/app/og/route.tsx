import { ImageResponse } from 'next/og';

import { FALLBACK_BRAND_NAME, getBrand } from '@/lib/storefront/brand';

/** The default share card (1200x630) for this domain's brand, for pages without an image of their own. */
export async function GET() {
  const brand = await getBrand();
  const name = brand?.name ?? FALLBACK_BRAND_NAME;
  const tagline = brand ? (brand.description ?? '').split(/(?<=[.!?])\s/)[0].slice(0, 80) : '';
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
          background: brand?.primaryColor ?? '#0f1238',
          color: brand?.secondaryColor ?? '#f3ead8',
        }}
      >
        <div style={{ fontSize: name.length > 12 ? 104 : 168, fontWeight: 700, letterSpacing: -4 }}>{name}</div>
        {tagline ? <div style={{ fontSize: 40, marginTop: 12, opacity: 0.85 }}>{tagline}</div> : null}
      </div>
    ),
    { width: 1200, height: 630, headers: { 'Cache-Control': 'public, max-age=3600', Vary: 'Host' } },
  );
}
