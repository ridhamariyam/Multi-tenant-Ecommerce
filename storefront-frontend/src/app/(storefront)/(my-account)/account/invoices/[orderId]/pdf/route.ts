import { NextResponse, type NextRequest } from 'next/server';

import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';
import { apiBaseUrl } from '@/lib/env';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Download the GST invoice PDF for one of the customer's orders.
 *
 * The token lives in an httpOnly cookie, so the browser cannot call
 * `GET /orders/{id}/invoice/pdf` itself; this streams the backend's PDF
 * through unchanged. The backend renders it from the stored order and only
 * for the order's own customer -- anyone else gets its 404.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  if (!UUID.test(orderId)) return new NextResponse('Not found', { status: 404 });

  const token = await getAccessToken();
  if (!token) return NextResponse.redirect(new URL(signInUrl('/account/orders'), request.url));

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/orders/${orderId}/invoice/pdf`, {
      headers: { Accept: 'application/pdf', Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return new NextResponse('Could not reach CliQ. Try again in a moment.', { status: 502 });
  }

  if (upstream.status === 401) {
    return NextResponse.redirect(new URL(signInUrl('/account/orders'), request.url));
  }
  if (upstream.status === 403 || upstream.status === 404) {
    return new NextResponse('Not found', { status: 404 });
  }
  if (!upstream.ok || !upstream.body) {
    return new NextResponse('The invoice could not be generated. Try again in a moment.', { status: 502 });
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/pdf',
      'Content-Disposition': upstream.headers.get('Content-Disposition') ?? 'attachment; filename="invoice.pdf"',
      'Cache-Control': 'private, no-store',
    },
  });
}
