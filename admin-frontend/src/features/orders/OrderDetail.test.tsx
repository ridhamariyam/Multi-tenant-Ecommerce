import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { NEXT_STATUSES } from "../../types/order";

const baseOrder = {
  id: "order-1", order_number: "ZN-1001", status: "PACKED", payment_status: "PENDING",
  payment_method: "CASH_ON_DELIVERY", payments: [], items: [],
  subtotal: "100.00", discount_amount: "0.00", shipping_amount: "0.00",
  cod_fee: "0.00", tax_amount: "0.00", total_amount: "100.00",
  advance_amount: "0.00", currency: "INR", coupon_code: null,
  estimated_delivery_date: null, return_reason: null, return_note: null,
  shipment: { courier_name: null, tracking_number: null, tracking_url: null },
  delivery_address: { full_name: "Customer", phone: "+919876543210", address_line_1: "Main Road", address_line_2: null, city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India" },
  contact_email: null, is_guest: false, gst: null, created_at: "2026-10-01T10:00:00Z",
};

describe("order status transitions", () => {
  it("offers the backend-supported delivery path from PACKED and persists delivery through the API", async () => {
    let current = baseOrder;
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["orders.view", "orders.manage"] }))),
      route("GET", "/admin/orders/order-1", () => ok(current)),
      route("GET", "/admin/orders/order-1/tracking", () => ok({ order_number: current.order_number, status: current.status, events: [] })),
      route("PATCH", "/admin/orders/order-1/status", (_url, init) => {
        const body = JSON.parse(String(init.body));
        current = { ...current, status: body.status };
        return ok(current);
      }),
    );
    renderApp("/orders/order-1");
    const select = await screen.findByRole("combobox", { name: "Move to" });
    expect(within(select).getAllByRole("option").map((option) => (option as HTMLOptionElement).value))
      .toEqual(["", ...NEXT_STATUSES.PACKED]);
    await userEvent.selectOptions(select, "DELIVERED");
    await userEvent.type(screen.getByRole("textbox", { name: "Note (shown in tracking)" }), "Handed to customer");
    await userEvent.click(screen.getByRole("button", { name: "Update status" }));
    await waitFor(() => expect(screen.getByText("Order moved to Delivered")).toBeInTheDocument());
    const patch = calls.find((call) => call.init.method === "PATCH" && call.url.pathname.endsWith("/status"));
    expect(JSON.parse(String(patch?.init.body))).toMatchObject({ status: "DELIVERED", note: "Handed to customer" });
    await waitFor(() => expect(calls.filter((call) => call.url.pathname.endsWith("/tracking")).length).toBeGreaterThan(1));
  });

  it("does not offer delivery to a PACKED order with an unpaid COD advance", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["orders.view", "orders.manage"] }))),
      route("GET", "/admin/orders/order-1", () => ok({ ...baseOrder, advance_amount: "20.00", payments: [{ id: "advance-1", purpose: "ADVANCE", status: "PENDING", provider: "COD", amount: "20.00", currency: "INR" }] })),
      route("GET", "/admin/orders/order-1/tracking", () => ok({ order_number: baseOrder.order_number, status: "PACKED", events: [] })),
    );
    renderApp("/orders/order-1");
    const select = await screen.findByRole("combobox", { name: "Move to" });
    expect(within(select).queryByRole("option", { name: "Delivered" })).not.toBeInTheDocument();
    expect(within(select).queryByRole("option", { name: "Out for delivery" })).not.toBeInTheDocument();
    expect(screen.getByText("Record the COD advance before moving this order forward.")).toBeInTheDocument();
  });
});
