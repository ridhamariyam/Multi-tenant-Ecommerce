import type { MetadataRoute } from 'next';

import { POLICY_SLUGS } from './(storefront)/(info)/policies/slugs';
import { catalogueApi } from '@/lib/api/catalogue';
import { categorySlug } from '@/lib/catalogue/slug';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';
const FETCH_SIZE = 100;
const STATIC_PATHS = ['/', '/products', '/about', '/contact', '/faq', ...POLICY_SLUGS.map(slug => `/policies/${slug}`)];

/** The catalogue is best-effort: an API outage still yields the static pages. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [categories, products] = await Promise.all([
    catalogueApi.listCategories({ page_size: FETCH_SIZE }).catch(() => null),
    catalogueApi.listProducts({ page_size: FETCH_SIZE }).catch(() => null),
  ]);

  const paths = [
    ...STATIC_PATHS,
    ...(categories?.items ?? []).map(category => `/collections/${categorySlug(category.name)}`),
    ...(products?.items ?? []).flatMap(product => (product.slug ? [`/products/${encodeURIComponent(product.slug)}`] : [])),
  ];
  return paths.map(path => ({ url: `${SITE_URL}${path}` }));
}
