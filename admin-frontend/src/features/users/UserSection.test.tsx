import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const member = (id: string, name: string, status: "ACTIVE" | "INACTIVE") => ({
  id, name, email: `${id}@example.com`, phone: "9876543210", role: "STAFF", status,
  permissions: ["orders.view"], effective_permissions: ["orders.view"], created_at: "2026-10-01T00:00:00Z",
});

describe("Staff & permissions", () => {
  it("combines search and supported status filtering, keeps access details and pagination", async () => {
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: [] }))),
      route("GET", "/admin/staff/permissions", () => ok([{ key: "orders.view", description: "View orders" }])),
      route("GET", "/admin/staff", (url) => ok([member("a", "Asha", "ACTIVE")], { page: Number(url.searchParams.get("page") ?? 1), page_size: 20, total_items: 1, total_pages: 1 })),
    );
    renderApp("/staff");
    expect(await screen.findByText("Asha")).toBeInTheDocument();
    const row = screen.getByText("Asha").closest("tr")!;
    expect(within(row).getByText("1 permissions")).toBeInTheDocument();
    await userEvent.click(within(row).getByText("1 permissions"));
    expect(within(row).getByText("View orders")).toBeVisible();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search staff" }), { target: { value: "Asha" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Staff status" }), { target: { value: "ACTIVE" } });
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/staff") && call.url.searchParams.get("search") === "Asha" && call.url.searchParams.get("status") === "ACTIVE" && call.url.searchParams.get("page") === "1")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("combobox", { name: "Staff status" })).toHaveValue("");
  });

  it("requires confirmation before deactivating a staff account", async () => {
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: [] }))),
      route("GET", "/admin/staff/permissions", () => ok([])),
      route("GET", "/admin/staff", () => ok([member("a", "Asha", "ACTIVE")], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
      route("PATCH", "/admin/staff/a", () => ok(member("a", "Asha", "INACTIVE"))),
    );
    renderApp("/staff");
    const row = (await screen.findByText("Asha")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByRole("combobox", { name: /^Status/ }), { target: { value: "INACTIVE" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.some((call) => call.init.method === "PATCH")).toBe(false);
    await userEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByRole("button", { name: "Confirm change" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PATCH")).toBe(true));
  });

  it("confirms before discarding an edited staff form", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: [] }))),
      route("GET", "/admin/staff/permissions", () => ok([])),
      route("GET", "/admin/staff", () => ok([member("a", "Asha", "ACTIVE")], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
    );
    renderApp("/staff");
    await userEvent.click(within((await screen.findByText("Asha")).closest("tr")!).getByRole("button", { name: "Edit" }));
    const form = screen.getByRole("dialog", { name: "Edit Asha" });
    const name = within(form).getByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Asha Rao");
    await userEvent.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog", { name: "Unsaved changes" })).getByRole("button", { name: "Continue editing" }));
    expect(name).toHaveValue("Asha Rao");
    await userEvent.click(within(form).getByRole("button", { name: "Cancel" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Unsaved changes" })).getByRole("button", { name: "Discard changes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
