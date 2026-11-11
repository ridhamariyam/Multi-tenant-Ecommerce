import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const inventoryRow = (id: string, status: "LOW" | "OUT_OF_STOCK" | "IN_STOCK", overrides: Record<string, unknown> = {}) => ({
  product_id: `p${id}`, product_name: `Product ${id}`, variant_id: `v${id}`, sku: `SKU-${id}`,
  variant_name: `Size ${id}`, variant_status: "ACTIVE", available_quantity: status === "OUT_OF_STOCK" ? 0 : 10,
  reserved_quantity: status === "LOW" ? 7 : 0, sellable_quantity: status === "OUT_OF_STOCK" ? 0 : status === "LOW" ? 3 : 10,
  low_stock_threshold: status === "LOW" ? 5 : 0, stock_status: status, unit_price: "100.00", stock_value: "100.00", ...overrides,
});
const catalogProduct = (id: string, category_id = "c1") => ({
  id: `p${id}`, name: `Product ${id}`, category_id, images: [{ id: `img${id}`, url: `/media/${id}.png`, is_primary: true, sort_order: 0 }],
});
const page = (rows: unknown[]) => ok(rows, { page: 1, page_size: 100, total_items: rows.length, total_pages: rows.length ? 1 : 0 });
const setup = (rows: unknown[], productRows: unknown[] = [], unsoldRows: unknown[] = []) => mockFetch(
  route("GET", "/auth/me", () => ok(profile({ permissions: ["catalogue.view", "reports.view"] }))),
  route("GET", "/admin/reports/inventory", () => ok(rows)),
  route("GET", "/admin/reports/unsold", () => ok(unsoldRows)),
  route("GET", "/catalogue/products", () => page(productRows)),
  route("GET", "/catalogue/categories", () => page([
    { id: "c1", name: "Kurtas", parent_id: null, status: "ACTIVE" },
    { id: "c2", name: "Cotton Kurtas", parent_id: "c1", status: "ACTIVE" },
    { id: "c3", name: "Dresses", parent_id: null, status: "ACTIVE" },
  ])),
);

describe("Inventory page", () => {
  it.each([
    ["all", "All Inventory"], ["low", "Low Stock"], ["out", "Out of Stock"], ["in", "In Stock"],
  ])("honors the %s dashboard shortcut and filters stock rows from the actual report", async (status, label) => {
    const { calls } = setup([
      inventoryRow("low", "LOW"), inventoryRow("out", "OUT_OF_STOCK"), inventoryRow("in", "IN_STOCK"),
    ], [catalogProduct("low"), catalogProduct("out"), catalogProduct("in")]);
    renderApp(`/inventory?stock_status=${status}`);
    expect(await screen.findByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
    await screen.findByRole("link", { name: `Product ${status === "all" ? "low" : status}` });
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/inventory") && call.url.searchParams.get("stock_status") === "all")).toBe(true);
    if (status !== "all") expect(screen.queryByRole("link", { name: "Product " + (status === "low" ? "out" : "low") })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "All Inventory" }));
    expect(screen.getByRole("link", { name: "Product low" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Product out" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Product in" })).toBeInTheDocument();
  });

  it("shows quantities, images, stock status, SKU search and category filtering", async () => {
    setup([inventoryRow("low", "LOW"), inventoryRow("dress", "IN_STOCK")], [catalogProduct("low", "c2"), catalogProduct("dress", "c3")]);
    renderApp("/inventory");
    const low = await screen.findByRole("link", { name: "Product low" });
    const row = low.closest("tr")!;
    expect(screen.getByRole("columnheader", { name: "Product ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Variant ID" })).toBeInTheDocument();
    expect(within(row).getByText("plow")).toBeInTheDocument();
    expect(within(row).getByText("vlow")).toBeInTheDocument();
    expect(within(row).getByText("SKU-low")).toBeInTheDocument();
    expect(within(row).getByText("Size low")).toBeInTheDocument();
    expect(within(row).getByText("7")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    await waitFor(() => expect(within(row).getByRole("img")).toHaveAttribute("src", "http://localhost:58000/media/low.png"));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search product or SKU" }), "SKU-dress");
    expect(screen.getByRole("link", { name: "Product dress" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Product low" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CSV" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Excel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "PDF" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "c1");
    expect(screen.getByRole("link", { name: "Product low" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Product dress" })).not.toBeInTheDocument();
  });

  it("explains a genuinely empty low-stock range and uses 50-record pagination", async () => {
    const rows = Array.from({ length: 51 }, (_, index) => inventoryRow(String(index), "IN_STOCK"));
    setup(rows, rows.map((_, index) => catalogProduct(String(index))));
    renderApp("/inventory?stock_status=low");
    expect(await screen.findByText(/No low-stock variants match these filters/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "All Inventory" }));
    expect(screen.getByText("Page 1 of 2 (51 items)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Product 50" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("link", { name: "Product 50" })).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search product or SKU" }), "SKU-1");
    expect(screen.getByText(/Page 1 of 1/)).toBeInTheDocument();
  });

  it("loads the real 30-day unsold report only when its view opens", async () => {
    const { calls } = setup([], [], [{ product_id: "p1", product_name: "Product 1", variant_id: "v1", sku: "SKU-1", sellable_quantity: 4, last_sold_at: null, listed_since: "2026-01-01T00:00:00Z" }]);
    renderApp("/inventory");
    await screen.findByRole("tab", { name: "Unsold Products" });
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/unsold"))).toBe(false);
    await userEvent.click(screen.getByRole("tab", { name: "Unsold Products" }));
    expect(await screen.findByRole("link", { name: "Product 1" })).toBeInTheDocument();
    expect(calls.some((call) => call.url.pathname.endsWith("/admin/reports/unsold") && call.url.searchParams.get("days") === "30")).toBe(true);
  });
});
