import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { CategoryInput } from "../../api/categories";
import Field from "../../components/common/Field";
import type { CatalogueStatus } from "../../types/api";
import type { Category } from "../../types/catalogue";
import { emptyToNull } from "../../utils/formatters";

function CategoryForm({
  category,
  parents,
  busy,
  onSubmit,
  onCancel,
  onDirtyChange,
}: {
  category: Category | null;
  parents: Category[];
  busy: boolean;
  onSubmit: (data: CategoryInput) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [name, setName] = useState(category?.name ?? "");
  const [description, setDescription] = useState(category?.description ?? "");
  const [parentId, setParentId] = useState(category?.parent_id ?? "");
  const [status, setStatus] = useState<CatalogueStatus>(category?.status ?? "ACTIVE");
  const [hsn, setHsn] = useState(category?.hsn_code ?? "");
  const [gst, setGst] = useState(category?.gst_rate ?? "");
  const [attempted, setAttempted] = useState(false);
  const signature = JSON.stringify({ name, description, parentId, status, hsn, gst });
  const [baseline] = useState(signature);
  useEffect(() => onDirtyChange(signature !== baseline), [signature, baseline, onDirtyChange]);
  const validate = () => {
    const problems: Record<string, string> = {};
    if (!name.trim()) problems.name = "Category name is required.";
    if (hsn && !/^\d{4}(\d{2}){0,2}$/.test(hsn.trim())) problems.hsn = "HSN code must be 4, 6 or 8 digits.";
    if (gst && !(Number(gst) >= 0 && Number(gst) <= 100)) problems.gst = "GST rate must be between 0 and 100.";
    return problems;
  };
  const fieldErrors = attempted ? validate() : {};

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (Object.keys(validate()).length) {
      setTimeout(() => (e.target as HTMLFormElement).querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    setAttempted(false);
    onSubmit({
      name: name.trim(),
      description: emptyToNull(description),
      ...(!category || parentId !== (category.parent_id ?? "") ? { parent_id: parentId || null } : {}),
      status,
      hsn_code: emptyToNull(hsn),
      gst_rate: emptyToNull(gst),
    });
  };

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="form-grid">
        <Field label="Name" required error={fieldErrors.name} guidance="Name this category as customers should see it." guidanceDismissible><input value={name} onChange={(e) => setName(e.target.value)} maxLength={150} /></Field>
        <Field label="Parent category" hint="Leave empty for a top-level category">
          <select value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">— Top level —</option>
            {parents.filter((p) => p.id !== category?.id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select value={status} disabled={category?.status === "ARCHIVED"} onChange={(e) => setStatus(e.target.value as CatalogueStatus)}>
            <option value="ACTIVE">Active</option>
            <option value="DRAFT">Draft</option>
            {category?.status === "ARCHIVED" && <option value="ARCHIVED">Archived</option>}
          </select>
        </Field>
        <Field label="Legacy HSN code" error={fieldErrors.hsn} hint="Checkout uses confirmed mappings in Tax & GST Settings."><input value={hsn} onChange={(e) => setHsn(e.target.value)} /></Field>
        <Field label="Legacy GST rate (%)" error={fieldErrors.gst} hint="Checkout uses confirmed mappings in Tax & GST Settings."><input type="number" min="0" max="100" step="0.01" value={gst} onChange={(e) => setGst(e.target.value)} /></Field>
        <Field label="Description" wide><textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      </div>
      {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button className="primary" disabled={busy}>{category ? "Save" : "Create category"}</button>
      </div>
    </form>
  );
}

export default CategoryForm;
