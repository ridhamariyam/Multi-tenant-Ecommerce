import { useState } from "react";
import type { MouseEvent } from "react";
import { archiveLook, createLook, listLooks, publishLook, updateLook } from "../../api/looks";
import type { Look, LookPin } from "../../api/looks";
import { listProducts, uploadUnattachedImage } from "../../api/products";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import "./looks.css";

const MAX_PINS = 6;

/** Styled photos with this store's products pinned on them; shown on the runway home. */
export default function LooksSection() {
  const looks = useApi(listLooks, []);
  const [editing, setEditing] = useState<Look | "new" | null>(null);
  return (
    <div className="looks-page">
      <PageHeader title="Lookbooks" subtitle="Pin products on a styled photo. Published looks appear on your store's home page." />
      {editing ? (
        <LookEditor look={editing === "new" ? null : editing} onDone={() => { setEditing(null); looks.reload(); }} />
      ) : (
        <button className="primary" onClick={() => setEditing("new")}>New look</button>
      )}
      {looks.error && <div className="status status-error" role="alert">{looks.error}</div>}
      <ul className="looks-grid">
        {(looks.data ?? []).map((look) => (
          <li key={look.id} className="panel look-card">
            {look.cover_url ? <img src={look.cover_url} alt="" /> : <div className="look-empty">No cover yet</div>}
            <strong>{look.title}</strong>
            <span className={`badge ${look.status === "PUBLISHED" ? "badge-ok" : "badge-warn"}`}>{look.status === "PUBLISHED" ? "On the store" : "Draft"}</span>
            <span className="muted">{look.pins.length} product{look.pins.length === 1 ? "" : "s"}</span>
            <button type="button" className="btn btn-sm" onClick={() => setEditing(look)}>Edit</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LookEditor({ look, onDone }: { look: Look | null; onDone: () => void }) {
  const products = useApi(() => listProducts({ page_size: 100 }), []);
  const [title, setTitle] = useState(look?.title ?? "");
  const [cover, setCover] = useState<string | null>(look?.cover_url ?? null);
  const [pins, setPins] = useState<LookPin[]>(look?.pins ?? []);
  const [active, setActive] = useState<number | null>(null);
  const action = useAction();

  function place(e: MouseEvent<HTMLDivElement>) {
    if (pins.length >= MAX_PINS && active === null) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    const y = Math.min(1, Math.max(0, (e.clientY - box.top) / box.height));
    if (active !== null) {
      setPins(pins.map((p, i) => (i === active ? { ...p, x, y } : p)));
      setActive(null);
    } else {
      setPins([...pins, { product_id: "", x, y }]);
      setActive(null);
    }
  }

  const body = () => ({ title: title.trim(), cover_url: cover, pins: pins.filter((p) => p.product_id).map(({ product_id, x, y }) => ({ product_id, x, y })) });

  return (
    <section className="panel form look-editor" aria-label="Look editor">
      <StatusMessage status={action.status} />
      <div className="form-grid">
        <Field label="Title"><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={150} required /></Field>
        <Field label="Cover photo" hint="A tall styled photo works best (3:4 or 9:16).">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const up = await action.run(() => uploadUnattachedImage(file), null, "Upload failed");
              if (up?.data) setCover(up.data.url);
            }}
          />
        </Field>
      </div>
      {cover && (
        <>
          <p className="muted">Click the photo to add a pin (up to {MAX_PINS}); choose its product below. Select a pin's “Move” then click to reposition it.</p>
          <div className="look-canvas" onClick={place} role="presentation">
            <img src={cover} alt="Look cover" />
            {pins.map((p, i) => (
              <span key={i} className={`look-pin ${active === i ? "is-active" : ""}`} style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}>{i + 1}</span>
            ))}
          </div>
        </>
      )}
      <ol className="look-pins">
        {pins.map((p, i) => (
          <li key={i}>
            <label>
              Pin {i + 1}
              <select aria-label={`Product for pin ${i + 1}`} value={p.product_id} onChange={(e) => setPins(pins.map((q, j) => (j === i ? { ...q, product_id: e.target.value } : q)))}>
                <option value="">Choose a product</option>
                {(products.data ?? []).map((prod) => <option key={prod.id} value={prod.id}>{prod.name}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-sm" onClick={() => setActive(i)}>Move</button>
            <button type="button" className="btn btn-sm" onClick={() => setPins(pins.filter((_, j) => j !== i))}>Remove</button>
          </li>
        ))}
      </ol>
      <div className="look-actions">
        <button
          className="primary"
          disabled={action.busy || !title.trim()}
          onClick={async () => {
            const saved = await action.run(() => (look ? updateLook(look.id, body()) : createLook(body())), "Saved.", "Could not save");
            if (saved?.data) onDone();
          }}
        >
          Save
        </button>
        {look && (
          <button
            type="button"
            className="btn"
            disabled={action.busy}
            onClick={async () => {
              const r = await action.run(() => updateLook(look.id, body()).then(() => publishLook(look.id, look.status !== "PUBLISHED")), look.status === "PUBLISHED" ? "Hidden from the store." : "Published.", "Could not publish");
              if (r?.data) onDone();
            }}
          >
            {look.status === "PUBLISHED" ? "Hide from store" : "Save & publish"}
          </button>
        )}
        {look && (
          <ConfirmButton message={`Archive “${look.title}”? It leaves the store.`} confirmLabel="Archive" onConfirm={async () => { if (await action.run(() => archiveLook(look.id), null, "Could not archive")) onDone(); }}>
            Archive
          </ConfirmButton>
        )}
        <button type="button" className="btn" onClick={onDone}>Cancel</button>
      </div>
    </section>
  );
}
