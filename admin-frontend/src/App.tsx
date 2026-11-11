import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequirePermission } from "./auth/Guards";
import { P } from "./auth/permissions";
import AdminLayout from "./layouts/AdminLayout";
import Login from "./screens/Login";
import { Profile, Settings } from "./screens/Account";
import DashboardOverview from "./features/overview/DashboardOverview";
import OrderSection from "./features/orders/OrderSection";
import OrderDetail from "./features/orders/OrderDetail";
import CustomerSection from "./features/customers/CustomerSection";
import CustomerDetail from "./features/customers/CustomerDetail";
import PaymentSection from "./features/payments/PaymentSection";
import CodSection from "./features/cod/CodSection";
import CouponSection from "./features/coupons/CouponSection";
import ProductSection from "./features/products/ProductSection";
import ProductManager from "./features/products/ProductManager";
import CategorySection from "./features/categories/CategorySection";
import InventorySection from "./features/inventory/InventorySection";
import ReviewSection from "./features/reviews/ReviewSection";
import CmsSection from "./features/cms/CmsSection";
import ShippingSection from "./features/shipping/ShippingSection";
import TaxSection from "./features/tax/TaxSection";
import IntegrationsSection from "./features/settings/IntegrationsSection";
import UserSection from "./features/users/UserSection";
import AuditLogSection from "./features/audit/AuditLogSection";
import ReportsSection from "./features/reports/ReportsSection";
import ReturnReasonsSection from "./features/returns/ReturnReasonsSection";

const guard = (permission: string | null, element: ReactNode) => (
  <RequirePermission permission={permission ?? undefined} adminOnly={permission === null}>
    {element}
  </RequirePermission>
);

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/signin" element={<Login />} />
      <Route path="/login" element={<Navigate to="/signin" replace />} />
      <Route
        element={
          <RequireAuth>
            <AdminLayout />
          </RequireAuth>
        }
      >
        <Route index element={guard(P.dashboard, <DashboardOverview />)} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="profile" element={<Profile />} />
        <Route path="settings" element={<Settings />} />
        <Route path="notifications" element={<Navigate to="/" replace />} />
        <Route path="reports" element={guard(P.reports, <ReportsSection />)} />
        <Route path="analytics" element={guard(P.reports, <ReportsSection />)} />
        <Route path="orders" element={guard(P.ordersView, <OrderSection />)} />
        <Route path="orders/:orderId" element={guard(P.ordersView, <OrderDetail />)} />
        <Route path="customers" element={guard(P.customersView, <CustomerSection />)} />
        <Route path="customers/:customerId" element={guard(P.customersView, <CustomerDetail />)} />
        <Route path="payments" element={guard(P.paymentsView, <PaymentSection />)} />
        <Route path="cod" element={guard(P.paymentsView, <CodSection />)} />
        <Route path="coupons" element={guard(P.couponsView, <CouponSection />)} />
        <Route path="discounts" element={guard(P.couponsView, <CouponSection />)} />
        <Route path="products" element={guard(P.catalogueView, <ProductSection />)} />
        <Route path="products/new" element={guard(P.catalogueView, <ProductManager />)} />
        <Route path="products/:productId" element={guard(P.catalogueView, <ProductManager />)} />
        <Route path="products/:productId/edit" element={guard(P.catalogueView, <ProductManager />)} />
        <Route path="categories" element={guard(P.catalogueView, <CategorySection />)} />
        <Route path="inventory" element={guard(P.catalogueView, <InventorySection />)} />
        <Route path="reviews" element={guard(P.reviewsView, <ReviewSection />)} />
        <Route path="cms" element={guard(P.cmsView, <CmsSection />)} />
        <Route path="banners" element={guard(P.cmsView, <CmsSection />)} />
        <Route path="content" element={guard(P.cmsView, <CmsSection />)} />
        <Route path="delivery" element={guard(P.settingsView, <ShippingSection />)} />
        <Route path="gst" element={guard(P.settingsView, <TaxSection />)} />
        <Route path="return-reasons" element={guard(P.ordersView, <ReturnReasonsSection />)} />
        <Route path="integrations" element={guard(P.settingsView, <IntegrationsSection />)} />
        <Route path="staff" element={guard(null, <UserSection />)} />
        <Route path="users" element={guard(null, <UserSection />)} />
        <Route path="roles" element={guard(null, <UserSection />)} />
        <Route path="activity" element={guard(P.audit, <AuditLogSection />)} />
        <Route path="audit-logs" element={guard(P.audit, <AuditLogSection />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/admin">
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
