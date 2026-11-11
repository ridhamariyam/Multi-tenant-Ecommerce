import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../auth/AuthContext";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { saveTokens } from "../../utils/storage";
import TaxSection from "./TaxSection";

const gst = { gstin: null, legal_name: null, address: null, state: null, state_code: null, invoice_prefix: "INV-", shipping_sac_code: null, gst_enabled: true };
const tax = { tax_percentage: "0.00", is_active: false };
const report = (rows: unknown[]) =>
  ok({ start_date: "2026-09-01", end_date: "2026-10-01", order_count: 2, taxable_amount: "2000.00", cgst_amount: "0.00", sgst_amount: "0.00", igst_amount: "0.00", tax_amount: "0.00", by_rate: rows, currency: "INR" });
const order = { id: "o1", order_number: "ZN-1001", status: "DELIVERED", payment_status: "PAID", total_amount: "1049.00", currency: "INR", payment_method: "CASH_ON_DELIVERY", tracking_number: null, created_at: "2026-10-01T10:00:00Z" };
const invoice = {
  invoice_number: "INV-ZN-1001", invoice_date: "2026-10-01", order_number: "ZN-1001", order_status: "DELIVERED", gst_type: "INTRA_STATE", place_of_supply: "Karnataka (29)",
  seller: { name: "CliQ. Clothing", gstin: "29ABCDE1234F1Z5", address: null, state: "Karnataka", state_code: "29" },
  buyer: { name: "Neha", address: "Bengaluru", state: "Karnataka", state_code: "29" },
  lines: [{ description: "Kurta - M", sku: "K-M", hsn_code: "6204", quantity: 1, unit_price: "999.00", discount: "0.00", taxable_value: "999.00", gst_rate: "5.00", cgst_amount: "24.98", sgst_amount: "24.97", igst_amount: "0.00", total: "1048.95" }],
  totals: { subtotal: "999.00", total: "1048.95" }, currency: "INR",
};

const rule = (over: Record<string, unknown>) => ({ id: "r1", code: "APPAREL_UPTO_2500", classification: "APPAREL", description: "Apparel (HSN 61/62), sale value up to Rs 2,500 per piece", hsn_prefixes: ["61", "62"], min_unit_value: null, max_unit_value: "2500.00", gst_rate: "5.00", effective_from: "2025-09-22", effective_to: null, is_fallback: false, verification_status: "UNVERIFIED", source: null, in_force: true, ...over });
const defaults = (status = "AWAITING_VERIFICATION") => ({
  rules: [rule({}), rule({ id: "r0", code: "APPAREL_UPTO_1000", max_unit_value: "1000.00", effective_from: "2017-07-01", effective_to: "2025-09-21", in_force: false, description: "Old apparel slab" })],
  default_classification: "APPAREL", fallback_gst_rate: null, system_fallback_rate: "18.00", reviewed_at: null, reviewed_by_id: null, status,
});

const base = (permissions: string[], role = "STAFF") => [
  route("GET", "/auth/me", () => ok(profile({ role, permissions }))),
  route("GET", "/admin/gst", () => ok(gst)),
  route("GET", "/admin/tax", () => ok(tax)),
  route("GET", "/admin/gst/rates", () => ok([])),
  route("GET", "/admin/gst/targets", () => ok({ products: [], categories: [] })),
  route("GET", "/admin/gst/defaults", () => ok(defaults())),
  route("GET", "/admin/gst/product-review", () => ok([])),
  route("GET", "/admin/gst/report", () => report([])),
  route("GET", "/admin/orders", () => ok([order], { page: 1, page_size: 20, total_items: 1, total_pages: 1 })),
];

function renderPage() {
  saveTokens("a", "r");
  return render(
    <AuthProvider>
      <MemoryRouter>
        <TaxSection />
      </MemoryRouter>
    </AuthProvider>
  );
}

const ALL = ["settings.view", "settings.manage", "reports.view", "orders.view"];

