import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchAllPages } from "../../api/client";
import { listCategories } from "../../api/categories";
import { listProducts } from "../../api/products";
import { getReport } from "../../api/reports";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import DataTable from "../../components/common/DataTable";
import type { Column } from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Pagination from "../../components/common/Pagination";
import Tabs from "../../components/common/Tabs";
import { useApi } from "../../hooks/useApi";
import type { PageMeta } from "../../types/api";
import { saveCsv } from "../../utils/csv";
import { formatDate, formatMoney } from "../../utils/formatters";
import ProductImage from "../products/ProductImage";
import { ExportButtons } from "../reports/ReportExports";
import "./inventory.css";

interface InventoryRow {
  product_id: string;
  product_name: string;
  variant_id: string;
  sku: string;
  variant_name: string;
  variant_status: string;
  available_quantity: number;
  reserved_quantity: number;
  sellable_quantity: number;
  low_stock_threshold: number;
  stock_status: "LOW" | "OUT_OF_STOCK" | "IN_STOCK";
  unit_price: string;
  stock_value: string;
}

interface UnsoldRow {
  product_id: string;
  product_name: string;
  variant_id: string;
  sku: string;
  sellable_quantity: number;
  last_sold_at: string | null;
  listed_since: string;
}

type View = "all" | "low" | "out" | "in" | "unsold";
const VIEW_STATUSES: Record<Exclude<View, "unsold">, InventoryRow["stock_status"] | null> = {
  all: null, low: "LOW", out: "OUT_OF_STOCK", in: "IN_STOCK",
};
const PAGE_SIZE = 50;

type VariantRow = { product_id: string; product_name: string; variant_id: string };

/** The columns both stock tables start with: picture, product and variant. */
function variantColumns<T extends VariantRow>(imageFor: (productId: string) => string | null | undefined): Column<T>[] {
  return [
    { key: "image", header: "", render: (row) => <ProductImage className="inventory-thumb" url={imageFor(row.product_id)} alt={`${row.product_name} thumbnail`} /> },
    { key: "product_id", header: "Product ID", render: (row) => <span className="inventory-record-id" title={row.product_id}>{row.product_id}</span> },
    { key: "product_name", header: "Product", render: (row) => <Link to={`/products/${row.product_id}`}>{row.product_name}</Link> },
    { key: "variant_id", header: "Variant ID", render: (row) => <span className="inventory-record-id" title={row.variant_id}>{row.variant_id}</span> },
  ];
}

