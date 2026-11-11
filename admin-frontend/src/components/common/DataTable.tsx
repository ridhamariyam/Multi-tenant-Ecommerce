import type { HTMLAttributes, ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: string;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowProps?: (row: T) => HTMLAttributes<HTMLTableRowElement>;
}

// A plain table with loading, error and empty states built in.
function DataTable<T>({ columns, rows, loading, error, onRetry, empty = "Nothing here yet.", rowKey, onRowClick, rowProps }: DataTableProps<T>) {
  if (error) return <div className="status status-error" role="alert">
    <span>{error}</span>{onRetry && <> <button type="button" className="link" onClick={onRetry}>Try again</button></>}
  </div>;
  if (loading && !rows) return <div className="state">Loading…</div>;
  if (!rows || rows.length === 0) return <div className="state muted">{empty}</div>;
  return (
    <div className="table-wrap">
      <table className={loading ? "is-loading" : undefined}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.align === "right" ? "num" : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              {...rowProps?.(row)}
              key={rowKey(row)}
              className={onRowClick ? "clickable" : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} className={c.align === "right" ? "num" : undefined}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "-")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
