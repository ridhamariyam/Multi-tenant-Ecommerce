import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../test/fetchMock";
import { renderApp } from "../test/renderApp";

function setup() {
  mockFetch(
    route("GET", "/auth/me", () => ok(profile({ name: "Seed Admin", role: "ADMIN", permissions: ["orders.view", "settings.view"] }))),
    route("GET", "/admin/orders", () => ok([])),
    route("POST", "/auth/logout", () => ok(null)),
  );
  renderApp("/orders");
  return userEvent.setup();
}

describe("Sidebar account controls", () => {
  it("moves the profile out of the header and opens working Profile and Settings destinations", async () => {
    const user = setup();
    const profileButton = await screen.findByRole("button", { name: /Signed in as Seed Admin/ });
    const sidebar = screen.getByRole("navigation", { name: "Admin sections" });
    expect(sidebar).toContainElement(profileButton);
    const header = screen.getByRole("banner");
    expect(within(header).queryByText(/Signed in as/)).not.toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Notifications" })).toBeInTheDocument();
    await user.click(profileButton);
    const menu = screen.getByRole("menu", { name: "Account" });
    expect(within(menu).getByRole("menuitem", { name: "Profile" })).toHaveFocus();
    await user.click(within(menu).getByRole("menuitem", { name: "Profile" }));
    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("Seed Admin", { selector: "dd" })).toBeInTheDocument();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(profileButton);
    await user.click(screen.getByRole("menuitem", { name: "Settings" }));
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Delivery" })).toHaveAttribute("href", "/delivery");
  });

  it("handles keyboard dismissal, outside clicks, mobile navigation and sign out", async () => {
    const user = setup();
    const profileButton = await screen.findByRole("button", { name: /Signed in as Seed Admin/ });
    await user.click(profileButton);
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Settings" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(profileButton).toHaveFocus();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(profileButton);
    await user.click(screen.getByRole("heading", { name: "Orders" }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Toggle menu" });
    await user.click(toggle);
    await user.click(profileButton);
    await user.click(screen.getByRole("menuitem", { name: "Profile" }));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(profileButton);
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
