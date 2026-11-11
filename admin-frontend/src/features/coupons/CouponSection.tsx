import { useMemo, useState } from "react";
import { fetchAllPages } from "../../api/client";
import { listCategories } from "../../api/categories";
import { createCoupon, deleteCoupon, listCoupons, updateCoupon } from "../../api/coupons";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import ConfirmButton from "../../components/common/ConfirmButton";
import GuidedControl from "../../components/guidance/GuidedControl";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { PageMeta } from "../../types/api";
import type { Coupon } from "../../types/coupon";
import { WEEKDAYS } from "../../types/coupon";
import { formatDate, formatMoney, label } from "../../utils/formatters";
import CouponForm from "./CouponForm";
import "./coupons.css";

const PAGE_SIZE = 20;
const FETCH_SIZE = 100;

function describe(c: Coupon): string {
  switch (c.discount_type) {
    case "PERCENTAGE":
      return `${Number(c.discount_value)}% off${c.max_discount_amount ? ` (max ${formatMoney(c.max_discount_amount)})` : ""}`;
    case "FIXED_AMOUNT":
      return `${formatMoney(c.discount_value)} off`;
    case "FREE_SHIPPING":
      return "Free shipping";
    case "BOGO":
      return `Buy ${c.buy_quantity} get ${c.get_quantity} at ${Number(c.discount_value)}% off`;
  }
}

function couponStatus(coupon: Coupon, now: Date) {
  if (!coupon.is_active) return "INACTIVE";
  if (coupon.starts_at && now < new Date(coupon.starts_at)) return "SCHEDULED";
  if (coupon.expires_at && now > new Date(coupon.expires_at)) return "EXPIRED";
  return "ACTIVE";
}

