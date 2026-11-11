import type { Product, SizeChartInput } from "../../types/catalogue";
import { emptyToNull } from "../../utils/formatters";

export interface ChartState {
  enabled: boolean;
  unit: "in" | "cm";
  measurements: string[];
  rows: { size: string; values: Record<string, string> }[];
  note: string;
}

export function chartFrom(product: Product | null): ChartState {
  const chart = product?.size_chart;
  if (!chart) return { enabled: false, unit: "in", measurements: ["Bust", "Waist", "Length"], rows: [{ size: "S", values: {} }], note: "" };
  return {
    enabled: true,
    unit: chart.unit,
    measurements: chart.measurements,
    rows: chart.rows.map((r) => ({ size: r.size, values: Object.fromEntries(Object.entries(chart.unit === "in" ? r.values_in : r.values_cm).map(([k, v]) => [k, String(v)])) })),
    note: chart.note ?? "",
  };
}

export function chartPayload(c: ChartState): { chart: SizeChartInput | null; error: string | null } {
  if (!c.enabled) return { chart: null, error: null };
  const measurements = c.measurements.map((m) => m.trim()).filter(Boolean);
  if (measurements.length === 0) return { chart: null, error: "Size chart: add at least one measurement." };
  if (new Set(measurements.map((m) => m.toLowerCase())).size !== measurements.length) return { chart: null, error: "Size chart: measurement names must be different." };
  const rows = [];
  for (const row of c.rows) {
    if (!row.size.trim()) return { chart: null, error: "Size chart: every row needs a size." };
    const values: Record<string, string> = {};
    for (const m of measurements) {
      const v = row.values[m]?.trim();
      if (!v) continue;
      const n = Number(v);
      if (!(n > 0 && n <= 1000)) return { chart: null, error: `Size chart: ${row.size} ${m} must be between 0 and 1000.` };
      values[m] = v;
    }
    if (Object.keys(values).length === 0) return { chart: null, error: `Size chart: size ${row.size} has no measurements.` };
    rows.push({ size: row.size.trim(), values });
  }
  if (rows.length === 0) return { chart: null, error: "Size chart: add at least one size." };
  return { chart: { unit: c.unit, measurements, rows, note: emptyToNull(c.note) }, error: null };
}
