import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { captureDownloads } from "../../test/setupDownloads";

const products = Array.from({ length: 105 }, (_, i) => ({ product_id: `p${i}`, product_name: `Product ${String(i).padStart(3, "0")}`, units_sold: i, orders: i, gross_sales: String(i * 100), discounts: "0", net_sales: String(i * 100) }));
const page = (rows: unknown[], number = 1, total = rows.length) => ok(rows, { page: number, page_size: 50, total_items: total, total_pages: Math.ceil(total / 50) });
function setup() {
  const downloads = captureDownloads();
  const mocked = mockFetch(
    route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["reports.view", "orders.view", "payments.view", "catalogue.view", "customers.view"] }))),
    route("GET", "/admin/reports/analytics", () => ok({ revenue: "200", orders: 2, average_order_value: "100", cod_orders: 1, prepaid_orders: 1, new_customers: 1, returning_customers: 1, top_products: products.slice(0, 6) })),
    route("GET", "/admin/reports/sales-by-product", (url) => url.searchParams.get("format") ? { body: "file", headers: { "content-disposition": `attachment; filename="products.${url.searchParams.get("format")}"` } } : ok(products)),
    route("GET", "/admin/reports/sales-by-category", () => ok([{ category_id: "cat1", category_name: "Apparel", units_sold: 3, orders: 2, gross_sales: "200", discounts: "0", net_sales: "200" }])),
    route("GET", "/admin/reports/sales-by-location", () => ok([{ state: "Karnataka", city: null, orders: 2, revenue: "200", returned_orders: 0 }])),
    route("GET", "/admin/reports/sales", (url) => url.searchParams.get("format") ? { body: "file", headers: { "content-disposition": "attachment; filename=\"sales.xlsx\"" } } : ok({ currency: "INR", summary: { orders: 2, subtotal: "210", revenue: "200", average_order_value: "100", net_revenue: "200", discount: "10", tax: "10" }, rows: [{ period: url.searchParams.get("start_date"), orders: 2, revenue: "200", average_order_value: "100" }] })),
    route("GET", "/admin/reports/customers", (url) => url.searchParams.get("format") ? { body: "file", headers: { "content-disposition": "attachment; filename=\"customers.xlsx\"" } } : ok({ customers_ordering: 100, new_customers: 25, returning_customers: 75, signups: 10, top_customers: products.slice(0, 100).map((p, i) => ({ customer_id: `c${i}`, name: p.product_name, orders: 2, total_spent: "200", phone: "+919999999999", email: null, last_order_at: "2026-10-01T00:00:00Z" })) })),
    route("GET", "/admin/reports/returns", (url) => url.searchParams.get("format") ? { body: "file", headers: { "content-disposition": "attachment; filename=\"returns.csv\"" } } : ok({ returned_orders: 2, returned_value: "100", delivered_orders: 8, return_rate: 20, by_product: [{ product_id: "p1", product_name: "Linen shirt", units_returned: 2, orders: 2 }], by_reason: [{ reason: "Refused at door", orders: 2, returned_value: "100" }] })),
    route("GET", "/admin/reports/unsold", () => ok([])),
    route("GET", "/admin/customers/c0", () => ok({ id: "c0", name: "Product 000", phone: "+919999999999", email: "buyer@example.com", status: "ACTIVE", is_verified: true, tags: [], order_blocked: false, order_blocked_at: null, order_block_reason: null, total_orders: 3, total_spent: "350", last_order_at: "2026-10-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z", first_order_at: "2026-01-10T00:00:00Z", is_returning: true, cancelled_orders: 0, returned_orders: 0, addresses: [{ id: "a1", full_name: "Product 000", phone: "+919999999999", address_line_1: "10 Main Road", address_line_2: null, city: "Bengaluru", state: "Karnataka", postal_code: "560001", country: "India", is_default: true }], notes: [], currency: "INR" })),
    route("GET", "/admin/customers/c0/orders", () => page([{ id: "o1", order_number: "ZN-1", status: "DELIVERED", payment_status: "PAID", total_amount: "100", currency: "INR", created_at: "2026-10-01T00:00:00Z" }])),
    route("GET", "/admin/cod/report", () => ok({ total_orders: 4, delivered_orders: 3, returned_orders: 1, cash_collected: "300", cash_remitted: "200", cash_outstanding: "100", net_revenue: "300" })),
    route("GET", "/admin/payments", (url) => page([{ id: "pay1", order_id: "o1", amount: "100", currency: "INR", status: "PAID", provider: "COD", purpose: "FULL", created_at: "2026-10-01T00:00:00Z" }], Number(url.searchParams.get("page")), 20)),
  );
  renderApp("/reports");
  return { ...mocked, downloads, user: userEvent.setup() };
}

