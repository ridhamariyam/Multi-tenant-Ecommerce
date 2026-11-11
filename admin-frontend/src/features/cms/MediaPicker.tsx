import { useId, useState } from "react";
import { listMedia, uploadMedia } from "../../api/cms";
import { mediaUrl } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Modal from "../../components/common/Modal";
import ImageUploadPicker from "../../components/common/ImageUploadPicker";
import { useApi } from "../../hooks/useApi";
import { checkImageFile, IMAGE_ACCEPT } from "./mediaRules";

/**
 * An image field: upload a picture from the computer or pick one already in
 * the media library. Uploads go into the media library too, so they can be
 * reused. A URL can still be pasted for images hosted elsewhere.
 */
function MediaPicker({
  value,
  onChange,
  label = "Image",
  required = false,
  validationError,
  hint,
  onUploadingChange,
}: {
  value: string;
  onChange: (url: string) => void;
  label?: string;
  required?: boolean;
  validationError?: string | null;
  hint?: string;
  /** Lets the form hold its Save button until the picture has finished uploading. */
  onUploadingChange?: (uploading: boolean) => void;
}) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();

  const upload = async (file: File | undefined) => {
    if (!file) return;
    const problem = checkImageFile(file);
    if (problem) return setError(problem);
    setBusy(true);
    onUploadingChange?.(true);
    setError(null);
    try {
      const media = await uploadMedia(file, null);
      onChange(media.data.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      onUploadingChange?.(false);
    }
  };

  return (
    <div className="field media-field">
      <label className="field-label" htmlFor={inputId}>
        {label}{required && <span className="required" aria-hidden="true"> *</span>}
      </label>
      {value ? (
        <img className="preview" src={mediaUrl(value)} alt="" />
      ) : (
        <div className="empty-state" style={{ padding: 16 }}>No image chosen yet</div>
      )}
      <div className="toolbar">
        {can(P.cmsManage) && (
          <ImageUploadPicker inputLabel={`Upload ${label}`} buttonLabel={busy ? "Uploading…" : "Upload image"} accept={IMAGE_ACCEPT} disabled={busy} onFiles={(files) => void upload(files[0])} />
        )}
        <button type="button" onClick={() => setOpen(true)}>Choose from library</button>
        {value && <button type="button" className="link" onClick={() => onChange("")}>Remove</button>}
      </div>
      {can(P.cmsManage) && <span className="field-hint">JPEG, PNG or WebP, up to 5 MB.</span>}
      <details>
        <summary className="field-hint">…or paste an image link</summary>
        <input id={inputId} value={value} onChange={(e) => onChange(e.target.value)} placeholder="/media/… or https://…" aria-required={required} aria-invalid={!!validationError || undefined} aria-describedby={validationError ? `${inputId}-error` : undefined} />
      </details>
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="status status-error">{error}</span>}
      {validationError && <span id={`${inputId}-error`} className="field-error" role="alert">{validationError}</span>}
      {open && <PickerModal onClose={() => setOpen(false)} onPick={(url) => { onChange(url); setOpen(false); }} />}
    </div>
  );
}

function PickerModal({ onClose, onPick }: { onClose: () => void; onPick: (url: string) => void }) {
  const media = useApi(() => listMedia({ page_size: 100 }), []);
  return (
    <Modal title="Choose an image" onClose={onClose} wide>
      {media.error && <div className="status status-error">{media.error}</div>}
      {media.loading && !media.data && <div className="state">Loading…</div>}
      {media.data?.length === 0 && (
        <div className="empty-state">
          <h4>Your media library is empty</h4>
          Close this and use “Upload image” — uploads are saved here for next time.
        </div>
      )}
      <div className="image-grid">
        {media.data?.map((m) => (
          <button type="button" key={m.id} className="image-card" onClick={() => onPick(m.url)} aria-label={`Use ${m.alt_text || m.filename}`}>
            <img src={mediaUrl(m.url)} alt={m.alt_text ?? ""} />
            <span>{m.alt_text || m.filename}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

export default MediaPicker;
