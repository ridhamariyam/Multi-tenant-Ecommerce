import { useState } from "react";
import { getOrderSheet, saveOrderSheet, syncOrderSheet } from "../../api/integrations";
import Field from "../../components/common/Field";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { OrderSheetSettings } from "../../types/settings";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "never");

/** Google Sheets: every successful order of this store, appended to its own spreadsheet. */
export default function OrderSheetPanel({ canEdit }: { canEdit: boolean }) {
  const sheet = useApi(getOrderSheet, []);
  if (sheet.error) return <div className="status status-error" role="alert">{sheet.error}</div>;
  if (!sheet.data) return <div className="state">Loading Google Sheets export…</div>;
  return <OrderSheetForm initial={sheet.data} canEdit={canEdit} />;
}

function OrderSheetForm({ initial, canEdit }: { initial: OrderSheetSettings; canEdit: boolean }) {
  const [current, setCurrent] = useState(initial);
  const [spreadsheet, setSpreadsheet] = useState(initial.spreadsheet_url ?? "");
  const [tab, setTab] = useState(initial.worksheet_name);
  const [enabled, setEnabled] = useState(initial.is_enabled);
  const action = useAction();
  const ready = current.credentials_configured;

  return (
    <section className="panel order-sheet-panel" aria-labelledby="order-sheet-title">
      <h3 id="order-sheet-title">Google Sheets — order export</h3>
      <p className="muted">
        Every successful order is added as a row: cash on delivery orders when they are placed, online orders once
        they are paid. Rows are added within about a minute.
      </p>

      {!ready ? (
        <div className="notice" role="status">
          Google Sheets is not set up on the server yet. Ask the project lead to add a Google service account key
          (<code>GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON</code>).
        </div>
      ) : (
        <ol className="order-sheet-steps">
          <li>Create a Google Sheet (or open an existing one).</li>
          <li>
            Click <strong>Share</strong> and add <code className="order-sheet-email">{current.service_account_email}</code> as an{" "}
            <strong>Editor</strong>.
          </li>
          <li>Paste the sheet&apos;s link below, turn the export on and save.</li>
        </ol>
      )}

      <StatusMessage status={action.status} />
      <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          const saved = await action.run(
            () => saveOrderSheet({ is_enabled: enabled, spreadsheet: spreadsheet.trim() || null, worksheet_name: tab.trim() || "Orders" }),
            enabled ? "Sheet connected. New orders will appear in it." : "Saved. The export is off.",
            "Could not save",
          );
          if (saved?.data) {
            setCurrent(saved.data);
            setSpreadsheet(saved.data.spreadsheet_url ?? "");
          }
        }}
      >
        <fieldset className="form" disabled={!canEdit || action.busy || !ready} style={{ border: 0, padding: 0 }}>
          <div className="form-grid">
            <Field label="Spreadsheet link" hint="Copy it from the browser's address bar while the sheet is open." wide>
              <input
                type="text"
                inputMode="url"
                placeholder="https://docs.google.com/spreadsheets/d/…"
                maxLength={500}
                value={spreadsheet}
                onChange={(e) => setSpreadsheet(e.target.value)}
                required={enabled}
              />
            </Field>
            <Field label="Tab name" hint="Created with a header row if it doesn't exist.">
              <input maxLength={100} value={tab} onChange={(e) => setTab(e.target.value)} />
            </Field>
          </div>
          <label className="check">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Add every successful order to this sheet
          </label>
          {canEdit && (
            <div className="order-sheet-actions">
              <button className="primary" disabled={action.busy}>Save</button>
              {current.is_enabled && (
                <button
                  type="button"
                  disabled={action.busy}
                  onClick={async () => {
                    const result = await action.run(() => syncOrderSheet(), null, "Could not sync");
                    if (!result?.data) return;
                    const { exported, error } = result.data;
                    action.setStatus(
                      error
                        ? { type: "error", text: error }
                        : { type: "success", text: exported ? `${exported} order${exported === 1 ? "" : "s"} added to the sheet.` : "The sheet is up to date." },
                    );
                    const fresh = await getOrderSheet().catch(() => null);
                    if (fresh?.data) setCurrent(fresh.data);
                  }}
                >
                  Sync now
                </button>
              )}
              {current.spreadsheet_url && (
                <a href={current.spreadsheet_url} target="_blank" rel="noreferrer">
                  Open sheet ↗
                </a>
              )}
            </div>
          )}
        </fieldset>
      </form>

      {current.spreadsheet_id && (
        <dl className="order-sheet-stats">
          <div><dt>In the sheet</dt><dd>{current.exported_orders}</dd></div>
          <div><dt>Waiting</dt><dd>{current.pending_orders}</dd></div>
          <div><dt>Last synced</dt><dd>{when(current.last_synced_at)}</dd></div>
        </dl>
      )}
      {current.last_error && (
        <div className="status status-error" role="alert">
          Last export failed ({when(current.last_error_at)}): {current.last_error}
        </div>
      )}
    </section>
  );
}
