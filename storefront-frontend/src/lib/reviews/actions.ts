'use server';

import { revalidateTag } from 'next/cache';

import { reviewApi } from '@/lib/api/reviews';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { getActionAccessToken } from '@/lib/auth/session';
import type { CheckoutState } from '@/lib/orders/state';

function toState(error: unknown): CheckoutState {
  if (error instanceof ApiError) {
    if (error.isRateLimited) return { status: 'error', message: 'Too many requests. Try again shortly.' };
    return { status: 'error', message: error.message, fieldErrors: error.fieldErrors() };
  }

  if (error instanceof ApiUnreachableError) {
    return { status: 'error', message: 'Could not reach CliQ. Try again in a moment.' };
  }

  throw error;
}

export type CreateReviewResult =
  | { status: 'success'; reviewId: string }
  | { status: 'error'; message: string; fieldErrors?: Record<string, string> };

/**
 * Create the review itself (rating and text). Photos follow, one request
 * each, through `/reviews/[reviewId]/photos` -- a server action's body limit
 * is too small for them. Called from a submit handler, not a form action, so
 * React never resets the form behind the customer's back.
 */
export async function createReview(input: {
  productId: string;
  rating: number;
  title: string;
  comment: string;
}): Promise<CreateReviewResult> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to write a review.' };

  if (!input.productId) return { status: 'error', message: 'Missing product.' };
  if (!Number.isInteger(input.rating) || input.rating < 1 || input.rating > 5) {
    return { status: 'error', message: 'Please select a star rating.', fieldErrors: { rating: 'Please select a star rating' } };
  }

  try {
    const review = await reviewApi.create(token, {
      product_id: input.productId,
      rating: input.rating,
      title: input.title.trim() || null,
      comment: input.comment.trim() || null,
    });
    // No revalidation here: refreshing the page now would swap the form for
    // the new review before its photos are uploaded. `refreshProductReviews`
    // runs once they are in.
    return { status: 'success', reviewId: review.id };
  } catch (error) {
    const state = toState(error);
    return { status: 'error', message: state.message ?? 'Could not save your review.', fieldErrors: state.fieldErrors };
  }
}

/** Refresh the product's cached reviews once its photos are in. */
export async function refreshProductReviews(productId: string): Promise<void> {
  if (productId) revalidateTag(`reviews:${productId}`);
}

export async function deleteReview(
  _previous: CheckoutState,
  formData: FormData,
): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in again.' };

  const reviewId = String(formData.get('review_id') ?? '');
  const productId = String(formData.get('product_id') ?? '');

  try {
    await reviewApi.remove(token, reviewId);
  } catch (error) {
    return toState(error);
  }

  revalidateTag(`reviews:${productId}`);
  return { status: 'success', message: 'Review deleted' };
}
