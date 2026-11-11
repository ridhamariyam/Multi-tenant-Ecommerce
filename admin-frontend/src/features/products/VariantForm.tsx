import { useState } from "react";
import type { FormEvent } from "react";
import Field from "../../components/common/Field";
import type { CatalogueStatus } from "../../types/api";
import { CATALOGUE_STATUSES } from "../../types/api";
import type { Variant, VariantInput } from "../../types/catalogue";
import { emptyToNull, isoToLocalInput, localInputToIso } from "../../utils/formatters";

export interface VariantFormResult {
  data: VariantInput;
  initialQuantity: number;
  lowStockThreshold: number;
}

// Size / colour / price / scheduled sale for one variant.
function VariantForm({ variant, busy, onSubmit, onCancel }: { variant: Variant | null; busy: boolean; onSubmit: (r: VariantFormResult) => void; onCancel: () => void }) {
  const [sku, setSku] = useState(variant?.sku ?? "");
  const [name, setName] = useState(variant?.name ?? "");
  const [price, setPrice] = useState(variant?.price ?? "");
  const [status, setStatus] = useState<CatalogueStatus>(variant?.status ?? "ACTIVE");
  const [size, setSize] = useState(variant?.options.Size ?? "");
  const [colour, setColour] = useState(variant?.options.Color ?? "");
  const [salePrice, setSalePrice] = useState(variant?.sale_price ?? "");
  const [saleStart, setSaleStart] = useState(isoToLocalInput(variant?.sale_starts_at ?? null));
  const [saleEnd, setSaleEnd] = useState(isoToLocalInput(variant?.sale_ends_at ?? null));
  const [qty, setQty] = useState("0");
  const [threshold, setThreshold] = useState("5");
  const [attempted, setAttempted] = useState(false);
  const validate = () => {
    const problems: Record<string, string> = {};
    if (!sku.trim()) problems.sku = "SKU is required.";
    if (!(Number(price) > 0)) problems.price = "Price must be greater than 0.";
    if (salePrice && !(Number(salePrice) > 0 && Number(salePrice) < Number(price))) problems.salePrice = "Sale price must be above 0 and below the regular price.";
    if (!salePrice && (saleStart || saleEnd)) problems.salePrice = "Set a sale price for the scheduled sale.";
    if (saleStart && saleEnd && new Date(saleEnd) <= new Date(saleStart)) problems.saleEnd = "Sale end must be after sale start.";
    if (!variant && (!Number.isInteger(Number(qty)) || Number(qty) < 0)) problems.qty = "Opening stock must be 0 or more.";
    if (!variant && (!Number.isInteger(Number(threshold)) || Number(threshold) < 0)) problems.threshold = "Alert level must be 0 or more.";
    return problems;
  };
  const fieldErrors = attempted ? validate() : {};

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (Object.keys(validate()).length) return;
    setAttempted(false);
    const options = [
      ...(size.trim() ? [{ name: "Size", value: size.trim() }] : []),
      ...(colour.trim() ? [{ name: "Color", value: colour.trim() }] : []),
    ];
    onSubmit({
      data: {
        sku: sku.trim().toUpperCase(),
        name: name.trim() || options.map((o) => o.value).join(" / ") || "Standard",
        price,
        status,
        options,
        sale_price: emptyToNull(salePrice),
        sale_starts_at: salePrice ? localInputToIso(saleStart) : null,
        sale_ends_at: salePrice ? localInputToIso(saleEnd) : null,
      },
      initialQuantity: Number(qty),
      lowStockThreshold: Number(threshold),
    });
  };

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="form-grid">
        <Field label="SKU" required error={fieldErrors.sku}><input value={sku} onChange={(e) => setSku(e.target.value)} /></Field>
        <Field label="Size"><input value={size} onChange={(e) => setSize(e.target.value)} placeholder="S, M, L, Free size…" /></Field>
        <Field label="Colour"><input value={colour} onChange={(e) => setColour(e.target.value)} /></Field>
        <Field label="Display name" hint="Blank = size / colour"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Price (₹)" required error={fieldErrors.price}><input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value as CatalogueStatus)}>
            {CATALOGUE_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Sale price (₹)" required={!!(saleStart || saleEnd)} error={fieldErrors.salePrice} hint="Blank = no sale"><input type="number" min="0" step="0.01" value={salePrice} onChange={(e) => setSalePrice(e.target.value)} /></Field>
        <Field label="Sale starts" hint="Blank = now"><input type="datetime-local" value={saleStart} onChange={(e) => setSaleStart(e.target.value)} /></Field>
        <Field label="Sale ends" error={fieldErrors.saleEnd} hint="Blank = until removed"><input type="datetime-local" value={saleEnd} onChange={(e) => setSaleEnd(e.target.value)} /></Field>
        {!variant && (
          <>
            <Field label="Opening stock" required error={fieldErrors.qty}><input type="number" min="0" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
            <Field label="Low-stock alert at" required error={fieldErrors.threshold}><input type="number" min="0" value={threshold} onChange={(e) => setThreshold(e.target.value)} /></Field>
          </>
        )}
      </div>
      {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button className="primary" disabled={busy}>{variant ? "Save variant" : "Add variant"}</button>
      </div>
    </form>
  );
}

export default VariantForm;
