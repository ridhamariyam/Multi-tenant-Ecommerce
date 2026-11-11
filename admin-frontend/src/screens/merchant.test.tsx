import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { mockFetch, ok, profile, route } from "../test/fetchMock";
import { getBrandId, getPlatformToken, getToken, savePlatformTokens, saveTokens, setBrandId } from "../utils/storage";

const ACCOUNT = {
  id: "acc-1", email: "owner@northwind.example", name: "Nora Owner", phone: null,
  status: "ACTIVE", is_platform_admin: false, created_at: "2026-11-11T00:00:00Z",
};
const SESSION = { access_token: "platform-access", refresh_token: "platform-refresh", token_type: "bearer", expires_in: 900, account: ACCOUNT };
const STORE = {
  id: "store-1", name: "Northwind", subdomain: "northwind", url: "http://northwind.localhost:3000", theme: "runway",
  logo_url: null, favicon_url: null, primary_color: "#123456", secondary_color: null, published: false, published_at: null,
};
const BRAND = {
  id: "brand-1", name: "Northwind", slug: "northwind", description: null, logo_url: null, contact_email: null, phone: null,
  currency: "INR", status: "ACTIVE", owner_account_id: "acc-1", created_at: "2026-11-11T00:00:00Z", updated_at: "2026-11-11T00:00:00Z",
};
const MEMBERSHIP = { membership_id: "m-1", role: "OWNER", brand: BRAND, store: STORE };
const BRAND_TOKEN = { access_token: "brand-access", token_type: "bearer", expires_in: 1800, brand_id: "brand-1", membership_id: "m-1" };
const ADMIN = profile({ role: "ADMIN", permissions: ["dashboard.view", "settings.view", "settings.manage"] });

const bearer = (init: RequestInit) => (init.headers as Record<string, string> | undefined)?.Authorization;

