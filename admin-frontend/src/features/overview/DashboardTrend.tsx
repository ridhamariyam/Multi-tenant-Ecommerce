import { formatMoney } from "../../utils/formatters";

export interface DashboardTrendRow { period: string; orders: number; revenue: string }

export default function DashboardTrend({ title, rows, metric, currency }: { title: string; rows: DashboardTrendRow[]; metric: "revenue" | "orders"; currency?: string }) {
  if (!rows.length) return <div className="dashboard-chart-empty">No sales data for this period.</div>;
  const points = [...rows].sort((a, b) => a.period.localeCompare(b.period));
  const values = points.map((row) => metric === "revenue" ? Number(row.revenue) : row.orders);
  const max = Math.max(0, ...values);
  const width = 600;
  const left = 48;
  const right = 585;
  const base = 142;
  const top = 16;
  const x = (index: number) => points.length === 1 ? (left + right) / 2 : left + index / (points.length - 1) * (right - left);
  const y = (value: number) => max > 0 ? base - value / max * (base - top) : base;
  const valueText = (value: number) => metric === "revenue" ? formatMoney(value, currency) : String(value);
  return <figure className="dashboard-line-chart" aria-label={title}>
    <figcaption>{title}</figcaption>
    <svg viewBox={`0 0 ${width} 180`} role="img" aria-label={`${title} from ${points[0].period} to ${points[points.length - 1].period}`}>
      <line x1={left} y1={base} x2={right} y2={base} className="trend-axis" />
      {points.length > 1 && <polyline points={values.map((value, index) => `${x(index)},${y(value)}`).join(" ")} className="trend-line" fill="none" />}
      {values.map((value, index) => <circle key={`${points[index].period}:${index}`} cx={x(index)} cy={y(value)} r="4" className="trend-point"><title>{points[index].period}: {valueText(value)}</title></circle>)}
      <text x={left} y="170">{points[0].period}</text>
      {points.length > 1 && <text x={right} y="170" textAnchor="end">{points[points.length - 1].period}</text>}
      <text x={left} y="12">{valueText(max)}</text>
    </svg>
  </figure>;
}
