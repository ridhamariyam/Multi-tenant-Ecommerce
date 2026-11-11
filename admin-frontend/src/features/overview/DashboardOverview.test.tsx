import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch, ok, route } from "../../test/fetchMock";
import type { DashboardOverview as Overview } from "../../types/dashboard";
import Header from "../../layouts/Header";
import AdminRefreshProvider from "../../layouts/AdminRefreshProvider";
import DashboardOverview from "./DashboardOverview";
import { currentWeekRange, dashboardPeriodRange } from "./dashboardPeriod";
import { inventoryProducts } from "./dashboardData";
import type { InventoryRow } from "./dashboardData";

const auth = vi.hoisted(() => ({ can: vi.fn(() => true), logout: vi.fn(), user: { id: "u1", tenant_id: "t1" } }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => auth }));

const metric = { order_count: 4, revenue: "400", previous_order_count: 2, previous_revenue: "200", order_count_change_pct: 100, revenue_change_pct: 100 };
const overview: Overview = {
  sales: { today: metric, week: metric, month: metric, total_order_count: 70, total_revenue: "7000" },
  orders: { total: 110, today: 6, pending: 5 },
  products: { total: 120 },
  inventory: { low_stock_count: 4, out_of_stock_count: 3, low_stock_variants: [], out_of_stock_variants: [] },
  customers: { total: 50, new_today: 1, new_this_month: 5 },
  payments: { paid_count: 90, pending_count: 2, failed_count: 1, refunded_count: 6, today_paid_amount: "400" },
  recent_orders: Array.from({ length: 6 }, (_, i) => ({ order_id: `o${i}`, order_number: `ORDER-${i}`, customer_email: `buyer${i}@example.com`, total_amount: "100", currency: "INR", order_status: "PENDING", payment_status: "PENDING", created_at: "2026-10-01T10:00:00Z" })),
  insights: {
    attention: { new_orders: 5, awaiting_packing: 7, awaiting_shipment: 3, in_transit: 2, advance_pending: 1 },
    comparison: { today_orders: 4, today_revenue: "400", yesterday_orders: 2, yesterday_revenue: "200", last_week_orders: 1, last_week_revenue: "100", orders_vs_yesterday_pct: 100, revenue_vs_yesterday_pct: 100, orders_vs_last_week_pct: 300, revenue_vs_last_week_pct: 300 },
    last_30_days: { revenue: "2000", orders: 20, average_order_value: "100", return_rate: 5, cancellation_rate: 2, cod_orders: 15, prepaid_orders: 5, cod_share_pct: 75, new_customers: 10, returning_customers: 5 },
    visitors_today: null, visitors_note: "Analytics is not connected.",
  },
};
const stock: InventoryRow[] = [
  { product_id: "p1", product_name: "Shirt", variant_id: "v1", sku: "S1", available_quantity: 2, sellable_quantity: 2, low_stock_threshold: 5, stock_status: "LOW" },
  { product_id: "p1", product_name: "Shirt", variant_id: "v2", sku: "S2", available_quantity: 0, sellable_quantity: 0, low_stock_threshold: 5, stock_status: "OUT_OF_STOCK" },
  { product_id: "p2", product_name: "Scarf", variant_id: "v3", sku: "S3", available_quantity: 0, sellable_quantity: 0, low_stock_threshold: 5, stock_status: "OUT_OF_STOCK" },
];
function setup(inventory = stock) {
  const mocked = mockFetch(
    route("GET", "/admin/dashboard", () => ok(overview)),
    route("GET", "/admin/reports/sales", (url) => ok({ currency: "INR", summary: { orders: 4, revenue: "400", average_order_value: "100" }, rows: [{ period: url.searchParams.get("start_date"), orders: 4, revenue: "400" }] })),
    route("GET", "/admin/reports/sales-by-product", () => ok([{ product_id: "p1", product_name: "Shirt", units_sold: 3, net_sales: "300" }])),
    route("GET", "/admin/reports/inventory", () => ok(inventory)),
  );
  render(<MemoryRouter><AdminRefreshProvider><Header menuOpen={false} onToggleMenu={() => undefined} /><DashboardOverview /></AdminRefreshProvider></MemoryRouter>);
  return { ...mocked, user: userEvent.setup() };
}

