import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Notifications from "./Notifications";
import { getDashboardOverview } from "../api/dashboard";
import type { DashboardOverview } from "../types/dashboard";

const auth = vi.hoisted(() => ({ user: { id: "u1", tenant_id: "t1" }, isAdmin: true, can: vi.fn(() => true) }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("../api/dashboard", () => ({ getDashboardOverview: vi.fn() }));

function overview(populated = true) {
  return {
    recent_orders: populated ? [{ order_id: "o1", order_number: "CLIQ-001", order_status: "PENDING", payment_status: "PAID", total_amount: "1200", currency: "INR", created_at: "2026-10-08T09:00:00Z" }] : [],
    inventory: { low_stock_variants: populated ? [{ product_id: "p1", product_name: "Linen shirt", variant_id: "v1", sku: "LS-M", available_quantity: 2 }] : [], out_of_stock_variants: [] },
  } as unknown as DashboardOverview;
}
function setup() {
  render(<MemoryRouter><Notifications /><Routes><Route path="/" element={<p>Dashboard</p>} /><Route path="/orders/o1" element={<h1>Order detail</h1>} /><Route path="/products/p1" element={<h1>Product detail</h1>} /></Routes></MemoryRouter>);
  return userEvent.setup();
}
async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /^Notifications/ }));
  return screen.getByRole("dialog", { name: "Notifications" });
}

describe("Notification popover", () => {
  beforeEach(() => {
    vi.mocked(getDashboardOverview).mockReset();
    vi.mocked(getDashboardOverview).mockResolvedValue({ success: true, message: "OK", data: overview(), meta: null });
    auth.isAdmin = true;
    auth.can.mockReturnValue(true);
  });

  it("opens without leaving the dashboard and filters real order, sale and stock notifications", async () => {
    const user = setup();
    expect(getDashboardOverview).not.toHaveBeenCalled();
    const dialog = await open(user);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(await within(dialog).findByText("Order CLIQ-001")).toBeInTheDocument();
    expect(within(dialog).getAllByRole("img", { name: "Unread" })).toHaveLength(3);
    expect(within(dialog).getByText("Order CLIQ-001").closest("a")?.querySelector("time")).toHaveAttribute("datetime", "2026-10-08T09:00:00Z");
    await user.click(within(dialog).getByRole("tab", { name: "Sales" }));
    expect(within(dialog).getByText("Sale · CLIQ-001")).toBeInTheDocument();
    expect(within(dialog).queryByText("Order CLIQ-001")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("link")).toHaveAttribute("href", "/orders/o1");
    await user.click(within(dialog).getByRole("tab", { name: "Alerts" }));
    expect(within(dialog).getByText("Low stock · Linen shirt")).toBeInTheDocument();
    expect(within(dialog).getByRole("link")).toHaveAttribute("href", "/products/p1");
    expect(within(dialog).getByText(/^First observed/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("link"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Product detail" })).toBeInTheDocument();
  });

  it("marks every category read and persists this state after reopening", async () => {
    const user = setup();
    const dialog = await open(user);
    await within(dialog).findByText("Order CLIQ-001");
    await user.click(within(dialog).getByRole("tab", { name: "Orders" }));
    await user.click(within(dialog).getByRole("button", { name: "Mark all as read" }));
    expect(within(dialog).getByText("0 unread")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("cliq:notifications:t1:u1")!).read).toHaveLength(3);
    await user.click(within(dialog).getByRole("button", { name: "Close notifications" }));
    const reopened = await open(user);
    await within(reopened).findByText("Order CLIQ-001");
    expect(within(reopened).queryByRole("img", { name: "Unread" })).not.toBeInTheDocument();
  });

  it("marks clicked orders read and navigates to their detail page", async () => {
    const user = setup();
    const dialog = await open(user);
    await within(dialog).findByText("Order CLIQ-001");
    await user.click(within(dialog).getByRole("tab", { name: "Orders" }));
    await user.click(within(dialog).getByRole("link"));
    expect(screen.getByRole("heading", { name: "Order detail" })).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("cliq:notifications:t1:u1")!).read).toEqual(["order:o1:PENDING"]);
  });

  it("anchors below the bell without locking scroll and supports keyboard tabs and Escape", async () => {
    const user = setup();
    const dialog = await open(user);
    await within(dialog).findByText("Order CLIQ-001");
    expect(document.body.style.overflow).toBe("");
    expect(dialog).not.toHaveAttribute("aria-modal", "true");
    expect(dialog.parentElement).toHaveClass("header-notification-anchor");
    const close = within(dialog).getByRole("button", { name: "Close notifications" });
    expect(close).toHaveFocus();
    within(dialog).getByRole("tab", { name: "All" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(within(dialog).getByRole("tab", { name: "Orders" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Notifications/ })).toHaveFocus();
  });

  it("dismisses on outside clicks and toggles from the bell", async () => {
    const user = setup();
    await open(user);
    await user.click(screen.getByText("Dashboard"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await open(user);
    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each([[1440, 900], [768, 1024], [390, 844]])("positions below the bell and clamps height at %ix%i", async (width, height) => {
    vi.stubGlobal("innerWidth", width);
    vi.stubGlobal("innerHeight", height);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 32, bottom: 70, left: width - 150, right: width - 112, width: 38, height: 38, x: width - 150, y: 32, toJSON: () => ({}) });
    const user = setup();
    const dialog = await open(user);
    expect(dialog.style.top).toBe("82px");
    expect(Number.parseFloat(dialog.style.maxHeight)).toBe(height - 82 - 16);
    vi.unstubAllGlobals();
  });

  it("shows empty states and refreshes from the icon beside Close", async () => {
    vi.mocked(getDashboardOverview).mockRejectedValueOnce(new Error("Unavailable"));
    const user = setup();
    const dialog = await open(user);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Could not load notifications");
    vi.mocked(getDashboardOverview).mockResolvedValue({ success: true, message: "OK", data: overview(false), meta: null });
    const refresh = within(dialog).getByRole("button", { name: "Refresh notifications" });
    expect(refresh).toHaveClass("notification-refresh");
    expect(within(dialog).queryByRole("button", { name: /^Refresh$/ })).not.toBeInTheDocument();
    await user.click(refresh);
    expect(await within(dialog).findByText("You're all caught up. No notifications yet.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("tab", { name: "Sales" }));
    expect(within(dialog).getByText("No sales notifications yet.")).toBeInTheDocument();
  });

  it("does not request dashboard data without permission", async () => {
    auth.isAdmin = false;
    auth.can.mockReturnValue(false);
    const user = setup();
    await open(user);
    expect(screen.getByText("Dashboard access is required to view store alerts.")).toBeInTheDocument();
    expect(getDashboardOverview).not.toHaveBeenCalled();
  });

  it("hides records that staff cannot access", async () => {
    auth.isAdmin = false;
    auth.can.mockImplementation((permission?: string) => permission === "dashboard.view" || permission === "catalogue.view");
    const user = setup();
    const dialog = await open(user);
    await within(dialog).findByText("Low stock · Linen shirt");
    expect(within(dialog).queryByText("Order CLIQ-001")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Sale · CLIQ-001")).not.toBeInTheDocument();
    expect(within(dialog).getByText("1 unread")).toBeInTheDocument();
  });
});
