import { useState } from "react";
import type { FormEvent } from "react";
import { listCategories } from "../../api/categories";
import { createSection, deleteSection, listSections, reorderSections, updateSection } from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Modal from "../../components/common/Modal";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { moveId, useDragSort } from "../../hooks/useDragSort";
import type { BannerItem, HomeSection, SectionType } from "../../types/cms";
import { SECTION_TYPES } from "../../types/cms";
import { emptyToNull, formatDate, isoToLocalInput, label, localInputToIso } from "../../utils/formatters";
import MediaPicker from "./MediaPicker";
import { cleanBanner, heroProblem, SECTION_HELP } from "./banners";
import ProductPicker from "./ProductPicker";

const HAS_BANNERS: SectionType[] = ["HERO_BANNER", "PROMO_STRIP"];
const SAFE_LINK = /^(\/|https?:\/\/)/;

function HomeSectionsTab() {
  const { can } = useAuth();
  const canEdit = can(P.cmsManage);
  const canPublish = can(P.cmsPublish);
  const sections = useApi(() => listSections(), []);
  const action = useAction();
  const [editing, setEditing] = useState<HomeSection | "new" | null>(null);
  const rows = sections.data ?? [];

  const saveOrder = (ids: string[]) =>
    action.run(async () => { await reorderSections(ids); sections.reload(); }, "Order saved", "Could not reorder");
  const move = (i: number, d: number) => {
    const ids = rows.map((s) => s.id);
    const [x] = ids.splice(i, 1);
    ids.splice(i + d, 0, x);
    saveOrder(ids);
  };
  const { dragProps } = useDragSort((moving, target) => saveOrder(moveId(rows.map((s) => s.id), moving, target)), canEdit);

  return (
    <div className="panel">
      <div className="panel-title">
        <p className="muted">Shown on the homepage top to bottom{canEdit ? " — drag rows to reorder" : ""}. Only active sections inside their date window are live.</p>
        {canEdit && <button className="primary" onClick={() => setEditing("new")}>Add section</button>}
      </div>
      <StatusMessage status={action.status} />
      <DataTable
        rows={sections.data}
        loading={sections.loading}
        error={sections.error}
        empty="No homepage sections yet — add a hero banner to change the top of your homepage."
        rowKey={(s) => s.id}
        rowProps={(s) => dragProps(s.id)}
        columns={[
          { key: "order", header: "#", render: (s) => <>{canEdit && <span className="drag-handle" aria-hidden>⠿ </span>}{rows.indexOf(s) + 1}</> },
          { key: "section_type", header: "Type", render: (s) => label(s.section_type) },
          { key: "title", header: "Title", render: (s) => s.title ?? "-" },
          { key: "window", header: "Schedule", render: (s) => (s.starts_at || s.ends_at ? `${formatDate(s.starts_at)} → ${formatDate(s.ends_at)}` : "Always") },
          { key: "state", header: "State", render: (s) => <Badge value={s.is_live ? "LIVE" : s.is_active ? "SCHEDULED" : "INACTIVE"} /> },
          {
            key: "x",
            header: "",
            render: (s) => {
              const i = rows.indexOf(s);
              return (
                <div className="toolbar">
                  {canEdit && <button disabled={i === 0 || action.busy} onClick={() => move(i, -1)} aria-label="Move up">↑</button>}
                  {canEdit && <button disabled={i === rows.length - 1 || action.busy} onClick={() => move(i, 1)} aria-label="Move down">↓</button>}
                  {canPublish && <button onClick={() => action.run(async () => { await updateSection(s.id, { is_active: !s.is_active }); sections.reload(); }, s.is_active ? "Section turned off" : "Section turned on", "Could not change section")}>{s.is_active ? "Turn off" : "Turn on"}</button>}
                  {canEdit && <button onClick={() => setEditing(s)}>Edit</button>}
                  {canEdit && <ConfirmButton message="Delete this section?" onConfirm={() => action.run(async () => { await deleteSection(s.id); sections.reload(); }, "Section deleted", "Could not delete")}>Delete</ConfirmButton>}
                </div>
              );
            },
          },
        ]}
      />
      {editing && (
        <Modal title={editing === "new" ? "Add homepage section" : `Edit ${label(editing.section_type)}`} onClose={() => setEditing(null)} showCloseButton={false} wide>
          <SectionForm
            section={editing === "new" ? null : editing}
            canPublish={canPublish}
            busy={action.busy}
            onCancel={() => setEditing(null)}
            onSubmit={async (payload) => {
              const ok = await action.run(() => (editing === "new" ? createSection(payload) : updateSection(editing.id, payload)), "Section saved", "Could not save section");
              if (ok) {
                setEditing(null);
                sections.reload();
              }
            }}
          />
        </Modal>
      )}
    </div>
  );
}