describe("CliQ. dashboard", () => {
  beforeEach(() => auth.can.mockReturnValue(true));

  it("opens Overview with four purposeful tabs, real metrics and a visible revenue graph", async () => {
    const { calls } = setup();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Overview", "Sales Performance", "Order Operations", "Inventory Health"]);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    const graph = within(await screen.findByRole("region", { name: "Overview revenue graph" }));
    expect(await graph.findByRole("img", { name: /Booked order value trend/ })).toBeInTheDocument();
    expect(screen.getByText("Today's booked order value").parentElement).toHaveTextContent("INR 400.00");
    expect(screen.getByText("Orders Today").parentElement).toHaveTextContent("6");
    expect(screen.getByText("Orders Needing Action").parentElement).toHaveTextContent("15");
    await waitFor(() => expect(screen.getByText("Out-of-Stock Products").parentElement).toHaveTextContent("2"));
    expect(screen.getByRole("link", { name: /Orders Needing Action/ })).toHaveAttribute("href", "/orders");
    expect(screen.getByRole("link", { name: /Out-of-Stock Products/ })).toHaveAttribute("href", "/inventory?stock_status=out");
    expect(await screen.findByRole("heading", { name: "Top-selling products this week" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Shirt" })).toHaveAttribute("href", "/products/p1");
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/sales") && call.url.searchParams.get("start_date") === dashboardPeriodRange("last7").start_date)).toBe(true);
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/sales-by-product") && call.url.searchParams.get("start_date") === currentWeekRange().start_date)).toBe(true);
    expect(screen.queryByText("Visitors today")).not.toBeInTheDocument();
    expect(screen.queryByText("Total successful payments")).not.toBeInTheDocument();
  });

  it("applies each date range to the graph and performance report, with previous-period comparison", async () => {
    const { user, calls } = setup();
    const period = screen.getByRole("combobox", { name: "Dashboard date range" });
    for (const value of ["today", "yesterday", "last7", "last30", "month"] as const) {
      await user.selectOptions(period, value);
      const range = dashboardPeriodRange(value);
      await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/sales") && call.url.searchParams.get("start_date") === range.start_date && call.url.searchParams.get("end_date") === range.end_date)).toBe(true));
      expect(await within(await screen.findByRole("region", { name: "Overview revenue graph" })).findByRole("img", { name: new RegExp(range.start_date) })).toBeInTheDocument();
    }
    await user.click(screen.getByRole("tab", { name: "Sales Performance" }));
    const range = dashboardPeriodRange("month");
    expect(await screen.findByRole("figure", { name: "Order trend" })).toBeInTheDocument();
    expect(screen.getByText("Average order value").parentElement).toHaveTextContent("INR 100.00");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/sales") && call.url.searchParams.get("start_date") === range.previous_start_date && call.url.searchParams.get("end_date") === range.previous_end_date)).toBe(true));
    expect(screen.getByRole("link", { name: /Detailed reports/ })).toHaveAttribute("href", "/reports");
  });

  it("shows non-overlapping order stages and only five linked recent orders", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("tab", { name: "Order Operations" }));
    expect(screen.getByText("Awaiting confirmation").parentElement).toHaveTextContent("5");
    expect(screen.getByText("Pending packing").parentElement).toHaveTextContent("7");
    expect(screen.getByText("Pending shipping").parentElement).toHaveTextContent("3");
    expect(screen.getByRole("link", { name: /Awaiting confirmation/ })).toHaveAttribute("href", "/orders?status=PENDING");
    expect(screen.getByRole("link", { name: /Pending shipping/ })).toHaveAttribute("href", "/orders?status=PACKED");
    expect(screen.getAllByRole("link", { name: /^ORDER-/ })).toHaveLength(5);
    expect(screen.queryByText("ORDER-5")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Order indicators" })).not.toBeInTheDocument();
  });

  it("keeps the four tabs keyboard accessible", async () => {
    const { user } = setup();
    await screen.findByRole("tab", { name: "Overview" });
    screen.getByRole("tab", { name: "Overview" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Sales Performance" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Sales Performance" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Inventory Health" })).toHaveFocus();
  });

  it("deduplicates variants into products, shows restocking quantities and handles empty stock", async () => {
    const { user } = setup();
    expect(inventoryProducts([stock[0], stock[0], stock[1], stock[2]]).filter((product) => product.out)).toHaveLength(2);
    await user.click(screen.getByRole("tab", { name: "Inventory Health" }));
    expect(await screen.findByRole("heading", { name: "Inventory alerts" })).toBeInTheDocument();
    expect(screen.getByText("Low-stock products").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Out-of-stock products").parentElement).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: /Low-stock products/ })).toHaveAttribute("href", "/inventory?stock_status=low");
    expect(screen.getByRole("link", { name: "Manage inventory" })).toHaveAttribute("href", "/inventory");
  });

  it("refreshes current data without changing the selected tab", async () => {
    const { user, calls } = setup();
    await user.click(screen.getByRole("tab", { name: "Inventory Health" }));
    const before = calls.filter((call) => call.url.pathname.endsWith("/admin/reports/inventory")).length;
    await user.click(screen.getByRole("button", { name: "Refresh workspace data" }));
    await waitFor(() => expect(calls.filter((call) => call.url.pathname.endsWith("/admin/reports/inventory")).length).toBeGreaterThan(before));
    expect(screen.getByRole("tab", { name: "Inventory Health" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows unavailable states without requesting reports when report access is absent", async () => {
    auth.can.mockImplementation((permission?: string) => permission === "dashboard.view" || permission === "orders.view");
    const { calls } = setup();
    expect(await screen.findByText("Today's booked order value")).toBeInTheDocument();
    expect(await screen.findByText(/Order-value graph unavailable/)).toBeInTheDocument();
    expect(screen.getByText("Out-of-Stock Products").parentElement).toHaveTextContent("Unavailable");
    expect(calls.some((call) => call.url.pathname.includes("/admin/reports/"))).toBe(false);
  });
});
