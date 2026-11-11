import { EXPORT_FORMATS, downloadReport } from "../../api/reports";
import type { ReportName } from "../../api/reports";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { saveCsv } from "../../utils/csv";

// Retained public component: Inventory and the original report downloads use it unchanged.
export function ExportButtons({ name, query }: { name: ReportName; query: object }) {
  const action = useAction();
  return <div className="toolbar"><span className="muted">Download:</span>
    {EXPORT_FORMATS.map(({ format, label }) => <button key={format} onClick={() => action.run(() => downloadReport(name, query, format), null, `${label} export failed`)} disabled={action.busy}>{label}</button>)}
    <StatusMessage status={action.status} />
  </div>;
}
export function ReportExports({ name, query, rows, local = false, pageOnly = false, filename = "report" }: { name?: ReportName; query: object; rows: object[]; local?: boolean; pageOnly?: boolean; filename?: string }) {
  if (name && !local) return <ExportButtons name={name} query={query} />;
  return <div className="toolbar">
    <button disabled={!rows.length} onClick={() => saveCsv(`${filename}.csv`, rows.map((row) => ({ ...query, ...row })))}>CSV{pageOnly ? " (page)" : ""}</button>
    <span className="muted">{name ? "Filtered Excel/PDF exports need backend filter support." : "Excel/PDF export is not provided by this API."}</span>
  </div>;
}
