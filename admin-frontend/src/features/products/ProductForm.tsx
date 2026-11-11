import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../../auth/AuthContext";
import Field from "../../components/common/Field";
import ImageUploadPicker from "../../components/common/ImageUploadPicker";
import type { AttributeValue, Category, Product, ProductFields } from "../../types/catalogue";
import { createAttributeValue, listAttributeValues } from "../../api/products";
import { useApi } from "../../hooks/useApi";
import type { AttributeName } from "../../types/catalogue";
import { emptyToNull } from "../../utils/formatters";
import { slugProblem } from "../../utils/slug";
import AttributeSelect from "./AttributeSelect";
import { IMAGE_TYPES, MAX_IMAGE_BYTES, checkNewImages } from "./newImages";
import type { NewImages } from "./newImages";
import { chartFrom, chartPayload } from "./sizeChart";
import type { ChartState } from "./sizeChart";
import ProductImage from "./ProductImage";
import { productDraftKey } from "./productDraft";

type Text = Record<
  | "name" | "short_description" | "description" | "brand" | "fabric" | "occasion" | "sleeve" | "neckline"
  | "fabric_details" | "washing_instructions" | "country_of_origin" | "hsn_code" | "gst_rate" | "seo_title" | "seo_description",
  string
>;

type UnsavedProduct = { text: Text; categoryId: string; featured: boolean; slug: string; chart: ChartState };
type SelectedImage = { id: number; file: File; preview: string };
function readUnsavedProduct(key: string): UnsavedProduct | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) as UnsavedProduct : null;
  } catch { return null; }
}

