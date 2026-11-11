import { Fragment } from "react";
import { getInvoice } from "../../api/orders";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import { useApi } from "../../hooks/useApi";
import { label } from "../../utils/formatters";

// The order's GST tax invoice exactly as the backend builds it (same data as the PDF).
function InvoiceModal({ orderId, onClose }: { orderId: string; onClose: () => void }) {
  const { data, error } = useApi(() => getInvoice(orderId), [orderId]);
  return (
    <Modal title="GST invoice" onClose={onClose} wide>
      {error && <div className="status status-error">{error}</div>}
      {!data && !error && <div className="state">Loading…</div>}
      {data && (
        <>
          <div className="grid-2">
            <dl className="kv">
              <dt>Invoice</dt><dd>{data.invoice_number}</dd>
              <dt>Date</dt><dd>{data.invoice_date}</dd>
              <dt>Supply</dt><dd>{data.gst_type ? label(data.gst_type) : "-"} · {data.place_of_supply ?? "-"}</dd>
            </dl>
            <dl className="kv">
              <dt>Seller</dt><dd>{data.seller.name ?? "-"} {data.seller.gstin && `(GSTIN ${data.seller.gstin})`}</dd>
              <dt>Buyer</dt><dd>{data.buyer.name ?? "-"}</dd>
            </dl>
          </div>
          <DataTable
            rows={data.lines}
            rowKey={(l) => `${l.description}-${l.sku}`}
            columns={[
              { key: "description", header: "Item" },
              { key: "hsn_code", header: "HSN/SAC" },
              { key: "quantity", header: "Qty", align: "right" },
              { key: "taxable_value", header: "Taxable", align: "right" },
              { key: "gst_rate", header: "GST %", align: "right" },
              { key: "cgst_amount", header: "CGST", align: "right" },
              { key: "sgst_amount", header: "SGST", align: "right" },
              { key: "igst_amount", header: "IGST", align: "right" },
              { key: "total", header: "Total", align: "right" },
            ]}
          />
          <dl className="kv" style={{ marginTop: 12 }}>
            {Object.entries(data.totals).map(([k, v]) => (<Fragment key={k}><dt>{label(k)}</dt><dd className="num">{v}</dd></Fragment>))}
          </dl>
        </>
      )}
    </Modal>
  );
}

export default InvoiceModal;
