import type { MetadataRoute } from 'next';

import { POLICY_SLUGS } from './(storefront)/(info)/policies/slugs';
import { catalogueApi } from '@/lib/api/catalogue';
import { categorySlug } from '@/lib/catalogue/slug';
import { mediaUrl } from '@/lib/media';
import { siteUrl } from '@/lib/seo';
import type { Page } from '@/types/api';

const PAGE_SIZE = 100;
/* 50 x 100 products; Google's limit per sitemap is 50,000 URLs. */
const MAX_PAGES = 50;

type Entry = MetadataRoute.Sitemap[number];

const STATIC: { path: string; priority: number; changeFrequency: Entry['changeFrequency'] }[] = [
  { path: '/', priority: 1, changeFrequency: 'daily' },
  { path: '/products', priority: 0.9, changeFrequency: 'daily' },
  { path: '/about', priority: 0.4, changeFrequency: 'monthly' },
  { path: '/contact', priority: 0.4, changeFrequency: 'monthly' },
  { path: '/faq', priority: 0.4, changeFrequency: 'monthly' },
  ...POLICY_SLUGS.map(slug => ({ path: `/policies/${slug}`, priority: 0.2, changeFrequency: 'yearly' as const })),
];

/** Every page of a listing, stopping early on an error so the rest still ships. */
async function everyPage<T>(fetchPage: (page: number) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const result = await fetchPage(page).catch(() => null);
    if (!result) break;
    items.push(...result.items);
    if (page >= result.meta.total_pages) break;
  }
  return items;
}

/** Per brand (the request's domain). The catalogue is best-effort: an API outage still yields the static pages. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = await siteUrl();
  const [categories, products] = await Promise.all([
    everyPage(page => catalogueApi.listCategories({ page, page_size: PAGE_SIZE })),
    everyPage(page => catalogueApi.listProducts({ page, page_size: PAGE_SIZE })),
  ]);

  const now = new Date();
  return [
    ...STATIC.map(({ path, priority, changeFrequency }) => ({ url: `${base}${path}`, lastModified: now, priority, changeFrequency })),
    ...categories.map(category => ({
      url: `${base}/collections/${categorySlug(category.name)}`,
      changeFrequency: 'weekly' as const,
      priority: 0.8,
    })),
    ...products.flatMap(product => {
      if (!product.slug) return [];
      const image = mediaUrl(product.primary_image?.url);
      return [{
        url: `${base}/products/${encodeURIComponent(product.slug)}`,
        changeFrequency: 'weekly' as const,
        priority: 0.7,
        ...(image ? { images: [image] } : {}),
      }];
    }),
  ];
}
