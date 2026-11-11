import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { listCustomers } from "../../api/customers";
import Badge from "../../components/common/Badge";
import GuidedControl from "../../components/guidance/GuidedControl";
import DataTable from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import { useApi } from "../../hooks/useApi";
import { useUrlFilters } from "../../hooks/useUrlFilters";
import { formatDate, formatMoney } from "../../utils/formatters";

function CustomerSection() {
  const navigate = useNavigate();
  const { params, setFilter, setPage } = useUrlFilters();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const list = useApi(
    () =>
      listCustomers({
        search: params.get("search"),
        status: params.get("status"),
        blocked: params.get("blocked") ?? undefined,
        sort: params.get("sort") ?? "newest",
        page: params.get("page") ?? 1,
      }),
    [params.toString()]
  );


  return (
    <div className="record-page">
      <PageHeader title="Customers" subtitle="Registered shoppers with their order history" />
      <form className="filters record-responsive-filters" onSubmit={(e: FormEvent) => { e.preventDefault(); setFilter("search", search.trim()); }}>
        <div className="record-search-row"><GuidedControl className="guided-control--wide" hint="Search customer names, phone numbers or email addresses." dismissible><input type="search" placeholder="Name, phone or email" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search customers" /></GuidedControl>
          <button type="submit">Search</button></div>
        <button type="button" className="record-filter-toggle" aria-expanded={mobileFiltersOpen} aria-controls="customer-secondary-filters" onClick={() => setMobileFiltersOpen((open) => !open)}>Filters{["status", "blocked", "sort"].filter((key) => params.has(key)).length ? ` (${["status", "blocked", "sort"].filter((key) => params.has(key)).length} active)` : ""} {mobileFiltersOpen ? "▴" : "▾"}</button>
        <div id="customer-secondary-filters" className="record-secondary-filters" data-open={mobileFiltersOpen}>
        <select aria-label="Status" value={params.get("status") ?? ""} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">Any status</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
        <GuidedControl hint="Find customers allowed or blocked from placing orders."><select aria-label="Ordering" value={params.get("blocked") ?? ""} onChange={(e) => setFilter("blocked", e.target.value)}>
          <option value="">Any ordering status</option>
          <option value="true">Blocked from ordering</option>
          <option value="false">Allowed to order</option>
        </select></GuidedControl>
        <GuidedControl hint="Order customers by recency, spending or order count."><select aria-label="Sort" value={params.get("sort") ?? "newest"} onChange={(e) => setFilter("sort", e.target.value)}>
          <option value="newest">Newest first</option>
          <option value="total_spent">Highest spend</option>
          <option value="orders">Most orders</option>
          <option value="last_order">Recent order</option>
        </select></GuidedControl>
        </div>
      </form>
      <div className="panel record-table-panel">
        <DataTable
          rows={list.data}
          loading={list.loading}
          error={list.error}
          empty="No customers found."
          rowKey={(c) => c.id}
          onRowClick={(c) => navigate(`/customers/${c.id}`)}
          columns={[
            { key: "id", header: "Customer ID", render: (c) => <span className="customer-id">{c.id}</span> },
            { key: "name", header: "Name", render: (c) => c.name ?? <span className="muted">No name</span> },
            { key: "phone", header: "Phone" },
            { key: "email", header: "Email", render: (c) => c.email ?? "-" },
            { key: "total_orders", header: "Orders", align: "right" },
            { key: "total_spent", header: "Total spent", align: "right", render: (c) => formatMoney(c.total_spent) },
            { key: "last_order_at", header: "Last order", render: (c) => formatDate(c.last_order_at) },
            { key: "status", header: "Status", render: (c) => <>{<Badge value={c.status} />} {c.order_blocked && <Badge value="BLOCKED" />}</> },
          ]}
        />
        <Pagination meta={list.meta} onPageChange={setPage} />
      </div>
    </div>
  );
}

export default CustomerSection;
