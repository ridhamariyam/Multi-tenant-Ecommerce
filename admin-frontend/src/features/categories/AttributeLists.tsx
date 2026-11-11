import { useState } from "react";
import { createAttributeValue, listAttributeValues, updateAttributeValue } from "../../api/products";
import Badge from "../../components/common/Badge";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { AttributeName, AttributeValue } from "../../types/catalogue";
import { ATTRIBUTE_NAMES } from "../../types/catalogue";

// Managed values for the storefront filters. A value used by products can be
// switched off but not renamed (renaming would silently change those products).
function AttributeLists({ canManage }: { canManage: boolean }) {
  const values = useApi(() => listAttributeValues(), []);
  const action = useAction();
  const [drafts, setDrafts] = useState<Record<AttributeName, string>>({ fabric: "", occasion: "", sleeve: "", neckline: "" });
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);

  const add = (attribute: AttributeName) => {
    const value = drafts[attribute].trim();
    if (!value) return;
    action.run(async () => { await createAttributeValue(attribute, value); setDrafts({ ...drafts, [attribute]: "" }); values.reload(); }, `Added "${value}"`, "Could not add value");
  };
  const save = (item: AttributeValue, changes: Partial<Pick<AttributeValue, "value" | "is_active">>, done: string) =>
    action.run(async () => { await updateAttributeValue(item.id, changes); setEditing(null); values.reload(); }, done, "Could not update value");

  return (
    <section className="panel attribute-values-panel" aria-label="Filter values">
      <h3>Filter values</h3>
      <p className="muted">Add values here or directly in a product form. Switched-off values remain on existing products.</p>
      <StatusMessage status={action.status} />
      {values.loading && <p className="muted">Loading filter values…</p>}
      {values.error && <div className="status status-error">{values.error}</div>}
      <div className="attribute-values-grid">
        {ATTRIBUTE_NAMES.map((name) => {
          const list = (values.data ?? []).filter((v) => v.attribute === name);
          return (
            <section key={name} className="attribute-values-card" aria-label={`${name} values`}>
              <h4 style={{ textTransform: "capitalize" }}>{name}</h4>
              {list.length === 0 && !values.loading && !values.error && <p className="muted">No values yet.</p>}
              <ul className="list-plain attribute-values-list">
                {list.map((item) => (
                  <li key={item.id} className="attribute-value-row">
                    {editing?.id === item.id ? (
                      <form className="attribute-value-edit" onSubmit={(e) => { e.preventDefault(); if (editing.value.trim()) save(item, { value: editing.value.trim() }, "Renamed"); }}>
                        <input aria-label={`Rename ${item.value}`} value={editing.value} onChange={(e) => setEditing({ id: item.id, value: e.target.value })} maxLength={100} />
                        <button disabled={action.busy}>Save</button>
                        <button type="button" onClick={() => setEditing(null)}>Cancel</button>
                      </form>
                    ) : (
                      <>
                        <span className="attribute-value-name">{item.value}</span>
                        <span className="muted attribute-value-count">{item.product_count} product{item.product_count === 1 ? "" : "s"}</span>
                        <Badge value={item.is_active ? "ACTIVE" : "INACTIVE"} />
                        {canManage && (
                          <span className="attribute-value-actions">
                            <button type="button" className="link" disabled={action.busy || item.product_count > 0} title={item.product_count > 0 ? "In use — add a new value and switch this one off instead" : undefined} onClick={() => setEditing({ id: item.id, value: item.value })}>
                              Rename
                            </button>
                            <button type="button" className="link" disabled={action.busy} onClick={() => save(item, { is_active: !item.is_active }, item.is_active ? "Switched off" : "Switched on")}>
                              {item.is_active ? "Disable" : "Enable"}
                            </button>
                          </span>
                        )}
                      </>
                    )}
                  </li>
                ))}
              </ul>
              {canManage && (
                <form className="attribute-add-form" onSubmit={(e) => { e.preventDefault(); add(name); }}>
                  <input aria-label={`New ${name}`} placeholder={`Add ${name}`} value={drafts[name]} onChange={(e) => setDrafts({ ...drafts, [name]: e.target.value })} maxLength={100} />
                  <button disabled={!drafts[name].trim() || action.busy}>Add</button>
                </form>
              )}
            </section>
          );
        })}
      </div>
    </section>
  );
}

export default AttributeLists;
