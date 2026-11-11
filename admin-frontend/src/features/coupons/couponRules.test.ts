import { describe, expect, it } from "vitest";
import { toForm, toPayload, validateCoupon } from "./couponRules";

const form = (overrides = {}) => ({ ...toForm(null), code: "DIWALI20", discount_value: "20", ...overrides });

describe("coupon rules", () => {
  it("accepts a valid percentage coupon", () => {
    expect(validateCoupon(form(), true)).toBeNull();
  });

  it("rejects percentages above 100", () => {
    expect(validateCoupon(form({ discount_value: "120" }), true)).toMatch(/cannot exceed 100/);
  });

  it("needs buy and get quantities for BOGO", () => {
    expect(validateCoupon(form({ discount_type: "BOGO", discount_value: "100" }), true)).toMatch(/BOGO/);
    expect(validateCoupon(form({ discount_type: "BOGO", discount_value: "100", buy_quantity: "2", get_quantity: "1" }), true)).toBeNull();
  });

  it("needs no value for free shipping and sends none", () => {
    const f = form({ discount_type: "FREE_SHIPPING", discount_value: "" });
    expect(validateCoupon(f, true)).toBeNull();
    expect(toPayload(f, true).discount_value).toBeNull();
  });

  it("refuses an end date before the start", () => {
    expect(validateCoupon(form({ starts_at: "2026-10-10T10:00", expires_at: "2026-10-01T10:00" }), true)).toMatch(/after the start/);
  });

  it("rejects unsafe codes only when creating", () => {
    expect(validateCoupon(form({ code: "bad code!" }), true)).toMatch(/Code/);
    expect(validateCoupon(form({ code: "bad code!" }), false)).toBeNull();
  });

  it("uppercases new codes and omits the code on edit", () => {
    expect(toPayload(form({ code: " diwali20 " }), true).code).toBe("DIWALI20");
    expect(toPayload(form(), false)).not.toHaveProperty("code");
  });

  it("drops BOGO quantities and the cap from other types", () => {
    const p = toPayload(form({ discount_type: "FIXED_AMOUNT", buy_quantity: "2", get_quantity: "1", max_discount_amount: "50" }), true);
    expect(p.buy_quantity).toBeNull();
    expect(p.max_discount_amount).toBeNull();
  });
});

describe("coupon weekdays", () => {
  it("sends the chosen days sorted, and none for every day", () => {
    expect(toPayload(form({ valid_weekdays: [4, 0, 2] }), true).valid_weekdays).toEqual([0, 2, 4]);
    expect(toPayload(form(), true).valid_weekdays).toEqual([]);
  });

  it("keeps an existing coupon's days when editing", () => {
    const existing = { ...toForm(null), valid_weekdays: [5, 6] };
    expect(toPayload(existing, false).valid_weekdays).toEqual([5, 6]);
  });
});
