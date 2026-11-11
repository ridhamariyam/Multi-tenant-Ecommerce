import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "./App";
import { AuthProvider, IDLE_TIMEOUT_MS } from "./auth/AuthContext";
import { mockFetch, ok, profile, route } from "./test/fetchMock";
import { saveTokens } from "./utils/storage";

function renderAt(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>
  );
}

const orderRow = { id: "o1", order_number: "ZN-1001", status: "PENDING", payment_status: "PENDING", total_amount: "1299.00", currency: "INR", payment_method: "CASH_ON_DELIVERY", tracking_number: null, created_at: "2026-10-01T10:00:00Z" };
const orders = (rows: unknown[]) => route("GET", "/admin/orders", () => ok(rows, { page: 1, page_size: 20, total_items: rows.length, total_pages: 1 }));

describe("admin panel access", () => {
  it("sends signed-out visitors to the login page", async () => {
    renderAt("/orders");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("signs staff in through the staff endpoint and shows only permitted sections", async () => {
    const { calls } = mockFetch(
      route("POST", "/staff/auth/login", () => ok({ access_token: "a", refresh_token: "r", token_type: "bearer", expires_in: 900 })),
      route("GET", "/auth/me", () => ok(profile({ permissions: ["orders.view"] }))),
      orders([orderRow])
    );
    renderAt("/orders");

    await userEvent.click(await screen.findByRole("tab", { name: "Staff" }));
    await userEvent.type(screen.getByLabelText("Email or phone"), "staff@cliq.example");
    await userEvent.type(screen.getByLabelText("Password"), "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("ZN-1001")).toBeInTheDocument();
    expect(calls.some((c) => c.url.pathname === "/api/v1/staff/auth/login")).toBe(true);
    const nav = screen.getByRole("navigation", { name: "Admin sections" });
    expect(nav).toHaveTextContent("Orders");
    expect(nav).not.toHaveTextContent("Products");
    expect(nav).not.toHaveTextContent("Staff & permissions");
  });

  it("refuses customer accounts", async () => {
    mockFetch(
      route("POST", "/admin/auth/login", () => ok({ access_token: "a", refresh_token: "r", token_type: "bearer", expires_in: 900 })),
      route("GET", "/auth/me", () => ok(profile({ role: "CUSTOMER" })))
    );
    renderAt("/");
    await userEvent.click(await screen.findByRole("tab", { name: "Store admin" }));
    await userEvent.type(await screen.findByLabelText("Email or phone"), "x@y.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("cannot use the admin panel");
  });

  it("signs out a customer session restored from storage", async () => {
    saveTokens("a", "r");
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "CUSTOMER", permissions: [] }))),
      route("POST", "/auth/logout", () => ok(null))
    );
    renderAt("/orders");

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(await screen.findByText("This account cannot use the admin panel.")).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
  });

  it("blocks a screen the account has no permission for", async () => {
    saveTokens("a", "r");
    mockFetch(route("GET", "/auth/me", () => ok(profile({ permissions: ["orders.view"] }))));
    renderAt("/staff");

    expect(await screen.findByText("No access")).toBeInTheDocument();
  });

  it("signs out after the configured inactivity period", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    saveTokens("a", "r");
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["orders.view"] }))),
      route("POST", "/auth/logout", () => ok(null)),
      orders([])
    );
    renderAt("/orders");
    expect(await screen.findByText("No orders match these filters.")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(IDLE_TIMEOUT_MS + 1000);
    });

    const minutes = IDLE_TIMEOUT_MS / 60_000;
    await waitFor(() => expect(screen.getByText(new RegExp(`signed out after ${minutes} minutes`))).toBeInTheDocument());
  });
});

describe("orders list", () => {
  it("shows the backend error instead of an empty table", async () => {
    saveTokens("a", "r");
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ permissions: ["orders.view"] }))),
      route("GET", "/admin/orders", () => ({ status: 500, body: { message: "Database unavailable" } }))
    );
    renderAt("/orders");

    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
  });

  it("passes the search box to the backend", async () => {
    saveTokens("a", "r");
    const { calls } = mockFetch(route("GET", "/auth/me", () => ok(profile({ permissions: ["orders.view"] }))), orders([orderRow]));
    renderAt("/orders");
    await screen.findByText("ZN-1001");

    await userEvent.type(screen.getByLabelText("Search orders"), "9876500001");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(calls.some((c) => c.url.searchParams.get("search") === "9876500001")).toBe(true));
  });
});
