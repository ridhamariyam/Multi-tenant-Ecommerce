import './globals.css';

import type { Metadata, Viewport } from 'next';
import type { CSSProperties, ReactNode } from 'react';

import StoreUnavailable from '@/components/StoreUnavailable';
import { BrandProvider } from '@/context/BrandContext';
import { mediaUrl } from '@/lib/media';
import { DEFAULT_OG_IMAGE, NO_INDEX, siteDescription, siteUrl } from '@/lib/seo';
import { FALLBACK_BRAND_NAME, getStorefront } from '@/lib/storefront/brand';

/**
 * Site-wide defaults for whichever brand this domain serves. A page sets
 * just `title: 'About'` and gets "About | <brand>"; Open Graph and Twitter
 * cards inherit the rest. No canonical here: it would be inherited by every
 * page and point them all at the home page. Pages that need one set it.
 */
export async function generateMetadata(): Promise<Metadata> {
  const state = await getStorefront();
  if (state.status === 'unknown') return { title: 'Store not available', robots: NO_INDEX };

  const brand = state.status === 'ok' ? state.brand : { name: FALLBACK_BRAND_NAME, description: null, faviconUrl: null };
  const name = brand.name;
  const description = siteDescription(brand);
  const favicon = mediaUrl(brand.faviconUrl);

  return {
    metadataBase: new URL(await siteUrl()),
    title: { default: name, template: `%s | ${name}` },
    description,
    applicationName: name,
    openGraph: {
      type: 'website',
      siteName: name,
      locale: 'en_IN',
      title: name,
      description,
      images: [{ ...DEFAULT_OG_IMAGE, alt: name }],
    },
    twitter: { card: 'summary_large_image', title: name, description, images: [DEFAULT_OG_IMAGE.url] },
    robots: { index: true, follow: true, 'max-image-preview': 'large' },
    formatDetection: { telephone: false },
    ...(favicon ? { icons: { icon: favicon } } : {}),
  };
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#ffffff',
};

/**
 * The only layout that renders the document itself. Nested layouts and the
 * root not-found page render inside <body>; a second <html> there breaks
 * hydration on every page.
 *
 * A domain no published store answers at gets the "not available" page
 * instead of any storefront content. A brand's colours replace the default
 * palette for everything under <body>.
 */
export default async function RootLayout({ children }: { children: ReactNode }) {
  const state = await getStorefront();
  const brand = state.status === 'ok' ? state.brand : null;
  const palette = {
    ...(brand?.primaryColor ? { '--cliq-midnight-navy': brand.primaryColor } : {}),
    ...(brand?.secondaryColor ? { '--cliq-champagne-gold': brand.secondaryColor } : {}),
  } as CSSProperties;

  return (
    <html lang="en-IN">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,500;1,400;1,500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={palette}>
        {state.status === 'unknown' ? (
          <StoreUnavailable />
        ) : (
          <BrandProvider brand={brand}>{children}</BrandProvider>
        )}
      </body>
    </html>
  );
}
