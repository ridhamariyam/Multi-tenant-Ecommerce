import './globals.css';

import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import { DEFAULT_OG_IMAGE, SITE_DESCRIPTION, SITE_NAME, siteUrl } from '@/lib/seo';

/**
 * Site-wide defaults. A page sets just `title: 'About'` and gets
 * "About | CliQ."; Open Graph and Twitter cards inherit the rest.
 * No canonical here: it would be inherited by every page and point them
 * all at the home page. Pages that should have one set their own.
 */
export async function generateMetadata(): Promise<Metadata> {
  return {
    metadataBase: new URL(await siteUrl()),
    title: { default: SITE_NAME, template: `%s | ${SITE_NAME}` },
    description: SITE_DESCRIPTION,
    applicationName: SITE_NAME,
    openGraph: {
      type: 'website',
      siteName: SITE_NAME,
      locale: 'en_IN',
      title: SITE_NAME,
      description: SITE_DESCRIPTION,
      images: [DEFAULT_OG_IMAGE],
    },
    twitter: { card: 'summary_large_image', title: SITE_NAME, description: SITE_DESCRIPTION, images: [DEFAULT_OG_IMAGE.url] },
    robots: { index: true, follow: true, 'max-image-preview': 'large' },
    formatDetection: { telephone: false },
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
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,500;1,400;1,500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
