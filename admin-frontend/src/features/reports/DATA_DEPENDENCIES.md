# Reports & Analytics data sources and limits

The six-tab Reports page uses existing frontend clients and existing tenant-scoped APIs. All report dates follow the backend's UTC date boundaries. The page does not change dedicated Admin management pages.

| Tab | Existing source | Supported information |
| --- | --- | --- |
| Overview | `/admin/reports/sales`, `/admin/reports/analytics` | Gross order subtotal, order revenue less returned-parcel value, orders, AOV, discounts, daily revenue/orders trends, COD vs prepaid order counts, top products, new vs returning customers. An optional equivalent previous period uses a second sales request. |
| Sales | `/admin/reports/sales`, `/admin/reports/sales-by-product`, `/admin/reports/sales-by-category`, `/admin/reports/sales-by-location` | Daily/weekly/monthly revenue, order volume, AOV, gross subtotal, discounts, tax and product/category/state/city breakdowns. Cancelled orders are excluded. The backend's `revenue` is non-cancelled order total; `net_revenue` subtracts returned parcel order value. |
| Products | `/admin/reports/sales-by-product`, `/admin/reports/sales-by-category`, `/admin/reports/unsold` | Top 100 products by revenue, units sold, revenue and category performance. The unsold endpoint accepts rolling days, so this page shows it only for the exact Last 7/Last 30 Days quick periods. |
| Customers | `/admin/reports/customers?top=100`, existing `/admin/customers/{id}` and `/admin/customers/{id}/orders` detail view | Period new/returning/ordering counts and top 100 customers' period spending and order counts. The report table omits phone and email; admins with `customers.view` can open the existing detail view from a customer ID or name for contact details, lifetime totals, last order, order history, saved addresses, status and permitted account actions. |
| Payments | `/admin/payments`, `/admin/reports/analytics`, `/admin/cod/report` | All-time payment record status counts, server-paged payment records, period COD/prepaid order counts, actual COD collections and parcel return rate. The COD/prepaid split is an **order payment type**, not a payment-method or settlement breakdown. |
| Returns | `/admin/reports/returns` | Returned-to-origin parcel count/rate/value, reasons and products. Returned parcel value is not a refund amount. |

Existing report endpoints retain server Excel, PDF and CSV exports for their supported query parameters, including date, grouping and breakdown. Search and sort in detailed report tables are client-side over the returned report, with 50 rows per page. Because those local filters are not accepted by the export APIs, locally filtered/sorted results offer a complete-subset CSV. The payments list has a current-page CSV only; it has no report export endpoint.

## Not available from existing APIs

- Refund transaction amount, count and trend; customer return requests and pending/approved/rejected states. The Returns report covers undelivered parcels, not customer return approvals.
- Per-day return/refund events needed for a return trend chart.
- Complete worst-seller ranking or exact custom-range no-sales list. Product sales are capped at the 100 highest-revenue products; unsold accepts a rolling day count only.
- Per-product time series, per-day new vs returning customer acquisition and individual purchase-frequency aggregates.
- Date-filtered payment transactions, payment-method identities (card/UPI/bank), payment amount breakdown by method, or a payment trend. The existing payment list is all-time; COD/PREPAID are providers, not settlement proof.
- Excel/PDF exports of local report search/sort or payment-list filters. The backend download endpoints do not accept those client-side parameters.

Unavailable metrics are labelled as such in the UI. No business figures or chart series are fabricated.
