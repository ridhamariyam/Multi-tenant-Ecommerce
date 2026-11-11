import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { listCategories } from "../../api/categories";
import { createProduct, getProduct, getRelated, listProducts, setRelated, updateProduct, uploadUnattachedImage } from "../../api/products";
import { getRatingSummary, listProductReviews } from "../../api/reviews";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import DataTable from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import Tabs from "../../components/common/Tabs";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import { formatDate } from "../../utils/formatters";
import ProductForm from "./ProductForm";
import { clearUnsavedProductDraft } from "./productDraft";
import ProductImages from "./ProductImages";
import VariantSection from "./VariantSection";
import { listVariants } from "../../api/variants";
import "./products.css";

type Tab = "details" | "images" | "variants" | "related" | "reviews";

// /products/new creates a product; /products/:id edits one.
function ProductManager() {
  const { productId = "new" } = useParams();
  const isNew = productId === "new";
  const navigate = useNavigate();
  const { can, user } = useAuth();
  const canManage = can(P.catalogueManage);
  const [tab, setTab] = useState<Tab>("details");
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [formVersion, setFormVersion] = useState(0);
  const categories = useApi(() => listCategories(), []);
  const product = useApi(() => (isNew ? Promise.resolve({ success: true, message: "", data: null, meta: null }) : getProduct(productId)), [productId]);
  const action = useAction();
  const { requestLeave, pendingLeave, cancelLeave, discardLeave } = useUnsavedChanges(hasUnsaved, () => {
    if (isNew && user) clearUnsavedProductDraft(user.tenant_id, user.id);
    setHasUnsaved(false);
    setFormVersion((version) => version + 1);
  });

  if (product.error) return <div className="status status-error">{product.error}</div>;
  if (!isNew && !product.data) return <div className="state">Loading…</div>;
  const p = product.data;

  return (
    <div className="product-editor">
      <PageHeader
        title={p ? p.name : "New product"}
        subtitle={p ? `/products/${p.slug}` : "Create the product with its photos, then add variants (sizes/colours) and stock."}
        actions={<>
          {p && <Badge value={p.status} />}
          {p && canManage && (p.status === "DRAFT" || p.status === "ACTIVE") &&
            <ConfirmButton className="btn" disabled={action.busy} message={p.status === "DRAFT" ? "Activate this product after adding a sellable variant?" : "Move this product back to Draft?"} onConfirm={() => {
              requestLeave(() => { void action.run(async () => {
                if (p.status === "DRAFT") {
                  const variants = await listVariants(p.id);
                  if (!variants.data.some((variant) => variant.status === "ACTIVE")) throw new Error("Add an active variant before activating this product.");
                }
                await updateProduct(p.id, { status: p.status === "DRAFT" ? "ACTIVE" : "DRAFT" });
                product.reload();
              }, p.status === "DRAFT" ? "Product activated" : "Product moved to Draft", "Could not update product status"); });
            }}>{p.status === "DRAFT" ? "Activate product" : "Move to Draft"}</ConfirmButton>}
          <Link className="btn" to="/products">Back to products</Link>
        </>}
      />
      <StatusMessage status={action.status} />
      {p && (
        <Tabs
          active={tab}
          onChange={(next) => requestLeave(() => setTab(next))}
          tabs={[
            { key: "details", label: "Details" },
            { key: "images", label: "Images" },
            { key: "variants", label: "Variants & stock" },
            { key: "related", label: "Related products" },
            { key: "reviews", label: "Reviews" },
          ]}
        />
      )}
      {tab === "details" && (canManage ? (
        <ProductForm
          key={`${p?.id ?? "new"}:${formVersion}`}
          product={p}
          categories={categories.data ?? []}
          busy={action.busy}
          requireImage={isNew}
          onDirtyChange={setHasUnsaved}
          onCancel={() => requestLeave(() => navigate("/products"))}
          onSubmit={async (fields, newImages) => {
            if (isNew && newImages) {
              const created = await action.run(
                async () => {
                  const urls = [];
                  for (const file of newImages.files) urls.push((await uploadUnattachedImage(file)).data.url);
                  return createProduct({
                    ...fields,
                    images: urls.map((url, i) => ({ url, alt_text: fields.name, is_primary: i === 0, sort_order: i })),
                  });
                },
                "Product created — now add variants",
                "Could not create product"
              );
              if (created) {
                setHasUnsaved(false);
                setTab("variants");
                navigate(`/products/${created.data.id}`, { replace: true });
              }
              return !!created;
            } else {
              const ok = await action.run(() => updateProduct(p!.id, fields), "Product saved", "Could not save product");
              if (ok) product.reload();
              return !!ok;
            }
          }}
        />
      ) : p && <ReadOnlyDetails product={p} />)}
      {p && tab === "images" && <ProductImages productId={p.id} canManage={canManage} />}
      {p && tab === "variants" && <VariantSection productId={p.id} canManage={canManage} />}
      {p && tab === "related" && <RelatedProducts productId={p.id} canManage={canManage} />}
      {p && tab === "reviews" && <ProductReviews productId={p.id} />}
      {pendingLeave && <ConfirmDialog
        title="Unsaved changes"
        message="You have unsaved changes. Do you want to discard them?"
        cancelLabel="Continue editing"
        confirmLabel="Discard changes"
        onCancel={cancelLeave}
        onConfirm={discardLeave}
      />}
    </div>
  );
}

