import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import { inventoryProducts } from "./dashboardData";
import type { InventoryRow } from "./dashboardData";

export default function DashboardInventory({ rows, loading, error }: { rows: InventoryRow[] | null; loading: boolean; error: string | null }) {
  const { can } = useAuth();
  const products = rows ? inventoryProducts(rows) : [];
  const low = products.filter((product) => product.low);
  const out = products.filter((product) => product.out);
  const restock = products.filter((product) => product.low || product.out)
    .sort((a, b) => Number(b.out) - Number(a.out) || a.sellable - b.sellable || a.name.localeCompare(b.name)).slice(0, 4);
  const count = (label: string, value: number, filter: string) => {
    const content = <><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong></>;
    return can(P.catalogueView) ? <Link className="stat-card inventory-metric-link" to={`/inventory?stock_status=${filter}`} key={label}>{content}</Link>
      : <div className="stat-card" key={label}>{content}</div>;
  };
  return <section className="panel dashboard-inventory-health" aria-label="Inventory Health">
    <div className="panel-title"><h3>Inventory alerts</h3>{can(P.catalogueView) && <Link to="/inventory">Manage inventory</Link>}</div>
    {loading ? <p className="state" role="status">Loading inventory alerts…</p>
      : error || !rows ? <p className="state">Inventory counts are unavailable. Open Inventory for current stock.</p>
        : <>
          <div className="stat-grid dashboard-stock-counts">{count("Low-stock products", low.length, "low")}{count("Out-of-stock products", out.length, "out")}</div>
          {restock.length ? <div className="dashboard-restock"><h4>Restock soon</h4><ul>{restock.map((product) => <li key={product.id}>
            {can(P.catalogueView) ? <Link to={`/products/${product.id}`}>{product.name}</Link> : <span>{product.name}</span>}
            <span>{product.sellable} sellable</span>
          </li>)}</ul></div> : <p className="muted">No inventory alerts.</p>}
        </>}
  </section>;
}
