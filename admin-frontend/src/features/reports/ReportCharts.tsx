import { formatMoney } from "../../utils/formatters";
import type { ReportRow } from "./ReportTable";

type Series = { name: string; values: number[]; color: string };

export function TrendChart({ title, rows, field, compare, currency = false }: { title: string; rows: ReportRow[]; field: string; compare?: ReportRow[]; currency?: boolean }) {
  const current = rows.map((row) => Number(row[field]) || 0);
  const previous = compare?.map((row) => Number(row[field]) || 0) ?? [];
  const count = Math.max(rows.length, previous.length);
  const max = Math.max(1, ...current, ...previous);
  const x = (i: number) => 46 + (count > 1 ? i / (count - 1) * 590 : 295);
  const y = (value: number) => 152 - value / max * 112;
  const series: Series[] = [{ name: "Selected period", values: current, color: "var(--accent)" }];
  if (compare) series.push({ name: "Previous period", values: previous, color: "var(--chart-secondary)" });
  return <figure className="report-chart" aria-label={title}>
    <figcaption>{title}</figcaption>
    {!count ? <div className="report-chart-empty">No recorded data in this period.</div> : <>
      <div className="report-legend">{series.map((line) => <span key={line.name}><i style={{ background: line.color }} />{line.name}</span>)}</div>
      <svg role="img" aria-label={`${title}; values are shown in point tooltips`} viewBox="0 0 680 190" preserveAspectRatio="xMidYMid meet">
        {[0, .5, 1].map((fraction) => <g key={fraction}><line x1="46" x2="636" y1={y(max * fraction)} y2={y(max * fraction)} stroke="var(--line)" /><text x="40" y={y(max * fraction) + 4} textAnchor="end">{currency ? formatMoney(max * fraction).replace(/^INR /, "₹") : Math.round(max * fraction)}</text></g>)}
        {series.map((line) => <g key={line.name}>
          <polyline points={line.values.map((value, i) => `${x(i)},${y(value)}`).join(" ")} fill="none" stroke={line.color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          {line.values.map((value, i) => <circle key={i} cx={x(i)} cy={y(value)} r="3.5" fill={line.color}><title>{line.name}, {line.name === "Previous period" ? compare?.[i]?.period : rows[i]?.period}: {currency ? formatMoney(value) : value}</title></circle>)}
        </g>)}
        <text x="46" y="180">{String(rows[0]?.period ?? compare?.[0]?.period ?? "")}</text>
        <text x="636" y="180" textAnchor="end">{String(rows.at(-1)?.period ?? compare?.at(-1)?.period ?? "")}</text>
      </svg>
    </>}
  </figure>;
}

export function BarChart({ title, rows, labelKey, valueKey, currency = false }: { title: string; rows: ReportRow[]; labelKey: string; valueKey: string; currency?: boolean }) {
  const shown = rows.slice(0, 6);
  const max = Math.max(1, ...shown.map((row) => Number(row[valueKey]) || 0));
  return <figure className="report-chart report-bars" aria-label={title}><figcaption>{title}</figcaption>
    {shown.length ? <div className="report-bar-list">{shown.map((row, index) => <div className="report-bar-row" key={`${row[labelKey]}-${index}`}>
      <span title={String(row[labelKey] ?? "Unknown")}>{String(row[labelKey] ?? "Unknown")}</span>
      <div className="report-bar-track"><i style={{ width: `${Math.max(2, (Number(row[valueKey]) || 0) / max * 100)}%` }} /></div>
      <strong>{currency ? formatMoney(row[valueKey]) : String(row[valueKey] ?? "0")}</strong>
    </div>)}</div> : <p className="muted">No data for this period.</p>}
  </figure>;
}

export function DonutChart({ title, parts }: { title: string; parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  const stops = parts.map((part, index) => {
    const start = total ? parts.slice(0, index).reduce((sum, entry) => sum + entry.value, 0) / total * 100 : 0;
    const end = total ? start + part.value / total * 100 : 0;
    return `${part.color} ${start}% ${end}%`;
  });
  return <figure className="report-chart report-donut" aria-label={title}><figcaption>{title}</figcaption>
    {total ? <div className="report-donut-content"><div className="report-donut-ring" style={{ background: `conic-gradient(${stops.join(", ")})` }} aria-hidden="true"><span>{total}</span></div>
      <ul>{parts.map((part) => <li key={part.label}><i style={{ background: part.color }} />{part.label}<strong>{part.value}</strong></li>)}</ul></div> : <p className="muted">No data for this period.</p>}
  </figure>;
}
