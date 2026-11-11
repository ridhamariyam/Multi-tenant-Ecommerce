import { expect, test } from "@playwright/test";
import { CONSOLE, MERCHANT_EMAIL, MERCHANT_PASSWORD, SECOND_BRAND } from "./env";

test.skip(!MERCHANT_EMAIL || !MERCHANT_PASSWORD, "Set E2E_MERCHANT_EMAIL / E2E_MERCHANT_PASSWORD (a test merchant)");

test("a merchant signs in, opens their brand and sees its plan and orders", async ({ page }) => {
  await page.goto(`${CONSOLE}/signin`);
  await page.getByLabel("Email").fill(MERCHANT_EMAIL);
  await page.getByLabel("Password").fill(MERCHANT_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  const card = page.locator("li", { hasText: SECOND_BRAND }).first();
  await card.getByRole("button", { name: "Manage" }).click();
  await expect(page.getByRole("link", { name: "Plan & billing" })).toBeVisible();

  await page.getByRole("link", { name: "Plan & billing" }).click();
  await expect(page.getByRole("heading", { name: /Current plan:/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Growth" })).toBeVisible();

  await page.getByRole("link", { name: "Orders" }).click();
  await expect(page).toHaveURL(/\/orders/);
});
