import type { MetadataRoute } from 'next';

import { siteDescription } from '@/lib/seo';
import { FALLBACK_BRAND_NAME, getBrand } from '@/lib/storefront/brand';

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const brand = (await getBrand()) ?? { name: FALLBACK_BRAND_NAME, description: null, primaryColor: null };
  return {
    name: brand.name,
    short_name: brand.name,
    description: siteDescription(brand),
    start_url: '/',
    display: 'standalone',
    background_color: '#ffffff',
    theme_color: brand.primaryColor ?? '#ffffff',
    icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' }],
  };
}
