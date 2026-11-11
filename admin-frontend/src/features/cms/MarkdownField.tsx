import { useState } from "react";
import Field from "../../components/common/Field";
import MarkdownPreview from "../../components/common/MarkdownPreview";

/** Write/Preview toggle over a Markdown text area. */
function MarkdownField({ label, value, onChange, rows, startInPreview = false }: { label: string; value: string; onChange: (value: string) => void; rows: number; startInPreview?: boolean }) {
  const [preview, setPreview] = useState(startInPreview);
  return (
    <>
      <div className="toolbar">
        <button type="button" className={preview ? "" : "primary"} onClick={() => setPreview(false)}>Write</button>
        <button type="button" className={preview ? "primary" : ""} onClick={() => setPreview(true)}>Preview</button>
      </div>
      {preview ? (
        <MarkdownPreview source={value} />
      ) : (
        <Field label={label} hint="Tip: ## makes a heading, - starts a bullet, **bold**, [link text](/faq)" wide>
          <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows} aria-label={label} />
        </Field>
      )}
    </>
  );
}

export default MarkdownField;
