import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["reviews.view", "reviews.manage", "catalogue.view", "customers.view", "orders.view"] })));
const review = (id: string, approved: boolean) => ({
  id, product_id: "p1", user_id: "c1", order_id: "o1", rating: 5, title: "Lovely",
  comment: "Comfortable fabric", is_verified_purchase: true, is_approved: approved,
  created_at: "2026-10-01T10:00:00Z", images: [{ id: "im1", image_url: "/media/review.png", alt_text: "Customer photo", created_at: "2026-10-01T10:00:00Z" }],
});
const product = { id: "p1", name: "Cotton Kurta", images: [{ id: "pi1", url: "/media/product.png", is_primary: true, sort_order: 0 }] };
const customer = { id: "c1", name: "Maya" };

describe("Reviews page", () => {
  it("shows supported approval views, details and confirms hiding an approved review", async () => {
    let approved = true;
    const { calls } = mockFetch(me,
      route("GET", "/admin/reviews", (url) => ok(
        url.searchParams.get("is_approved") === "false" ? [] : [review("r1", approved)],
        { page: 1, page_size: 20, total_items: 1, total_pages: 1 },
      )),
      route("GET", "/catalogue/products/p1", () => ok(product)),
      route("GET", "/admin/customers/c1", () => ok(customer)),
      route("PATCH", "/admin/reviews/r1", () => { approved = false; return ok(review("r1", false)); }),
    );
    renderApp("/reviews");
    expect(await screen.findByText(/No unpublished reviews/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Waiting for Approval / Hidden" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Hidden" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Review status" }), "true");
    expect(await screen.findByText("Cotton Kurta")).toBeInTheDocument();
    expect(await screen.findByText("Maya")).toBeInTheDocument();
    expect(screen.getByText("Comfortable fabric")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Customer photo" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(calls.some((call) => call.init.method === "PATCH" && call.url.pathname.endsWith("/admin/reviews/r1"))).toBe(false);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Hide" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PATCH" && call.url.pathname.endsWith("/admin/reviews/r1"))).toBe(true));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Review status" }), "");
    expect(await screen.findByText("Cotton Kurta")).toBeInTheDocument();
  });

  it("keeps request states, dates and linked order/customer details", async () => {
    const { calls } = mockFetch(me,
      route("GET", "/admin/reviews", () => ok([])),
      route("GET", "/admin/reviews/requests", () => ok([{
        id: "rr1", order_id: "o1", customer_id: "c1", status: "PENDING",
        send_after: "2026-10-10T10:00:00Z", sent_at: null, created_at: "2026-10-08T10:00:00Z",
      }], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
      route("GET", "/admin/orders/o1", () => ok({ id: "o1", order_number: "CLIQ-100" })),
      route("GET", "/admin/orders/o1/tracking", () => ok({ order_number: "CLIQ-100", events: [{ status: "DELIVERED", occurred_at: "2026-10-07T10:00:00Z" }] })),
      route("GET", "/admin/customers/c1", () => ok(customer)),
    );
    renderApp("/reviews");
    await userEvent.click(await screen.findByRole("tab", { name: "Review requests" }));
    expect(await screen.findByRole("link", { name: "CLIQ-100" })).toHaveAttribute("href", "/orders/o1");
    expect(await screen.findByRole("link", { name: "Maya" })).toHaveAttribute("href", "/customers/c1");
    expect(screen.getByRole("columnheader", { name: "Delivered" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Cancelled" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Request status" }), "SENT");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/reviews/requests") && call.url.searchParams.get("status") === "SENT")).toBe(true));
  });
});
