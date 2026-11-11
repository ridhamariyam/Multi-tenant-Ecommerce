import { P } from "./auth/permissions";

export interface NavItem {
  path: string;
  label: string;
  permission?: string;
  adminOnly?: boolean;
}

// Sidebar structure. Each screen's route in App.tsx uses the same permission.
export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { path: "/", label: "Dashboard", permission: P.dashboard },
      { path: "/reports", label: "Reports & analytics", permission: P.reports },
    ],
  },
  {
    title: "Sales",
    items: [
      { path: "/orders", label: "Orders", permission: P.ordersView },
      { path: "/customers", label: "Customers", permission: P.customersView },
      { path: "/payments", label: "Payments", permission: P.paymentsView },
      { path: "/cod", label: "Cash on delivery", permission: P.paymentsView },
      { path: "/coupons", label: "Coupons", permission: P.couponsView },
    ],
  },
  {
    title: "Catalogue",
    items: [
      { path: "/products", label: "Products", permission: P.catalogueView },
      { path: "/categories", label: "Categories", permission: P.catalogueView },
      { path: "/inventory", label: "Inventory", permission: P.catalogueView },
      { path: "/reviews", label: "Reviews", permission: P.reviewsView },
    ],
  },
  {
    title: "Content",
    items: [{ path: "/cms", label: "Website content", permission: P.cmsView }],
  },
  {
    title: "Settings",
    items: [
      { path: "/delivery", label: "Delivery", permission: P.settingsView },
      { path: "/gst", label: "GST & invoicing", permission: P.settingsView },
      { path: "/return-reasons", label: "Return reasons", permission: P.ordersView },
      { path: "/integrations", label: "Integrations", permission: P.settingsView },
      { path: "/staff", label: "Staff & permissions", adminOnly: true },
      { path: "/activity", label: "Activity log", permission: P.audit },
    ],
  },
];
