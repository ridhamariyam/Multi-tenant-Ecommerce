import { useState } from "react";
import type { FormEvent } from "react";
import { createPage, deletePage, getPage, listPages, updatePage } from "../../api/cms";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { CmsPage, PageType } from "../../types/cms";
import { PAGE_TYPES } from "../../types/cms";
import { slugProblem } from "../../utils/slug";
import { emptyToNull, formatDate, label } from "../../utils/formatters";
import ContentEditor from "./ContentEditor";
import type { ContentFormProps } from "./ContentEditor";
import ContentRowActions from "./ContentRowActions";
import MarkdownField from "./MarkdownField";
import { StorefrontPages } from "./OverviewTab";
import { LiveState } from "./PublishControls";

function PagesTab() {
  const { can } = useAuth();
  const canEdit = can(P.cmsManage);
  const [page, setPage] = useState(1);
  const pages = useApi(() => listPages({ page }), [page]);
  const action = useAction();
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const open = (id: string | "new", preview = false) => {
    setPreviewing(preview);
    setEditingId(id);
  };

  return (
    <>
    <div className="panel">
      <div className="panel-title">
        <p className="muted">Extra pages you write here appear on the website at /pages/… — link them from a menu so customers can find them.</p>
        {canEdit && <button className="primary" onClick={() => open("new")}>New page</button>}
      </div>
      <StatusMessage status={action.status} />
      <DataTable
        rows={pages.data as unknown as CmsPage[] | null}
        loading={pages.loading}
        error={pages.error}
        empty="No pages created in the CMS yet. Your website's existing pages are listed below."
        rowKey={(p) => p.id}
        onRowClick={(p) => open(p.id)}
        columns={[
          { key: "title", header: "Title" },
          { key: "slug", header: "URL", render: (p) => `/pages/${p.slug}` },
          { key: "page_type", header: "Type", render: (p) => label(p.page_type) },
          { key: "state", header: "State", render: (p) => <LiveState item={p} /> },
          { key: "updated_at", header: "Updated", render: (p) => formatDate(p.updated_at) },
          {
            key: "actions",
            header: "Actions",
            render: (p) => (
              <ContentRowActions
                kind="pages"
                row={p}
                path={`/pages/${p.slug}`}
                action={action}
                onEdit={() => open(p.id)}
                onPreview={() => open(p.id, true)}
                onDelete={() => deletePage(p.id)}
                onChanged={pages.reload}
              />
            ),
          },
        ]}
      />
      <Pagination meta={pages.meta} onPageChange={setPage} />
      {editingId && (
        <ContentEditor
          kind="pages"
          itemId={editingId === "new" ? null : editingId}
          canEdit={canEdit}
          load={getPage}
          create={createPage}
          update={updatePage}
          remove={deletePage}
          onClose={() => { setEditingId(null); pages.reload(); }}
          onCreated={setEditingId}
          renderForm={(form) => <PageForm {...form} canEdit={canEdit} startInPreview={previewing} />}
        />
      )}
    </div>
    <StorefrontPages />
    </>
  );
}

function PageForm({ item: page, busy, onSubmit, canEdit, startInPreview }: ContentFormProps<CmsPage> & { canEdit: boolean; startInPreview: boolean }) {
  const [title, setTitle] = useState(page?.title ?? "");
  const [slug, setSlug] = useState(page?.slug ?? "");
  const [type, setType] = useState<PageType>(page?.page_type ?? "CUSTOM");
  const [body, setBody] = useState(page?.body ?? "");
  const [seoTitle, setSeoTitle] = useState(page?.seo_title ?? "");
  const [seoDescription, setSeoDescription] = useState(page?.seo_description ?? "");
  const [attempted, setAttempted] = useState(false);
  const titleError = !title.trim() ? "Page title is required." : null;
  const slugError = slugProblem(slug);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (titleError || slugError) return;
    setAttempted(false);
    onSubmit({ title: title.trim(), slug: emptyToNull(slug), page_type: type, body, seo_title: emptyToNull(seoTitle), seo_description: emptyToNull(seoDescription) });
  };

  return (
    <form className="form" onSubmit={submit} noValidate style={{ marginTop: 12 }}>
      <fieldset disabled={!canEdit} style={{ border: 0, padding: 0, margin: 0 }} className="form">
        <div className="form-grid">
          <Field label="Title" required error={attempted ? titleError : null} guidance="Enter the heading customers will see on this page." guidanceDismissible><input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="URL slug" error={attempted ? slugError : null} hint="Blank = made from the title"><input value={slug} onChange={(e) => setSlug(e.target.value)} /></Field>
          <Field label="Page type">
            <select value={type} onChange={(e) => setType(e.target.value as PageType)}>
              {PAGE_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
            </select>
          </Field>
        </div>
        <MarkdownField label="Page text" value={body} onChange={setBody} rows={14} startInPreview={startInPreview} />
        <div className="form-grid">
          <Field label="SEO title"><input value={seoTitle} onChange={(e) => setSeoTitle(e.target.value)} /></Field>
          <Field label="SEO description" wide><textarea value={seoDescription} onChange={(e) => setSeoDescription(e.target.value)} /></Field>
        </div>
      </fieldset>
      {attempted && (titleError || slugError) && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
      {canEdit && <div className="form-actions"><button className="primary" disabled={busy}>{page?.status === "PUBLISHED" ? "Save — updates the website" : "Save draft"}</button></div>}
    </form>
  );
}

export default PagesTab;
