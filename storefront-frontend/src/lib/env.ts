/**
 * The API origin, read once and validated.
 *
 * Resolved lazily rather than at module load so a missing variable surfaces
 * as a clear runtime error on the request that needed it, instead of
 * breaking an unrelated build.
 */
export function apiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;

  if (!url) {
    throw new Error(
      'NEXT_PUBLIC_API_URL is not set. Copy .env.example to .env.local and point it at the CliQ API.',
    );
  }

  return url.replace(/\/+$/, '');
}
