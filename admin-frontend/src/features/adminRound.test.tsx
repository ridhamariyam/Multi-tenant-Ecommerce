import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockFetch, ok, profile, route } from "../test/fetchMock";
import { renderApp } from "../test/renderApp";
import { captureDownloads } from "../test/setupDownloads";
import { currentWeekRange } from "./overview/dashboardPeriod";

const ADMIN = profile({ role: "ADMIN", permissions: ["dashboard.view", "orders.view", "orders.manage", "reports.view", "catalogue.view", "catalogue.manage", "customers.view", "customers.manage", "cms.view", "cms.manage", "cms.publish", "settings.view", "settings.manage", "coupons.view", "coupons.manage"] });
const me = route("GET", "/auth/me", () => ok(ADMIN));
const page = (rows: unknown[]) => ok(rows, { page: 1, page_size: 20, total_items: rows.length, total_pages: 1 });
const order = (n: number, status = "CONFIRMED") => ({ id: `o${n}`, order_number: `ZN-${n}`, status, payment_status: "PENDING", total_amount: "999.00", currency: "INR", payment_method: "CASH_ON_DELIVERY", tracking_number: null, created_at: "2026-10-01T10:00:00Z" });

describe("orders list", () => {
  it("offers only payment methods the backend supports", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/orders", () => page([order(1)])));
    renderApp("/orders");
    const select = await screen.findByLabelText("Payment method");

    const values = within(select).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    await userEvent.selectOptions(select, "CASH_ON_DELIVERY");

    expect(values).toEqual(["", "UPI", "CREDIT_CARD", "DEBIT_CARD", "NET_BANKING", "CASH_ON_DELIVERY"]);
    await waitFor(() => expect(calls.some((c) => c.url.searchParams.get("payment_method") === "CASH_ON_DELIVERY")).toBe(true));
    expect(calls.some((c) => c.url.searchParams.get("payment_method") === "PREPAID")).toBe(false);
  });

  it("prints labels for the selected orders in one download", async () => {
    const downloads = captureDownloads();
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/orders", () => page([order(1), order(2), order(3)])),
      route("POST", "/admin/orders/shipping-labels/pdf", () => ({ body: "%PDF", headers: { "content-type": "application/pdf", "content-disposition": 'attachment; filename="labels-2-orders.pdf"' } }))
    );
    renderApp("/orders");

    await userEvent.click(await screen.findByLabelText("Select ZN-1"));
    await userEvent.click(screen.getByLabelText("Select ZN-3"));
    await userEvent.click(screen.getByRole("button", { name: "Print 2 shipping labels" }));

    await waitFor(() => expect(downloads()).toEqual(["labels-2-orders.pdf"]));
    const call = calls.find((c) => c.url.pathname.endsWith("/shipping-labels/pdf"))!;
    expect(JSON.parse(call.init.body as string)).toEqual({ order_ids: ["o1", "o3"] });
  });
});

describe("dashboard", () => {
  it("requests actual product sales for the current UTC week", async () => {
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/dashboard", () => ({ status: 500, body: { message: "skip" } })),
      route("GET", "/admin/reports/sales-by-product", () => ok([]))
    );
    renderApp("/");

    await waitFor(() => {
      const call = calls.find((c) => c.url.pathname.endsWith("/sales-by-product"));
      expect(call?.url.searchParams.get("start_date")).toBe(currentWeekRange().start_date);
      expect(call?.url.searchParams.get("end_date")).toBe(currentWeekRange().end_date);
    });
  });
});

