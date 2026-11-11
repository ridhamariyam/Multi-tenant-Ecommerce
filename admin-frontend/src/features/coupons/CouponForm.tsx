import { useState } from "react";
import type { FormEvent } from "react";
import Field from "../../components/common/Field";
import type { Category } from "../../types/catalogue";
import type { Coupon, CouponInput, DiscountType } from "../../types/coupon";
import { DISCOUNT_TYPES, WEEKDAYS } from "../../types/coupon";
import { label } from "../../utils/formatters";
import { TYPE_HELP, couponFieldErrors, toForm, toPayload } from "./couponRules";
import type { FormState } from "./couponRules";

function CouponForm({
  coupon,
  categories,
  busy,
  onSubmit,
  onCancel,
}: {
  coupon: Coupon | null;
  categories: Category[];
  busy: boolean;
  onSubmit: (payload: CouponInput) => void;
  onCancel: () => void;
}) {
  const isNew = coupon === null;
  const [f, setF] = useState<FormState>(() => toForm(coupon));
  const [attempted, setAttempted] = useState(false);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((prev) => ({ ...prev, [k]: v }));
  const fieldErrors = attempted ? couponFieldErrors(f, isNew) : {};

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (Object.keys(couponFieldErrors(f, isNew)).length) {
      setTimeout(() => (e.target as HTMLFormElement).querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    setAttempted(false);
    onSubmit(toPayload(f, isNew));
  };

  return (
    <form className="form coupon-form" onSubmit={submit} noValidate>
      <div className="coupon-form-content">
      <div className="form-grid">
        <Field label="Code" required={isNew} error={fieldErrors.code} guidance="Customers enter this code at checkout." guidanceDismissible><input value={f.code} disabled={!isNew} onChange={(e) => set("code", e.target.value)} placeholder="DIWALI20" /></Field>
        <Field label="Type" hint={TYPE_HELP[f.discount_type]}>
          <select value={f.discount_type} onChange={(e) => set("discount_type", e.target.value as DiscountType)}>
            {DISCOUNT_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </select>
        </Field>
        {f.discount_type !== "FREE_SHIPPING" && (
          <Field label={f.discount_type === "FIXED_AMOUNT" ? "Amount off (₹)" : "Percent off"} required error={fieldErrors.discount_value}>
            <input type="number" min="0" step="0.01" value={f.discount_value} onChange={(e) => set("discount_value", e.target.value)} />
          </Field>
        )}
        {f.discount_type === "PERCENTAGE" && (
          <Field label="Max discount (₹)" error={fieldErrors.max_discount_amount} hint="Optional cap"><input type="number" min="0" step="0.01" value={f.max_discount_amount} onChange={(e) => set("max_discount_amount", e.target.value)} /></Field>
        )}
        {f.discount_type === "BOGO" && (
          <>
            <Field label="Buy quantity" required error={fieldErrors.buy_quantity}><input type="number" min="1" value={f.buy_quantity} onChange={(e) => set("buy_quantity", e.target.value)} /></Field>
            <Field label="Get quantity" required error={fieldErrors.get_quantity}><input type="number" min="1" value={f.get_quantity} onChange={(e) => set("get_quantity", e.target.value)} /></Field>
          </>
        )}
        <Field label="Minimum order (₹)" error={fieldErrors.min_order_amount}><input type="number" min="0" step="0.01" value={f.min_order_amount} onChange={(e) => set("min_order_amount", e.target.value)} /></Field>
        <Field label="Minimum items (volume discount)" error={fieldErrors.min_quantity}><input type="number" min="1" value={f.min_quantity} onChange={(e) => set("min_quantity", e.target.value)} /></Field>
        <Field label="Starts" error={fieldErrors.starts_at}><input type="datetime-local" value={f.starts_at} onChange={(e) => set("starts_at", e.target.value)} /></Field>
        <Field label="Ends" error={fieldErrors.expires_at}><input type="datetime-local" value={f.expires_at} onChange={(e) => set("expires_at", e.target.value)} /></Field>
        <Field label="Total uses allowed" error={fieldErrors.usage_limit} hint="Blank = unlimited"><input type="number" min="0" value={f.usage_limit} onChange={(e) => set("usage_limit", e.target.value)} /></Field>
        <Field label="Uses per customer" error={fieldErrors.per_customer_usage_limit} hint="Blank = unlimited"><input type="number" min="0" value={f.per_customer_usage_limit} onChange={(e) => set("per_customer_usage_limit", e.target.value)} /></Field>
        <Field label="Only for categories" hint="None selected = whole catalogue" wide>
          <select multiple size={Math.min(6, Math.max(3, categories.length))} value={f.category_ids} onChange={(e) => set("category_ids", Array.from(e.target.selectedOptions, (o) => o.value))}>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
      </div>
      <fieldset className="toolbar" style={{ border: 0, padding: 0 }}>
        <legend className="field-label">Only on these days (shop time) — none ticked = every day</legend>
        {WEEKDAYS.map((day, index) => (
          <label key={day} className="check">
            <input
              type="checkbox"
              checked={f.valid_weekdays.includes(index)}
              onChange={(e) =>
                set("valid_weekdays", e.target.checked ? [...f.valid_weekdays, index] : f.valid_weekdays.filter((d) => d !== index))
              }
            />
            {day}
          </label>
        ))}
      </fieldset>
      <div className="toolbar">
        <label className="check"><input type="checkbox" checked={f.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Active</label>
        <label className="check"><input type="checkbox" checked={f.is_automatic} onChange={(e) => set("is_automatic", e.target.checked)} /> Apply automatically (no code needed)</label>
        <label className="check"><input type="checkbox" checked={f.first_order_only} onChange={(e) => set("first_order_only", e.target.checked)} /> First order only</label>
      </div>
      </div>
      <div className="coupon-form-footer">
      {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button className="primary" disabled={busy}>{isNew ? "Create coupon" : "Save coupon"}</button>
      </div>
      </div>
    </form>
  );
}

export default CouponForm;
