import { apiBaseUrl } from '@/lib/env';

/**
 * Absolute URL for an image the API serves.
 *
 * Uploaded files come back as "/media/<tenant>/<file>" -- a path relative to
 * the API, not to the storefront. Rendered as-is the browser asks the
 * frontend host for it and gets a 404, so the API's origin goes back on.
 * Anything already absolute (a CDN, an external URL) passes through
 * untouched.
 */
export function mediaUrl(url: string): string;
export function mediaUrl(url: string | null | undefined): string | null;
export function mediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:')) return url;

  const origin = new URL(apiBaseUrl()).origin;
  return `${origin}${url.startsWith('/') ? '' : '/'}${url}`;
}
