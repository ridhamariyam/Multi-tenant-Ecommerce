export interface GuidancePreference {
  enabled: boolean;
  dismissed: string[];
}

export interface GuidanceControls {
  preference: GuidancePreference;
  setEnabled: (enabled: boolean) => void;
  resetDismissed: () => void;
}

export const DEFAULT_GUIDANCE: GuidancePreference = { enabled: true, dismissed: [] };

const descriptions: Record<string, { title: string; description: string }> = {
  "/": { title: "Dashboard", description: "See store highlights, sales trends, orders needing action, and stock alerts." },
  "/reports": { title: "Reports & analytics", description: "Explore sales and operational reports. Choose a date range to compare results." },
  "/orders": { title: "Orders", description: "View orders, update their status, and manage delivery." },
  "/customers": { title: "Customers", description: "View customer details, order history, and account status." },
  "/payments": { title: "Payments", description: "Review payment records, methods, and payment statuses." },
  "/cod": { title: "Cash on delivery", description: "Manage COD rules and review cash collection records." },
  "/coupons": { title: "Coupons", description: "Create promotional offers and check their validity and usage." },
  "/products": { title: "Products", description: "Create products, manage variants and stock, and archive products." },
  "/categories": { title: "Categories", description: "Organize products into categories and subcategories." },
  "/inventory": { title: "Inventory", description: "Check stock levels and identify products that need restocking." },
  "/reviews": { title: "Reviews", description: "Moderate customer reviews and manage review requests." },
  "/cms": { title: "Website content", description: "Update the homepage and other content customers see on the website." },
  "/delivery": { title: "Delivery", description: "Review delivery settings and shipping rules." },
  "/gst": { title: "GST & invoicing", description: "Manage seller GST details and view tax reports and invoices." },
  "/return-reasons": { title: "Return reasons", description: "Manage the reasons customers can select for returns." },
  "/integrations": { title: "Integrations", description: "Check which services are configured and what setup is still needed." },
  "/staff": { title: "Staff & permissions", description: "Manage staff accounts and choose what each person can access." },
  "/activity": { title: "Activity log", description: "Review admin actions and sign-in events for your workspace." },
  "/profile": { title: "Profile", description: "Review your admin account and contact information." },
  "/settings": { title: "Settings", description: "Find workspace settings and control page guidance here." },
};

export function guidanceForPath(pathname: string) {
  const section = pathname === "/" ? "/" : `/${pathname.split("/")[1]}`;
  if (!descriptions[section]) return null;
  const key = section === "/products" && pathname !== "/products"
    ? pathname === "/products/new" ? "/products/new" : "/products/detail"
    : section === "/orders" && pathname !== "/orders" ? "/orders/detail"
    : section === "/customers" && pathname !== "/customers" ? "/customers/detail" : section;
  return { key, ...descriptions[section] };
}

export function guidanceStorageKey(tenantId: string, userId: string) {
  return `cliq_admin_guidance_v1:${tenantId}:${userId}`;
}

export function readGuidance(key: string): GuidancePreference {
  try {
    const stored = JSON.parse(localStorage.getItem(key) ?? "null") as Partial<GuidancePreference> | null;
    if (!stored) return { ...DEFAULT_GUIDANCE, dismissed: [] };
    return {
      enabled: typeof stored.enabled === "boolean" ? stored.enabled : true,
      dismissed: Array.isArray(stored.dismissed) ? stored.dismissed.filter((value): value is string => typeof value === "string") : [],
    };
  } catch {
    return { ...DEFAULT_GUIDANCE, dismissed: [] };
  }
}

export function writeGuidance(key: string, preference: GuidancePreference) {
  try { localStorage.setItem(key, JSON.stringify(preference)); } catch { /* Keep the in-memory preference. */ }
}
