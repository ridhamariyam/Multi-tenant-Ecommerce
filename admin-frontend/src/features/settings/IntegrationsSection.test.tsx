import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const integration = (key: string, name: string, credentials_configured: boolean, integrated: boolean) => ({
  key, name, purpose: "External service", credentials_configured, integrated,
  status: !credentials_configured ? "PENDING_CREDENTIALS" : integrated ? "ACTIVE" : "CREDENTIALS_PRESENT_INTEGRATION_PENDING",
  required_settings: ["EXAMPLE_SECRET_NAME"], note: "Set up by the project lead.",
});

const sheet = (overrides: Record<string, unknown> = {}) => ({
  credentials_configured: true, service_account_email: "orders@cliq-sheets.iam.gserviceaccount.com",
  is_enabled: false, spreadsheet_id: null, spreadsheet_url: null, worksheet_name: "Orders",
  last_synced_at: null, last_error: null, last_error_at: null, pending_orders: 0, exported_orders: 0,
  ...overrides,
});

describe("Google Sheets order export", () => {
  it("shows the address to share with and connects a sheet", async () => {
    const SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit";
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["settings.view", "settings.manage"] }))),
      route("GET", "/admin/integrations/google-sheets", () => ok(sheet())),
      route("PUT", "/admin/integrations/google-sheets", () => ok(sheet({
        is_enabled: true, spreadsheet_id: "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", spreadsheet_url: SHEET, pending_orders: 3,
      }))),
      route("GET", "/admin/integrations", () => ok([])),
    );
    renderApp("/integrations");

    expect(await screen.findByText("orders@cliq-sheets.iam.gserviceaccount.com")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Spreadsheet link"), SHEET);
    await userEvent.click(screen.getByLabelText("Add every successful order to this sheet"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Sheet connected. New orders will appear in it.")).toBeInTheDocument();
    const put = calls.find((c) => c.init.method === "PUT")!;
    expect(JSON.parse(String(put.init.body))).toEqual({ is_enabled: true, spreadsheet: SHEET, worksheet_name: "Orders" });
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(screen.getByText("Waiting").nextSibling).toHaveTextContent("3");
  });

  it("explains that the server key is missing", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["settings.view", "settings.manage"] }))),
      route("GET", "/admin/integrations/google-sheets", () => ok(sheet({ credentials_configured: false, service_account_email: null }))),
      route("GET", "/admin/integrations", () => ok([])),
    );
    renderApp("/integrations");

    expect(await screen.findByText(/Google Sheets is not set up on the server yet/)).toBeInTheDocument();
    expect(screen.getByLabelText("Spreadsheet link")).toBeDisabled();
  });
});

describe("Integrations setup view", () => {
  it("distinguishes missing credentials, incomplete setup and unverified configuration", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["settings.view"] }))),
      route("GET", "/admin/integrations/google-sheets", () => ok(sheet())),
      route("GET", "/admin/integrations", () => ok([
        integration("ccavenue", "CCAvenue", false, false),
        integration("shiprocket", "Shiprocket", true, false),
        integration("msg91_customer_otp", "MSG91 OTP widget", true, true),
      ])),
    );
    renderApp("/integrations");

    const ccavenue = (await screen.findByText("CCAvenue")).closest("tr")!;
    const shiprocket = screen.getByText("Shiprocket").closest("tr")!;
    const msg91 = screen.getByText("MSG91 OTP widget").closest("tr")!;
    expect(within(ccavenue).getByText("Credentials missing")).toBeInTheDocument();
    expect(within(shiprocket).getByText("Configuration incomplete")).toBeInTheDocument();
    expect(within(shiprocket).getByText(/Courier credentials are present/)).toBeInTheDocument();
    expect(within(msg91).getByText("Configured · not verified")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(within(ccavenue).getByText("EXAMPLE_SECRET_NAME")).not.toBeVisible();
    await userEvent.click(within(ccavenue).getByText("Technical setup"));
    expect(within(ccavenue).getByText("EXAMPLE_SECRET_NAME")).toBeVisible();
  });
});
