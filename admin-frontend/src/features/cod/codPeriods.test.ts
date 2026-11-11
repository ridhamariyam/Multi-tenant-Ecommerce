import { describe, expect, it } from "vitest";
import { codCurrentMonthRange, codPeriodRange } from "./codPeriods";

describe("COD report periods", () => {
  const now = new Date("2026-03-01T00:15:00Z");

  it("uses inclusive UTC dates for every preset across month and year boundaries", () => {
    expect(codPeriodRange("all", now, "", "")).toEqual({ start: "0001-01-01", end: "2026-03-01" });
    expect(codPeriodRange("today", now, "", "")).toEqual({ start: "2026-03-01", end: "2026-03-01" });
    expect(codPeriodRange("yesterday", now, "", "")).toEqual({ start: "2026-02-28", end: "2026-02-28" });
    expect(codPeriodRange("last7", now, "", "")).toEqual({ start: "2026-02-23", end: "2026-03-01" });
    expect(codPeriodRange("lastMonth", now, "", "")).toEqual({ start: "2026-02-01", end: "2026-02-28" });
    expect(codPeriodRange("lastYear", now, "", "")).toEqual({ start: "2025-01-01", end: "2025-12-31" });
    expect(codPeriodRange("custom", now, "2026-01-04", "2026-01-09")).toEqual({ start: "2026-01-04", end: "2026-01-09" });
  });

  it("keeps the current calendar month independent from the selected period", () => {
    expect(codCurrentMonthRange(now)).toEqual({ start: "2026-03-01", end: "2026-03-01" });
    expect(codCurrentMonthRange(new Date("2026-03-31T23:59:59Z"))).toEqual({ start: "2026-03-01", end: "2026-03-31" });
    expect(codPeriodRange("lastMonth", new Date("2026-01-03T00:00:00Z"), "", "")).toEqual({ start: "2025-12-01", end: "2025-12-31" });
  });
});