function InventorySection() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const requested = params.get("stock_status") ?? "all";
  const view: View = requested in VIEW_STATUSES || requested === "unsold" ? requested as View : "all";
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [page, setPage] = useState(1);
  const inventory = useApi(() => getReport<InventoryRow[]>("inventory", { stock_status: "all" }), []);
  const unsold = useApi(() => view === "unsold"
    ? getReport<UnsoldRow[]>("unsold", { days: 30 })
    : Promise.resolve({ success: true, message: "", data: [] as UnsoldRow[], meta: null }), [view]);
  const products = useApi(() => fetchAllPages((page) => listProducts({ page, page_size: 100 }), "catalogue"), []);
  const categories = useApi(() => fetchAllPages((page) => listCategories({ page, page_size: 100 }), "catalogue"), []);
  const productMap = useMemo(() => new Map((products.data ?? []).map((product) => [product.id, product])), [products.data]);
  const categoryList = useMemo(() => categories.data ?? [], [categories.data]);
  const categoryNames = useMemo(() => new Map(categoryList.map((category) => [category.id, category.name])), [categoryList]);
  const categoryOptions = useMemo(() => categoryList.map((category) => category.id).sort((a, b) => (categoryNames.get(a) ?? a).localeCompare(categoryNames.get(b) ?? b)), [categoryList, categoryNames]);
  const matchingCategories = useMemo(() => {
    if (!categoryId) return null;
    const ids = new Set([categoryId]);
    for (let i = 0; i < categoryList.length; i++) {
      let changed = false;
      for (const category of categoryList) if (category.parent_id && ids.has(category.parent_id) && !ids.has(category.id)) { ids.add(category.id); changed = true; }
      if (!changed) break;
    }
    return ids;
  }, [categoryId, categoryList]);
  const categoryMatches = (productId: string) => !matchingCategories || matchingCategories.has(productMap.get(productId)?.category_id ?? "");
  const term = search.trim().toLowerCase();
  const stockRows = (inventory.data ?? []).filter((row) => {
    const stockStatus = view === "unsold" ? null : VIEW_STATUSES[view];
    return (!stockStatus || row.stock_status === stockStatus)
      && (!term || row.product_name.toLowerCase().includes(term) || row.sku.toLowerCase().includes(term))
      && categoryMatches(row.product_id);
  });
  const unsoldRows = (unsold.data ?? []).filter((row) => (!term || row.product_name.toLowerCase().includes(term) || row.sku.toLowerCase().includes(term)) && categoryMatches(row.product_id));
  const filtered = view === "unsold" ? unsoldRows : stockRows;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const meta: PageMeta | null = (view === "unsold" ? unsold.data : inventory.data) ? { page: currentPage, page_size: PAGE_SIZE, total_items: filtered.length, total_pages: totalPages } : null;
  const localFilters = !!term || !!categoryId;
  const exportName = view === "unsold" ? "unsold" : "inventory";
  const exportQuery = view === "unsold" ? { days: 30 } : { stock_status: view };
  const imageFor = (productId: string) => {
    const images = productMap.get(productId)?.images ?? [];
    return (images.find((image) => image.is_primary) ?? images[0])?.url;
  };
  const changeView = (next: View) => {
    setPage(1);
    setParams((previous) => { const nextParams = new URLSearchParams(previous); nextParams.set("stock_status", next); return nextParams; });
  };
  const empty = view === "low"
    ? "No low-stock variants match these filters. Low stock means sellable stock above zero and at or below the variant's alert threshold; a threshold of zero has no low-stock range."
    : view === "unsold" ? "No products match the last 30 days without sales." : "No inventory records match these filters.";

  return (
    <div className="record-page inventory-page">
      <PageHeader title="Inventory" subtitle="Sellable stock = available minus reserved. Update quantities and alert thresholds from a product's Variants & stock tab."
        actions={can(P.reports) && (!localFilters
          ? <ExportButtons name={exportName} query={exportQuery} />
          : <div className="toolbar inventory-export"><button type="button" disabled={filtered.length === 0} onClick={() => saveCsv(`${exportName}-filtered.csv`, filtered.map((row) => ({ ...row })))}>CSV</button><button type="button" disabled title="The report API cannot apply product, SKU or category filters to Excel exports">Excel</button><button type="button" disabled title="The report API cannot apply product, SKU or category filters to PDF exports">PDF</button></div>)}
      />
      {!can(P.reports) && <p className="muted">Inventory reports require the reports.view permission.</p>}
      <Tabs active={view} onChange={changeView} tabs={[
        { key: "all", label: "All Inventory" }, { key: "low", label: "Low Stock" }, { key: "out", label: "Out of Stock" }, { key: "in", label: "In Stock" }, { key: "unsold", label: "Unsold Products" },
      ]} />
      <div className="filters inventory-filters">
        <GuidedControl className="guided-control--wide" hint="Find a product or a specific variant SKU." dismissible><input type="search" aria-label="Search product or SKU" placeholder="Search product or SKU" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></GuidedControl>
        <GuidedControl hint="Narrow stock records to a category and its subcategories."><select aria-label="Category" value={categoryId} disabled={!products.data || !categories.data} onChange={(event) => { setCategoryId(event.target.value); setPage(1); }}>
          <option value="">All categories</option>
          {categoryOptions.map((id) => <option key={id} value={id}>{categoryNames.get(id) ?? "Category unavailable"}</option>)}
        </select></GuidedControl>
        {(search || categoryId) && <button type="button" onClick={() => { setSearch(""); setCategoryId(""); setPage(1); }}>Clear filters</button>}
      </div>
      {products.error && <p className="muted inventory-data-note">Product images and category filtering are unavailable: {products.error}</p>}
      <div className="panel record-table-panel inventory-table-panel">
        {view === "unsold" ? <DataTable rows={unsold.data ? visible as UnsoldRow[] : null} loading={unsold.loading} error={unsold.error} empty={empty} rowKey={(row) => row.variant_id} columns={[
          ...variantColumns(imageFor),
          { key: "sku", header: "SKU" },
          { key: "sellable_quantity", header: "Sellable", align: "right" },
          { key: "last_sold_at", header: "Last sold", render: (row) => formatDate(row.last_sold_at) },
          { key: "listed_since", header: "Listed since", render: (row) => formatDate(row.listed_since) },
        ]} /> : <DataTable rows={inventory.data ? visible as InventoryRow[] : null} loading={inventory.loading} error={inventory.error} empty={empty} rowKey={(row) => row.variant_id} columns={[
          ...variantColumns(imageFor),
          { key: "variant_name", header: "Variant" },
          { key: "sku", header: "SKU" },
          { key: "available_quantity", header: "Available", align: "right" },
          { key: "reserved_quantity", header: "Reserved", align: "right" },
          { key: "sellable_quantity", header: "Sellable", align: "right" },
          { key: "low_stock_threshold", header: "Alert at", align: "right" },
          { key: "stock_status", header: "Stock", render: (row) => <Badge value={row.stock_status} /> },
          { key: "stock_value", header: "Stock value", align: "right", render: (row) => formatMoney(row.stock_value) },
        ]} />}
        <Pagination meta={meta} onPageChange={setPage} />
      </div>
    </div>
  );
}

export default InventorySection;
