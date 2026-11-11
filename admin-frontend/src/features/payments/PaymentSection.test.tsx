import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const paymentId = "4f6553b0-7609-4b10-a0c0-cfc61a83ea11";
const orderId = "6b17686c-13de-47d8-b0f8-6f8fcfe39492";
const payment = (overrides: Record<string, unknown> = {}) => ({
  id: paymentId, order_id: orderId, amount: "799.00", currency: "INR", status: "PENDING",
  provider: "COD", purpose: "FULL", remitted_at: null, remittance_reference: null,
  created_at: "2026-10-01T10:00:00Z", ...overrides,
});
const page = (rows: unknown[], current = 1, total = rows.length, size = 100) => ok(rows, {
  page: current, page_size: size, total_items: total, total_pages: Math.ceil(total / size),
});
const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["payments.view", "payments.manage", "orders.view", "settings.view"] })));

describe("Payments page", () => {
  it("opens a real payment detail without the obsolete CCAvenue notice", async () => {
    const { calls } = mockFetch(me,
      route("GET", "/admin/payments", () => page([payment({ remittance_reference: "BANK-42" })])),
    );
    renderApp("/payments");
    const idButton = await screen.findByRole("button", { name: "4f6553b0…ea11" });
    expect(idButton).toHaveAttribute("title", paymentId);
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute("href", `/orders/${orderId}`);
    expect(screen.queryByText(/CCAvenue merchant credentials are not configured/)).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/integrations"))).toBe(false);
    await userEvent.click(idButton);
    const detail = screen.getByRole("dialog", { name: "Payment details" });
    expect(within(detail).getByText(paymentId)).toBeInTheDocument();
    expect(within(detail).getByText("BANK-42")).toBeInTheDocument();
  });

  it("combines status, method, purpose, date, and ID search over all API pages", async () => {
    const data = [
      payment({ id: "cod-pending", created_at: "2026-10-01T10:00:00Z" }),
      payment({ id: "prepaid-paid", provider: "PREPAID", purpose: "ADVANCE", status: "PAID", created_at: "2026-10-02T10:00:00Z" }),
      payment({ id: "other-paid", provider: "PREPAID", purpose: "FULL", status: "PAID", created_at: "2026-09-30T10:00:00Z" }),
    ];
    const { calls } = mockFetch(me,
      route("GET", "/admin/payments", (url) => Number(url.searchParams.get("page")) === 2 ? page(data.slice(2), 2, 3, 2) : page(data.slice(0, 2), 1, 3, 2)),
      route("GET", "/admin/integrations", () => ok([{ key: "ccavenue", credentials_configured: true }])),
    );
    // The loader requests page_size=100; this fixture simulates two API pages.
    // Its first page reports two pages while retaining the actual records.
    renderApp("/payments");
    expect(await screen.findByRole("button", { name: "cod-pending" })).toBeInTheDocument();
    expect(screen.queryByText(/CCAvenue merchant credentials are not configured/)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment status" }), "PAID");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment method" }), "PREPAID");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment purpose" }), "ADVANCE");
    fireEvent.change(screen.getByLabelText("Payment from date"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Payment to date"), { target: { value: "2026-10-31" } });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search payment or order ID" }), "prepaid");
    expect(screen.getByRole("button", { name: "prepaid-paid" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "cod-pending" })).not.toBeInTheDocument();
    expect(screen.getByText("Page 1 of 1 (1 items)")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.pathname.endsWith("/admin/payments")).every((call) => !call.url.searchParams.has("status"))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Clear Filters" }));
    expect(screen.getByText("Page 1 of 1 (3 items)")).toBeInTheDocument();
  });

  it("summarizes actual payment states by date and does not invent partial refund amounts", async () => {
    mockFetch(me,
      route("GET", "/admin/payments", () => page([
        payment({ id: "paid", status: "PAID", amount: "200.00" }),
        payment({ id: "failed", status: "FAILED", amount: "900.00" }),
        payment({ id: "pending", status: "PENDING", amount: "100.00" }),
        payment({ id: "refunded", status: "REFUNDED", amount: "50.00" }),
        payment({ id: "partial", status: "PARTIALLY_REFUNDED", amount: "80.00" }),
        payment({ id: "older", status: "PAID", amount: "400.00", created_at: "2026-09-01T10:00:00Z" }),
      ])),
      route("GET", "/admin/integrations", () => ok([])),
    );
    renderApp("/payments");
    expect(await screen.findByText("Partial refund amounts unavailable")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Payment from date"), { target: { value: "2026-10-01" } });
    const summary = screen.getByLabelText("Payment summary");
    expect(within(summary).getByText("INR 200.00")).toBeInTheDocument();
    expect(within(summary).getByText("Partial refund amounts unavailable")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Payment to date"), { target: { value: "2026-09-01" } });
    expect(screen.getByRole("alert")).toHaveTextContent("End date must be on or after start date.");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows and filters Razorpay payments as gateway records", async () => {
    mockFetch(me, route("GET", "/admin/payments", () => page([
      payment({ id: "gw-paid", provider: "RAZORPAY", status: "PAID" }),
      payment({ id: "cod-pay", provider: "COD", status: "PENDING" }),
    ])));
    renderApp("/payments");
    expect(await screen.findByRole("button", { name: "gw-paid" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Payment method" }), "RAZORPAY");
    expect(screen.getByRole("button", { name: "gw-paid" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "cod-pay" })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Razorpay" })).toBeInTheDocument();
  });

  it("keeps the existing authorized COD advance action tied to a pending payment", async () => {
    let state = "PENDING";
    const { calls } = mockFetch(me,
      route("GET", "/admin/payments", () => page([payment({ purpose: "ADVANCE", provider: "PREPAID", status: state })])),
      route("GET", "/admin/integrations", () => ok([])),
      route("POST", `/admin/payments/${paymentId}/mark-paid`, () => { state = "PAID"; return ok(payment({ purpose: "ADVANCE", status: state })); }),
    );
    renderApp("/payments");
    await userEvent.click(await screen.findByRole("button", { name: "Mark advance received" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark advance received" }));
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith(`/admin/payments/${paymentId}/mark-paid`))).toBe(true));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark advance received" })).not.toBeInTheDocument());
  });
});
