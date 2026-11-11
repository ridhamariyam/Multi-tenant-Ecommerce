import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../../App";
import { AuthProvider } from "../../auth/AuthContext";
import { mockFetch, ok, route } from "../../test/fetchMock";
import { savePlatformTokens } from "../../utils/storage";

const account = (isAdmin: boolean) => ({
  id: "acc-ops", email: "ops@cliq.example", name: "Ops", phone: null, status: "ACTIVE",
  is_platform_admin: isAdmin, created_at: "2026-11-01T00:00:00Z",
});
const OVERVIEW = { brands_total: 2, brands_active: 2, brands_suspended: 0, stores_published: 1, domains_pending: 1, merchant_accounts: 3 };
const brandRow = (status = "ACTIVE", reason: string | null = null) => ({
  brand: {
    id: "b-1", name: "Northwind", slug: "northwind", description: null, logo_url: null, contact_email: null, phone: null,
    currency: "INR", status, owner_account_id: "acc-1", created_at: "2026-11-11T00:00:00Z", updated_at: "2026-11-11T00:00:00Z",
  },
  store: { id: "s-1", name: "Northwind", subdomain: "northwind", url: "http://northwind.localhost:3000", theme: "runway", logo_url: null, favicon_url: null, primary_color: null, secondary_color: null, published: true, published_at: null },
  member_count: 2,
  suspended_at: status === "ACTIVE" ? null : "2026-11-11T10:00:00Z",
  suspension_reason: reason,
});
const meta = { page: 1, page_size: 20, total_items: 1, total_pages: 1 };
const pageOf = <T,>(items: T[]) => ({ body: { success: true, message: "OK", data: items, meta } });

function renderAt(path: string) {
  savePlatformTokens("platform-access", "platform-refresh");
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("platform console", () => {
  it("is only for platform operators", async () => {
    mockFetch(
      route("GET", "/platform/auth/me", () => ok(account(false))),
      route("GET", "/brands/me", () => ok([])),
    );
    renderAt("/platform");

    expect(await screen.findByRole("heading", { name: "Create your first brand" })).toBeInTheDocument();
    expect(screen.queryByText("Platform admin")).not.toBeInTheDocument();
  });

  it("shows totals and suspends a brand with a reason", async () => {
    let row = brandRow();
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(account(true))),
      route("GET", "/platform/admin/overview", () => ok(OVERVIEW)),
      route("GET", "/platform/admin/brands", () => pageOf([row])),
      route("POST", "/platform/admin/brands/b-1/suspend", (_u, init) => {
        row = brandRow("SUSPENDED", JSON.parse(String(init.body)).reason);
        return ok(row);
      }),
    );
    renderAt("/platform");

    expect(await screen.findByText("Domains to verify")).toBeInTheDocument();
    const card = (await screen.findByText("Northwind")).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Suspend brand" })).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Chargeback fraud review");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend brand" }));

    expect(await screen.findByText("Suspended: Chargeback fraud review")).toBeInTheDocument();
    const suspend = calls.find((c) => c.url.pathname.endsWith("/suspend"))!;
    expect((suspend.init.headers as Record<string, string>).Authorization).toBe("Bearer platform-access");
  });

  it("checks a pending domain's DNS and explains a mismatch", async () => {
    const domain = {
      domain: { id: "d-1", domain: "shop.northwind.example", is_primary: false, verified_at: null, verification_record: "cliq-verify=abc", created_at: "2026-11-11T00:00:00Z" },
      brand_id: "b-1", brand_name: "Northwind", store_subdomain: "northwind",
    };
    mockFetch(
      route("GET", "/platform/auth/me", () => ok(account(true))),
      route("GET", "/platform/admin/overview", () => ok(OVERVIEW)),
      route("GET", "/platform/admin/brands", () => pageOf([brandRow()])),
      route("GET", "/platform/admin/domains", (url) => {
        expect(url.searchParams.get("status")).toBe("pending");
        return pageOf([domain]);
      }),
      route("POST", "/platform/admin/domains/d-1/check", () => ok({
        domain: domain.domain, verified: false, record_name: "_cliq-verify.shop.northwind.example",
        expected: "cliq-verify=abc", found: ["cliq-verify=wrong"], problem: "A TXT record exists but does not contain the expected value.",
      })),
    );
    renderAt("/platform");

    await userEvent.click(await screen.findByRole("tab", { name: "Domains" }));
    const row = (await screen.findByText("shop.northwind.example")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Check DNS" }));

    expect(await within(row).findByText(/does not contain the expected value/)).toBeInTheDocument();
    expect(within(row).getByText("cliq-verify=wrong")).toBeInTheDocument();
    expect(within(row).getByText("Pending")).toBeInTheDocument();
  });

  it("shows background jobs and which providers still need credentials", async () => {
    mockFetch(
      route("GET", "/platform/auth/me", () => ok(account(true))),
      route("GET", "/platform/admin/overview", () => ok(OVERVIEW)),
      route("GET", "/platform/admin/brands", () => pageOf([brandRow()])),
      route("GET", "/platform/admin/system", () => ok({
        environment: "production", release: "7", database: true, redis: true, error_reporting: false, alerts: true,
        jobs: [
          { name: "order-sheets", status: "ok", last_run_at: "2026-11-11T10:00:00Z", last_ok_at: "2026-11-11T10:00:00Z", every_seconds: 60, error: null },
          { name: "shipment-sync", status: "failed", last_run_at: "2026-11-11T10:00:00Z", last_ok_at: null, every_seconds: 900, error: "timed out" },
        ],
        providers: [
          { key: "razorpay", name: "Razorpay payments", configured: true, needed_for: "Online payments and refunds" },
          { key: "smtp", name: "Email (SMTP)", configured: false, needed_for: "Password resets" },
        ],
      })),
    );
    renderAt("/platform");

    await userEvent.click(await screen.findByRole("tab", { name: "System" }));

    const failed = (await screen.findByText("shipment-sync")).closest("tr")!;
    expect(within(failed).getByText("Failed")).toBeInTheDocument();
    expect(within(failed).getByText("timed out")).toBeInTheDocument();
    const smtp = screen.getByText("Email (SMTP)").closest("tr")!;
    expect(within(smtp).getByText("Missing")).toBeInTheDocument();
    expect(screen.getByText("Error reporting: Not set up")).toBeInTheDocument();
  });
});
