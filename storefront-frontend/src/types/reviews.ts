export const MIN_RATING = 1;
export const MAX_RATING = 5;
export const MAX_IMAGES_PER_REVIEW = 5;

export interface ReviewImage {
  id: string;
  image_url: string;
  alt_text: string | null;
  created_at: string;
}

export interface Review {
  id: string;
  product_id: string | null;
  user_id: string | null;
  order_id: string | null;
  rating: number;
  title: string | null;
  comment: string | null;
  is_verified_purchase: boolean;
  is_approved: boolean;
  created_at: string;
  images: ReviewImage[];
}

export interface RatingSummary {
  product_id: string;
  average_rating: number;
  total_reviews: number;
  /** Star value (1-5) to the number of reviews awarding it. */
  rating_distribution: Record<string, number>;
}

export interface ReviewCreate {
  product_id: string;
  rating: number;
  title?: string | null;
  comment?: string | null;
  images?: { image_url: string; alt_text?: string | null }[];
}

export interface ReviewUpdate {
  rating?: number;
  title?: string | null;
  comment?: string | null;
}
