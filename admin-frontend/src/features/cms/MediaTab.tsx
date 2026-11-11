import { useEffect, useState } from "react";
import { deleteMedia, listMedia, updateMedia, uploadMedia } from "../../api/cms";
import Modal from "../../components/common/Modal";
import type { Media } from "../../types/cms";
import { mediaUrl } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import GuidedControl from "../../components/guidance/GuidedControl";
import ImageUploadPicker from "../../components/common/ImageUploadPicker";
import { P } from "../../auth/permissions";
import ConfirmButton from "../../components/common/ConfirmButton";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { emptyToNull } from "../../utils/formatters";

const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 5 * 1024 * 1024;

// Files are stored by the backend's storage service, never in the database.
function MediaTab() {
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const media = useApi(() => listMedia({ page, page_size: 40 }), [page]);
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [alt, setAlt] = useState("");
  const [describing, setDescribing] = useState<Media | null>(null);
  const [description, setDescription] = useState("");
  useEffect(() => () => { if (previewUrl && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const chooseImage = (chosen: File[]) => {
    const next = chosen[0];
    if (!next) return;
    if (!ALLOWED.includes(next.type)) return action.setStatus({ type: "error", text: "Only JPEG, PNG or WebP images." });
    if (next.size > MAX_BYTES) return action.setStatus({ type: "error", text: "Images must be 5 MB or smaller." });
    setFile(next);
    setPreviewUrl(typeof URL.createObjectURL === "function" ? URL.createObjectURL(next) : null);
    action.setStatus(null);
  };

  const upload = () => {
    if (!file) return;
    if (!ALLOWED.includes(file.type)) return action.setStatus({ type: "error", text: "Only JPEG, PNG or WebP images." });
    if (file.size > MAX_BYTES) return action.setStatus({ type: "error", text: "Images must be 5 MB or smaller." });
    action.run(async () => { await uploadMedia(file, emptyToNull(alt)); setFile(null); setPreviewUrl(null); setAlt(""); media.reload(); }, "Uploaded", "Upload failed");
  };

  return (
    <div className="panel">
      <StatusMessage status={action.status} />
      {can(P.cmsManage) && (
        <div className="filters">
          <GuidedControl className="guided-control--wide" hint="Choose an image to reuse in website content." dismissible><ImageUploadPicker inputLabel="Image file" buttonLabel="Upload image" accept={ALLOWED.join(",")} onFiles={chooseImage} disabled={action.busy} /></GuidedControl>
          <GuidedControl hint="Describe the image for screen readers."><input placeholder="Alt text" value={alt} onChange={(e) => setAlt(e.target.value)} /></GuidedControl>
          <button className="primary" disabled={!file || action.busy} onClick={upload}>Upload</button>
        </div>
      )}
      {file && <div className="media-selected-image"><span>{previewUrl ? <img src={previewUrl} alt="Selected image preview" /> : file.name}</span><button type="button" className="link" onClick={() => { setFile(null); setPreviewUrl(null); }}>Remove selected image</button><small className="muted">JPEG, PNG or WebP, up to 5 MB.</small></div>}
      {media.error && <div className="status status-error">{media.error}</div>}
      <p className="help">Pictures you upload here (or from any image field) can be reused anywhere on the website. A picture that is in use can't be deleted.</p>
      {media.data?.length === 0 && (
        <div className="empty-state"><h4>No pictures yet</h4>Upload your first picture above.</div>
      )}
      <div className="image-grid">
        {media.data?.map((m) => (
          <div className="image-card" key={m.id}>
            <img src={mediaUrl(m.url)} alt={m.alt_text ?? ""} />
            <span title={m.url}>{m.filename}</span>
            <small className="muted">{Math.round(m.size_bytes / 1024)} KB</small>
            <button className="link" onClick={() => navigator.clipboard?.writeText(m.url)}>Copy URL</button>
            {can(P.cmsManage) && (
              <button className="link" onClick={() => { setDescribing(m); setDescription(m.alt_text ?? ""); }}>Edit description</button>
            )}
            {can(P.cmsManage) && (
              <ConfirmButton
                className="link"
                title="Delete this picture?"
                message="It will be removed from your media library. Pictures still used on the website can't be deleted."
                confirmLabel="Delete"
                onConfirm={() => action.run(async () => { await deleteMedia(m.id); media.reload(); }, "Deleted", "Could not delete")}
              >
                Delete
              </ConfirmButton>
            )}
          </div>
        ))}
      </div>
      <Pagination meta={media.meta} onPageChange={setPage} />
      {describing && (
        <Modal title="Picture description" onClose={() => setDescribing(null)} showCloseButton={false}>
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              action.run(async () => { await updateMedia(describing.id, description.trim() || null); setDescribing(null); media.reload(); }, "Description saved", "Could not save");
            }}
          >
            <p className="muted">Describe what's in the picture. Screen readers read it out and Google uses it.</p>
            <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={255} aria-label="Picture description" autoFocus />
            <div className="form-actions"><button type="button" onClick={() => setDescribing(null)}>Cancel</button><button className="primary">Save</button></div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export default MediaTab;
