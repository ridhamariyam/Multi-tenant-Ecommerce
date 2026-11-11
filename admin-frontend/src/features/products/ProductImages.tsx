import { useEffect, useState } from "react";
import { addImageUrl, deleteImage, listImages, makePrimary, reorderImages, uploadImage } from "../../api/images";
import ConfirmButton from "../../components/common/ConfirmButton";
import ImageUploadPicker from "../../components/common/ImageUploadPicker";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { emptyToNull } from "../../utils/formatters";
import ProductImage from "./ProductImage";

const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 5 * 1024 * 1024;

function ProductImages({ productId, canManage }: { productId: string; canManage: boolean }) {
  const images = useApi(() => listImages(productId), [productId]);
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [alt, setAlt] = useState("");
  const list = images.data ?? [];

  useEffect(() => () => { if (previewUrl && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const move = (index: number, delta: number) => {
    const next = [...list];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    action.run(async () => { await reorderImages(productId, next.map((img, i) => ({ id: img.id, sort_order: i }))); images.reload(); }, null, "Could not reorder");
  };

  const upload = () => {
    if (!file) return;
    if (!ALLOWED.includes(file.type)) return action.setStatus({ type: "error", text: "Only JPEG, PNG or WebP images." });
    if (file.size > MAX_BYTES) return action.setStatus({ type: "error", text: "Image must be 5 MB or smaller." });
    action.run(async () => { await uploadImage(productId, file, emptyToNull(alt)); setFile(null); setPreviewUrl(null); setAlt(""); images.reload(); }, "Image uploaded", "Upload failed");
  };
  const chooseImage = (chosen: File[]) => {
    const next = chosen[0];
    if (!next) return;
    if (!ALLOWED.includes(next.type)) return action.setStatus({ type: "error", text: "Only JPEG, PNG or WebP images." });
    if (next.size > MAX_BYTES) return action.setStatus({ type: "error", text: "Image must be 5 MB or smaller." });
    setFile(next);
    setPreviewUrl(typeof URL.createObjectURL === "function" ? URL.createObjectURL(next) : null);
    action.setStatus(null);
  };

  return (
    <div className="panel">
      <StatusMessage status={action.status} />
      {images.error && <div className="status status-error">{images.error}</div>}
      <div className="image-grid">
        {list.map((img, i) => (
          <div className="image-card" key={img.id}>
            <ProductImage url={img.url} alt={img.alt_text ?? ""} />
            {img.is_primary ? <strong>Main image</strong> : canManage && <button className="link" onClick={() => action.run(async () => { await makePrimary(img.id); images.reload(); }, "Main image set", "Could not set main image")}>Make main</button>}
            {canManage && (
              <div className="toolbar">
                <button disabled={i === 0 || action.busy} onClick={() => move(i, -1)} aria-label="Move left">←</button>
                <button disabled={i === list.length - 1 || action.busy} onClick={() => move(i, 1)} aria-label="Move right">→</button>
                <ConfirmButton message="Delete this image?" onConfirm={() => action.run(async () => { await deleteImage(img.id); images.reload(); }, "Image deleted", "Could not delete image")}>✕</ConfirmButton>
              </div>
            )}
          </div>
        ))}
        {list.length === 0 && !images.loading && <p className="muted">No images.</p>}
      </div>
      {canManage && (
        <div className="grid-2" style={{ marginTop: 16 }}>
          <div className="form">
            <h4>Upload</h4>
            <ImageUploadPicker inputLabel="Image file" buttonLabel="Upload image" accept={ALLOWED.join(",")} onFiles={chooseImage} disabled={action.busy} />
            <small className="muted">JPEG, PNG or WebP, up to 5 MB.</small>
            {previewUrl && <div className="product-upload-preview"><ProductImage url={previewUrl} alt="Selected image preview" /></div>}
            {file && <button type="button" className="link" onClick={() => { setFile(null); setPreviewUrl(null); }}>Remove selected image</button>}
            <input placeholder="Alt text (describe the image)" value={alt} onChange={(e) => setAlt(e.target.value)} />
            <button disabled={!file || action.busy} onClick={upload}>Upload image</button>
          </div>
          <form className="form" onSubmit={(e) => { e.preventDefault(); if (!/^(https?:\/\/|\/)/.test(url.trim())) return action.setStatus({ type: "error", text: "Enter an https:// or /media/ URL." }); action.run(async () => { await addImageUrl(productId, url.trim(), emptyToNull(alt)); setUrl(""); images.reload(); }, "Image added", "Could not add image"); }}>
            <h4>Add by URL</h4>
            <input placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
            <button disabled={!url.trim() || action.busy}>Add image</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default ProductImages;
