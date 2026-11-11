import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const orderId = "11111111-1111-4111-8111-111111111111";
const entry = (id: string, action: string) => ({
  id, actor_id: "22222222-2222-4222-8222-222222222222", actor_name: "Asha", actor_role: "ADMIN",
  action, entity_type: action.startsWith("auth.") ? "session" : "order",
  entity_id: action.startsWith("auth.") ? null : orderId,
  summary: action.startsWith("auth.") ? "Signed in (admin)" : "Updated order",
  changes: action.startsWith("auth.") ? null : { method: "PATCH" }, ip_address: "127.0.0.1",
  created_at: "2026-10-12T10:00:00Z",
});

describe("Activity log", () => {
  it("keeps distinct events, opens recorded details and links only supported records", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["audit.view", "orders.view"] }))),
      route("GET", "/admin/audit-logs", () => ok([entry("event-1", "order.updated"), entry("event-2", "order.updated")], { page: 1, page_size: 20, total_items: 2, total_pages: 1 })),
    );
    renderApp("/activity");
    expect((await screen.findAllByRole("button", { name: "Order Updated" })).length).toBe(2);
    expect(screen.getAllByRole("link", { name: "order" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "order" })[0]).toHaveAttribute("href", `/orders/${orderId}`);
    await userEvent.click(screen.getAllByRole("button", { name: "Order Updated" })[0]);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("order.updated")).toBeInTheDocument();
    expect(within(dialog).getByText("127.0.0.1")).toBeInTheDocument();
    expect(within(dialog).getByText(/"method": "PATCH"/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open record" })).toHaveAttribute("href", `/orders/${orderId}`);
  });

  it("filters sign-ins by the real auth prefix, clears filters and resets pagination", async () => {
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["audit.view"] }))),
      route("GET", "/admin/audit-logs", (url) => {
        const filtered = url.searchParams.get("action") === "auth.";
        return ok(filtered ? [entry("success", "auth.login"), entry("failure", "auth.login_failed")] : [entry("order", "order.updated")],
          { page: Number(url.searchParams.get("page") ?? 1), page_size: 20, total_items: filtered ? 2 : 21, total_pages: filtered ? 1 : 2 });
      }),
    );
    renderApp("/activity");
    expect(await screen.findByRole("button", { name: "Order Updated" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/audit-logs") && call.url.searchParams.get("page") === "2")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Sign-ins only" }));
    expect(await screen.findByRole("button", { name: "Sign-in failed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Signed in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign-ins only" })).toHaveAttribute("aria-pressed", "true");
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/audit-logs") && call.url.searchParams.get("action") === "auth." && call.url.searchParams.get("entity_type") === "session" && call.url.searchParams.get("page") === "1")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByRole("button", { name: "Order Updated" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-10-12" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-10-11" } });
    expect(await screen.findByText("End date must be on or after start date.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Order Updated" })).not.toBeInTheDocument());
  });
});
