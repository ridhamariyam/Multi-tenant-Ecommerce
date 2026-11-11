// Mirrors the backend's permission keys (app/auth/permissions.py).
export const P = {
  dashboard: "dashboard.view",
  ordersView: "orders.view",
  ordersManage: "orders.manage",
  catalogueView: "catalogue.view",
  catalogueManage: "catalogue.manage",
  customersView: "customers.view",
  customersManage: "customers.manage",
  couponsView: "coupons.view",
  couponsManage: "coupons.manage",
  reviewsView: "reviews.view",
  reviewsManage: "reviews.manage",
  paymentsView: "payments.view",
  paymentsManage: "payments.manage",
  settingsView: "settings.view",
  settingsManage: "settings.manage",
  reports: "reports.view",
  cmsView: "cms.view",
  cmsManage: "cms.manage",
  cmsPublish: "cms.publish",
  audit: "audit.view",
} as const;

