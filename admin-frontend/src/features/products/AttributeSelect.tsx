import { useRef, useState } from "react";
import type { AttributeValue } from "../../types/catalogue";

// Pick a fabric/occasion/sleeve/neckline value from the store's managed list.
// A value saved before the list existed stays selectable (marked "not in list").
function AttributeSelect({
  label,
  value,
  options,
  onChange,
  existingValues = options,
  onCreate,
}: {
  label: string;
  value: string;
  options: AttributeValue[];
  onChange: (value: string) => void;
  existingValues?: AttributeValue[];
  onCreate?: (value: string) => Promise<string>;
}) {
  const known = options.some((o) => o.value.toLowerCase() === value.toLowerCase());
  const [adding, setAdding] = useState(false);
  const [newValue, setNewValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const save = async () => {
    if (!onCreate || submitting.current) return;
    const trimmed = newValue.trim();
    if (!trimmed) return setError(`${label[0].toUpperCase()}${label.slice(1)} name is required.`);
    const duplicate = existingValues.find((item) => item.value.toLocaleLowerCase() === trimmed.toLocaleLowerCase());
    if (duplicate) return setError(duplicate.is_active ? "This value already exists." : "This value already exists but is switched off. Enable it in Categories → Filter values.");
    submitting.current = true;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const created = await onCreate(trimmed);
      onChange(created);
      setNewValue("");
      setAdding(false);
      setMessage(`Added ${created}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add value.");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };
  return (
    <div className="attribute-picker">
    <select aria-label={label} value={known ? options.find((o) => o.value.toLowerCase() === value.toLowerCase())!.value : value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Not set</option>
      {value && !known && <option value={value}>{value} (not in list)</option>}
      {options.map((o) => (
        <option key={o.id} value={o.value}>
          {o.value}
        </option>
      ))}
    </select>
    {onCreate && (adding ? <div className="attribute-picker-add">
      <input aria-label={`New ${label} name`} value={newValue} maxLength={100} disabled={busy} aria-invalid={!!error} onChange={(event) => { setNewValue(event.target.value); setError(null); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void save(); } }} placeholder={`New ${label} name`} />
      <button type="button" className="primary" disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save"}</button>
      <button type="button" disabled={busy} onClick={() => { setAdding(false); setNewValue(""); setError(null); }}>Cancel</button>
    </div> : <button type="button" className="link attribute-picker-trigger" onClick={() => { setAdding(true); setError(null); setMessage(null); }}>+ Add new {label}</button>)}
    {error && <small className="field-error" role="alert">{error}</small>}
    {message && <small className="attribute-picker-success" role="status">{message}</small>}
    </div>
  );
}

export default AttributeSelect;