function renderAt(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("merchant accounts", () => {
  it("signs in, lists the merchant's brands and opens one with a brand token", async () => {
    const { calls } = mockFetch(
      route("POST", "/platform/auth/login", () => ok(SESSION)),
      route("GET", "/brands/me", () => ok([MEMBERSHIP])),
      route("POST", "/brands/brand-1/switch", () => ok(BRAND_TOKEN)),
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", "/brand/store", () => ok(STORE)),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/signin");

    await userEvent.type(await screen.findByLabelText("Email"), "owner@northwind.example");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const card = (await screen.findByText("Northwind")).closest("li")!;
    expect(within(card).getByText("Owner")).toBeInTheDocument();
    expect(within(card).getByText("Not published")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Manage" }));

    await waitFor(() => expect(getToken()).toBe("brand-access"));
    expect(getBrandId()).toBe("brand-1");
    expect(getPlatformToken()).toBe("platform-access");
    const me = calls.find((c) => c.url.pathname === "/api/v1/auth/me")!;
    expect(bearer(me.init)).toBe("Bearer brand-access");
    const brands = calls.find((c) => c.url.pathname === "/api/v1/brands/me")!;
    expect(bearer(brands.init)).toBe("Bearer platform-access");
    expect(await screen.findByText("Managing")).toBeInTheDocument();
  });

  it("creates the first brand and opens it straight away", async () => {
    savePlatformTokens("platform-access", "platform-refresh");
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(ACCOUNT)),
      route("GET", "/brands/me", () => ok([])),
      route("POST", "/brands/register", () => ok({ brand: BRAND, store: STORE, token: BRAND_TOKEN })),
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", "/brand/store", () => ok(STORE)),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/brands");

    expect(await screen.findByRole("heading", { name: "Create your first brand" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Brand name"), "Northwind Goods");
    expect(screen.getByLabelText("Store address")).toHaveValue("northwind-goods");
    await userEvent.click(screen.getByRole("button", { name: "Create brand" }));

    await waitFor(() => expect(getToken()).toBe("brand-access"));
    const register = calls.find((c) => c.url.pathname === "/api/v1/brands/register")!;
    expect(JSON.parse(String(register.init.body))).toEqual({ name: "Northwind Goods", subdomain: "northwind-goods" });
    expect(calls.some((c) => c.url.pathname.endsWith("/switch"))).toBe(false);
  });

  it("renews an expired brand token from the platform session and retries", async () => {
    savePlatformTokens("platform-access", "platform-refresh");
    saveTokens("expired-brand", null);
    setBrandId("brand-1");
    let storeCalls = 0;
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(ACCOUNT)),
      route("GET", "/auth/me", (_url, init) =>
        bearer(init) === "Bearer brand-access" ? ok(ADMIN) : { status: 401, body: { success: false, message: "expired" } }),
      route("POST", "/brands/brand-1/switch", (_url, init) =>
        bearer(init) === "Bearer platform-access" ? ok(BRAND_TOKEN) : { status: 401, body: {} }),
      route("GET", "/brand/store", () => { storeCalls += 1; return ok(STORE); }),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/store");

    expect(await screen.findByRole("heading", { name: "Store & branding" })).toBeInTheDocument();
    expect(getToken()).toBe("brand-access");
    expect(calls.filter((c) => c.url.pathname === "/api/v1/brands/brand-1/switch")).toHaveLength(1);
    expect(storeCalls).toBeGreaterThan(0);
  });

  it("publishes the store and adds a custom domain", async () => {
    savePlatformTokens("platform-access", "platform-refresh");
    saveTokens("brand-access", null);
    setBrandId("brand-1");
    const domains: unknown[] = [];
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(ACCOUNT)),
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", "/brand/store", () => ok(STORE)),
      route("POST", "/brand/store/publish", () => ok({ ...STORE, published: true, published_at: "2026-11-11T10:00:00Z" })),
      route("GET", "/brand/domains", () => ok(domains)),
      route("POST", "/brand/domains", (_url, init) => {
        const body = JSON.parse(String(init.body));
        const created = { id: "d-1", domain: body.domain, is_primary: false, verified_at: null, verification_record: "cliq-verify=abc123", created_at: "2026-11-11T10:00:00Z" };
        domains.push(created);
        return ok(created);
      }),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/store");

    await userEvent.click(await screen.findByRole("button", { name: "Publish store" }));
    expect(await screen.findByText("Your store is live.")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Domain"), "https://Shop.Northwind.example/");
    await userEvent.click(screen.getByRole("button", { name: "Add domain" }));

    expect(await screen.findByText("cliq-verify=abc123")).toBeInTheDocument();
    expect(screen.getByText("northwind.localhost")).toBeInTheDocument();
    const add = calls.find((c) => c.url.pathname === "/api/v1/brand/domains" && c.init.method === "POST")!;
    expect(JSON.parse(String(add.init.body))).toEqual({ domain: "shop.northwind.example", is_primary: false });
  });

  it("adds a teammate with the platform session", async () => {
    savePlatformTokens("platform-access", "platform-refresh");
    saveTokens("brand-access", null);
    setBrandId("brand-1");
    const members: { id: string; account_id: string; email: string; name: string | null; role: string; status: string; created_at: string }[] = [{ id: "m-1", account_id: "acc-1", email: ACCOUNT.email, name: ACCOUNT.name, role: "OWNER", status: "ACTIVE", created_at: "2026-11-11T00:00:00Z" }];
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(ACCOUNT)),
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", "/brand/store", () => ok(STORE)),
      route("GET", "/brands/brand-1/members", () => ok(members)),
      route("POST", "/brands/brand-1/members", (_url, init) => {
        const body = JSON.parse(String(init.body));
        const added = { id: "m-2", account_id: "acc-2", email: body.email, name: null, role: body.role, status: "ACTIVE", created_at: "2026-11-11T00:00:00Z" };
        members.push(added);
        return ok(added);
      }),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/team");

    expect(await screen.findByText("Nora Owner (you)")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "packer@northwind.example");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "ORDER_MANAGER");
    await userEvent.click(screen.getByRole("button", { name: "Add to team" }));

    expect((await screen.findAllByText("packer@northwind.example")).length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox", { name: "Role for packer@northwind.example" })).toHaveValue("ORDER_MANAGER");
    const add = calls.find((c) => c.url.pathname === "/api/v1/brands/brand-1/members" && c.init.method === "POST")!;
    expect(bearer(add.init)).toBe("Bearer platform-access");
  });

  it("hides store settings from a per-store login", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    saveTokens("legacy-access", "legacy-refresh");
    renderAt("/store");

    expect(await screen.findByText("Store settings are managed by signing in with a merchant account.")).toBeInTheDocument();
  });
});

