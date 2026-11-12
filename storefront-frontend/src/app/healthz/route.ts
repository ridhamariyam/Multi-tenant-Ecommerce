// Liveness for the hosting platform's health check: no brand lookup, no API call.
export const dynamic = 'force-static';

export function GET() {
  return new Response('ok', { headers: { 'content-type': 'text/plain', 'cache-control': 'no-store' } });
}
