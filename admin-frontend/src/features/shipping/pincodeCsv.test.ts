import { describe, expect, it } from "vitest";
import { parsePincodeCsv } from "./pincodeCsv";

describe("pincode bulk text", () => {
  it("parses full and minimal lines and skips a header", () => {
    const { rules, errors } = parsePincodeCsv("pincode,serviceable,cod\n560001,yes,no,2,4,49,Bengaluru,Karnataka\n682001");
    expect(errors).toEqual([]);
    expect(rules).toEqual([
      { pincode: "560001", is_serviceable: true, cod_available: false, min_delivery_days: 2, max_delivery_days: 4, shipping_amount: "49", city: "Bengaluru", state: "Karnataka" },
      { pincode: "682001", is_serviceable: true, cod_available: true, min_delivery_days: null, max_delivery_days: null, shipping_amount: null, city: null, state: null },
    ]);
  });

  it("reports invalid pincodes with their line", () => {
    expect(parsePincodeCsv("560001\n012345\nabc").errors).toEqual([
      'Line 2: "012345" is not a 6-digit pincode',
      'Line 3: "abc" is not a 6-digit pincode',
    ]);
  });
});
