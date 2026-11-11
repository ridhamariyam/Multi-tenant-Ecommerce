import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { guidanceForPath, guidanceStorageKey } from "./guidanceConfig";

const admin = (id = "u1") => profile({ id, role: "ADMIN", permissions: ["orders.view", "catalogue.view", "reviews.view", "cms.view"] });
const requests = (id = "u1") => mockFetch(
  route("GET", "/auth/me", () => ok(admin(id))),
  route("GET", "/admin/orders", () => ok([], { page: 1, page_size: 20, total_items: 0, total_pages: 1 })),
);
const orderSearchHint = /Search by order number, customer name, phone, email, product or SKU/;

describe("inline Admin guidance", () => {
  it("shows a control hint until Got it and remembers dismissal across navigation", async () => {
    requests();
    const app = renderApp("/orders");
    const hint = await screen.findByText(orderSearchHint);
    const search = screen.getByRole("searchbox", { name: "Search orders" });
    expect(hint.closest(".guided-control")).toContainElement(search);
    expect(search.closest(".guided-control")?.nextElementSibling).toBe(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByText("Filter by the order's current fulfilment status.").closest(".guided-control")).toContainElement(screen.getByRole("combobox", { name: "Order status" }));
    expect(screen.getByText("Start of the order date range.").closest(".guided-control")).toContainElement(screen.getByLabelText("From date"));
    const selectAll = await screen.findByRole("checkbox", { name: "Select all eligible on this page" });
    expect(selectAll.closest(".record-table-panel")?.firstElementChild).toContainElement(selectAll);
    expect(screen.queryByText("Welcome to CliQ. Admin")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByText(orderSearchHint)).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search orders" }).closest(".filters")).toHaveClass("filters");
    expect(screen.getByRole("checkbox", { name: "Select all eligible on this page" }).parentElement?.parentElement).toHaveClass("record-table-panel");
    app.unmount();
    renderApp("/orders");
    expect(await screen.findByRole("combobox", { name: "Order status" })).toBeInTheDocument();
    expect(screen.queryByText(orderSearchHint)).not.toBeInTheDocument();
    expect(guidanceForPath("/orders/order-1")?.key).toBe("/orders/detail");
    expect(guidanceForPath("/products/new")?.key).toBe("/products/new");
  });

  it("reopens the current page's inline hint from Help", async () => {
    requests();
    renderApp("/orders");
    await screen.findByText(orderSearchHint);
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    await userEvent.click(screen.getByRole("button", { name: "Show page guidance" }));
    expect(await screen.findByText(orderSearchHint)).toBeInTheDocument();
  });

  it("turns hints off globally, then shows dismissed hints when turned on again", async () => {
    requests();
    let app = renderApp("/settings");
    expect(await screen.findByText(/Turn this off to hide hints/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    let toggle = screen.getByRole("checkbox", { name: /Show page guidance/ });
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(screen.queryByRole("button", { name: "Show page guidance" })).not.toBeInTheDocument();
    app.unmount();
    app = renderApp("/orders");
    await screen.findByRole("combobox", { name: "Order status" });
    expect(screen.queryByText(orderSearchHint)).not.toBeInTheDocument();
    app.unmount();
    renderApp("/settings");
    toggle = await screen.findByRole("checkbox", { name: /Show page guidance/ });
    await userEvent.click(toggle);
    expect(await screen.findByText(/Turn this off to hide hints/)).toBeInTheDocument();
  });

  it("resets dismissals in Settings and keeps them per admin", async () => {
    requests("u1");
    let app = renderApp("/settings");
    await screen.findByText(/Turn this off to hide hints/);
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByText(/Turn this off to hide hints/)).not.toBeInTheDocument();
    app.unmount();
    app = renderApp("/orders");
    await screen.findByText(orderSearchHint);
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    app.unmount();
    app = renderApp("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Show guidance again" }));
    expect(await screen.findByText(/Turn this off to hide hints/)).toBeInTheDocument();
    app.unmount();
    app = renderApp("/orders");
    expect(await screen.findByText(orderSearchHint)).toBeInTheDocument();
    app.unmount();
    requests("u2");
    renderApp("/settings");
    expect(await screen.findByText(/Turn this off to hide hints/)).toBeInTheDocument();
    expect(localStorage.getItem(guidanceStorageKey("t1", "u1"))).not.toBeNull();
    expect(localStorage.getItem(guidanceStorageKey("t1", "u2"))).toBeNull();
  });
});
