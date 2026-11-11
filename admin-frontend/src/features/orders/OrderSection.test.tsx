import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { captureDownloads } from "../../test/setupDownloads";
import { ORDER_STATUSES, PAYMENT_STATUSES } from "../../types/order";

const admin = profile({ role: "ADMIN", permissions: ["orders.view", "orders.manage", "payments.manage"] });
const me = route("GET", "/auth/me", () => ok(admin));
const order = (id: string, status = "CONFIRMED", paymentStatus = "PENDING") => ({
  id, order_number: `ZN-${id}`, status, payment_status: paymentStatus,
  payment_method: "CASH_ON_DELIVERY", created_at: "2026-10-01T10:00:00Z",
  tracking_number: null, total_amount: "999.00", currency: "INR",
});
const page = (rows: unknown[], current = 1, total = rows.length) => ok(rows, { page: current, page_size: 20, total_items: total, total_pages: Math.max(1, Math.ceil(total / 20)) });

describe("orders filters and labels", () => {
  it("links each order to details, keeps label selection usable, and preserves filters across pages", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", (url) =>
      page([order("1")], Number(url.searchParams.get("page") ?? 1), 40)
    ));
    renderApp("/orders?payment_method=CASH_ON_DELIVERY&start_date=2026-10-01");
    const orderLink = await screen.findByRole("link", { name: "ZN-1" });
    expect(orderLink).toHaveAttribute("href", "/orders/1");
    expect(orderLink).toHaveAttribute("title", "Open order and customer details");
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/orders/1");
    expect(screen.getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
    const dateRange = screen.getByRole("group", { name: "Order date range" });
    expect(within(dateRange).getByLabelText("From date")).toBeInTheDocument();
    expect(within(dateRange).getByText("to")).toBeInTheDocument();
    expect(within(dateRange).getByLabelText("To date")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select ZN-1" }));
    expect(screen.getByRole("button", { name: "Print 1 shipping label" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    const next = calls.filter((call) => call.url.pathname.endsWith("/admin/orders") && call.url.searchParams.get("page") === "2").at(-1)!.url.searchParams;
    expect(next.get("payment_method")).toBe("CASH_ON_DELIVERY");
    expect(next.get("start_date")).toBe("2026-10-01");
    expect(screen.getByRole("combobox", { name: "Payment method" })).toHaveValue("CASH_ON_DELIVERY");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("combobox", { name: "Payment method" })).toHaveValue("");
  });

  it("offers only payment statuses found across the matching orders for every order status", async () => {
    const records = ORDER_STATUSES.flatMap((status, index) => [
      order(`${index}-a`, status, PAYMENT_STATUSES[index % PAYMENT_STATUSES.length]),
      order(`${index}-b`, status, PAYMENT_STATUSES[(index + 2) % PAYMENT_STATUSES.length]),
    ]);
    const { calls } = mockFetch(me, route("GET", "/admin/orders", (url) => {
      const matching = records.filter((record) =>
        (!url.searchParams.has("status") || record.status === url.searchParams.get("status")) &&
        (!url.searchParams.has("payment_status") || record.payment_status === url.searchParams.get("payment_status"))
      );
      const current = Number(url.searchParams.get("page") ?? 1);
      const size = Number(url.searchParams.get("page_size") ?? 20);
      return ok(matching.slice((current - 1) * size, current * size), { page: current, page_size: size, total_items: matching.length, total_pages: Math.max(1, Math.ceil(matching.length / size)) });
    }));
    renderApp("/orders");
    const statusSelect = await screen.findByRole("combobox", { name: "Order status" });
    const paymentSelect = screen.getByRole("combobox", { name: "Payment status" });

    for (const [index, status] of ORDER_STATUSES.entries()) {
      await userEvent.selectOptions(statusSelect, status);
      const expected = ["", ...PAYMENT_STATUSES.filter((payment) =>
        payment === PAYMENT_STATUSES[index % PAYMENT_STATUSES.length] || payment === PAYMENT_STATUSES[(index + 2) % PAYMENT_STATUSES.length]
      )];
      await waitFor(() => expect(within(paymentSelect).getAllByRole("option").map((option) => (option as HTMLOptionElement).value)).toEqual(expected));
      const scoped = calls.filter((call) => call.url.pathname.endsWith("/admin/orders") && call.url.searchParams.get("status") === status && call.url.searchParams.get("page_size") === "1");
      expect(scoped).toHaveLength(PAYMENT_STATUSES.length);
    }
    await userEvent.selectOptions(statusSelect, ORDER_STATUSES[0]);
    await waitFor(() => expect(paymentSelect).not.toBeDisabled());
    expect(calls.filter((call) => call.url.pathname.endsWith("/admin/orders") && call.url.searchParams.get("status") === ORDER_STATUSES[0] && call.url.searchParams.get("page_size") === "1")).toHaveLength(PAYMENT_STATUSES.length);
  });

  it("preserves a payment status that still has matches and clears one that does not", async () => {
    const records = [order("1", "CONFIRMED", "PENDING"), order("2", "DELIVERED", "PENDING"), order("3", "DELIVERED", "PAID"), order("4", "CANCELLED", "REFUNDED")];
    const { calls } = mockFetch(me, route("GET", "/admin/orders", (url) => {
      const matching = records.filter((record) =>
        (!url.searchParams.has("status") || record.status === url.searchParams.get("status")) &&
        (!url.searchParams.has("payment_status") || record.payment_status === url.searchParams.get("payment_status"))
      );
      return page(matching, Number(url.searchParams.get("page") ?? 1), matching.length);
    }));
    renderApp("/orders?status=CONFIRMED&payment_status=PENDING&page=2");
    const statusSelect = await screen.findByRole("combobox", { name: "Order status" });
    const paymentSelect = screen.getByRole("combobox", { name: "Payment status" });
    await waitFor(() => expect(paymentSelect).not.toBeDisabled());
    await userEvent.selectOptions(statusSelect, "DELIVERED");
    await waitFor(() => expect(paymentSelect).not.toBeDisabled());
    expect(paymentSelect).toHaveValue("PENDING");
    expect(within(paymentSelect).getAllByRole("option").map((option) => (option as HTMLOptionElement).value)).toEqual(["", "PENDING", "PAID"]);
    await screen.findByRole("cell", { name: "ZN-2" });

    await userEvent.selectOptions(statusSelect, "CANCELLED");
    await waitFor(() => expect(paymentSelect).toHaveValue(""));
    expect(within(paymentSelect).getAllByRole("option").map((option) => (option as HTMLOptionElement).value)).toEqual(["", "REFUNDED"]);
    await screen.findByRole("cell", { name: "ZN-4" });
    const final = calls.filter((call) => call.url.pathname.endsWith("/admin/orders") && call.url.searchParams.get("status") === "CANCELLED" && call.url.searchParams.get("page_size") !== "1").at(-1)!.url.searchParams;
    expect(final.get("payment_status")).toBeNull();
    expect(final.get("page")).toBe("1");
  });

  it("keeps payment choices available when the API cannot provide combination counts", async () => {
    mockFetch(me, route("GET", "/admin/orders", (url) =>
      url.searchParams.get("page_size") === "1"
        ? { status: 503, body: { message: "Counts unavailable" } }
        : page([])
    ));
    renderApp("/orders?status=RETURN_REQUESTED");
    expect(await screen.findByText(/Available payment statuses could not be checked/)).toBeInTheDocument();
    const paymentSelect = screen.getByRole("combobox", { name: "Payment status" });
    expect(within(paymentSelect).getAllByRole("option").map((option) => (option as HTMLOptionElement).value)).toEqual(["", ...PAYMENT_STATUSES]);
  });

  it("combines independent order, payment, search and date filters without inferring payment from delivery", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", (url) => page(
      url.searchParams.get("status") === "DELIVERED" && url.searchParams.get("payment_status") === "PENDING"
        ? [order("1", "DELIVERED", "PENDING")] : []
    )));
    renderApp("/orders?page=3");
    await screen.findByRole("combobox", { name: "Order status" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Order status" }), "DELIVERED");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment status" }), "PENDING");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment method" }), "CASH_ON_DELIVERY");
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-10-09" } });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search orders" }), "name@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByRole("cell", { name: "ZN-1" });
    const last = calls.filter((call) => call.url.pathname.endsWith("/admin/orders")).at(-1)!.url.searchParams;
    expect(Object.fromEntries(last)).toMatchObject({
      status: "DELIVERED", payment_status: "PENDING", payment_method: "CASH_ON_DELIVERY",
      start_date: "2026-10-01", end_date: "2026-10-09", search: "name@example.com", page: "1",
    });
    expect(screen.getByRole("combobox", { name: "Payment status" })).toHaveValue("PENDING");
    expect(screen.getByRole("cell", { name: "PENDING" })).toBeInTheDocument();
    const counts = calls.filter((call) => call.url.pathname.endsWith("/admin/orders") && call.url.searchParams.get("page_size") === "1" && call.url.searchParams.get("search") === "name@example.com");
    expect(counts).toHaveLength(PAYMENT_STATUSES.length);
    expect(counts.every((call) => call.url.searchParams.get("payment_method") === "CASH_ON_DELIVERY" && call.url.searchParams.get("start_date") === "2026-10-01" && call.url.searchParams.get("end_date") === "2026-10-09")).toBe(true);
  });

  it("blocks an invalid date range before any list request and fetches when corrected", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", () => page([order("1")])));
    renderApp("/orders?start_date=2026-10-09&end_date=2026-10-01");
    expect(await screen.findByRole("alert")).toHaveTextContent("end date cannot be before");
    expect(calls.filter((call) => call.url.pathname.endsWith("/admin/orders"))).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-10-10" } });
    await screen.findByRole("cell", { name: "ZN-1" });
    expect(calls.filter((call) => call.url.pathname.endsWith("/admin/orders"))).toHaveLength(1);
  });

  it("selects only eligible mixed-status orders for the label PDF", async () => {
    const downloads = captureDownloads();
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/orders", () => page([
        order("1", "PENDING"), order("2", "CONFIRMED"), order("3", "PROCESSING"),
        order("4", "PACKED"), order("5", "SHIPPED"), order("6", "OUT_FOR_DELIVERY"),
        order("7", "DELIVERED"), order("8", "CANCELLED"),
      ])),
      route("POST", "/admin/orders/shipping-labels/pdf", () => ({ body: "%PDF", headers: { "content-type": "application/pdf", "content-disposition": 'attachment; filename="labels.pdf"' } }))
    );
    renderApp("/orders");
    expect(await screen.findByRole("checkbox", { name: "Select ZN-1" })).toBeDisabled();
    for (const id of ["7", "8"]) expect(screen.getByRole("checkbox", { name: `Select ZN-${id}` })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select all eligible on this page" }));
    for (const id of ["2", "3", "4", "5", "6"]) expect(screen.getByRole("checkbox", { name: `Select ZN-${id}` })).toBeChecked();
    for (const id of ["1", "7", "8"]) expect(screen.getByRole("checkbox", { name: `Select ZN-${id}` })).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Print 5 shipping labels" }));
    await waitFor(() => expect(downloads()).toEqual(["labels.pdf"]));
    expect(JSON.parse(calls.find((call) => call.url.pathname.endsWith("/shipping-labels/pdf"))!.init.body as string)).toEqual({ order_ids: ["2", "3", "4", "5", "6"] });
    await userEvent.click(screen.getByRole("checkbox", { name: "Select all eligible on this page" }));
    expect(screen.getByRole("button", { name: "Print shipping labels" })).toBeDisabled();
  });

  it("keeps individual ineligible orders out of selection and formats the method without changing its value", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", () => page([order("1", "PENDING"), order("2", "CONFIRMED")])));
    renderApp("/orders");
    const pending = await screen.findByRole("checkbox", { name: "Select ZN-1" });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute("title", expect.stringContaining("unavailable"));
    expect(screen.getAllByRole("cell", { name: "COD" })).toHaveLength(2);
    await userEvent.click(screen.getByRole("checkbox", { name: "Select ZN-2" }));
    expect(screen.getByRole("button", { name: "Print 1 shipping label" })).toBeEnabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment method" }), "CASH_ON_DELIVERY");
    expect(calls.at(-1)?.url.searchParams.get("payment_method")).toBe("CASH_ON_DELIVERY");
  });

  it("explains why Select All cannot select a page with no eligible orders", async () => {
    mockFetch(me, route("GET", "/admin/orders", () => page([order("1", "PENDING"), order("2", "CANCELLED"), order("3", "DELIVERED")])));
    renderApp("/orders");
    const selectAll = await screen.findByRole("checkbox", { name: "Select all eligible on this page" });
    expect(selectAll).toBeEnabled();
    expect(screen.getByText("(0 eligible)")).toBeInTheDocument();
    await userEvent.click(selectAll);
    expect(screen.getByRole("status")).toHaveTextContent("No orders on this page are eligible for shipping labels");
    expect(screen.getByRole("button", { name: "Print shipping labels" })).toBeDisabled();
    expect(selectAll).not.toBeChecked();
  });

  it("keeps stale ineligible selections out of label counts and offers a compact clear action", async () => {
    let currentStatus = "CONFIRMED";
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/orders", () => page([order("1", currentStatus)])),
      route("POST", "/admin/orders/shipping-labels/pdf", () => ({ body: "%PDF", headers: { "content-type": "application/pdf" } }))
    );
    renderApp("/orders");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select ZN-1" }));
    expect(screen.getByRole("button", { name: "Print 1 shipping label" })).toBeEnabled();
    currentStatus = "CANCELLED";
    await userEvent.click(screen.getByRole("button", { name: "Refresh workspace data" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("1 selected order is no longer eligible");
    expect(screen.getByRole("button", { name: "Print shipping labels" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Select ZN-1" })).toBeDisabled();
    expect(calls.some((call) => call.url.pathname.endsWith("/shipping-labels/pdf"))).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Clear invalid selections" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear selection" })).not.toBeInTheDocument();
  });

  it("keeps eligible selections across pages for one bulk label PDF", async () => {
    const downloads = captureDownloads();
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/orders", (url) => page([order(url.searchParams.get("page") === "2" ? "2" : "1")], Number(url.searchParams.get("page") ?? 1), 40)),
      route("POST", "/admin/orders/shipping-labels/pdf", () => ({ body: "%PDF", headers: { "content-type": "application/pdf", "content-disposition": 'attachment; filename="labels.pdf"' } }))
    );
    renderApp("/orders");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select ZN-1" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select ZN-2" }));
    await userEvent.click(screen.getByRole("button", { name: "Print 2 shipping labels" }));
    await waitFor(() => expect(downloads()).toEqual(["labels.pdf"]));
    expect(JSON.parse(calls.find((call) => call.url.pathname.endsWith("/shipping-labels/pdf"))!.init.body as string)).toEqual({ order_ids: ["1", "2"] });
  });

  it("resets pagination, clears hidden selections, and offers clear filters for empty results", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", (url) =>
      page(url.searchParams.has("status") ? [] : [order("1")], Number(url.searchParams.get("page") ?? 1), 40)
    ));
    renderApp("/orders?page=2");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select ZN-1" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Order status" }), "CANCELLED");
    await screen.findByText("No orders match these filters.");
    expect(screen.getByRole("button", { name: "Print shipping labels" })).toBeDisabled();
    const filtered = calls.filter((call) => call.url.pathname.endsWith("/admin/orders")).at(-1)!.url.searchParams;
    expect(filtered.get("page")).toBe("1");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await screen.findByRole("cell", { name: "ZN-1" });
    expect(screen.getByRole("combobox", { name: "Order status" })).toHaveValue("");
  });
});

