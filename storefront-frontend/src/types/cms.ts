export interface StorefrontBannerItem {
  image_url: string | null;
  mobile_image_url: string | null;
  heading: string | null;
  text: string | null;
  link_url: string | null;
  cta_label: string | null;
  alt_text: string | null;
}

export interface StorefrontHomeSection {
  id: string;
  section_type: 'HERO_BANNER' | 'PROMO_STRIP' | 'FEATURED_PRODUCTS' | 'NEW_ARRIVALS' | 'BESTSELLERS' | 'SEASONAL';
  title: string | null;
  subtitle: string | null;
  position: number;
  ends_at: string | null;
  items: StorefrontBannerItem[];
}