describe("Reports & Analytics", () => {
  it("shows exactly six tabs and a real Overview revenue chart by default", async () => {
    setup();
    await screen.findByRole("heading", { name: "Reports & analytics" });
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Overview", "Sales", "Products", "Customers", "Payments", "Returns"]);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await screen.findByRole("figure", { name: "Booked order value trend" });
    expect(screen.getByText("Gross sales").parentElement).toHaveTextContent("INR 210.00");
    expect(screen.getByText("Refunds").parentElement).toHaveTextContent("Unavailable");
    expect(screen.getByRole("img", { name: /Booked order value trend/ })).toBeInTheDocument();
  });

  it("updates current and previous range requests together and validates custom dates", async () => {
    const { user, calls } = setup();
    await screen.findByRole("figure", { name: "Booked order value trend" });
    await user.click(screen.getByLabelText("Compare previous period"));
    await screen.findByRole("figure", { name: "Booked order value comparison" });
    await user.selectOptions(screen.getByLabelText("Quick date range"), "week");
    await waitFor(() => expect(calls.filter((call) => call.url.pathname.endsWith("/reports/sales") && !call.url.searchParams.has("format")).some((call) => call.url.searchParams.get("start_date") !== call.url.searchParams.get("end_date"))).toBe(true));
    const dates = calls.filter((call) => call.url.pathname.endsWith("/reports/sales") && !call.url.searchParams.has("format")).slice(-2).map((call) => call.url.searchParams.get("start_date"));
    expect(dates[0]).not.toBe(dates[1]);
    await user.selectOptions(screen.getByLabelText("Quick date range"), "yesterday");
    expect(screen.getByLabelText("From")).toHaveValue(screen.getByLabelText("To").getAttribute("value") ?? (screen.getByLabelText("To") as HTMLInputElement).value);
    const count = calls.length;
    await user.clear(screen.getByLabelText("From"));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a valid date range");
    expect(calls.length).toBe(count);
  });

  it("groups Sales charts and retains date-aware Excel exports and breakdowns", async () => {
    const { user, calls, downloads } = setup();
    await user.click(await screen.findByRole("tab", { name: "Sales" }));
    await screen.findByRole("figure", { name: "Booked order value trend" });
    expect(screen.getByRole("figure", { name: "Order volume" })).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Group by" }), "month");
    await user.selectOptions(screen.getByRole("combobox", { name: "Sales breakdown" }), "sales-by-location");
    await user.selectOptions(screen.getByRole("combobox", { name: "Location level" }), "city");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("sales-by-location") && call.url.searchParams.get("level") === "city")).toBe(true));
    await user.click(screen.getAllByRole("button", { name: "Excel" })[0]);
    await waitFor(() => expect(downloads()).toContain("sales.xlsx"));
    const download = calls.find((call) => call.url.pathname.endsWith("/reports/sales") && call.url.searchParams.get("format") === "xlsx")!;
    expect(download.url.searchParams.get("group_by")).toBe("month");
    expect(download.url.searchParams.get("start_date")).toBe((screen.getByLabelText("From") as HTMLInputElement).value);
  });

  it("paginates Products at 50 and exports only locally filtered rows as CSV", async () => {
    const { user, downloads } = setup();
    await user.click(await screen.findByRole("tab", { name: "Products" }));
    const reportPanel = (await screen.findByRole("heading", { name: "Product performance" })).closest<HTMLElement>(".panel")!;
    const table = within(reportPanel).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(51);
    await user.click(within(reportPanel).getByRole("button", { name: "Next" }));
    expect(within(table).getByText("Product 050")).toBeInTheDocument();
    await user.type(within(reportPanel).getByRole("textbox", { name: "Search report" }), "Product 010");
    expect(within(reportPanel).getByText("Page 1 of 1 (1 items)")).toBeInTheDocument();
    expect(within(reportPanel).queryByRole("button", { name: "Excel" })).not.toBeInTheDocument();
    await user.click(within(reportPanel).getByRole("button", { name: "CSV" }));
    expect(downloads()).toHaveLength(1);
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)![0] as Blob;
    const contents = await new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blob); });
    expect(contents).toContain("Product 010");
    expect(contents).not.toContain("Product 002");
  });

  it("keeps customer data private in the summary table and supports payment-status paging", async () => {
    const { user, calls } = setup();
    await user.click(await screen.findByRole("tab", { name: "Customers" }));
    await screen.findByRole("heading", { name: "Top 100 customers by spending" });
    expect(screen.getByText("Page 1 of 2 (100 items)")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Phone" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Customer ID" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "c0" })).toHaveAttribute("href", "/customers/c0");
    expect(screen.getByRole("link", { name: "Product 000" })).toHaveAttribute("href", "/customers/c0");
    await user.click(screen.getByRole("tab", { name: "Payments" }));
    await screen.findByRole("columnheader", { name: "Payment ID" });
    await user.selectOptions(screen.getByLabelText("Payment status"), "REFUNDED");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/payments") && call.url.searchParams.get("status") === "REFUNDED" && call.url.searchParams.get("page_size") === "50")).toBe(true));
  });

  it("opens the existing customer detail view from the report ID", async () => {
    const { user } = setup();
    await user.click(await screen.findByRole("tab", { name: "Customers" }));
    await user.click(await screen.findByRole("link", { name: "c0" }));
    await screen.findByRole("heading", { name: "Contact" });
    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
    expect(screen.getByText("10 Main Road", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Total spent").parentElement).toHaveTextContent("INR 350.00");
    expect(screen.getByRole("heading", { name: "Order history" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "ZN-1" })).toBeInTheDocument();
  });

  it("reports only actual returned-parcel data and labels refund dependencies", async () => {
    const { user } = setup();
    await user.click(await screen.findByRole("tab", { name: "Returns" }));
    await screen.findByRole("figure", { name: "Most returned products" });
    expect(screen.getByText("Returned parcels").parentElement).toHaveTextContent("2");
    expect(screen.getByText("Refund amount").parentElement).toHaveTextContent("Unavailable");
    expect(screen.getByText(/undelivered returned parcels/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Return reasons" })).toBeInTheDocument();
  });
});
