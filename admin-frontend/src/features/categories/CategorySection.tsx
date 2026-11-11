import { useEffect, useMemo, useState } from "react";
import { fetchAllPages } from "../../api/client";
import { archiveCategory, createCategory, listCategories, updateCategory } from "../../api/categories";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import Tabs from "../../components/common/Tabs";
import { useAction } from "../../hooks/useAction";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import type { PageMeta } from "../../types/api";
import type { Category } from "../../types/catalogue";
import AttributeLists from "./AttributeLists";
import CategoryForm from "./CategoryForm";
import "./categories.css";

const FETCH_SIZE = 100;
const PAGE_SIZE = 20;
type CategoryLoad = { rows: Category[] | null; error: string | null };

function ordered(categories: Category[]): (Category & { depth: number })[] {
  const byParent = new Map<string, Category[]>();
  for (const category of categories) {
    const key = category.parent_id ?? "";
    byParent.set(key, [...(byParent.get(key) ?? []), category]);
  }
  const visited = new Set<string>();
  const result: (Category & { depth: number })[] = [];
  const visit = (category: Category, depth: number) => {
    if (visited.has(category.id)) return;
    visited.add(category.id);
    result.push({ ...category, depth });
    (byParent.get(category.id) ?? []).forEach((child) => visit(child, depth + 1));
  };
  categories.filter((category) => !category.parent_id || !categories.some((parent) => parent.id === category.parent_id)).forEach((category) => visit(category, 0));
  categories.forEach((category) => visit(category, 0));
  return result;
}

function CategorySection() {
  const { can } = useAuth();
  const canManage = can(P.catalogueManage);
  const [loaded, setLoaded] = useState<CategoryLoad>({ rows: null, error: null });
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState<"categories" | "values">("categories");
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [formDirty, setFormDirty] = useState(false);
  const action = useAction();
  const { requestLeave, pendingLeave, cancelLeave, discardLeave } = useUnsavedChanges(formDirty, () => setFormDirty(false));

  useEffect(() => {
    let active = true;
    fetchAllPages((page) => listCategories({ include_archived: true, page, page_size: FETCH_SIZE }), "categories").then(({ data: rows }) => { if (active) setLoaded({ rows, error: null }); })
      .catch((error: Error) => { if (active) setLoaded({ rows: null, error: error.message }); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [version]);

  const categories = useMemo(() => loaded.rows ?? [], [loaded.rows]);
  const orderedCategories = useMemo(() => ordered(categories), [categories]);
  const filtered = orderedCategories.filter((category) => category.name.toLowerCase().includes(search.trim().toLowerCase()) && (!status || category.status === status));
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const meta: PageMeta | null = loaded.rows && !loading ? { page: currentPage, page_size: PAGE_SIZE, total_items: filtered.length, total_pages: totalPages } : null;
  const reload = () => { setLoaded({ rows: null, error: null }); setLoading(true); setVersion((value) => value + 1); };
  const parent = (category: Category) => categories.find((candidate) => candidate.id === category.parent_id);
  const parentName = (category: Category) => parent(category)?.name ?? (category.parent_id ? "Parent unavailable" : "Top level");
  const canRestore = (category: Category) => !category.parent_id || (parent(category)?.status !== "ARCHIVED" && !!parent(category));

  return (
    <div className="categories-page">
      <PageHeader title="Categories" subtitle="Organize categories and product filter values" actions={canManage && tab === "categories" && <button className="primary" onClick={() => setEditing("new")}>New category</button>} />
      <StatusMessage status={action.status} />
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "categories", label: "Categories & subcategories" }, { key: "values", label: "Filter values" }]} />
      {tab === "categories" && <>
      <div className="filters category-filters">
        <GuidedControl className="guided-control--wide" hint="Find categories and subcategories by name." dismissible><input type="search" aria-label="Search categories" placeholder="Search category name" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></GuidedControl>
        <GuidedControl hint="Show active, draft or archived categories."><select aria-label="Category status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">All</option><option value="ACTIVE">Active</option><option value="DRAFT">Draft</option><option value="ARCHIVED">Archived</option>
        </select></GuidedControl>
        {(search || status) && <button type="button" onClick={() => { setSearch(""); setStatus(""); setPage(1); }}>Clear filters</button>}
      </div>
      <div className="panel record-table-panel category-table-panel">
        <DataTable rows={loaded.rows && !loading ? visible : null} loading={loading} error={loaded.error}
          empty="No categories match these filters."
          rowKey={(category) => category.id}
          onRowClick={canManage ? setEditing : undefined}
          columns={[
            { key: "id", header: "Category ID", render: (category) => <span className="category-list-id" title={category.id}>{category.id}</span> },
            { key: "name", header: "Category name", render: (category) => <span className="category-name" style={{ paddingLeft: Math.min(category.depth, 4) * 14 }}>{category.depth > 0 && "↳ "}{canManage ? <button type="button" className="link" onClick={(event) => { event.stopPropagation(); setEditing(category); }}>{category.name}</button> : category.name}</span> },
            { key: "parent", header: "Parent category", render: parentName },
            { key: "status", header: "Status", render: (category) => <Badge value={category.status} /> },
            { key: "hsn_code", header: "Legacy HSN", render: (category) => category.hsn_code ?? "-" },
            { key: "gst_rate", header: "Legacy GST %", render: (category) => category.gst_rate ?? "-" },
            { key: "actions", header: "Actions", render: (category) => canManage && (category.status === "ARCHIVED"
              ? <button type="button" disabled={action.busy || !canRestore(category)} title={!canRestore(category) ? "Restore the parent category first" : undefined} onClick={(event) => { event.stopPropagation(); action.run(async () => { await updateCategory(category.id, { status: "DRAFT" }); reload(); }, "Category restored to draft", "Could not restore category"); }}>Restore to draft</button>
              : <ConfirmButton message={`Archive ${category.name}? It will be hidden from the store. Categories containing products or subcategories cannot be archived.`} disabled={action.busy} onConfirm={() => action.run(async () => { await archiveCategory(category.id); reload(); }, "Category archived", "Could not archive")}>Archive</ConfirmButton>) },
          ]}
        />
        <Pagination meta={meta} onPageChange={setPage} />
      </div>
      </>}
      {tab === "values" && <AttributeLists canManage={canManage} />}
      {editing && <Modal title={editing === "new" ? "New category" : `Edit ${editing.name}`} onClose={() => requestLeave(() => setEditing(null))} showCloseButton={false}>
        <CategoryForm key={editing === "new" ? "new" : editing.id} category={editing === "new" ? null : editing} parents={categories.filter((category) => !category.parent_id && (category.status !== "ARCHIVED" || (editing !== "new" && category.id === editing.parent_id)))} busy={action.busy} onDirtyChange={setFormDirty} onCancel={() => requestLeave(() => setEditing(null))} onSubmit={async (data) => {
          const ok = await action.run(() => editing === "new" ? createCategory(data) : updateCategory(editing.id, data), "Category saved", "Could not save category");
          if (ok) { setFormDirty(false); setEditing(null); reload(); }
        }} />
      </Modal>}
      {pendingLeave && <ConfirmDialog title="Unsaved changes" message="You have unsaved changes. Do you want to discard them?" cancelLabel="Continue editing" confirmLabel="Discard changes" onCancel={cancelLeave} onConfirm={discardLeave} />}
    </div>
  );
}

export default CategorySection;
