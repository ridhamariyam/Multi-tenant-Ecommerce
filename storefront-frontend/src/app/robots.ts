import type { MetadataRoute } from 'next';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/account', '/my-orders', '/cart', '/checkout', '/order-confirmation', '/invoice', '/payment-history'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
