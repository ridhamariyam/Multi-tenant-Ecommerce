import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const coupon = (id: string, overrides: Record<string, unknown> = {}) => ({
  id, code: id.toUpperCase(), discount_type: "PERCENTAGE", discount_value: "10.00", currency: "INR",
  min_order_amount: null, max_discount_amount: null, starts_at: null, expires_at: null,
  usage_limit: null, per_customer_usage_limit: null, times_used: 0, is_active: true,
  is_automatic: false, first_order_only: false, min_quantity: null, buy_quantity: null,
  get_quantity: null, category_ids: [], valid_weekdays: [], created_at: "2026-10-01T10:00:00Z", ...overrides,
});
const paged = (rows: unknown[], current = 1, total = rows.length) => ok(rows, {
  page: current, page_size: 100, total_items: total, total_pages: Math.ceil(total / 100),
});
const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["coupons.view", "coupons.manage"] })));
const categories = route("GET", "/admin/categories", () => ok([]));

describe("Coupons page", () => {
  it("keeps filtered pagination consistent across backend pages", async () => {
    const data = Array.from({ length: 101 }, (_, index) => coupon(`code${index}`, { is_active: index % 2 === 0 }));
    mockFetch(me, categories, route("GET", "/admin/coupons", (url) => {
      const current = Number(url.searchParams.get("page") ?? 1);
      return paged(data.slice((current - 1) * 100, current * 100), current, data.length);
    }));
    renderApp("/coupons");
    expect(await screen.findByText("Page 1 of 6 (101 items)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 2 of 6 (101 items)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Enabled only" }));
    expect(screen.getByText("Page 1 of 3 (51 items)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 3 of 3 (51 items)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CODE100" })).toBeInTheDocument();
  });

  it("combines code, lifecycle status and offer filters with accurate usage and pagination", async () => {
    const data = [
      coupon("global3"),
      coupon("global4", { usage_limit: 1 }),
      coupon("fixed", { discount_type: "FIXED_AMOUNT", is_active: false }),
      coupon("expired", { expires_at: "2020-01-01T00:00:00Z" }),
      coupon("scheduled", { starts_at: "2099-01-01T00:00:00Z" }),
    ];
    mockFetch(me, categories, route("GET", "/admin/coupons", () => paged(data)));
    renderApp("/coupons");
    expect(await screen.findByRole("button", { name: "GLOBAL3" })).toBeInTheDocument();
    expect(screen.getAllByText("0 / unlimited").length).toBeGreaterThan(0);
    expect(screen.getByText("0 / 1")).toBeInTheDocument();
    expect(screen.queryByText("Disabled")).not.toBeInTheDocument();
    expect(screen.getAllByText("Inactive").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Scheduled").length).toBeGreaterThan(1);
    expect(screen.getByText("Page 1 of 1 (5 items)")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Coupon status" }), "INACTIVE");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Offer type" }), "FIXED_AMOUNT");
    expect(screen.getByRole("button", { name: "FIXED" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "GLOBAL3" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search coupon code" }), "not-found");
    expect(screen.getByText("No coupons match these filters.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear Filters" }));
    expect(screen.getByRole("button", { name: "GLOBAL3" })).toBeInTheDocument();
  });

  it("keeps Enabled only consistent with Inactive, opens editing, and confirms deletion", async () => {
    const { calls } = mockFetch(me, categories,
      route("GET", "/admin/coupons", () => paged([coupon("enabled"), coupon("disabled", { is_active: false })])),
      route("DELETE", "/admin/coupons/enabled", () => ok(null)),
    );
    renderApp("/coupons");
    await screen.findByRole("button", { name: "ENABLED" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Coupon status" }), "INACTIVE");
    expect(screen.getByRole("button", { name: "DISABLED" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Enabled only" }));
    expect(screen.getByRole("combobox", { name: "Coupon status" })).toHaveValue("");
    expect(screen.queryByRole("button", { name: "DISABLED" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ENABLED" }));
    expect(screen.getByRole("dialog", { name: "Edit ENABLED" })).toBeInTheDocument();
    expect(within(screen.getByRole("dialog", { name: "Edit ENABLED" })).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog", { name: "Edit ENABLED" })).getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const confirmation = screen.getByRole("dialog");
    expect(within(confirmation).getByText("Delete coupon ENABLED?")).toBeInTheDocument();
    expect(calls.some((call) => call.init.method === "DELETE")).toBe(false);
    await userEvent.click(within(confirmation).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/coupons/enabled") && call.init.method === "DELETE")).toBe(true));
  });
});