describe("reports", () => {
  it("downloads a report as Excel and PDF", async () => {
    const downloads = captureDownloads();
    const file = (name: string) => ({ body: "x", headers: { "content-disposition": `attachment; filename="${name}"` } });
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/reports/sales-by-product", (url) =>
        url.searchParams.get("format") === "xlsx" ? file("p.xlsx") : url.searchParams.get("format") === "pdf" ? file("p.pdf") : ok([])
      ),
      route("GET", "/admin/reports/analytics", () => ok({ top_products: [] }))
    );
    renderApp("/reports");

    await userEvent.click(await screen.findByRole("tab", { name: "Products" }));
    const reportPanel = (await screen.findByRole("heading", { name: "Product performance" })).closest<HTMLElement>(".panel")!;
    await userEvent.click(within(reportPanel).getByRole("button", { name: "Excel" }));
    await userEvent.click(within(reportPanel).getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(downloads()).toEqual(["p.xlsx", "p.pdf"]));
    expect(calls.filter((c) => c.url.searchParams.get("format")).map((c) => c.url.searchParams.get("format"))).toEqual(["xlsx", "pdf"]);
  });
});

describe("customers", () => {
  const customer = (blocked: boolean) => ({
    id: "c1", name: "Neha", email: null, phone: "+919876500001", status: "ACTIVE", is_verified: true, tags: [],
    order_blocked: blocked, order_blocked_at: blocked ? "2026-10-01T10:00:00Z" : null, order_block_reason: blocked ? "Fake orders" : null,
    total_orders: 1, total_spent: "999.00", last_order_at: null, created_at: "2026-09-01T10:00:00Z",
    first_order_at: null, is_returning: false, cancelled_orders: 0, returned_orders: 0, addresses: [], notes: [], currency: "INR",
  });

  it("blocks a customer from ordering with a reason", async () => {
    let blocked = false;
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/customers/c1", () => ok(customer(blocked))),
      route("GET", "/admin/customers/c1/orders", () => page([])),
      route("PUT", "/admin/customers/c1/order-block", () => { blocked = true; return ok(customer(true)); })
    );
    renderApp("/customers/c1");

    await userEvent.type(await screen.findByLabelText("Block reason"), "Fake orders");
    await userEvent.click(screen.getByRole("button", { name: "Block ordering" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Block this customer?" })).getByRole("button", { name: "Block ordering" }));

    expect(await screen.findByText(/Blocked from placing orders: Fake orders/)).toBeInTheDocument();
    const call = calls.find((c) => c.init.method === "PUT")!;
    expect(JSON.parse(call.init.body as string)).toEqual({ blocked: true, reason: "Fake orders" });
  });
});

describe("order returns", () => {
  it("records the return reason when marking an order returned", async () => {
    const shipped = {
      id: "o1", order_number: "ZN-1", status: "SHIPPED", payment_status: "PENDING", items: [], subtotal: "999.00", coupon_code: null,
      discount_amount: "0.00", shipping_amount: "0.00", cod_fee: "0.00", tax_amount: "0.00", total_amount: "999.00", advance_amount: "0.00",
      currency: "INR", payment_method: "CASH_ON_DELIVERY", payment: null, payments: [], gst: null,
      delivery_address: { full_name: "Neha", phone: "+919876500001", address_line_1: "1 St", address_line_2: null, city: "Kochi", state: "Kerala", postal_code: "682001", country: "India" },
      contact_email: null, is_guest: false, estimated_delivery_date: null, shipment: { courier_name: null, tracking_number: null, tracking_url: null },
      return_reason: null, return_note: null, created_at: "2026-10-01T10:00:00Z",
    };
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/orders/o1", () => ok(shipped)),
      route("GET", "/admin/orders/o1/tracking", () => ok({ events: [] })),
      route("GET", "/admin/return-reasons", () => ok([{ id: "r1", label: "Refused at door", is_active: true, position: 0 }])),
      route("PATCH", "/admin/orders/o1/status", () => ok({ ...shipped, status: "RETURNED", return_reason: "Refused at door" }))
    );
    renderApp("/orders/o1");

    await userEvent.selectOptions(await screen.findByLabelText("Move to"), "RETURNED");
    await userEvent.selectOptions(await screen.findByLabelText("Return reason"), "r1");
    await userEvent.type(screen.getByLabelText("Return details"), "Not home twice");
    await userEvent.click(screen.getByRole("button", { name: "Update status" }));

    await waitFor(() => expect(calls.some((c) => c.init.method === "PATCH")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.init.method === "PATCH")!.init.body as string);
    expect(body).toMatchObject({ status: "RETURNED", return_reason_id: "r1", return_note: "Not home twice" });
  });
});

describe("CMS drag and drop", () => {
  const section = (id: string, title: string, position: number) => ({
    id, section_type: "PROMO_STRIP", title, subtitle: null, is_active: true, position, starts_at: null, ends_at: null, is_live: true,
    items: [], settings: { product_ids: null, category_id: null, limit: 8, days: 30, countdown_ends_at: null }, updated_at: "2026-10-01T10:00:00Z",
  });

  it("saves the new homepage order after dropping a section on another", async () => {
    let order = [section("s1", "First", 0), section("s2", "Second", 1), section("s3", "Third", 2)];
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cms/sections", () => ok(order)),
      route("PUT", "/admin/cms/sections/order", (_u, init) => {
        const ids: string[] = JSON.parse(init.body as string).ids;
        order = ids.map((id, i) => ({ ...order.find((s) => s.id === id)!, position: i }));
        return ok(order);
      })
    );
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Homepage" }));

    const third = (await screen.findByText("Third")).closest("tr")!;
    const first = screen.getByText("First").closest("tr")!;
    fireEvent.dragStart(third);
    fireEvent.dragOver(first);
    fireEvent.drop(first);

    await waitFor(() => expect(calls.some((c) => c.init.method === "PUT")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.init.method === "PUT")!.init.body as string)).toEqual({ ids: ["s3", "s1", "s2"] });
    await waitFor(() => {
      const titles = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[2].textContent);
      expect(titles).toEqual(["Third", "First", "Second"]);
    });
  });
});

