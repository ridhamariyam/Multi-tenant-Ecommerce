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

test("an unknown store address gets no store", async ({ page }) => {
  const unknown = STORE.replace(/:\/\/[^/:]+/, "://no-such-brand-e2e.localhost");
  if (unknown.startsWith("https:")) {
    // Production: the proxy refuses to get a certificate for an unknown name,
    // so the connection itself fails -- nothing is served for it at all.
    const failed = await page.goto(unknown).then(() => false, () => true);
    expect(failed).toBe(true);
    return;
  }
  await page.goto(unknown);
  await expect(page.getByText(/no store|isn.t available|not found/i).first()).toBeVisible();
});
