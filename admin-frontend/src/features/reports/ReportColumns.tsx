import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Column } from "../../components/common/DataTable";
import { formatDate, formatMoney, label } from "../../utils/formatters";
import type { ReportRow as Row } from "./ReportTable";

const MONEY = new Set(["subtotal", "discount", "shipping", "cod_fee", "tax", "revenue", "returned_value", "net_revenue", "average_order_value", "gross_sales", "discounts", "net_sales", "discount_given", "order_revenue", "total_spent", "cancelled_value", "cod_revenue", "prepaid_revenue", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount"]);

// Generic columns from a row: money formatted, numbers right-aligned, ids linked.
export function columnsFor(rows: Row[], hide: string[] = [], currency?: string): Column<Row>[] {
  if (!rows.length) return [];
  return Object.keys(rows[0])
    .filter((k) => !hide.includes(k))
    .map((k) => ({
      key: k,
      header: label(k.replace(/_id$/, "")),
      align: typeof rows[0][k] === "number" || MONEY.has(k) ? ("right" as const) : undefined,
      render: (r: Row): ReactNode => {
        const v = r[k];
        if (k === "name" && r.customer_id) return <Link to={`/customers/${r.customer_id}`}>{v ?? "View customer"}</Link>;
        if (v === null) return "-";
        if (MONEY.has(k)) return formatMoney(v, currency);
        if (k === "product_name" && r.product_id) return <Link to={`/products/${r.product_id}`}>{v}</Link>;
        if (/_at$/.test(k)) return formatDate(String(v));
        return String(v);
      },
    }));
}

