import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { mediaUrl } from "../../api/client";
import { getCustomer } from "../../api/customers";
import { getOrder, getTracking } from "../../api/orders";
import { getProduct } from "../../api/products";
import { dispatchReviewRequests, listModeration, listReviewRequests, moderateReview } from "../../api/reviews";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import Tabs from "../../components/common/Tabs";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { ApiResponse } from "../../types/api";
import type { Product } from "../../types/catalogue";
import type { Order, OrderTracking } from "../../types/order";
import type { CustomerDetail } from "../../types/user";
import { formatDate } from "../../utils/formatters";
import ProductImage from "../products/ProductImage";
import "./reviews.css";

function useLookups<T>(ids: string[], fetchRecord: (id: string) => Promise<ApiResponse<T>>, tenantId: string, enabled = true) {
  const [lookup, setLookup] = useState<{ tenant: string; records: Map<string, T | null> }>(() => ({ tenant: tenantId, records: new Map() }));
  const records = lookup.tenant === tenantId ? lookup.records : new Map<string, T | null>();
  const key = ids.join("|");
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const missing = ids.filter((id) => !records.has(id));
    if (missing.length) {
      void Promise.all(missing.map(async (id) => {
        try { return [id, (await fetchRecord(id)).data] as const; }
        catch { return [id, null] as const; }
      })).then((records) => {
        if (!active) return;
        setLookup((current) => {
          const next = new Map(current.tenant === tenantId ? current.records : []);
          records.forEach(([id, record]) => next.set(id, record));
          return { tenant: tenantId, records: next };
        });
      });
    }
    return () => { active = false; };
    // The record API is fixed for each use of this hook; key follows the visible page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tenantId, enabled]);
  return records;
}

function ReviewSection() {
  const [tab, setTab] = useState<"reviews" | "requests">("reviews");
  return (
    <div className="reviews-page record-page">
      <PageHeader title="Reviews" subtitle="Moderate customer reviews and manage requests after delivery" />
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "reviews", label: "Moderation" }, { key: "requests", label: "Review requests" }]} />
      {tab === "reviews" ? <Moderation /> : <Requests />}
    </div>
  );
}

function Moderation() {
  const { can, user } = useAuth();
  const canManage = can(P.reviewsManage);
  const canViewProducts = can(P.catalogueView);
  const canViewCustomers = can(P.customersView);
  const [filter, setFilter] = useState<"" | "true" | "false">("false");
  const [page, setPage] = useState(1);
  const list = useApi(() => listModeration({ is_approved: filter || undefined, page, page_size: 20 }), [filter, page]);
  const rows = useMemo(() => list.data ?? [], [list.data]);
  const productIds = useMemo(() => [...new Set(rows.map((row) => row.product_id).filter((id): id is string => !!id))], [rows]);
  const customerIds = useMemo(() => [...new Set(rows.map((row) => row.user_id).filter((id): id is string => !!id))], [rows]);
  const products = useLookups<Product>(productIds, getProduct, user?.tenant_id ?? "", canViewProducts);
  const customers = useLookups<CustomerDetail>(customerIds, getCustomer, user?.tenant_id ?? "", canViewCustomers);
  const action = useAction();
  const moderate = (id: string, approve: boolean) =>
    action.run(async () => { await moderateReview(id, approve); list.reload(); }, approve ? "Review approved" : "Review hidden", "Could not update review");

  return (
    <div className="panel reviews-table-panel">
      <StatusMessage status={action.status} />
      <div className="filters reviews-filters">
        <GuidedControl hint="Show unpublished, approved or all customer reviews." dismissible><select aria-label="Review status" value={filter} onChange={(event) => { setFilter(event.target.value as typeof filter); setPage(1); }}>
          <option value="false">Waiting for Approval / Hidden</option>
          <option value="true">Approved</option>
          <option value="">All reviews</option>
        </select></GuidedControl>
        <span className="muted">Waiting and hidden share one status in the current review API.</span>
      </div>
      <DataTable
        rows={list.data}
        loading={list.loading}
        error={list.error}
        empty={filter === "false" ? "No unpublished reviews. Check Approved or All reviews for other records." : "No reviews match this view."}
        rowKey={(review) => review.id}
        columns={[
          { key: "product", header: "Product", render: (review) => {
            const product = review.product_id && canViewProducts ? products.get(review.product_id) : null;
            const image = product?.images.find((entry) => entry.is_primary) ?? product?.images[0];
            return review.product_id ? <div className="review-product"><ProductImage className="review-product-thumb" url={image?.url} alt={product?.name ?? "Product thumbnail"} />{canViewProducts ? <Link to={`/products/${review.product_id}`}>{product?.name ?? "View product"}</Link> : "Product"}</div> : "Deleted product";
          } },
          { key: "rating", header: "Rating", render: (review) => <span aria-label={`${review.rating} out of 5 stars`}>{review.rating} ★{review.is_verified_purchase ? " · Verified" : ""}</span> },
          { key: "customer", header: "Customer", render: (review) => review.user_id && canViewCustomers
            ? <Link to={`/customers/${review.user_id}`}>{customers.get(review.user_id)?.name ?? "View customer"}</Link>
            : review.user_id ? "Customer" : "Erased account" },
          { key: "text", header: "Review", render: (review) => <div className="review-copy">{review.title && <strong>{review.title}</strong>}<div>{review.comment || "No written review"}</div></div> },
          { key: "images", header: "Photos", render: (review) => review.images.length ? <div className="review-photos">{review.images.map((image) => <a key={image.id} href={mediaUrl(image.image_url)} target="_blank" rel="noreferrer"><ProductImage className="review-photo" url={image.image_url} alt={image.alt_text ?? "Customer review photo"} /></a>)}</div> : "—" },
          { key: "created_at", header: "Date", render: (review) => formatDate(review.created_at) },
          { key: "status", header: "Status", render: (review) => <Badge value={review.is_approved ? "APPROVED" : "UNPUBLISHED"} /> },
          { key: "actions", header: "Actions", render: (review) => canManage && (review.is_approved
            ? <ConfirmButton message="Hide this review from shoppers? It can be approved again later." className="" disabled={action.busy} onConfirm={() => moderate(review.id, false)}>Hide</ConfirmButton>
            : <button type="button" className="primary" onClick={() => moderate(review.id, true)} disabled={action.busy}>Approve</button>) },
        ]}
      />
      <Pagination meta={list.meta} onPageChange={setPage} />
    </div>
  );
}

