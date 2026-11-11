import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchAllPages } from "../../api/client";
import { listCategories } from "../../api/categories";
import { archiveProduct, downloadImportTemplate, importProducts, listProducts } from "../../api/products";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { useUrlFilters } from "../../hooks/useUrlFilters";
import type { PageMeta } from "../../types/api";
import type { ImportResult } from "../../types/catalogue";
import ProductImage from "./ProductImage";
import "./products.css";

const PAGE_SIZE = 20;
const FETCH_SIZE = 100;

function ProductSection() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const canManage = can(P.catalogueManage);
  const { params, setParams, setFilter, setPage } = useUrlFilters();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [importing, setImporting] = useState(false);
  const [lastArchived, setLastArchived] = useState<{ id: string; name: string } | null>(null);
  const categories = useApi(() => listCategories(), []);
  const query = {
    search: params.get("search"),
    category_id: params.get("category_id"),
    featured: params.get("featured"),
    sort: params.get("sort") ?? "newest",
    status: params.get("status"),
  };
  const products = useApi(
    () => fetchAllPages((page) => listProducts({ ...query, page, page_size: FETCH_SIZE }), "products"),
    [query.search, query.category_id, query.featured, query.sort, query.status]
  );
  const loading = products.loading;
  const records = products.data;
  const selectedStatus = params.get("status") ?? "";
  const filtered = useMemo(() => records?.filter((product) =>
    (!selectedStatus || product.status === selectedStatus)
  ) ?? [], [records, selectedStatus]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const requestedPage = Number(params.get("page") ?? 1);
  const page = Number.isFinite(requestedPage) ? Math.min(Math.max(1, requestedPage), totalPages) : 1;
  const rows = records ? filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE) : null;
  const meta: PageMeta | null = records ? { page, page_size: PAGE_SIZE, total_items: filtered.length, total_pages: totalPages } : null;
  const action = useAction();
  const categoryName = (id: string) => categories.data?.find((c) => c.id === id)?.name ?? "-";
  const clearFilters = () => { setSearch(""); setParams(new URLSearchParams()); };


  return (
    <div className="record-page products-page">
      <PageHeader
        title="Products"
        actions={canManage && (<><button onClick={() => setImporting(true)}>Bulk upload</button><Link className="btn" to="/products/new">New product</Link></>)}
      />
      <StatusMessage status={action.status} />
      {lastArchived && <p className="product-archive-link">Archived {lastArchived.name}. <Link to={`/products/${lastArchived.id}`}>View archived product</Link></p>}
      <form className="filters product-filters" onSubmit={(e: FormEvent) => { e.preventDefault(); setFilter("search", search.trim()); }}>
        <GuidedControl className="guided-control--wide" hint="Find products by name." dismissible><input type="search" placeholder="Search products" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search products" /></GuidedControl>
        <button>Search</button>
        <GuidedControl hint="Limit results to one product category."><select aria-label="Category" value={params.get("category_id") ?? ""} onChange={(e) => setFilter("category_id", e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.parent_id ? `↳ ${c.name}` : c.name}</option>)}
        </select></GuidedControl>
        <select aria-label="Sort" value={params.get("sort") ?? "newest"} onChange={(e) => setFilter("sort", e.target.value)}>
          <option value="newest">Newest</option>
          <option value="name_asc">Name A–Z</option>
          <option value="name_desc">Name Z–A</option>
        </select>
        <GuidedControl hint="Show active, draft or archived products."><select aria-label="Product status" value={params.get("status") ?? ""} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">All statuses</option><option value="ACTIVE">Active</option><option value="DRAFT">Draft</option><option value="ARCHIVED">Archived</option>
        </select></GuidedControl>
        <GuidedControl hint="Show only products marked as featured."><label className="check"><input type="checkbox" checked={params.get("featured") === "true"} onChange={(e) => setFilter("featured", e.target.checked ? "true" : "")} /> Featured only</label></GuidedControl>
        <button type="button" onClick={clearFilters} disabled={!params.toString() && !search}>Clear Filters</button>
      </form>
      <div className="panel record-table-panel product-table-panel">
        <DataTable
          rows={rows}
          loading={loading}
          error={loading ? null : products.error}
          empty={selectedStatus === "ARCHIVED" ? "No archived products match these filters." : "No products found."}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`/products/${p.id}`)}
          columns={[
            { key: "img", header: "", render: (p) => { const img = p.images.find((i) => i.is_primary) ?? p.images[0]; return <ProductImage className="thumb" url={img?.url} />; } },
            { key: "id", header: "Product ID", render: (p) => <span className="product-list-id" title={p.id}>{p.id}</span> },
            { key: "name", header: "Name", render: (p) => <Link to={`/products/${p.id}`} className="product-code" onClick={(event) => event.stopPropagation()}>{p.name}</Link> },
            { key: "category", header: "Category", render: (p) => categoryName(p.category_id) },
            { key: "fabric", header: "Fabric", render: (p) => p.fabric ?? "-" },
            { key: "status", header: "Status", render: (p) => <Badge value={p.status} /> },
            { key: "is_featured", header: "Featured", render: (p) => (p.is_featured ? "Yes" : "") },
            {
              key: "x",
              header: "",
              render: (p) =>
                canManage && p.status !== "ARCHIVED" && (
                  <ConfirmButton message={`Archive ${p.name}? Shoppers will no longer see it.`} disabled={action.busy} onConfirm={() => action.run(async () => { await archiveProduct(p.id); setLastArchived({ id: p.id, name: p.name }); products.reload(); }, "Product archived", "Could not archive")}>Archive</ConfirmButton>
                ),
            },
          ]}
        />
        <Pagination meta={meta} onPageChange={setPage} />
      </div>
      {importing && <ImportModal onClose={() => setImporting(false)} onImported={() => products.reload()} />}
    </div>
  );
}

function ImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const action = useAction();

  const run = async (dryRun: boolean) => {
    if (!file) return;
    const response = await action.run(() => importProducts(file, dryRun), null, "Import failed");
    if (!response) return;
    setResult(response.data);
    if (!dryRun && response.data.errors.length === 0) {
      action.setStatus({ type: "success", text: `Imported ${response.data.products} products and ${response.data.variants} variants.` });
      onImported();
    }
  };

  return (
    <Modal title="Bulk product upload" onClose={onClose} wide>
      <div className="form">
        <p className="muted">
          Upload an Excel file (<strong>.xlsx</strong>) or a CSV, one row per variant (size/colour). Rows with the same product name and category become one product.
          Nothing is created unless every row is valid; existing SKUs are never overwritten.
        </p>
        <div className="toolbar">
          <button className="link" onClick={() => action.run(() => downloadImportTemplate("xlsx"), null, "Could not download template")}>Excel template</button>
          <button className="link" onClick={() => action.run(() => downloadImportTemplate("csv"), null, "Could not download template")}>CSV template</button>
        </div>
        <input
          type="file"
          accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
          onChange={(e) => {
            const chosen = e.target.files?.[0] ?? null;
            setResult(null);
            if (chosen && !/\.(xlsx|csv)$/i.test(chosen.name)) {
              setFile(null);
              action.setStatus({ type: "error", text: "Choose an Excel .xlsx or a .csv file." });
              return;
            }
            setFile(chosen);
          }}
          aria-label="Product file"
        />
        <StatusMessage status={action.status} />
        {result && (
          <div className="panel">
            <p>{result.rows} rows → {result.products} products, {result.variants} variants {result.dry_run && "(check only, nothing saved)"}</p>
            {result.errors.length > 0 ? (
              <DataTable rows={result.errors} rowKey={(e) => `${e.row}-${e.message}`} columns={[{ key: "row", header: "Row" }, { key: "message", header: "Problem" }]} />
            ) : result.dry_run && <p className="status status-success">All rows are valid.</p>}
          </div>
        )}
        <div className="form-actions">
          <button onClick={() => run(true)} disabled={!file || action.busy}>Check file</button>
          <button className="primary" onClick={() => run(false)} disabled={!file || action.busy || !result || !result.dry_run || result.errors.length > 0}>Import</button>
        </div>
      </div>
    </Modal>
  );
}

export default ProductSection;