function ProductForm({
  product,
  categories,
  busy,
  requireImage,
  onSubmit,
  onCancel,
  onDirtyChange,
}: {
  product: Product | null;
  categories: Category[];
  busy: boolean;
  requireImage: boolean;
  onSubmit: (fields: ProductFields, newImages: NewImages | null) => Promise<boolean>;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const { user } = useAuth();
  const draftKey = productDraftKey(user?.tenant_id ?? "", user?.id ?? "");
  const [savedDraft] = useState(() => product ? null : readUnsavedProduct(draftKey));
  const [text, setText] = useState<Text>(() => {
    const keys: (keyof Text)[] = ["name", "short_description", "description", "brand", "fabric", "occasion", "sleeve", "neckline", "fabric_details", "washing_instructions", "country_of_origin", "hsn_code", "gst_rate", "seo_title", "seo_description"];
    return Object.fromEntries(keys.map((k) => [k, product ? ((product[k] as string | null) ?? "") : (savedDraft?.text[k] ?? "")])) as Text;
  });
  const [categoryId, setCategoryId] = useState(product?.category_id ?? savedDraft?.categoryId ?? "");
  const [featured, setFeatured] = useState(product?.is_featured ?? savedDraft?.featured ?? false);
  const [selectedImages, setSelectedImages] = useState<SelectedImage[]>([]);
  const [imageSelectionError, setImageSelectionError] = useState<string | null>(null);
  const previewUrls = useRef<string[]>([]);
  const nextImageId = useRef(0);
  const files = selectedImages.map((image) => image.file);
  const [slug, setSlug] = useState(product?.slug ?? savedDraft?.slug ?? "");
  const attributes = useApi(() => listAttributeValues(), []);
  const [createdOptions, setCreatedOptions] = useState<AttributeValue[]>([]);
  const allOptions = [...(attributes.data ?? []), ...createdOptions.filter((created) => !(attributes.data ?? []).some((item) => item.id === created.id))];
  const optionsFor = (name: AttributeName) => allOptions.filter((item) => item.attribute === name && item.is_active);
  const existingFor = (name: AttributeName) => allOptions.filter((item) => item.attribute === name);
  const createValue = async (name: AttributeName, value: string) => {
    const created = (await createAttributeValue(name, value)).data;
    setCreatedOptions((current) => [...current, created]);
    attributes.reload();
    return created.value;
  };
  const [chart, setChart] = useState<ChartState>(() => savedDraft?.chart ?? chartFrom(product));
  const [error, setError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  useEffect(() => () => { if (typeof URL.revokeObjectURL === "function") previewUrls.current.forEach((url) => URL.revokeObjectURL(url)); }, []);
  const signature = JSON.stringify({ text, categoryId, featured, files: files.map((file) => [file.name, file.size, file.lastModified]), slug, chart });
  const [baseline, setBaseline] = useState(signature);
  const dirty = signature !== baseline || (!!savedDraft && !product);

  useEffect(() => {
    if (product || submitted || !dirty) return;
    try { sessionStorage.setItem(draftKey, JSON.stringify({ text, categoryId, featured, slug, chart } satisfies UnsavedProduct)); } catch { /* Storage can be unavailable. */ }
  }, [product, submitted, dirty, draftKey, text, categoryId, featured, slug, chart]);

  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);

  const t = (k: keyof Text) => ({ value: text[k], onChange: (e: { target: { value: string } }) => setText({ ...text, [k]: e.target.value }) });
  const validate = () => {
    const problems: Record<string, string> = {};
    if (!text.name.trim()) problems.name = "Product name is required.";
    if (!categoryId) problems.category = "Choose a category.";
    if (requireImage) {
      const imageProblem = imageSelectionError ?? checkNewImages(files);
      if (imageProblem) problems.photos = imageProblem;
    }
    const slugError = slugProblem(slug);
    if (slugError) problems.slug = slugError;
    if (text.hsn_code && !/^\d{4}(\d{2}){0,2}$/.test(text.hsn_code.trim())) problems.hsn = "HSN code must be 4, 6 or 8 digits.";
    if (text.gst_rate.trim() && !(Number(text.gst_rate) >= 0 && Number(text.gst_rate) <= 100)) problems.gst = "GST rate must be between 0 and 100.";
    return problems;
  };
  const fieldErrors = attempted ? validate() : {};

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (Object.keys(validate()).length) {
      setTimeout(() => (e.target as HTMLFormElement).querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    const { chart: sizeChart, error: chartError } = chartPayload(chart);
    if (chartError) return setError(chartError);
    setError(null);
    setAttempted(false);
    const fields: ProductFields = {
      category_id: categoryId,
      name: text.name.trim(),
      short_description: emptyToNull(text.short_description),
      description: emptyToNull(text.description),
      brand: emptyToNull(text.brand),
      status: product?.status ?? "DRAFT",
      gender: product?.gender ?? null,
      fabric: emptyToNull(text.fabric),
      occasion: emptyToNull(text.occasion),
      sleeve: emptyToNull(text.sleeve),
      neckline: emptyToNull(text.neckline),
      fabric_details: emptyToNull(text.fabric_details),
      washing_instructions: emptyToNull(text.washing_instructions),
      country_of_origin: emptyToNull(text.country_of_origin),
      size_chart: sizeChart,
      hsn_code: emptyToNull(text.hsn_code),
      gst_rate: emptyToNull(text.gst_rate),
      is_featured: featured,
      seo_title: emptyToNull(text.seo_title),
      seo_description: emptyToNull(text.seo_description),
      ...(slug ? { slug } : {}),
    };
    const saved = await onSubmit(fields, requireImage ? { files } : null);
    if (saved) {
      if (!product) {
        sessionStorage.removeItem(draftKey);
        setSubmitted(true);
      }
      setBaseline(signature);
      onDirtyChange(false);
    }
  };

  const setRowValue = (i: number, m: string, v: string) =>
    setChart({ ...chart, rows: chart.rows.map((r, idx) => (idx === i ? { ...r, values: { ...r.values, [m]: v } } : r)) });
  const selectImages = (chosen: File[]) => {
    const wrongType = chosen.find((file) => !IMAGE_TYPES.includes(file.type));
    const tooBig = chosen.find((file) => file.size > MAX_IMAGE_BYTES);
    if (wrongType || tooBig) return setImageSelectionError(checkNewImages(chosen));
    setImageSelectionError(null);
    const additions = chosen.map((file) => {
      const preview = typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : "";
      if (preview) previewUrls.current.push(preview);
      return { id: nextImageId.current++, file, preview };
    });
    setSelectedImages((current) => [...current, ...additions]);
  };
  const removeImage = (id: number) => {
    setSelectedImages((current) => current.filter((image) => image.id !== id));
    setImageSelectionError(null);
  };
  const moveImage = (index: number, delta: number) => {
    setSelectedImages((current) => {
      const next = [...current];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    });
  };

  return (
    <form className="form product-form" onSubmit={submit} noValidate>
      <div className="panel">
        <h3>Basics</h3>
        <div className="form-grid">
          <Field label="Name" required error={fieldErrors.name} guidance="Enter the product name customers will see." guidanceDismissible><input {...t("name")} maxLength={255} /></Field>
          <Field label="Category" required error={fieldErrors.category} guidance="Choose where this product appears in the catalogue.">
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Choose…</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.parent_id ? `↳ ${c.name}` : c.name}</option>)}
            </select>
          </Field>
          <Field label="Brand"><input {...t("brand")} /></Field>
          <Field label="URL slug" error={fieldErrors.slug} hint={product ? `/products/${product.slug}` : "Blank = made from the name"}>
            <input value={slug} onChange={(e) => setSlug(e.target.value.trim())} placeholder="cotton-kurta-navy" />
          </Field>
          {requireImage && (
            <>
              <Field label="Photos" required error={imageSelectionError ?? fieldErrors.photos} hint="JPEG, PNG or WebP, up to 5 MB each. The first photo is the main image.">
                <ImageUploadPicker inputLabel="Product photos" buttonLabel="Upload images" accept={IMAGE_TYPES.join(",")} multiple onFiles={selectImages} />
              </Field>
              {selectedImages.length > 0 && <div className="product-new-previews field-wide" aria-label="Selected product images">
                {selectedImages.map((image, index) => <div key={image.id} className="product-new-preview">
                  {image.preview ? <ProductImage url={image.preview} alt={`Selected photo ${index + 1}`} /> : <span>{image.file.name}</span>}
                  <span>{index === 0 ? "Primary image" : `Image ${index + 1}`}</span>
                  <div className="toolbar">
                    <button type="button" disabled={index === 0} onClick={() => moveImage(index, -1)} aria-label={`Move ${image.file.name} left`}>←</button>
                    <button type="button" disabled={index === selectedImages.length - 1} onClick={() => moveImage(index, 1)} aria-label={`Move ${image.file.name} right`}>→</button>
                    <button type="button" onClick={() => removeImage(image.id)} aria-label={`Remove ${image.file.name}`}>Remove</button>
                  </div>
                </div>)}
              </div>}
            </>
          )}
          <Field label="Short description" wide><input {...t("short_description")} maxLength={500} /></Field>
          <Field label="Description" wide><textarea className="product-description" {...t("description")} /></Field>
        </div>
        <label className="check" style={{ marginTop: 8 }}><input type="checkbox" checked={featured} onChange={(e) => setFeatured(e.target.checked)} /> Featured product</label>
      </div>

      <div className="panel">
        <h3>Fabric &amp; care</h3>
        <div className="form-grid">
          {(["fabric", "occasion", "sleeve", "neckline"] as const).map((name) => (
            <Field key={name} label={name[0].toUpperCase() + name.slice(1)}>
              <AttributeSelect label={name} value={text[name]} options={optionsFor(name)} existingValues={existingFor(name)} onCreate={(value) => createValue(name, value)} onChange={(value) => setText((current) => ({ ...current, [name]: value }))} />
            </Field>
          ))}
          <Field label="Country of origin"><input {...t("country_of_origin")} /></Field>
          <Field label="Fabric details" wide><textarea {...t("fabric_details")} /></Field>
          <Field label="Washing instructions" wide><textarea {...t("washing_instructions")} /></Field>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <h3>Size chart</h3>
          <label className="check"><input type="checkbox" checked={chart.enabled} onChange={(e) => setChart({ ...chart, enabled: e.target.checked })} /> This product has a size chart</label>
        </div>
        {chart.enabled && (
          <>
            <div className="filters">
              <Field label="Unit">
                <select value={chart.unit} onChange={(e) => setChart({ ...chart, unit: e.target.value as "in" | "cm" })}>
                  <option value="in">inches</option>
                  <option value="cm">cm</option>
                </select>
              </Field>
              <Field label="Measurements (comma separated)">
                <input value={chart.measurements.join(", ")} onChange={(e) => setChart({ ...chart, measurements: e.target.value.split(",").map((m) => m.trimStart()) })} />
              </Field>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Size</th>
                    {chart.measurements.filter((m) => m.trim()).map((m) => <th key={m}>{m.trim()}</th>)}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {chart.rows.map((row, i) => (
                    <tr key={i}>
                      <td><input aria-label="Size" value={row.size} onChange={(e) => setChart({ ...chart, rows: chart.rows.map((r, idx) => (idx === i ? { ...r, size: e.target.value } : r)) })} /></td>
                      {chart.measurements.filter((m) => m.trim()).map((m) => (
                        <td key={m}><input aria-label={`${row.size} ${m}`} type="number" step="0.1" min="0" value={row.values[m.trim()] ?? ""} onChange={(e) => setRowValue(i, m.trim(), e.target.value)} /></td>
                      ))}
                      <td><button type="button" className="danger" onClick={() => setChart({ ...chart, rows: chart.rows.filter((_, idx) => idx !== i) })}>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="toolbar" style={{ marginTop: 8 }}>
              <button type="button" onClick={() => setChart({ ...chart, rows: [...chart.rows, { size: "", values: {} }] })}>Add size</button>
            </div>
            <Field label="Note"><input value={chart.note} onChange={(e) => setChart({ ...chart, note: e.target.value })} maxLength={500} /></Field>
          </>
        )}
      </div>

      <div className="panel">
        <h3>Tax &amp; SEO</h3>
        <div className="form-grid">
          <Field label="Legacy HSN code" error={fieldErrors.hsn} hint="Checkout uses confirmed mappings in Tax & GST Settings."><input {...t("hsn_code")} /></Field>
          <Field label="Legacy GST rate (%)" error={fieldErrors.gst} hint="Checkout uses confirmed mappings in Tax & GST Settings." guidance="Set active tax mappings in Tax & GST Settings."><input type="number" min="0" max="100" step="0.01" {...t("gst_rate")} /></Field>
          <Field label="SEO title"><input {...t("seo_title")} /></Field>
          <Field label="SEO description" wide><textarea {...t("seo_description")} /></Field>
        </div>
      </div>

      {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
      {error && <div className="status status-error" role="alert">{error}</div>}
      <div className="form-actions product-form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button className="primary" disabled={busy || (!dirty && !!product)}>{product ? "Save changes" : "Create product"}</button>
      </div>
    </form>
  );
}

export default ProductForm;
