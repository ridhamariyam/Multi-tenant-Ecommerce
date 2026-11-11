import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../test/fetchMock";
import { renderApp } from "../test/renderApp";
import { NAV_GROUPS } from "../routes";


describe("Admin redesign", () => {
  it("keeps every admin navigation destination and dismisses the mobile menu with Escape", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: NAV_GROUPS.flatMap((group) => group.items.flatMap((item) => item.permission ? [item.permission] : [])) }))),
      route("GET", "/admin/orders", () => ok([])),
    );
    renderApp("/orders");
    const nav = await screen.findByRole("navigation", { name: "Admin sections" });
    for (const item of NAV_GROUPS.flatMap((group) => group.items)) {
      expect(within(nav).getByRole("link", { name: item.label })).toHaveAttribute("href", item.path);
    }
    const toggle = screen.getByRole("button", { name: "Toggle menu" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
    await userEvent.click(toggle);
    await userEvent.click(within(nav).getByRole("link", { name: "Orders" }));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
