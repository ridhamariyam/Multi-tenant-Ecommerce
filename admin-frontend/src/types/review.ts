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
  images: { id: string; image_url: string; alt_text: string | null; created_at: string }[];
}

export interface RatingSummary {
  product_id: string;
  average_rating: number;
  total_reviews: number;
  rating_distribution: Record<string, number>;
}

export interface ReviewRequest {
  id: string;
  order_id: string;
  customer_id: string;
  status: string;
  send_after: string;
  sent_at: string | null;
  created_at: string;
}
