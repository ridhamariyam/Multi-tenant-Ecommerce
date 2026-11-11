import { cache } from 'react';

import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';

/**
 * Which brand's store this request is for, from `GET /storefront/resolve`.
 *
 * The API answers from the visited domain (see lib/api/visited-host.ts), so
 * one deployment serves every brand: its own name, logo, colours and SEO.
 * Cached for a minute per domain (Next keys the fetch cache on headers).
 */

export interface StorefrontBrand {
  name: string;
  slug: string;
  description: string | null;
  logoUrl: string | null;
  faviconUrl: string | null;
  primaryColor: string | null;
  secondaryColor: string | null;
  currency: string;
  theme: string;
}

export type StorefrontState =
  | { status: 'ok'; brand: StorefrontBrand }
  /** No published store answers at this domain. */
  | { status: 'unknown' }
  /** The API could not be reached; pages render with fallbacks and fail on their own data. */
  | { status: 'unavailable' };

interface ResolveResponse {
  brand: { name: string; slug: string; description: string | null; logo_url: string | null; currency: string };
  store: {
    name: string;
    theme: string;
    logo_url: string | null;
    favicon_url: string | null;
    primary_color: string | null;
    secondary_color: string | null;
  };
}

/** Name used only when the API is down, so a page can still say something. */
export const FALLBACK_BRAND_NAME = 'CliQ.';

export const getStorefront = cache(async (): Promise<StorefrontState> => {
  try {
    const { brand, store } = await apiRequest<ResolveResponse>('/storefront/resolve', {
      revalidate: 60,
      tags: ['storefront'],
    });
    return {
      status: 'ok',
      brand: {
        name: store.name || brand.name,
        slug: brand.slug,
        description: brand.description,
        logoUrl: store.logo_url ?? brand.logo_url,
        faviconUrl: store.favicon_url,
        primaryColor: store.primary_color,
        secondaryColor: store.secondary_color,
        currency: brand.currency,
        theme: store.theme,
      },
    };
  } catch (error) {
    if (error instanceof ApiError && error.code === 'UNKNOWN_STOREFRONT') return { status: 'unknown' };
    if (error instanceof ApiError && error.isNotFound) return { status: 'unknown' };
    return { status: 'unavailable' };
  }
});

export async function getBrand(): Promise<StorefrontBrand | null> {
  const state = await getStorefront();
  return state.status === 'ok' ? state.brand : null;
}

export async function brandName(): Promise<string> {
  return (await getBrand())?.name ?? FALLBACK_BRAND_NAME;
}
