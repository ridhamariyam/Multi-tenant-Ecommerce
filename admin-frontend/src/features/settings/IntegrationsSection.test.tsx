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

describe("Integrations setup view", () => {
  it("distinguishes missing credentials, incomplete setup and unverified configuration", async () => {
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["settings.view"] }))),
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
