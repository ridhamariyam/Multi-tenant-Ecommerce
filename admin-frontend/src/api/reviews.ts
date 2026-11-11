import type { RatingSummary, Review, ReviewRequest } from "../types/review";
import { request } from "./client";

export const listModeration = (query: object) => request<Review[]>("/admin/reviews", { query });
export const listProductReviews = (productId: string) =>
  request<Review[]>(`/admin/reviews/product/${productId}`, { query: { page_size: 100 } });
export const getRatingSummary = (productId: string) =>
  request<RatingSummary>(`/admin/reviews/product/${productId}/summary`);
export const moderateReview = (id: string, isApproved: boolean) =>
  request<Review>(`/admin/reviews/${id}`, { method: "PATCH", body: { is_approved: isApproved } });
export const listReviewRequests = (query: object) =>
  request<ReviewRequest[]>("/admin/reviews/requests", { query });
export const dispatchReviewRequests = () =>
  request<{ sent: number; completed: number }>("/admin/reviews/requests/dispatch", { method: "POST" });
