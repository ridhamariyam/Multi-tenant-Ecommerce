import { NextResponse, type NextRequest } from 'next/server';

import { reviewApi } from '@/lib/api/reviews';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { getActionAccessToken } from '@/lib/auth/session';
import type { ReviewImage } from '@/types/reviews';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACCEPTED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
/** Mirrors the backend's `max_upload_bytes`; the backend enforces it regardless. */
const MAX_BYTES = 5 * 1024 * 1024;

function fail(status: number, message: string) {
  return NextResponse.json({ message }, { status });
}

/**
 * Upload one photo to the signed-in customer's own review.
 *
 * Photos cannot go through a server action (its request body is capped well
 * below a phone photo), so the browser posts each one here and it is passed
 * to the backend's `POST /reviews/{id}/images/upload` with the session token.
 * The backend is the authority: it checks that the review is the caller's,
 * the image type, that the file really decodes as an image, its size and the
 * per-review photo limit. The checks here only fail fast with a clear message.
 */
export async function POST(request: NextRequest, { params }: { params: Promise<{ reviewId: string }> }) {
  // The session cookie is SameSite=Lax, which already keeps cross-site posts
  // from carrying it; requiring a same-origin request makes that explicit.
  const origin = request.headers.get('origin');
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host');
  let sameOrigin = false;
  try {
    sameOrigin = !!origin && !!host && new URL(origin).host === host;
  } catch {
    sameOrigin = false;
  }
  if (!sameOrigin) return fail(403, 'Invalid request origin.');

  const { reviewId } = await params;
  if (!UUID.test(reviewId)) return fail(404, 'Review not found.');

  const token = await getActionAccessToken();
  if (!token) return fail(401, 'Sign in to add photos to your review.');

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return fail(400, 'No photo was received.');
  }

  const file = form.get('file');
  if (!(file instanceof File) || file.size === 0) return fail(400, 'No photo was received.');
  if (!ACCEPTED_TYPES.has(file.type)) return fail(415, 'Photos must be JPEG, PNG or WebP.');
  if (file.size > MAX_BYTES) return fail(413, 'Each photo must be 5 MB or smaller.');

  const altText = String(form.get('alt_text') ?? '').trim().slice(0, 255) || null;

  try {
    const review = await reviewApi.uploadImage(token, reviewId, file, file.name || 'photo', altText);
    const image: ReviewImage | undefined = review.images[review.images.length - 1];
    return NextResponse.json({ image }, { status: 201 });
  } catch (error) {
    if (error instanceof ApiError) return fail(error.status, error.message);
    if (error instanceof ApiUnreachableError) return fail(502, 'Could not reach CliQ. Try again in a moment.');
    throw error;
  }
}