describe("GST & invoicing page", () => {
  it("guards navigation after seller details change and leaves without a prompt when unchanged", async () => {
    mockFetch(...base(ALL));
    renderApp("/gst");
    const prefix = await screen.findByRole("textbox", { name: /Invoice prefix/ });
    await userEvent.clear(prefix);
    await userEvent.type(prefix, "CLIQ-");
    await userEvent.click(within(screen.getByRole("navigation", { name: "Admin sections" })).getByRole("link", { name: "Orders" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue editing" }));
    expect(prefix).toHaveValue("CLIQ-");
  });
  it("shows the GST report for orders placed before a seller state was set", async () => {
    mockFetch(
      route("GET", "/admin/gst/report", () => report([{ gst_type: null, gst_rate: null, taxable_amount: "2000.00", cgst_amount: "0.00", sgst_amount: "0.00", igst_amount: "0.00" }])),
      ...base(ALL)
    );
    renderPage();

    expect(await screen.findByText("Not set")).toBeInTheDocument();
    expect(screen.getByText("Business tax & GST settings")).toBeInTheDocument();
  });

  it("uses the selected date range for both GST totals and rows without showing stale data", async () => {
    const { calls } = mockFetch(
      route("GET", "/admin/gst/report", (url) => {
        const amount = url.searchParams.get("start_date") === "2026-09-01" ? "200.00" : "100.00";
        return ok({ start_date: url.searchParams.get("start_date"), end_date: url.searchParams.get("end_date"), order_count: 1,
          taxable_amount: amount, cgst_amount: "0.00", sgst_amount: "0.00", igst_amount: "0.00", tax_amount: "0.00",
          by_rate: [{ component: "ITEMS", gst_type: null, gst_rate: null, taxable_amount: amount, cgst_amount: "0.00", sgst_amount: "0.00", igst_amount: "0.00" }], currency: "INR" });
      }),
      ...base(ALL),
    );
    renderPage();
    expect(await screen.findByText("GST on orders")).toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText("From")[0], { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getAllByLabelText("To")[0], { target: { value: "2026-10-01" } });
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/gst/report") && call.url.searchParams.get("start_date") === "2026-09-01" && call.url.searchParams.get("end_date") === "2026-10-01")).toBe(true));
    expect((await screen.findAllByText("INR 200.00")).length).toBe(2);
    expect(screen.getByRole("columnheader", { name: "Component" })).toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText("To")[0], { target: { value: "2026-08-01" } });
    expect(await screen.findByText(/Choose a valid date range/)).toBeInTheDocument();
    expect(screen.queryByText("INR 200.00")).not.toBeInTheDocument();
  });

  it("lists invoices and opens one from the invoice endpoint", async () => {
    mockFetch(route("GET", "/admin/orders/o1/invoice", () => ok(invoice)), ...base(ALL));
    renderPage();

    const row = (await screen.findByText("ZN-1001")).closest("tr")!;
    expect(within(row).getByText("Available")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Payment" })).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "View" }));

    expect(await screen.findByText("INV-ZN-1001")).toBeInTheDocument();
    expect(screen.getByText("Kurta - M")).toBeInTheDocument();
  });

  it("downloads the invoice PDF with the server's file name", async () => {
    const createObjectURL = vi.fn(() => "blob:invoice");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { calls } = mockFetch(
      route("GET", "/admin/orders/o1/invoice/pdf", () => ({ body: "%PDF-1.4", headers: { "content-type": "application/pdf", "content-disposition": 'attachment; filename="INV-ZN-1001.pdf"' } })),
      ...base(ALL)
    );
    renderPage();

    const row = (await screen.findByText("ZN-1001")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    const link = click.mock.instances[0] as unknown as HTMLAnchorElement;
    expect(link.download).toBe("INV-ZN-1001.pdf");
    expect((calls.find((c) => c.url.pathname.endsWith("/invoice/pdf"))!.init.headers as Record<string, string>).Authorization).toBe("Bearer a");
  });

  it("hides invoices and the report from staff without those permissions", async () => {
    mockFetch(...base(["settings.view"]));
    renderPage();

    expect(await screen.findByText("Business tax & GST settings")).toBeInTheDocument();
    expect(screen.queryByText("Invoices")).not.toBeInTheDocument();
    expect(screen.queryByText("GST report")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("checks the shipping SAC code before saving", async () => {
    const { calls } = mockFetch(...base(ALL, "ADMIN"));
    renderPage();

    await userEvent.type(await screen.findByLabelText("Shipping SAC code"), "99A");
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);

    expect(await screen.findByText(/SAC code must be 4, 6 or 8 digits/)).toBeInTheDocument();
    expect(calls.some((c) => c.init.method === "PUT")).toBe(false);
  });

  it("requires an explicit accountant confirmation before activating a pending rate", async () => {
    const pending = { id: "rate-1", product_id: null, category_id: "c1", category_name: "Kurtas", hsn_code: "6204", gst_rate: "5.00", effective_from: "2026-10-01", status: "PENDING", ca_confirmed: false, approved_at: null, created_at: "2026-10-01T00:00:00Z" };
    const { calls } = mockFetch(
      route("GET", "/admin/gst/rates", () => ok([pending])),
      route("POST", "/admin/gst/rates/rate-1/approve", () => ok({ ...pending, status: "ACTIVE", ca_confirmed: true })),
      ...base(ALL, "ADMIN"),
    );
    renderPage();

    const approve = await screen.findByRole("button", { name: "Approve rate" });
    expect(approve).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Accountant confirmed"));
    await userEvent.click(approve);
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/gst/rates/rate-1/approve"))).toBe(true));
    const call = calls.find((item) => item.url.pathname.endsWith("/admin/gst/rates/rate-1/approve"));
    expect(JSON.parse(call!.init.body as string)).toEqual({ ca_confirmed: true });
  });

  it("shows the system defaults as awaiting verification and records the review only after confirmation", async () => {
    const { calls } = mockFetch(
      route("POST", "/admin/gst/defaults/review", () => ok(defaults("REVIEWED"))),
      route("GET", "/admin/gst/product-review", () => ok([{ product_id: "p1", product_name: "Silver Jhumka", category_name: "Jewellery", hsn_code: "7117", source: "FALLBACK", verification: "NEEDS_REVIEW", rule_codes: ["FALLBACK_UNCLASSIFIED"], rates: ["18.00"], reason: "HSN 7117 is not covered", needs_review: true }])),
      ...base(ALL, "ADMIN"),
    );
    renderPage();

    expect(await screen.findByText("Apparel (HSN 61/62), sale value up to Rs 2,500 per piece")).toBeInTheDocument();
    expect(screen.queryByText("Old apparel slab")).not.toBeInTheDocument();
    expect(await screen.findByText("Silver Jhumka")).toBeInTheDocument();
    expect(screen.getByText("Fallback")).toBeInTheDocument();
    expect(screen.getByText("NEEDS REVIEW")).toBeInTheDocument();

    const mark = screen.getByRole("button", { name: "Mark defaults reviewed" });
    expect(mark).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/checked these rules/));
    await userEvent.click(mark);
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/gst/defaults/review"))).toBe(true));
    const call = calls.find((item) => item.url.pathname.endsWith("/admin/gst/defaults/review"));
    expect(JSON.parse(call!.init.body as string)).toEqual({ reviewed: true });
  });

  it("sends the GST switch, assumed classification and fallback rate with the business details", async () => {
    const { calls } = mockFetch(route("PUT", "/admin/gst", (_url, init) => ok({ ...gst, ...JSON.parse(init.body as string) })), ...base(ALL, "ADMIN"));
    renderPage();

    await userEvent.selectOptions(await screen.findByLabelText("Assume classification"), "");
    await userEvent.type(screen.getByLabelText("Fallback rate %"), "12");
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => expect(calls.some((c) => c.init.method === "PUT")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.init.method === "PUT")!.init.body as string);
    expect(body).toMatchObject({ gst_enabled: true, default_classification: null, fallback_gst_rate: "12" });
  });
});
