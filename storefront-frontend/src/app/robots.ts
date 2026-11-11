import type { MetadataRoute } from 'next';

import { siteUrl } from '@/lib/seo';

/** Per brand: the sitemap lives on whichever domain this request came in on. */
export default async function robots(): Promise<MetadataRoute.Robots> {
  const base = await siteUrl();
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: [
        '/account',
        '/cart',
        '/checkout',
        '/order-confirmation',
        '/track-order',
        '/search-result',
        '/wishlist',
        '/api/',
        '/*?signin=',
      ],
    },
    sitemap: `${base}/sitemap.xml`,
  };
}
