import type { Metadata } from 'next';
import { headers } from 'next/headers';

/**
 * Shared SEO pieces for the storefront.
 *
 * Every brand is served from its own domain, so absolute URLs (canonical
 * links, Open Graph, sitemap, structured data) come from the request's host.
 * NEXT_PUBLIC_SITE_URL is only the fallback for when there is no request
 * (build time). Names and descriptions come from the resolved brand.
 */

export interface SeoBrand {
  name: string;
  description: string | null;
}

export function siteDescription(brand: SeoBrand): string {
  return plainText(brand.description, 200) || `Shop ${brand.name} online.`;
}

export async function siteUrl(): Promise<string> {
  const h = await headers();
  const host = h.get('x-forwarded-host')?.split(',')[0]?.trim() || h.get('host');
  if (!host) {
    return (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/+$/, '');
  }
  const forwarded = h.get('x-forwarded-proto')?.split(',')[0]?.trim();
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host) || host.endsWith('.localhost') || host.endsWith('.test');
  return `${forwarded || (local ? 'http' : 'https')}://${host}`;
}

export async function absoluteUrl(path: string): Promise<string> {
  if (/^https?:\/\//.test(path)) return path;
  return `${await siteUrl()}${path.startsWith('/') ? path : `/${path}`}`;
}

/** The default share card, served by app/og/route.tsx (drawn for the visited brand). */
export const DEFAULT_OG_IMAGE = { url: '/og', width: 1200, height: 630 };

/** A title without a trailing "| <brand>" -- the layout's template adds the brand once. */
export function withoutBrand(title: string, name: string): string {
  const brand = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\.$/, '\\.?');
  return title.replace(new RegExp(`\\s*[|\\-–—]\\s*${brand}\\s*$`, 'i'), '').trim();
}

/** For pages that are personal or transient: cart, checkout, account, orders, search. */
export const NO_INDEX: Metadata['robots'] = { index: false, follow: true };

/** Markdown or HTML squeezed into one line of plain text, cut at a word near `max`. */
export function plainText(value: string | null | undefined, max = 160): string {
  if (!value) return '';
  const text = value
    .replace(/<[^>]*>/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[#*_`>~|-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (text.length <= max) return text;
  const cut = text.slice(0, max - 1);
  return `${cut.slice(0, cut.lastIndexOf(' ') > max * 0.6 ? cut.lastIndexOf(' ') : cut.length)}…`;
}

/** schema.org structured data. `<` is escaped so no value can close the script tag. */
export function JsonLd({ data }: { data: Record<string, unknown> | Record<string, unknown>[] }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }}
    />
  );
}