function Requests() {
  const { can, user } = useAuth();
  const canViewCustomers = can(P.customersView);
  const canViewOrders = can(P.ordersView);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const list = useApi(() => listReviewRequests({ status, page, page_size: 20 }), [status, page]);
  const rows = useMemo(() => list.data ?? [], [list.data]);
  const orderIds = useMemo(() => [...new Set(rows.map((row) => row.order_id))], [rows]);
  const customerIds = useMemo(() => [...new Set(rows.map((row) => row.customer_id))], [rows]);
  const orders = useLookups<Order>(orderIds, getOrder, user?.tenant_id ?? "", canViewOrders);
  const tracking = useLookups<OrderTracking>(orderIds, getTracking, user?.tenant_id ?? "", canViewOrders);
  const customers = useLookups<CustomerDetail>(customerIds, getCustomer, user?.tenant_id ?? "", canViewCustomers);
  const action = useAction();
  return (
    <div className="panel reviews-table-panel">
      <StatusMessage status={action.status} />
      <div className="filters reviews-filters">
        <GuidedControl hint="Filter post-delivery review requests by their sending status." dismissible><select aria-label="Request status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">All requests</option>
          <option value="PENDING">Pending</option>
          <option value="SENT">Sent</option>
          <option value="COMPLETED">Completed</option>
          <option value="CANCELLED">Cancelled</option>
        </select></GuidedControl>
        {can(P.reviewsManage) && <button type="button" onClick={() => action.run(async () => { const result = await dispatchReviewRequests(); list.reload(); return result; }, "Due review requests processed", "Could not process requests")} disabled={action.busy}>Send due requests now</button>}
      </div>
      <DataTable
        rows={list.data}
        loading={list.loading}
        error={list.error}
        empty="No review requests match this view. Requests are created for eligible delivered orders."
        rowKey={(request) => request.id}
        columns={[
          { key: "order_id", header: "Order", render: (request) => canViewOrders ? <Link to={`/orders/${request.order_id}`}>{orders.get(request.order_id)?.order_number ?? "View order"}</Link> : "Order" },
          { key: "customer_id", header: "Customer", render: (request) => canViewCustomers
            ? <Link to={`/customers/${request.customer_id}`}>{customers.get(request.customer_id)?.name ?? "View customer"}</Link> : "Customer" },
          { key: "delivered_at", header: "Delivered", render: (request) => formatDate(canViewOrders ? tracking.get(request.order_id)?.events.filter((event) => event.status === "DELIVERED").at(-1)?.occurred_at : null) },
          { key: "created_at", header: "Requested", render: (request) => formatDate(request.created_at) },
          { key: "send_after", header: "Due", render: (request) => formatDate(request.send_after) },
          { key: "sent_at", header: "Sent", render: (request) => formatDate(request.sent_at) },
          { key: "status", header: "Status", render: (request) => <Badge value={request.status} /> },
        ]}
      />
      <Pagination meta={list.meta} onPageChange={setPage} />
    </div>
  );
}

export default ReviewSection;