const detail = (status: string, advance = "0.00") => ({
  ...order("1", status), items: [], subtotal: "999.00", coupon_code: null,
  discount_amount: "0.00", shipping_amount: "0.00", cod_fee: "0.00", tax_amount: "0.00",
  advance_amount: advance, payment: null,
  payments: Number(advance) > 0 ? [{ id: "p1", order_id: "1", amount: advance, currency: "INR", status: "PENDING", provider: "PREPAID", purpose: "ADVANCE", remitted_at: null, remittance_reference: null, created_at: "2026-10-01T10:00:00Z" }] : [],
  gst: null, delivery_address: { full_name: "Neha", phone: "+919876500001", address_line_1: "1 St", address_line_2: null, city: "Kochi", state: "Kerala", postal_code: "682001", country: "India" },
  contact_email: null, is_guest: false, estimated_delivery_date: null,
  shipment: { courier_name: null, tracking_number: null, tracking_url: null }, return_reason: null, return_note: null,
});

describe("order detail action eligibility", () => {
  it("does not offer transitions or a shipping label for a delivered order", async () => {
    mockFetch(me,
      route("GET", "/admin/orders/1", () => ok(detail("DELIVERED"))),
      route("GET", "/admin/orders/1/tracking", () => ok({ events: [] }))
    );
    renderApp("/orders/1");
    expect(await screen.findByText("This order is closed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Shipping label" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Move to" })).not.toBeInTheDocument();
  });

  it("withholds transitions that require an unpaid COD advance", async () => {
    const { calls } = mockFetch(me,
      route("GET", "/admin/orders/1", () => ok(detail("PENDING", "100.00"))),
      route("GET", "/admin/orders/1/tracking", () => ok({ events: [] }))
    );
    renderApp("/orders/1");
    const move = await screen.findByRole("combobox", { name: "Move to" });
    expect(within(move).getAllByRole("option").map((option) => (option as HTMLOptionElement).value)).toEqual(["", "CANCELLED"]);
    expect(screen.getByText(/Record the COD advance/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update status" })).toBeDisabled();
    expect(calls.some((call) => call.init.method === "PATCH")).toBe(false);
  });

  it("does not offer tracking updates for a cancelled order", async () => {
    mockFetch(me,
      route("GET", "/admin/orders/1", () => ok(detail("CANCELLED"))),
      route("GET", "/admin/orders/1/tracking", () => ok({ events: [] }))
    );
    renderApp("/orders/1");
    expect(await screen.findByText("This order is closed.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Add tracking update" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Shipping label" })).not.toBeInTheDocument();
  });
});
