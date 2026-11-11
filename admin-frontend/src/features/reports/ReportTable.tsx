import { useState } from "react";
import type { ReactNode } from "react";
import type { Column } from "../../components/common/DataTable";
import DataTable from "../../components/common/DataTable";
import Pagination from "../../components/common/Pagination";
import type { ReportName } from "../../api/reports";
import { ReportExports } from "./ReportExports";

export type ReportRow = Record<string, string | number | null>;
export default function ReportTable({ rows, columns, rowKey, heading, summary, name, query = {}, loading, error, empty, localOnly = false, filename = "report" }: {
  rows: ReportRow[] | null; columns: Column<ReportRow>[]; rowKey: (row: ReportRow) => string;
  heading?: ReactNode; summary?: ReactNode; name?: ReportName; query?: object; loading?: boolean; error?: string | null; empty?: string; localOnly?: boolean; filename?: string;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("");
  const [page, setPage] = useState(1);
  const needle = search.trim().toLocaleLowerCase();
  const source = loading ? null : rows;
  const filtered = source?.filter((row) => columns.some((column) => String(row[column.key] ?? "").toLocaleLowerCase().includes(needle))) ?? [];
  const [field, direction] = sort.split(":");
  const ordered = sort ? [...filtered].sort((a, b) => {
    const x = a[field]; const y = b[field];
    const numeric = x !== null && y !== null && x !== "" && y !== "" && Number.isFinite(Number(x)) && Number.isFinite(Number(y));
    const result = numeric ? Number(x) - Number(y) : String(x ?? "").localeCompare(String(y ?? ""));
    return direction === "desc" ? -result : result;
  }) : filtered;
  const pages = Math.max(1, Math.ceil(ordered.length / 50));
  const current = Math.min(page, pages);
  const exportRows = ordered.map((row) => Object.fromEntries(columns.filter((column) => column.key in row).map((column) => [column.key, row[column.key]])));
  return <>
    <div className="panel-title">{heading ?? <span />}<ReportExports name={name} query={query} rows={exportRows} local={localOnly || !!needle || !!sort} filename={filename} /></div>
    {summary}
    {summary && needle && <p className="muted">Summary cards cover the selected date range; search filters the table rows.</p>}
    <div className="filters">
      <input aria-label="Search report" placeholder="Search this report…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
      <select aria-label="Sort report" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
        <option value="">Report order</option>
        {columns.flatMap((column) => [<option key={`${column.key}:asc`} value={`${column.key}:asc`}>{column.header} ↑</option>, <option key={`${column.key}:desc`} value={`${column.key}:desc`}>{column.header} ↓</option>])}
      </select>
    </div>
    <DataTable rows={source ? ordered.slice((current - 1) * 50, current * 50) : null} columns={columns} rowKey={rowKey} loading={loading} error={error} empty={empty} />
    {source && !error && <Pagination meta={{ page: current, page_size: 50, total_items: ordered.length, total_pages: pages }} onPageChange={setPage} />}
  </>;
}
