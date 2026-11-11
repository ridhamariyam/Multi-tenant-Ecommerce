export type ContentStatus = "DRAFT" | "PUBLISHED";
export type SectionType =
  | "HERO_BANNER"
  | "PROMO_STRIP"
  | "FEATURED_PRODUCTS"
  | "NEW_ARRIVALS"
  | "BESTSELLERS"
  | "SEASONAL";
export const SECTION_TYPES: SectionType[] = [
  "HERO_BANNER",
  "PROMO_STRIP",
  "FEATURED_PRODUCTS",
  "NEW_ARRIVALS",
  "BESTSELLERS",
  "SEASONAL",
];
export type PageType =
  | "ABOUT"
  | "CONTACT"
  | "SHIPPING_POLICY"
  | "RETURN_POLICY"
  | "PRIVACY_POLICY"
  | "TERMS"
  | "FAQ"
  | "CUSTOM";
export const PAGE_TYPES: PageType[] = [
  "ABOUT",
  "CONTACT",
  "SHIPPING_POLICY",
  "RETURN_POLICY",
  "PRIVACY_POLICY",
  "TERMS",
  "FAQ",
  "CUSTOM",
];
export type LinkType = "URL" | "HOME" | "CATEGORY" | "PRODUCT" | "PAGE" | "BLOG_POST" | "BLOG_INDEX" | "FAQ";
export const LINK_TYPES: LinkType[] = ["URL", "HOME", "CATEGORY", "PRODUCT", "PAGE", "BLOG_POST", "BLOG_INDEX", "FAQ"];

export interface BannerItem {
  image_url: string | null;
  mobile_image_url: string | null;
  heading: string | null;
  text: string | null;
  link_url: string | null;
  cta_label: string | null;
  alt_text: string | null;
}

export interface SectionSettings {
  product_ids: string[] | null;
  category_id: string | null;
  limit: number;
  days: number;
  countdown_ends_at: string | null;
}

export interface HomeSection {
  id: string;
  section_type: SectionType;
  title: string | null;
  subtitle: string | null;
  is_active: boolean;
  position: number;
  starts_at: string | null;
  ends_at: string | null;
  is_live: boolean;
  items: BannerItem[];
  settings: SectionSettings;
  updated_at: string;
}

interface Publishable {
  status: ContentStatus;
  published_at: string | null;
  is_live: boolean;
  created_at: string;
  updated_at: string;
}

export interface CmsPage extends Publishable {
  id: string;
  slug: string;
  title: string;
  page_type: PageType;
  body: string;
  seo_title: string | null;
  seo_description: string | null;
}

export interface FaqCategory {
  id: string;
  name: string;
  position: number;
  is_active: boolean;
}

export interface Faq extends Publishable {
  id: string;
  category_id: string;
  question: string;
  answer: string;
  position: number;
}

export interface NavItem {
  id: string;
  menu: "HEADER" | "FOOTER";
  label: string;
  link_type: LinkType;
  target: string | null;
  href: string;
  parent_id: string | null;
  position: number;
  is_active: boolean;
  open_in_new_tab: boolean;
  children: NavItem[];
}

export interface BlogPost extends Publishable {
  id: string;
  slug: string;
  title: string;
  excerpt: string | null;
  content: string;
  featured_image_url: string | null;
  author_name: string | null;
  category: string | null;
  tags: string[];
  seo_title: string | null;
  seo_description: string | null;
}

export interface Media {
  id: string;
  url: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  alt_text: string | null;
  created_at: string;
}

export const SOCIAL_NETWORKS = ["instagram", "facebook", "x", "youtube", "pinterest", "tiktok", "linkedin"] as const;
export type SocialNetwork = (typeof SOCIAL_NETWORKS)[number];

export interface SiteSettings {
  logo_url: string | null;
  logo_alt: string | null;
  tagline: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  whatsapp_number: string | null;
  address: string | null;
  social_links: Partial<Record<SocialNetwork, string>>;
  copyright_text: string | null;
  updated_at?: string | null;
}