describe("product creation", () => {
  it("uploads the chosen photos and creates the product with them", async () => {
    const created = { id: "p1", slug: "new-kurta", name: "New Kurta", status: "DRAFT", images: [], options: [] };
    const { calls } = mockFetch(
      me,
      route("GET", "/catalogue/categories", () => ok([{ id: "c1", tenant_id: "t", parent_id: null, name: "Kurtas", description: null, status: "ACTIVE", hsn_code: null, gst_rate: null }])),
      route("GET", "/catalogue/attributes", () => ok([{ id: "v1", attribute: "fabric", value: "Cotton", is_active: true, position: 0, product_count: 0 }])),
      route("POST", "/catalogue/images/upload", () => ({ status: 201, body: { success: true, message: "", data: { url: "/media/t/kurta.png" }, meta: null } })),
      route("POST", "/catalogue/products", () => ({ status: 201, body: { success: true, message: "", data: created, meta: null } })),
      route("GET", "/catalogue/products/p1", () => ok({ ...created, category_id: "c1", size_chart: null }))
    );
    renderApp("/products/new");

    await userEvent.type(await screen.findByLabelText("Name"), "New Kurta");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "c1");
    await userEvent.selectOptions(await screen.findByLabelText("fabric"), "Cotton");
    await userEvent.upload(screen.getByLabelText("Product photos"), new File(["png"], "kurta.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => expect(calls.some((c) => c.init.method === "POST" && c.url.pathname.endsWith("/catalogue/products"))).toBe(true));
    const order = calls.filter((c) => c.init.method === "POST").map((c) => c.url.pathname);
    expect(order).toEqual(["/api/v1/catalogue/images/upload", "/api/v1/catalogue/products"]);
    const body = JSON.parse(calls.find((c) => c.url.pathname.endsWith("/catalogue/products") && c.init.method === "POST")!.init.body as string);
    expect(body.images).toEqual([{ url: "/media/t/kurta.png", alt_text: "New Kurta", is_primary: true, sort_order: 0 }]);
    expect(body.fabric).toBe("Cotton");
  });
});

describe("CMS banner editing", () => {
  const cmsMocks = (extra: Parameters<typeof mockFetch> = []) =>
    mockFetch(
      me,
      ...extra,
      route("GET", "/admin/cms/sections", () => ok([])),
      route("GET", "/catalogue/categories", () => ok([])),
      route("POST", "/admin/cms/media", () => ({ status: 201, body: { success: true, message: "", data: { id: "m1", url: "/media/t/hero.png", filename: "hero.png", content_type: "image/png", size_bytes: 10, alt_text: null, created_at: "" }, meta: null } })),
      route("POST", "/admin/cms/sections", (_u, init) => ({ status: 201, body: { success: true, message: "", data: JSON.parse(init.body as string), meta: null } }))
    );

  it("uploads a hero picture from the computer and keeps the spaces typed into the heading", async () => {
    const { calls } = cmsMocks();
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Homepage" }));

    await userEvent.click(await screen.findByRole("button", { name: "Add section" }));
    await userEvent.upload(screen.getByLabelText("Upload Picture"), new File(["png"], "hero.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText(/^Heading/), "Festive Drop — New In ");
    await userEvent.type(screen.getByLabelText(/^Text/), "Cotton kurtas for the season");
    await userEvent.click(screen.getByRole("button", { name: "Save section" }));

    await waitFor(() => expect(calls.some((c) => c.init.method === "POST" && c.url.pathname.endsWith("/sections"))).toBe(true));
    expect(calls.filter((c) => c.init.method === "POST").map((c) => c.url.pathname)).toEqual(["/api/v1/admin/cms/media", "/api/v1/admin/cms/sections"]);
    const body = JSON.parse(calls.find((c) => c.url.pathname.endsWith("/sections") && c.init.method === "POST")!.init.body as string);
    expect(body.items[0]).toMatchObject({ image_url: "/media/t/hero.png", heading: "Festive Drop — New In", text: "Cotton kurtas for the season" });
  });

  it("waits for a slow upload before saving, without losing text typed meanwhile", async () => {
    let finishUpload: () => void = () => undefined;
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cms/sections", () => ok([])),
      route("GET", "/catalogue/categories", () => ok([])),
      route("POST", "/admin/cms/sections", (_u, init) => ({ status: 201, body: { success: true, message: "", data: JSON.parse(init.body as string), meta: null } }))
    );
    // Replace the media upload with one that only completes when we say so.
    const realFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/admin/cms/media")
        ? new Promise<Response>((resolve) => {
            finishUpload = () => resolve(new Response(JSON.stringify({ success: true, message: "", data: { id: "m9", url: "/media/t/slow.png", filename: "slow.png", content_type: "image/png", size_bytes: 1, alt_text: null, created_at: "" }, meta: null }), { status: 201 }));
          })
        : realFetch(input, init)
    );
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Homepage" }));

    await userEvent.click(await screen.findByRole("button", { name: "Add section" }));
    await userEvent.upload(screen.getByLabelText("Upload Picture"), new File(["png"], "slow.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText(/^Heading/), "Typed while uploading");

    expect(screen.getByRole("button", { name: /Waiting for the picture/ })).toBeDisabled();
    finishUpload();
    const save = await screen.findByRole("button", { name: "Save section" });
    await userEvent.click(save);

    await waitFor(() => expect(calls.some((c) => c.init.method === "POST")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.init.method === "POST")!.init.body as string);
    expect(body.items[0]).toMatchObject({ image_url: "/media/t/slow.png", heading: "Typed while uploading" });
  });

  it("refuses to save a hero banner without a picture", async () => {
    const { calls } = cmsMocks();
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Homepage" }));

    await userEvent.click(await screen.findByRole("button", { name: "Add section" }));
    await userEvent.type(screen.getByLabelText(/^Heading/), "No picture");
    await userEvent.click(screen.getByRole("button", { name: "Save section" }));

    expect(await screen.findByText("Slide 1 needs a picture.")).toBeInTheDocument();
    expect(calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("rejects a file that isn't a picture before uploading", async () => {
    const { calls } = cmsMocks();
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Homepage" }));

    await userEvent.click(await screen.findByRole("button", { name: "Add section" }));
    await userEvent.upload(screen.getByLabelText("Upload Picture"), new File(["%PDF"], "menu.pdf", { type: "application/pdf" }), { applyAccept: false });

    expect(await screen.findByText(/isn't a JPEG, PNG or WebP picture/)).toBeInTheDocument();
    expect(calls.some((c) => c.init.method === "POST")).toBe(false);
  });
});

describe("CMS confirmations and row actions", () => {
  const page = { id: "pg1", slug: "about-us", title: "About us", page_type: "ABOUT", status: "PUBLISHED", published_at: "2026-10-01T10:00:00Z", is_live: true, updated_at: "2026-10-01T10:00:00Z" };

  it("asks in a styled dialog before unpublishing, and every page has Edit", async () => {
    let unpublished = false;
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cms/pages", () => ok([{ ...page, status: unpublished ? "DRAFT" : "PUBLISHED", is_live: !unpublished }], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
      route("POST", "/admin/cms/pages/pg1/unpublish", () => { unpublished = true; return ok({ ...page, status: "DRAFT" }); })
    );
    const confirmSpy = vi.spyOn(window, "confirm");
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Pages" }));

    const row = (await screen.findByText("About us")).closest("tr")!;
    expect(within(row).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Unpublish" }));
    const dialog = await screen.findByRole("dialog", { name: "Unpublish this page?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Unpublish" }));

    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith("/unpublish"))).toBe(true));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(await screen.findByText(/hidden from the website/)).toBeInTheDocument();
  });

  it("edits an existing page in place, keeping its id and slug", async () => {
    const full = { ...page, body: "Old text", seo_title: null, seo_description: null, created_at: page.updated_at };
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cms/pages", () => ok([page], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
      route("GET", "/admin/cms/pages/pg1", () => ok(full)),
      route("PATCH", "/admin/cms/pages/pg1", (_u, init) => ok({ ...full, ...JSON.parse(init.body as string), updated_at: "2026-10-02T10:00:00Z" }))
    );
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Pages" }));

    const row = (await screen.findByText("About us")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit “About us”" });
    const text = within(dialog).getByLabelText("Page text");
    expect(text).toHaveValue("Old text");
    await userEvent.clear(text);
    await userEvent.type(text, "New text");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save — updates the website" }));

    await waitFor(() => expect(calls.some((c) => c.init.method === "PATCH")).toBe(true));
    const saved = JSON.parse(calls.find((c) => c.init.method === "PATCH")!.init.body as string);
    expect(saved).toMatchObject({ slug: "about-us", body: "New text" });
    expect(calls.some((c) => c.init.method === "POST")).toBe(false);
  });

  it("marks a taken-down page Unpublished and offers a preview", async () => {
    mockFetch(me, route("GET", "/admin/cms/pages", () => ok([{ ...page, status: "DRAFT", is_live: false }], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })));
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Pages" }));

    const row = (await screen.findByText("About us")).closest("tr")!;
    expect(within(row).getByText("UNPUBLISHED")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Preview" })).toBeInTheDocument();
  });

  it("cancelling the dialog does nothing", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/cms/pages", () => ok([page], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })));
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Pages" }));

    const row = (await screen.findByText("About us")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Delete" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.some((c) => c.init.method === "DELETE")).toBe(false);
  });
});

describe("Website content overview", () => {
  it("opens on the whole website, marking what the CMS manages and what the storefront does", async () => {
    mockFetch(me, route("GET", "/admin/cms/sections", () => ok([])));
    renderApp("/cms");

    const about = (await screen.findAllByText("About Us"))[0].closest("tr")!;
    expect(within(about).getByText("Storefront-managed")).toBeInTheDocument();
    expect(within(about).queryByRole("button", { name: /Edit|Open/ })).not.toBeInTheDocument();

    const hero = screen.getByText("Hero banners").closest("tr")!;
    expect(within(hero).getByText("CMS · Homepage")).toBeInTheDocument();
    await userEvent.click(within(hero).getByRole("button", { name: "Open Homepage" }));
    expect(await screen.findByRole("button", { name: "Add section" })).toBeInTheDocument();
  });

  it("lists the website's existing pages under the CMS pages, read-only", async () => {
    mockFetch(me, route("GET", "/admin/cms/pages", () => ok([], { page: 1, page_size: 20, total_items: 0, total_pages: 0 })));
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Pages" }));

    expect(await screen.findByText(/No pages created in the CMS yet/)).toBeInTheDocument();
    const privacy = screen.getByText("Privacy Policy").closest("tr")!;
    expect(within(privacy).getByText("Not on the website yet.")).toBeInTheDocument();
    expect(within(privacy).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("/about-us").closest("tr")).toHaveTextContent("Storefront-managed");
  });
});

describe("Logo & contact", () => {
  const empty = { logo_url: null, logo_alt: null, tagline: null, contact_email: null, contact_phone: null, whatsapp_number: null, address: null, social_links: {}, copyright_text: null };

  it("keeps unsaved website settings when continuing and changes tabs after discard", async () => {
    mockFetch(me, route("GET", "/admin/cms/site", () => ok(empty)));
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Logo & contact" }));
    const tagline = await screen.findByLabelText(/^Tagline/);
    await userEvent.type(tagline, "New tagline");
    await userEvent.click(screen.getByRole("tab", { name: "Pages" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue editing" }));
    expect(tagline).toHaveValue("New tagline");
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Discard changes" }));
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  it("saves the logo, contact details and social links", async () => {
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cms/site", () => ok(empty)),
      route("POST", "/admin/cms/media", () => ({ status: 201, body: { success: true, message: "", data: { id: "m2", url: "/media/t/logo.png", filename: "logo.png", content_type: "image/png", size_bytes: 10, alt_text: null, created_at: "" }, meta: null } })),
      route("PUT", "/admin/cms/site", (_u, init) => ok(JSON.parse(init.body as string)))
    );
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Logo & contact" }));

    await userEvent.upload(await screen.findByLabelText("Upload Logo picture"), new File(["png"], "logo.png", { type: "image/png" }));
    await userEvent.type(screen.getByLabelText(/^Tagline/), "Everyday ethnic wear");
    await userEvent.type(screen.getByLabelText(/^Email/), "hello@cliq.example");
    await userEvent.type(screen.getByLabelText(/^Instagram/), "https://instagram.com/cliq");
    await userEvent.click(screen.getByRole("button", { name: "Save website details" }));

    await waitFor(() => expect(calls.some((c) => c.init.method === "PUT")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.init.method === "PUT")!.init.body as string);
    expect(body).toMatchObject({ logo_url: "/media/t/logo.png", tagline: "Everyday ethnic wear", contact_email: "hello@cliq.example", social_links: { instagram: "https://instagram.com/cliq" } });
  });

  it("explains a bad social link instead of saving", async () => {
    const { calls } = mockFetch(me, route("GET", "/admin/cms/site", () => ok(empty)));
    renderApp("/cms");
    await userEvent.click(await screen.findByRole("tab", { name: "Logo & contact" }));

    await userEvent.type(await screen.findByLabelText(/^Facebook/), "facebook.com/cliq");
    await userEvent.click(screen.getByRole("button", { name: "Save website details" }));

    expect(await screen.findByText("The facebook link must start with https://")).toBeInTheDocument();
    expect(calls.some((c) => c.init.method === "PUT")).toBe(false);
  });
});
