// The CliQ website, area by area, and where each part is managed.
//
// "cms" parts are edited in a tab of this section. "storefront" parts are pages
// designed and built in the storefront itself: they are listed here so the
// admin sees the whole site, but nothing in the CMS changes them.
//
// Paths are the storefront's own routes; update this list when the storefront's
// pages or links change.

export type CmsTab = "overview" | "site" | "home" | "pages" | "faqs" | "navigation" | "blog" | "media";

export type ManagedBy = { cms: CmsTab } | "storefront";

export interface WebsitePart {
  name: string;
  path: string | null; // where it is on the website; null when it has no page of its own
  managedBy: ManagedBy;
  note: string;
}

export interface WebsiteArea {
  area: string;
  parts: WebsitePart[];
}

export const TAB_LABELS: Record<CmsTab, string> = {
  overview: "Overview",
  home: "Homepage",
  site: "Logo & contact",
  pages: "Pages",
  faqs: "FAQs",
  navigation: "Menus",
  blog: "Blog",
  media: "Media library",
};

/** Information pages built in the storefront. Read-only here. */
export const STOREFRONT_PAGES: WebsitePart[] = [
  { name: "About Us", path: "/about-us", managedBy: "storefront", note: "Designed in the storefront." },
  { name: "Contact Us", path: "/contact-us-1", managedBy: "storefront", note: "Designed in the storefront." },
  { name: "FAQ", path: "/faqs-1", managedBy: "storefront", note: "Designed in the storefront. Questions added in the FAQs tab appear at /faq." },
  { name: "Gift Vouchers", path: "/our-gift-vouchers", managedBy: "storefront", note: "Designed in the storefront." },
  { name: "Shipping Policy", path: null, managedBy: "storefront", note: "No page of its own yet — the footer's “Shipping & Returns” link opens the FAQ page." },
  { name: "Return / Refund Policy", path: null, managedBy: "storefront", note: "No page of its own yet — the footer's “Shipping & Returns” link opens the FAQ page." },
  { name: "Privacy Policy", path: null, managedBy: "storefront", note: "Not on the website yet." },
  { name: "Terms & Conditions", path: null, managedBy: "storefront", note: "Not on the website yet." },
];

export const WEBSITE_MAP: WebsiteArea[] = [
  {
    area: "Homepage",
    parts: [
      { name: "Hero banners", path: "/", managedBy: { cms: "home" }, note: "The website shows its built-in banner until a hero banner is published here." },
      { name: "Promotional strips", path: "/", managedBy: { cms: "home" }, note: "Announcement bars." },
      { name: "Product sections", path: "/", managedBy: { cms: "home" }, note: "Featured, new arrivals, bestsellers and seasonal shelves." },
    ],
  },
  { area: "Information pages", parts: STOREFRONT_PAGES },
  {
    area: "Header",
    parts: [
      { name: "Logo", path: null, managedBy: { cms: "site" }, note: "Without a logo the website shows the name “CliQ.”." },
      { name: "Navigation menu", path: null, managedBy: { cms: "navigation" }, note: "The website shows its built-in links until a header menu is set up." },
    ],
  },
  {
    area: "Footer",
    parts: [
      { name: "Links", path: null, managedBy: { cms: "navigation" }, note: "The website shows its built-in columns until a footer menu is set up." },
      { name: "Tagline, contact details, social links, copyright", path: null, managedBy: { cms: "site" }, note: "" },
    ],
  },
  {
    area: "Articles & help",
    parts: [
      { name: "Blog / articles", path: "/blog", managedBy: { cms: "blog" }, note: "" },
      { name: "FAQ questions", path: "/faq", managedBy: { cms: "faqs" }, note: "" },
      { name: "Your own extra pages", path: "/pages/…", managedBy: { cms: "pages" }, note: "Pages you create in the Pages tab." },
    ],
  },
  {
    area: "Media",
    parts: [{ name: "Images", path: null, managedBy: { cms: "media" }, note: "Pictures used by banners, articles and the logo." }],
  },
];
