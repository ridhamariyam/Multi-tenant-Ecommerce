import { notFound, redirect } from "next/navigation";
import AdminClientApp from "../AdminClientApp";

type Props = { params: Promise<{ segments?: string[] }> };

const singleSegmentRoutes = new Set([
  "signin", "login", "profile", "settings", "notifications", "dashboard", "reports",
  "analytics", "orders", "customers", "payments", "cod", "coupons", "discounts",
  "products", "categories", "inventory", "reviews", "cms", "banners", "content",
  "delivery", "gst", "return-reasons", "integrations", "staff", "users", "roles",
  "activity", "audit-logs",
]);

function isExistingAdminRoute(segments: string[]): boolean {
  if (segments.length === 0) return true;
  if (segments.length === 1) return singleSegmentRoutes.has(segments[0]);
  if (segments.length === 2 && ["orders", "customers", "products"].includes(segments[0])) {
    return Boolean(segments[1]);
  }
  if (
    segments.length === 3 &&
    segments[0] === "products" &&
    segments[2] === "edit"
  ) {
    return Boolean(segments[1]);
  }
  return false;
}

export default async function AdminPage({ params }: Props) {
  const { segments = [] } = await params;

  if (segments.length === 1 && segments[0] === "dashboard") redirect("/admin");
  if (segments.length === 1 && segments[0] === "login") redirect("/admin/signin");
  if (segments.length === 1 && segments[0] === "notifications") redirect("/admin");
  if (!isExistingAdminRoute(segments)) notFound();

  return <AdminClientApp />;
}
