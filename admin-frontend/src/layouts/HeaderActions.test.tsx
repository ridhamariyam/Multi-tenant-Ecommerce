import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockFetch, ok, profile, route } from "../test/fetchMock";
import { renderApp } from "../test/renderApp";

function setup() {
  const mocked = mockFetch(
    route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["orders.view", "catalogue.view", "catalogue.manage", "coupons.manage", "cms.view", "reports.view"] }))),
    route("GET", "/admin/orders", () => ok([], { page: 1, page_size: 20, total_items: 0, total_pages: 0 })),
  );
  renderApp("/orders");
  return { ...mocked, user: userEvent.setup() };
}

describe("Global workspace actions", () => {
  it("makes Quick Actions available on Orders and Profile with keyboard dismissal and valid routes", async () => {
    const { user } = setup();
    await screen.findByRole("heading", { name: "Orders" });
    const quick = screen.getByRole("button", { name: "Quick Actions" });
    await user.click(quick);
    expect(screen.getByRole("menuitem", { name: "Add Product" })).toHaveAttribute("href", "/products/new");
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Create Coupon" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(quick).toHaveFocus();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Signed in as/ }));
    await user.click(screen.getByRole("menuitem", { name: "Profile" }));
    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Quick Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "View Orders" }));
    expect(await screen.findByRole("heading", { name: "Orders" })).toBeInTheDocument();
  });

  it("refreshes the current page, disables the icon while loading, and recovers after errors", async () => {
    const { user, fn } = setup();
    await screen.findByText("No orders match these filters.");
    const refresh = screen.getByRole("button", { name: "Refresh workspace data" });
    await waitFor(() => expect(refresh).toBeEnabled());
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => String(input).includes("/admin/orders")
      ? new Promise<Response>((resolve) => { finish = resolve; }) : fn(input, init)));
    await user.click(refresh);
    await waitFor(() => expect(refresh).toBeDisabled());
    expect(refresh).toHaveAttribute("aria-busy", "true");
    await act(async () => finish(new Response(JSON.stringify({ message: "Temporarily unavailable" }), { status: 503 })));
    expect(await screen.findByText("Temporarily unavailable")).toBeInTheDocument();
    await waitFor(() => expect(refresh).toBeEnabled());
    vi.stubGlobal("fetch", fn);
    await user.click(refresh);
    expect(await screen.findByText("No orders match these filters.")).toBeInTheDocument();
    await waitFor(() => expect(refresh).toHaveAttribute("aria-busy", "false"));
  });
});
