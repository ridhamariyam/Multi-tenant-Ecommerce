/**
 * Where the CliQ API is, read lazily and validated.
 *
 * Resolved at call time rather than at module load so a missing variable
 * surfaces as a clear runtime error on the request that needed it, instead
 * of breaking an unrelated build.
 *
 * - On the server: API_INTERNAL_URL (a private address, e.g.
 *   http://api:8000/api/v1 inside Docker) or NEXT_PUBLIC_API_URL.
 * - In the browser: this storefront's own origin + /api/v1, proxied to the
 *   API by next.config.ts. Going through the storefront's domain is what
 *   tells the API which brand's store the shopper is on.
 */
export function apiBaseUrl(): string {
  if (typeof window !== 'undefined') return `${window.location.origin}/api/v1`;
  return serverApiUrl();
}

export function serverApiUrl(): string {
  const url = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL;

  if (!url) {
    throw new Error(
      'NEXT_PUBLIC_API_URL is not set. Copy .env.example to .env.local and point it at the CliQ API.',
    );
  }

  return url.replace(/\/+$/, '');
}

/** The API's public origin, for files it serves (/media/...). */
export function publicApiOrigin(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error('NEXT_PUBLIC_API_URL is not set.');
  return new URL(url).origin;
}
