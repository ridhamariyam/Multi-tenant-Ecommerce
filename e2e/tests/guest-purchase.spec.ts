import { expect, test } from "@playwright/test";
import { STORE } from "./env";

test("a guest buys with cash on delivery and can track the order", async ({ page }) => {
  // Add the first product that can actually be bought (stock changes as tests run).
  await page.goto(`${STORE}/products`);
  const hrefs = [...new Set(await page.locator('a[href^="/products/"]').evaluateAll((as) => as.map((a) => a.getAttribute("href")!)))];
  let added = false;
  for (const href of hrefs.slice(0, 8)) {
    await page.goto(`${STORE}${href}`);
    await page.waitForLoadState("networkidle"); // hydrated, so the button really works
    const size = page.getByRole("combobox", { name: /size/i });
    if (await size.count()) {
      const values = await size.locator("option:not([disabled])").evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value).filter(Boolean));
      if (!values.length) continue;
      await size.selectOption(values[values.length - 1]);
    }
    const button = page.getByRole("button", { name: "Add to cart" });
    if (!(await button.isEnabled())) continue;
    await button.click();
    await page.waitForTimeout(1500);
    await page.goto(`${STORE}/cart`);
    if (!(await page.getByText(/your (bag|cart) is empty/i).count())) {
      added = true;
      break;
    }
  }
  expect(added, "no product could be added to the bag").toBe(true);

  await page.goto(`${STORE}/checkout`);
  await page.getByLabel("Full name").fill("E2E Guest");
  await page.getByPlaceholder("10-digit mobile number").fill("9000099001");
  await page.getByLabel("Email (optional)").fill("e2e-guest@example.com");
  await page.getByLabel("Address", { exact: true }).fill("1 Test Lane");
  await page.getByLabel("City").fill("Kochi");
  await page.getByLabel("State").fill("Kerala");
  await page.getByLabel(/pincode/i).fill("682001");
  await page.getByRole("radio", { name: /Cash on Delivery/ }).check();
  await expect(page.getByRole("button", { name: /^Place Order/ })).toBeEnabled();
  const invalid = await page.evaluate(() =>
    Array.from(document.querySelectorAll("form :invalid")).map((e) => (e as HTMLInputElement).name || e.id),
  );
  expect(invalid).toEqual([]);
  await page.getByRole("button", { name: /^Place Order/ }).click();

  await expect(page.getByRole("heading", { name: /your order is placed/i })).toBeVisible();
  const orderNumber = (await page.locator("strong", { hasText: /^ORD-/ }).first().textContent())!.trim();

  await page.goto(`${STORE}/track-order?order=${orderNumber}`);
  const form = page.locator("form", { has: page.getByRole("button", { name: /track order/i }) });
  await form.getByPlaceholder("10-digit mobile number").fill("9000099001");
  await form.getByRole("button", { name: /track order/i }).click();
  await expect(page.getByText(orderNumber).first()).toBeVisible();
});
