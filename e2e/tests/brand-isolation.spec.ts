import { expect, test } from "@playwright/test";
import { SECOND_BRAND, SECOND_STORE, STORE } from "./env";

test("each domain shows only its own brand", async ({ page }) => {
  await page.goto(STORE);
  const firstTitle = await page.title();

  await page.goto(SECOND_STORE);
  await expect(page).toHaveTitle(new RegExp(SECOND_BRAND));
  expect(await page.title()).not.toBe(firstTitle);

  const resolved = await page.evaluate(async () => (await fetch("/api/v1/storefront/resolve")).json());
  expect(resolved.data.brand.name).toContain(SECOND_BRAND);
});

test("an unknown store address shows the not-found store page", async ({ page }) => {
  const response = await page.goto(STORE.replace("://localhost", "://no-such-brand-e2e.localhost"));
  expect(response?.status()).toBeGreaterThanOrEqual(200);
  await expect(page.getByText(/no store|isn.t available|not found/i).first()).toBeVisible();
});