const EMPTY_BANNER: BannerItem = { image_url: null, mobile_image_url: null, heading: null, text: null, link_url: null, cta_label: null, alt_text: null };

function SectionForm({ section, canPublish, busy, onSubmit, onCancel }: { section: HomeSection | null; canPublish: boolean; busy: boolean; onSubmit: (p: object) => void; onCancel: () => void }) {
  const categories = useApi(() => listCategories(), []);
  const [type, setType] = useState<SectionType>(section?.section_type ?? "HERO_BANNER");
  const [title, setTitle] = useState(section?.title ?? "");
  const [subtitle, setSubtitle] = useState(section?.subtitle ?? "");
  const [startsAt, setStartsAt] = useState(isoToLocalInput(section?.starts_at ?? null));
  const [endsAt, setEndsAt] = useState(isoToLocalInput(section?.ends_at ?? null));
  const [active, setActive] = useState(section?.is_active ?? false);
  const [items, setItems] = useState<BannerItem[]>(section?.items.length ? section.items : [EMPTY_BANNER]);
  const [productIds, setProductIds] = useState<string[]>(section?.settings.product_ids ?? []);
  const [categoryId, setCategoryId] = useState(section?.settings.category_id ?? "");
  const [limit, setLimit] = useState(String(section?.settings.limit ?? 8));
  const [days, setDays] = useState(String(section?.settings.days ?? 30));
  const [error, setError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const dateError = startsAt && endsAt && new Date(endsAt) <= new Date(startsAt) ? "The end must be after the start." : null;
  const limitError = !(Number(limit) >= 1 && Number(limit) <= 48) ? "Number of products must be 1–48." : null;

  // Keep exactly what is typed (spaces included); values are tidied on save.
  // Functional update: an upload finishing later must not overwrite edits made meanwhile.
  const setItem = (i: number, k: keyof BannerItem, v: string) => {
    setError(null);
    setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, [k]: v === "" ? null : v } : it)));
  };
  const [uploads, setUploads] = useState(0);
  const trackUpload = (uploading: boolean) => setUploads((n) => n + (uploading ? 1 : -1));
  // Slides are reordered here and saved with the section.
  const slideIds = items.map((_, i) => String(i));
  // Slides are tracked by position, so they stay put while a picture uploads
  // (otherwise the picture would land on whichever slide moved into its place).
  const { dragProps: slideDrag } = useDragSort((moving, target) =>
    setItems(moveId(slideIds, moving, target).map((id) => items[Number(id)])),
    uploads === 0
  );

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (dateError) return setError(dateError);
    const banners = HAS_BANNERS.includes(type)
      ? items.map(cleanBanner).filter((i) => Object.values(i).some(Boolean))
      : [];
    for (const b of banners) {
      for (const url of [b.image_url, b.mobile_image_url, b.link_url]) if (url && !SAFE_LINK.test(url)) return setError(`"${url}" must start with / or https://`);
    }
    if (type === "HERO_BANNER") {
      const problem = heroProblem(items.map(cleanBanner));
      if (problem) return setError(problem.startsWith("Slide ") ? "Please complete the highlighted banner fields before continuing." : problem);
    }
    const lim = Number(limit);
    if (limitError) return setError(limitError);
    setError(null);
    onSubmit({
      ...(section ? {} : { section_type: type }),
      title: emptyToNull(title),
      subtitle: emptyToNull(subtitle),
      starts_at: localInputToIso(startsAt),
      ends_at: localInputToIso(endsAt),
      ...(canPublish ? { is_active: active } : {}),
      items: banners,
      settings: {
        product_ids: productIds.length ? productIds : null,
        category_id: categoryId || null,
        limit: lim,
        days: Number(days) || 30,
        countdown_ends_at: section?.settings.countdown_ends_at ?? null, // no editor yet; keep what is set
      },
    });
  };

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="form-grid">
        <Field label="What kind of section?" hint={SECTION_HELP[type]} wide>
          <select value={type} disabled={!!section} onChange={(e) => setType(e.target.value as SectionType)}>
            {SECTION_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </select>
        </Field>
        <Field label="Title" hint={type === "HERO_BANNER" ? "Shown as the small line above the headline" : "Shown above the section"}><input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Subtitle" hint="Optional"><input value={subtitle} onChange={(e) => setSubtitle(e.target.value)} /></Field>
        <Field label="Show from" hint="Blank = immediately"><input type="datetime-local" value={startsAt} onChange={(e) => { setError(null); setStartsAt(e.target.value); }} /></Field>
        <Field label="Show until" error={attempted ? dateError : null} hint="Blank = no end"><input type="datetime-local" value={endsAt} onChange={(e) => { setError(null); setEndsAt(e.target.value); }} /></Field>
      </div>
      {canPublish ? (
        <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active (visible on the storefront within its schedule)</label>
      ) : (
        <p className="muted">Saved as inactive — someone with publish rights turns it on.</p>
      )}

      {HAS_BANNERS.includes(type) && (
        <div className="panel">
          <h4>{type === "HERO_BANNER" ? "Banner slides" : "Promo messages"}</h4>
          {type === "HERO_BANNER" && <p className="help">Every slide needs a picture. Upload one from your computer or choose one you uploaded before.</p>}
          {items.map((it, i) => (
            <div key={i} {...slideDrag(String(i))} className="form-grid" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 12, marginBottom: 12 }}>
              <span className="drag-handle field-wide">⠿ Slide {i + 1} — drag to reorder</span>
              <MediaPicker label="Picture" required={type === "HERO_BANNER"} validationError={attempted && type === "HERO_BANNER" && !it.image_url ? `Slide ${i + 1} needs a picture.` : null} value={it.image_url ?? ""} onChange={(v) => setItem(i, "image_url", v || "")} onUploadingChange={trackUpload} />
              <MediaPicker label="Phone picture" hint="Optional — a taller picture for phones" value={it.mobile_image_url ?? ""} onChange={(v) => setItem(i, "mobile_image_url", v || "")} onUploadingChange={trackUpload} />
              <Field label="Heading" hint="The big headline"><input value={it.heading ?? ""} onChange={(e) => setItem(i, "heading", e.target.value)} /></Field>
              <Field label="Text" hint="A short line under the headline"><input value={it.text ?? ""} onChange={(e) => setItem(i, "text", e.target.value)} /></Field>
              <Field label="Link" hint="Where the button goes, e.g. /shop-list"><input value={it.link_url ?? ""} onChange={(e) => setItem(i, "link_url", e.target.value)} /></Field>
              <Field label="Button text" hint="e.g. Shop the collection"><input value={it.cta_label ?? ""} onChange={(e) => setItem(i, "cta_label", e.target.value)} /></Field>
              <Field label="Picture description" hint="Describes the picture for screen readers and Google"><input value={it.alt_text ?? ""} onChange={(e) => setItem(i, "alt_text", e.target.value)} /></Field>
              <div><button type="button" className="danger" disabled={uploads > 0} onClick={() => setItems(items.filter((_, idx) => idx !== i))}>Remove</button></div>
            </div>
          ))}
          <button type="button" disabled={items.length >= 12} onClick={() => setItems([...items, EMPTY_BANNER])}>Add {type === "HERO_BANNER" ? "slide" : "message"}</button>
        </div>
      )}

      {!HAS_BANNERS.includes(type) && (
        <div className="panel">
          <h4>Products</h4>
          <div className="form-grid">
            <Field label="How many products" required error={attempted ? limitError : null}><input type="number" min="1" max="48" value={limit} onChange={(e) => { setError(null); setLimit(e.target.value); }} /></Field>
            {type === "BESTSELLERS" && <Field label="Bestsellers over the last (days)"><input type="number" min="1" max="365" value={days} onChange={(e) => setDays(e.target.value)} /></Field>}
            <Field label="Limit to category" hint="Includes its sub-categories">
              <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                <option value="">All categories</option>
                {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          </div>
          {(type === "FEATURED_PRODUCTS" || type === "SEASONAL") && (
            <>
              <p className="muted">{type === "FEATURED_PRODUCTS" ? "Hand-pick products (blank = products marked Featured)." : "Hand-pick products, or leave empty to use the category."}</p>
              <ProductPicker value={productIds} onChange={setProductIds} max={48} />
            </>
          )}
        </div>
      )}
      {error && <div className="status status-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button className="primary" disabled={busy || uploads > 0}>{uploads > 0 ? "Waiting for the picture to finish uploading…" : "Save section"}</button>
      </div>
    </form>
  );
}

export default HomeSectionsTab;