function ReadOnlyDetails({ product }: { product: NonNullable<Awaited<ReturnType<typeof getProduct>>["data"]> }) {
  return (
    <div className="panel">
      <dl className="kv">
        {(["short_description", "fabric", "occasion", "sleeve", "neckline", "country_of_origin", "washing_instructions", "hsn_code", "gst_rate"] as const).map((k) => (
          <Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd>{product[k] ?? "-"}</dd></Fragment>
        ))}
      </dl>
    </div>
  );
}

function RelatedProducts({ productId, canManage }: { productId: string; canManage: boolean }) {
  const related = useApi(() => getRelated(productId), [productId]);
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const results = useApi(() => (term ? listProducts({ search: term, page_size: 10 }) : Promise.resolve({ success: true, message: "", data: [], meta: null })), [term]);
  const action = useAction();
  const ids = related.data?.map((r) => r.id) ?? [];
  const save = (next: string[]) => action.run(async () => { await setRelated(productId, next); related.reload(); }, "Related products saved", "Could not save related products");

  return (
    <div className="panel">
      <StatusMessage status={action.status} />
      <p className="muted">Shown as “You may also like” on the product page, in this order (max 20).</p>
      <DataTable
        rows={related.data}
        loading={related.loading}
        error={related.error}
        empty="No related products picked."
        rowKey={(r) => r.id}
        columns={[
          { key: "name", header: "Product", render: (r) => <Link to={`/products/${r.id}`}>{r.name}</Link> },
          { key: "status", header: "Status", render: (r) => <Badge value={r.status} /> },
          ...(canManage ? [{ key: "x", header: "", render: (r: { id: string }) => <button className="danger" onClick={() => save(ids.filter((id) => id !== r.id))}>Remove</button> }] : []),
        ]}
      />
      {canManage && (
        <>
          <form className="filters" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); setTerm(search.trim()); }}>
            <input type="search" placeholder="Find a product to add" value={search} onChange={(e) => setSearch(e.target.value)} />
            <button>Search</button>
          </form>
          <ul className="list-plain">
            {results.data?.filter((r) => r.id !== productId && !ids.includes(r.id)).map((r) => (
              <li key={r.id} className="toolbar">
                {r.name} <Badge value={r.status} />
                <button disabled={ids.length >= 20 || action.busy} onClick={() => save([...ids, r.id])}>Add</button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ProductReviews({ productId }: { productId: string }) {
  const summary = useApi(() => getRatingSummary(productId), [productId]);
  const reviews = useApi(() => listProductReviews(productId), [productId]);
  return (
    <div className="panel">
      {summary.data && (
        <p>
          <strong>{summary.data.average_rating.toFixed(1)}★</strong> from {summary.data.total_reviews} approved reviews ·{" "}
          {Object.entries(summary.data.rating_distribution).map(([star, count]) => `${star}★ ${count}`).join(" · ")}
        </p>
      )}
      <DataTable
        rows={reviews.data}
        loading={reviews.loading}
        error={reviews.error}
        empty="No reviews yet."
        rowKey={(r) => r.id}
        columns={[
          { key: "rating", header: "Rating", render: (r) => `${r.rating}★` },
          { key: "title", header: "Review", render: (r) => <><strong>{r.title}</strong> {r.comment}</> },
          { key: "is_approved", header: "Status", render: (r) => <Badge value={r.is_approved ? "PUBLISHED" : "PENDING"} /> },
          { key: "created_at", header: "Date", render: (r) => formatDate(r.created_at) },
        ]}
      />
      <Link to="/reviews">Moderate reviews</Link>
    </div>
  );
}

export default ProductManager;
