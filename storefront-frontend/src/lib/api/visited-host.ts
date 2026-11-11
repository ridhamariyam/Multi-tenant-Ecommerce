import { unstable_rethrow } from 'next/navigation';

/**
 * The domain the shopper is on, for server-side API calls.
 *
 * The API picks the brand from the host it is asked about. Server-side calls
 * go straight to the API, so they say which storefront domain they are for
 * with X-Forwarded-Host (honoured when the API has TRUST_FORWARDED_HOST).
 * Next keys its fetch cache on request headers, so cached catalogue reads
 * stay separate per brand.
 *
 * Null in the browser (calls go through the same-origin /api/v1 proxy,
 * which sets the header itself) and outside a request (build time).
 */
export async function visitedHost(): Promise<string | null> {
  if (typeof window !== 'undefined') return null;
  try {
    const { headers } = await import('next/headers');
    return (await headers()).get('host');
  } catch (error) {
    // Let Next's own signals (dynamic rendering, redirects) through.
    unstable_rethrow(error);
    return null;
  }
}

/**
 * The shopper's IP, for server-side API calls.
 *
 * Server-side calls reach the API from the storefront container, so without
 * this every shopper of a brand would share one per-IP rate limit (guest
 * checkout, order tracking, search, sign-in). Caddy sets X-Forwarded-For to
 * the connecting client and ignores any value the client sent, so the first
 * entry is the shopper. Null in the browser and outside a request.
 */
export async function visitorIp(): Promise<string | null> {
  if (typeof window !== 'undefined') return null;
  try {
    const { headers } = await import('next/headers');
    return forwardedClientIp((await headers()).get('x-forwarded-for'));
  } catch (error) {
    unstable_rethrow(error);
    return null;
  }
}

/** First address in an X-Forwarded-For value (the original client). */
export function forwardedClientIp(value: string | null | undefined): string | null {
  return value?.split(',')[0]?.trim() || null;
}