function CouponSection() {
  const { can } = useAuth();
  const canManage = can(P.couponsManage);
  const [activeOnly, setActiveOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offer, setOffer] = useState("");
  const [page, setPage] = useState(1);
  const categories = useApi(() => listCategories(), []);
  const [editing, setEditing] = useState<Coupon | "new" | null>(null);
  const action = useAction();

  const coupons = useApi(() => fetchAllPages((page) => listCoupons({ page, page_size: FETCH_SIZE }), "coupons"), []);

  const loading = coupons.loading;
  const records = coupons.data;
  const filtered = useMemo(() => records?.filter((coupon) =>
    (!activeOnly || coupon.is_active) &&
    (!search || coupon.code.toLowerCase().includes(search.trim().toLowerCase())) &&
    (!status || couponStatus(coupon, new Date()) === status) &&
    (!offer || coupon.discount_type === offer)
  ) ?? [], [records, activeOnly, search, status, offer]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const rows = records ? filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE) : null;
  const meta: PageMeta | null = records ? { page: currentPage, page_size: PAGE_SIZE, total_items: filtered.length, total_pages: totalPages } : null;
  const clearFilters = () => { setActiveOnly(false); setSearch(""); setStatus(""); setOffer(""); setPage(1); };

  return (
    <div className="record-page coupon-page">
      <PageHeader title="Coupons & offers" actions={canManage && <button className="primary" onClick={() => setEditing("new")}>New coupon</button>} />
      <StatusMessage status={action.status} />
      <div className="filters coupon-filters">
        <GuidedControl className="guided-control--wide" hint="Find an offer by its coupon code." dismissible><input type="search" aria-label="Search coupon code" placeholder="Search code" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></GuidedControl>
        <GuidedControl hint="Show active, inactive, expired or scheduled offers."><select aria-label="Coupon status" value={status} onChange={(event) => { setStatus(event.target.value); if (event.target.value === "INACTIVE") setActiveOnly(false); setPage(1); }}>
          <option value="">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option><option value="EXPIRED">Expired</option><option value="SCHEDULED">Scheduled</option>
        </select></GuidedControl>
        <GuidedControl hint="Filter coupons by the kind of discount offered."><select aria-label="Offer type" value={offer} onChange={(event) => { setOffer(event.target.value); setPage(1); }}>
          <option value="">All offers</option><option value="PERCENTAGE">Percentage</option><option value="FIXED_AMOUNT">Fixed amount</option><option value="FREE_SHIPPING">Free shipping</option><option value="BOGO">Buy one get one</option>
        </select></GuidedControl>
        <label className="check"><input type="checkbox" checked={activeOnly} onChange={(event) => { setActiveOnly(event.target.checked); if (event.target.checked && status === "INACTIVE") setStatus(""); setPage(1); }} /> Enabled only</label>
        <button type="button" onClick={clearFilters} disabled={!activeOnly && !search && !status && !offer}>Clear Filters</button>
      </div>
      <div className="panel record-table-panel coupon-table-panel">
        <DataTable
          rows={rows}
          loading={loading}
          error={loading ? null : coupons.error}
          empty={activeOnly || search || status || offer ? "No coupons match these filters." : "No coupons yet."}
          rowKey={(c) => c.id}
          onRowClick={canManage ? (c) => setEditing(c) : undefined}
          columns={[
            { key: "code", header: "Code", render: (c) => canManage ? <button type="button" className="link coupon-code" onClick={(event) => { event.stopPropagation(); setEditing(c); }}>{c.code}</button> : <strong>{c.code}</strong> },
            { key: "type", header: "Offer", render: describe },
            {
              key: "rules",
              header: "Conditions",
              render: (c) =>
                [
                  c.is_automatic && "automatic",
                  c.first_order_only && "first order",
                  c.min_order_amount && `min ${formatMoney(c.min_order_amount)}`,
                  c.min_quantity && `min ${c.min_quantity} items`,
                  c.category_ids.length > 0 && `${c.category_ids.length} categories`,
                  c.valid_weekdays.length > 0 && `only ${c.valid_weekdays.map((d) => WEEKDAYS[d]).join("/")}`,
                ].filter(Boolean).join(", ") || "-",
            },
            { key: "dates", header: "Valid", render: (c) => <span className="coupon-dates"><span>From {c.starts_at ? formatDate(c.starts_at) : "immediately"}</span><span>Until {c.expires_at ? formatDate(c.expires_at) : "no expiry"}</span></span> },
            { key: "times_used", header: "Used", align: "right", render: (c) => `${c.times_used} / ${c.usage_limit === null ? "unlimited" : c.usage_limit}` },
            { key: "is_active", header: "Status", render: (c) => {
              const status = couponStatus(c, new Date());
              return <span className={`badge badge-${status === "ACTIVE" ? "ok" : status === "INACTIVE" || status === "EXPIRED" ? "bad" : "info"}`}>{label(status)}</span>;
            } },
            {
              key: "x",
              header: "",
              render: (c) =>
                canManage && (
                  <ConfirmButton message={`Delete coupon ${c.code}?`} onConfirm={() => action.run(async () => { await deleteCoupon(c.id); coupons.reload(); }, "Coupon deleted", "Could not delete coupon")}>
                    Delete
                  </ConfirmButton>
                ),
            },
          ]}
        />
        <Pagination meta={meta} onPageChange={setPage} />
      </div>
      {editing && (
        <Modal title={editing === "new" ? "New coupon" : `Edit ${editing.code}`} onClose={() => setEditing(null)} showCloseButton={false} wide>
          <CouponForm
            coupon={editing === "new" ? null : editing}
            categories={categories.data ?? []}
            busy={action.busy}
            onCancel={() => setEditing(null)}
            onSubmit={async (payload) => {
              const ok = await action.run(
                () => (editing === "new" ? createCoupon(payload) : updateCoupon(editing.id, payload)),
                editing === "new" ? "Coupon created" : "Coupon saved",
                `Could not save coupon (${label(payload.discount_type)})`
              );
              if (ok) {
                setEditing(null);
                coupons.reload();
              }
            }}
          />
        </Modal>
      )}
    </div>
  );
}

export default CouponSection;
