import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import ProductImage from "./ProductImage";

const product = (id: string, overrides: Record<string, unknown> = {}) => ({
  id, category_id: "c1", name: `Product ${id}`, slug: `product-${id}`, short_description: null,
  description: null, brand: null, status: "ACTIVE", gender: "WOMEN", fabric: null,
  occasion: null, sleeve: null, neckline: null, fabric_details: null, washing_instructions: null,
  country_of_origin: null, size_chart: null, hsn_code: null, gst_rate: null, is_featured: false,
  seo_title: null, seo_description: null, options: [], images: [], ...overrides,
});
const paged = (rows: unknown[], current = 1, total = rows.length) => ok(rows, {
  page: current, page_size: 100, total_items: total, total_pages: Math.ceil(total / 100),
});
const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["catalogue.view", "catalogue.manage"] })));
const categories = route("GET", "/catalogue/categories", () => ok([]));

describe("Products listing", () => {
  it("creates a reusable fabric from a new product, selects it, and reloads it for editing", async () => {
    sessionStorage.clear();
    const values: Array<{ id: string; attribute: "fabric"; value: string; is_active: boolean; position: number; product_count: number }> = [];
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => ok([], { page: 1, page_size: 100, total_items: 0, total_pages: 1 })),
      route("GET", "/catalogue/attributes", () => ok(values)),
      route("POST", "/catalogue/attributes", (_url, init) => {
        const body = JSON.parse(init.body as string);
        const created = { id: "fabric-1", attribute: body.attribute, value: body.value, is_active: true, position: 0, product_count: 0 } as const;
        values.push(created);
        return ok(created);
      }),
      route("GET", "/catalogue/products/p1", () => ok(product("p1"))),
    );
    const app = renderApp("/products/new");
    await screen.findByRole("combobox", { name: "fabric" });
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Unfinished kurta");
    await userEvent.click(screen.getByRole("button", { name: "+ Add new occasion" }));
    await userEvent.type(screen.getByRole("textbox", { name: "New occasion name" }), "Festival");
    await userEvent.click(within(screen.getByRole("textbox", { name: "New occasion name" }).closest(".attribute-picker")!).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Unfinished kurta");
    await userEvent.click(screen.getByRole("button", { name: "+ Add new fabric" }));
    await userEvent.type(screen.getByRole("textbox", { name: "New fabric name" }), "  Handloom  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "fabric" })).toHaveValue("Handloom"));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Unfinished kurta");
    expect(calls.filter((call) => call.url.pathname.endsWith("/catalogue/attributes") && call.init.method === "POST")).toHaveLength(1);
    expect(calls.some((call) => call.url.pathname.endsWith("/catalogue/products") && call.init.method === "POST")).toBe(false);
    app.unmount();
    const editor = renderApp("/products/p1");
    const fabric = await screen.findByRole("combobox", { name: "fabric" });
    await waitFor(() => expect(within(fabric).getByRole("option", { name: "Handloom" })).toBeInTheDocument());
    editor.unmount();
    renderApp("/categories");
    await userEvent.click(await screen.findByRole("tab", { name: "Filter values" }));
    expect(await screen.findByText("Handloom")).toBeInTheDocument();
    sessionStorage.clear();
  });
  it("shows inline required errors, ignores whitespace, and allows an explicit draft with optional fields blank", async () => {
    const created = product("p2", { name: "Cotton Kurta", status: "DRAFT" });
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => ok([{ id: "c1", name: "Kurtas", parent_id: null, status: "ACTIVE" }])),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("POST", "/catalogue/images/upload", () => ok({ url: "/media/kurta.jpg" })),
      route("POST", "/catalogue/products", () => ok(created)),
      route("GET", "/catalogue/products/p2", () => ok(created)),
      route("GET", "/catalogue/products/p2/variants", () => ok([])),
    );
    renderApp("/products/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).toHaveAttribute("aria-required", "true");
    expect(screen.getByRole("textbox", { name: "Brand" })).not.toHaveAttribute("aria-required");
    await userEvent.click(screen.getByRole("button", { name: "Create product" }));
    expect(name).toHaveAccessibleDescription("Product name is required.");
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveAccessibleDescription("Choose a category.");
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    await userEvent.type(name, "   ");
    expect(name).toHaveAccessibleDescription("Product name is required.");
    await userEvent.clear(name);
    await userEvent.type(name, "Cotton Kurta");
    expect(name).not.toHaveAttribute("aria-invalid");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "c1");
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["png"], "kurta.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Create product" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "POST" && call.url.pathname.endsWith("/catalogue/products"))).toBe(true));
    const posted = calls.find((call) => call.init.method === "POST" && call.url.pathname.endsWith("/catalogue/products"));
    expect(JSON.parse(posted!.init.body as string)).toMatchObject({ status: "DRAFT", brand: null });
  });

  it("creates a draft and opens Variants & stock as the next step", async () => {
    const created = product("p1", { name: "Cotton Kurta", status: "DRAFT" });
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => ok([{ id: "c1", name: "Kurtas", parent_id: null, status: "ACTIVE" }])),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("POST", "/catalogue/images/upload", () => ok({ url: "/media/kurta.jpg" })),
      route("POST", "/catalogue/products", () => ok(created)),
      route("GET", "/catalogue/products/p1", () => ok(created)),
      route("GET", "/catalogue/products/p1/variants", () => ok([])),
    );
    renderApp("/products/new");
    await userEvent.type(await screen.findByRole("textbox", { name: "Name" }), "Cotton Kurta");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "c1");
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["png"], "kurta.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Create product" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Variants & stock" })).toHaveAttribute("aria-selected", "true"));
    const posted = calls.find((call) => call.url.pathname.endsWith("/catalogue/products") && call.init.method === "POST");
    expect(JSON.parse(posted!.init.body as string)).toMatchObject({ status: "DRAFT", images: [{ url: "/media/kurta.jpg", is_primary: true }] });
  });

  it("starts new products as drafts and previews the first image as primary", async () => {
    mockFetch(me, categories, route("GET", "/catalogue/attributes", () => ok([])));
    renderApp("/products/new");
    await screen.findByRole("textbox", { name: "Name" });
    expect(screen.queryByRole("combobox", { name: "Status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Gender" })).not.toBeInTheDocument();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:kurta-preview") });
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["png"], "kurta.png", { type: "image/png" }));
    expect(screen.getByRole("img", { name: "Selected photo 1" })).toHaveAttribute("src", "blob:kurta-preview");
    expect(screen.getByText("Primary image")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /an image URL/ })).not.toBeInTheDocument();
  });

  it("reorders and removes staged photos and rejects unsupported uploads", async () => {
    mockFetch(me, categories, route("GET", "/catalogue/attributes", () => ok([])));
    renderApp("/products/new");
    await screen.findByRole("textbox", { name: "Name" });
    const first = new File(["a"], "first.png", { type: "image/png" });
    const second = new File(["b"], "second.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("Product photos"), [first, second]);
    expect(screen.getByText("Primary image")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Move second.png left" }));
    expect(screen.getByRole("button", { name: "Move second.png left" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Remove second.png" }));
    expect(screen.queryByRole("button", { name: "Remove second.png" })).not.toBeInTheDocument();
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["pdf"], "bad.pdf", { type: "application/pdf" }), { applyAccept: false });
    expect(screen.getByText(/bad.pdf: only JPEG, PNG or WebP photos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove first.png" })).toBeInTheDocument();
  });

  it("keeps the new product unsaved when image upload fails", async () => {
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => ok([{ id: "c1", name: "Kurtas", parent_id: null, status: "ACTIVE" }])),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("POST", "/catalogue/images/upload", () => ({ status: 500, body: { success: false, message: "Image upload failed", data: null } })),
    );
    renderApp("/products/new");
    await userEvent.type(await screen.findByRole("textbox", { name: "Name" }), "Cotton Kurta");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "c1");
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["png"], "kurta.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Create product" }));
    expect(await screen.findByText(/Could not create product/)).toBeInTheDocument();
    expect(calls.some((call) => call.url.pathname.endsWith("/catalogue/products") && call.init.method === "POST")).toBe(false);
  });

  it("resolves valid media URLs and replaces failed images with a consistent placeholder", () => {
    const view = render(<ProductImage url="/media/valid.jpg" alt="Kurta" />);
    const image = screen.getByRole("img");
    expect(image).toHaveAttribute("src", "http://localhost:58000/media/valid.jpg");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: "Product image unavailable" })).toBeInTheDocument();
    view.rerender(<ProductImage url="https://example.com/working.jpg" alt="Kurta" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "https://example.com/working.jpg");
  });

  it("filters active and draft status across API pages while retaining compact pagination and product links", async () => {
    const data = Array.from({ length: 101 }, (_, index) => product(String(index), {
      status: index % 2 === 0 ? "ACTIVE" : "DRAFT",
      gender: index === 100 ? "MEN" : "WOMEN",
      images: index === 100 ? [{ id: "img1", url: "/media/kurta.jpg", is_primary: true, sort_order: 0 }] : [],
    }));
    const { calls } = mockFetch(me, categories, route("GET", "/catalogue/products", (url) => {
      const current = Number(url.searchParams.get("page") ?? 1);
      const status = url.searchParams.get("status");
      const matching = status ? data.filter((row) => row.status === status) : data;
      return paged(matching.slice((current - 1) * 100, current * 100), current, matching.length);
    }));
    renderApp("/products");
    expect(await screen.findByText("Page 1 of 6 (101 items)")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Product ID" })).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Product status" }), "ACTIVE");
    expect(await screen.findByText("Page 1 of 3 (51 items)")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Gender" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Product 0" })).toHaveAttribute("href", "/products/0");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Product status" }), "DRAFT");
    expect(await screen.findByText("Page 1 of 3 (50 items)")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Product status" }), "ARCHIVED");
    expect(await screen.findByText(/No archived products match/)).toBeInTheDocument();
    expect(calls.some((call) => call.url.pathname.endsWith("/catalogue/products") && call.url.searchParams.get("status") === "ARCHIVED")).toBe(true);
    expect(calls.filter((call) => call.url.pathname.endsWith("/catalogue/products")).every((call) => !call.url.searchParams.has("gender"))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Clear Filters" }));
    expect(await screen.findByText("Page 1 of 6 (101 items)")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Product status" })).toHaveValue(""));
  });

  it("uses a CliQ. dialog for unsaved detail changes, tabs and navigation", async () => {
    const existing = product("p1");
    mockFetch(me, categories,
      route("GET", "/catalogue/products/p1", () => ok(existing)),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("GET", "/catalogue/products", () => paged([])),
    );
    renderApp("/products/p1");
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Edited product");
    await userEvent.click(screen.getByRole("tab", { name: "Images" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue editing" }));
    expect(name).toHaveValue("Edited product");
    await userEvent.click(screen.getByRole("link", { name: "Back to products" }));
    expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Products" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Unsaved changes" })).not.toBeInTheDocument();
  });

  it("navigates directly from an unchanged new form", async () => {
    sessionStorage.removeItem("cliq-admin-new-product-form:t1:u1");
    mockFetch(me, categories,
      route("GET", "/catalogue/attributes", () => ok([])),
      route("GET", "/catalogue/products", () => paged([])),
    );
    renderApp("/products/new");
    await screen.findByRole("textbox", { name: "Name" });
    await userEvent.click(screen.getByRole("link", { name: "Back to products" }));
    expect(await screen.findByRole("heading", { name: "Products" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Unsaved changes" })).not.toBeInTheDocument();
  });

  it("guards sidebar navigation from a changed new form", async () => {
    mockFetch(me, categories,
      route("GET", "/catalogue/attributes", () => ok([])),
      route("GET", "/catalogue/products", () => paged([])),
    );
    renderApp("/products/new");
    await userEvent.type(await screen.findByRole("textbox", { name: "Name" }), "Unsaved Kurta");
    await userEvent.click(within(screen.getByRole("navigation", { name: "Admin sections" })).getByRole("link", { name: "Products" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Products" })).toBeInTheDocument();
  });

  it("warns on browser unload only while the product form has unsaved changes", async () => {
    sessionStorage.removeItem("cliq-admin-new-product-form:t1:u1");
    mockFetch(me, categories, route("GET", "/catalogue/attributes", () => ok([])));
    renderApp("/products/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    const cleanUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);
    await userEvent.type(name, "Kurta");
    const dirtyUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyUnload);
    expect(dirtyUnload.defaultPrevented).toBe(true);
    sessionStorage.removeItem("cliq-admin-new-product-form:t1:u1");
  });

  it("keeps a changed new form on backdrop and Continue editing, then discards through Cancel", async () => {
    mockFetch(me, categories,
      route("GET", "/catalogue/attributes", () => ok([])),
      route("GET", "/catalogue/products", () => paged([])),
    );
    renderApp("/products/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.type(name, "Unsaved Kurta");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("dialog", { name: "Unsaved changes" }).parentElement!);
    expect(screen.queryByRole("dialog", { name: "Unsaved changes" })).not.toBeInTheDocument();
    expect(name).toHaveValue("Unsaved Kurta");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue editing" }));
    expect(name).toHaveValue("Unsaved Kurta");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Products" })).toBeInTheDocument();
    expect(sessionStorage.getItem("cliq-admin-new-product-form:t1:u1")).toBeNull();
  });

  it("does not create a product until explicit submission and retains unsaved fields in this session", async () => {
    const { calls } = mockFetch(me, categories, route("GET", "/catalogue/attributes", () => ok([])));
    const app = renderApp("/products/new");
    await userEvent.type(await screen.findByRole("textbox", { name: "Name" }), "Unsaved Kurta");
    expect(calls.some((call) => call.init.method === "POST" && call.url.pathname.endsWith("/catalogue/products"))).toBe(false);
    app.unmount();
    expect(JSON.parse(sessionStorage.getItem("cliq-admin-new-product-form:t1:u1") ?? "{}").text?.name).toBe("Unsaved Kurta");
    renderApp("/products/new");
    expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("Unsaved Kurta");
    sessionStorage.removeItem("cliq-admin-new-product-form:t1:u1");
  });

  it("archives through the API and refreshes the list", async () => {
    let archived = false;
    const { calls } = mockFetch(me, categories,
      route("GET", "/catalogue/products", () => paged(archived ? [] : [product("p1")])) ,
      route("DELETE", "/catalogue/products/p1", () => { archived = true; return ok(null); }),
    );
    renderApp("/products");
    await screen.findByRole("link", { name: "Product p1" });
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "DELETE" && call.url.pathname.endsWith("/catalogue/products/p1"))).toBe(true));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Product p1" })).not.toBeInTheDocument());
    expect(screen.getByRole("link", { name: "View archived product" })).toHaveAttribute("href", "/products/p1");
  });

  it("keeps a product visible and reports an archive failure", async () => {
    mockFetch(me, categories,
      route("GET", "/catalogue/products", () => paged([product("p1")])),
      route("DELETE", "/catalogue/products/p1", () => ({ status: 409, body: { detail: "Product cannot be archived" } })),
    );
    renderApp("/products");
    await screen.findByRole("link", { name: "Product p1" });
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("link", { name: "Product p1" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View archived product" })).not.toBeInTheDocument();
    expect(await screen.findByText(/Could not archive/)).toBeInTheDocument();
  });

  it("requests, paginates and links archived products from the listing API", async () => {
    const archived = Array.from({ length: 21 }, (_, index) => product(`archived-${index}`, { status: "ARCHIVED" }));
    const { calls } = mockFetch(me, categories, route("GET", "/catalogue/products", (url) => paged(url.searchParams.get("status") === "ARCHIVED" ? archived : [])));
    renderApp("/products?status=ARCHIVED");
    await screen.findByRole("link", { name: "Product archived-0" });
    expect(calls.some((call) => call.url.searchParams.get("status") === "ARCHIVED")).toBe(true);
    expect(screen.getByText("Page 1 of 2 (21 items)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Product archived-0" })).toHaveAttribute("href", "/products/archived-0");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("link", { name: "Product archived-20" })).toHaveAttribute("href", "/products/archived-20");
  });
});
