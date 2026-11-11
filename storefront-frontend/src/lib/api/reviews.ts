import { apiRequest, apiRequestPage } from '@/lib/api/client';
import type { Page, PageParams } from '@/types/api';
import type { RatingSummary, Review, ReviewCreate, ReviewUpdate } from '@/types/reviews';

const REVIEW_REVALIDATE = 60;

export const reviewApi = {
  /** Approved reviews for a product. Public. */
  listForProduct(productId: string, params: PageParams = {}): Promise<Page<Review>> {
    return apiRequestPage<Review>(`/reviews/product/${productId}`, {
      query: { ...params },
      revalidate: REVIEW_REVALIDATE,
      tags: [`reviews:${productId}`],
    });
  },

  summary(productId: string): Promise<RatingSummary> {
    return apiRequest<RatingSummary>(`/reviews/product/${productId}/summary`, {
      revalidate: REVIEW_REVALIDATE,
      tags: [`reviews:${productId}`],
    });
  },

  /** Only a delivered product may be reviewed, once per customer. */
  create(token: string, data: ReviewCreate): Promise<Review> {
    return apiRequest<Review>('/reviews', {
      method: 'POST',
      body: data,
      token,
      cache: 'no-store',
    });
  },

  update(token: string, reviewId: string, data: ReviewUpdate): Promise<Review> {
    return apiRequest<Review>(`/reviews/${reviewId}`, {
      method: 'PATCH',
      body: data,
      token,
      cache: 'no-store',
    });
  },

  /**
   * Attach one photo to the caller's own review. The backend checks the
   * author, the type (JPEG/PNG/WebP), that it decodes as an image, its size
   * and the per-review limit; nothing about the file is trusted here.
   */
  uploadImage(token: string, reviewId: string, file: Blob, filename: string, altText: string | null): Promise<Review> {
    const formData = new FormData();
    formData.set('file', file, filename);
    if (altText) formData.set('alt_text', altText);
    return apiRequest<Review>(`/reviews/${reviewId}/images/upload`, {
      method: 'POST',
      formData,
      token,
      cache: 'no-store',
    });
  },

  remove(token: string, reviewId: string): Promise<null> {
    return apiRequest<null>(`/reviews/${reviewId}`, {
      method: 'DELETE',
      token,
      cache: 'no-store',
    });
  },
};
