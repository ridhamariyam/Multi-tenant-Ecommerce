import { describe, expect, it } from "vitest";
import { chartPayload } from "./sizeChart";

const chart = (overrides = {}) => ({
  enabled: true,
  unit: "in" as const,
  measurements: ["Bust", "Length"],
  rows: [{ size: "S", values: { Bust: "34", Length: "40" } }],
  note: "",
  ...overrides,
});

describe("size chart", () => {
  it("is omitted when switched off", () => {
    expect(chartPayload(chart({ enabled: false }))).toEqual({ chart: null, error: null });
  });

  it("builds the payload the backend expects", () => {
    expect(chartPayload(chart()).chart).toEqual({
      unit: "in",
      measurements: ["Bust", "Length"],
      rows: [{ size: "S", values: { Bust: "34", Length: "40" } }],
      note: null,
    });
  });

  it("rejects duplicate measurement names", () => {
    expect(chartPayload(chart({ measurements: ["Bust", "bust"] })).error).toMatch(/different/);
  });

  it("rejects out-of-range values", () => {
    expect(chartPayload(chart({ rows: [{ size: "S", values: { Bust: "0" } }] })).error).toMatch(/between 0 and 1000/);
  });

  it("needs a size label and at least one measurement per row", () => {
    expect(chartPayload(chart({ rows: [{ size: " ", values: { Bust: "30" } }] })).error).toMatch(/needs a size/);
    expect(chartPayload(chart({ rows: [{ size: "M", values: {} }] })).error).toMatch(/no measurements/);
  });
});