describe("password reset", () => {
  it("asks for a link without revealing whether the account exists", async () => {
    const { calls } = mockFetch(route("POST", "/platform/auth/password/forgot", () => ok(null)));
    renderAt("/forgot-password");

    await userEvent.type(screen.getByLabelText("Email"), "owner@brand.example");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(await screen.findByText(/If an account uses that email/)).toBeInTheDocument();
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ email: "owner@brand.example" });
  });

  it("sets a new password from the emailed token", async () => {
    const { calls } = mockFetch(route("POST", "/platform/auth/password/reset", () => ok(null)));
    renderAt("/reset-password?token=abc123token");

    await userEvent.type(screen.getByLabelText("New password"), "brand-new-pass");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ token: "abc123token", password: "brand-new-pass" });
  });
});

const PLAN = (code: string, name: string, price: number, products: number | null, domains: boolean) => ({
  code, name, monthly_price: price, currency: "INR", monthly_ai_credits: 0, product_limit: products, staff_limit: 3,
  features: { custom_domains: domains, sheets_export: false, ai_studio: false, lookbooks: true }, is_active: true,
});
const FREE = PLAN("FREE", "Free", 0, 25, false);
const STARTER = PLAN("STARTER", "Starter", 99900, 500, true);
const billing = (plan = FREE, extra: Record<string, unknown> = {}) => ({
  plan, effective_plan: plan,
  subscription: { status: "ACTIVE", billing_provider: "manual", current_period_start: "2026-11-11T00:00:00Z", current_period_end: "2026-12-11T00:00:00Z", cancel_at_period_end: false, trial_used: false, lapsed: false },
  usage: { products: 3, staff: 1 }, plans: [FREE, STARTER], online_billing: true, ...extra,
});

describe("plan & billing", () => {
  it("shows usage against the plan and upgrades through Razorpay", async () => {
    saveTokens("brand-access", null);
    setBrandId("brand-1");
    savePlatformTokens("platform-access", "platform-refresh");
    const opened: Record<string, unknown>[] = [];
    (window as unknown as { Razorpay: unknown }).Razorpay = class {
      constructor(private options: Record<string, unknown>) { opened.push(options); }
      on() {}
      open() {
        (this.options.handler as (r: unknown) => void)({ razorpay_payment_id: "pay_1", razorpay_subscription_id: "sub_1", razorpay_signature: "sig" });
      }
    };
    const { calls } = mockFetch(
      route("GET", "/platform/auth/me", () => ok(ACCOUNT)),
      route("GET", "/auth/me", () => ok(ADMIN)),
      route("GET", "/brand/billing", () => ok(billing())),
      route("POST", "/brand/billing/checkout", () => ok({ subscription_id: "sub_1", key_id: "rzp_test_Plat", plan_code: "STARTER", plan_name: "Starter", amount: 99900, currency: "INR", trial_days: 14 })),
      route("POST", "/brand/billing/confirm", () => ok(billing(STARTER, { subscription: { status: "TRIALING", billing_provider: "razorpay", current_period_start: "2026-11-11T00:00:00Z", current_period_end: "2026-11-25T00:00:00Z", cancel_at_period_end: false, trial_used: true, lapsed: false } }))),
      route("GET", /\/api\/v1\/admin\//, () => ok([])),
    );
    renderAt("/billing");

    expect(await screen.findByRole("heading", { name: "Current plan: Free" })).toBeInTheDocument();
    expect(screen.getByText("Products").nextSibling).toHaveTextContent("3 / 25");
    const starter = screen.getByRole("region", { name: "Starter" });
    await userEvent.click(within(starter).getByRole("button", { name: "Start 14-day free trial" }));

    expect(await screen.findByText("You're on Starter.")).toBeInTheDocument();
    expect(opened[0]).toMatchObject({ key: "rzp_test_Plat", subscription_id: "sub_1" });
    const confirm = calls.find((c) => c.url.pathname === "/api/v1/brand/billing/confirm")!;
    expect(JSON.parse(String(confirm.init.body))).toEqual({ razorpay_payment_id: "pay_1", razorpay_subscription_id: "sub_1", razorpay_signature: "sig" });
    expect(screen.getByRole("heading", { name: "Current plan: Starter" })).toBeInTheDocument();
    expect(screen.getByText(/Free trial/)).toBeInTheDocument();
    delete (window as unknown as { Razorpay?: unknown }).Razorpay;
  });
});
