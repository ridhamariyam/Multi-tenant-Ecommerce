import { useState } from "react";
import { archiveVariant, createVariant, listVariants, updateVariant } from "../../api/variants";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { Variant } from "../../types/catalogue";
import { formatDate, formatMoney } from "../../utils/formatters";
import InventoryPanel from "./InventoryPanel";
import VariantForm from "./VariantForm";

function VariantSection({ productId, canManage }: { productId: string; canManage: boolean }) {
  const variants = useApi(() => listVariants(productId), [productId]);
  const action = useAction();
  const [editing, setEditing] = useState<Variant | "new" | null>(null);
  const [stockFor, setStockFor] = useState<string | null>(null);
  const stockVariant = variants.data?.find((v) => v.id === stockFor) ?? null;

  return (
    <div className="panel variant-table-panel">
      <div className="panel-title">
        <h3>Sizes, colours, prices &amp; stock</h3>
        {canManage && <button className="primary" onClick={() => setEditing("new")}>Add variant</button>}
      </div>
      <StatusMessage status={action.status} />
      <DataTable
        rows={variants.data}
        loading={variants.loading}
        error={variants.error}
        empty="No variants yet — add at least one so the product can be bought."
        rowKey={(v) => v.id}
        columns={[
          { key: "sku", header: "SKU" },
          { key: "options", header: "Size / colour", render: (v) => Object.values(v.options).join(" / ") || v.name },
          { key: "price", header: "Price", align: "right", render: (v) => formatMoney(v.price) },
          {
            key: "sale",
            header: "Sale",
            render: (v) =>
              v.sale_price ? (
                <span>
                  {formatMoney(v.sale_price)} {v.is_on_sale ? <Badge value="LIVE" /> : <span className="muted">scheduled</span>}
                  <br />
                  <small className="muted">{formatDate(v.sale_starts_at)} → {formatDate(v.sale_ends_at)}</small>
                </span>
              ) : "-",
          },
          { key: "stock", header: "Sellable", align: "right", render: (v) => <>{v.inventory?.sellable_quantity ?? "-"} {v.inventory?.is_low_stock && <Badge value="LOW" />}</> },
          { key: "status", header: "Status", render: (v) => <Badge value={v.status} /> },
          {
            key: "x",
            header: "",
            render: (v) => (
              <div className="toolbar">
                <button onClick={() => setStockFor(v.id)}>Stock</button>
                {canManage && <button onClick={() => setEditing(v)}>Edit</button>}
                {canManage && v.status !== "ARCHIVED" && (
                  <ConfirmButton message={`Archive ${v.sku}? It can no longer be bought.`} onConfirm={() => action.run(async () => { await archiveVariant(v.id); variants.reload(); }, "Variant archived", "Could not archive")}>Archive</ConfirmButton>
                )}
              </div>
            ),
          },
        ]}
      />
      {editing && (
        <Modal title={editing === "new" ? "Add variant" : `Edit ${editing.sku}`} onClose={() => setEditing(null)} showCloseButton={false} wide>
          <VariantForm
            variant={editing === "new" ? null : editing}
            busy={action.busy}
            onCancel={() => setEditing(null)}
            onSubmit={async ({ data, initialQuantity, lowStockThreshold }) => {
              const ok = await action.run(
                () => (editing === "new" ? createVariant(productId, { ...data, initial_quantity: initialQuantity, low_stock_threshold: lowStockThreshold }) : updateVariant(editing.id, data)),
                "Variant saved",
                "Could not save variant"
              );
              if (ok) {
                setEditing(null);
                variants.reload();
              }
            }}
          />
        </Modal>
      )}
      {stockVariant && (
        <Modal title={`Stock — ${stockVariant.sku}`} onClose={() => setStockFor(null)} wide>
          <InventoryPanel variant={stockVariant} canManage={canManage} onChanged={variants.reload} />
        </Modal>
      )}
    </div>
  );
}

export default VariantSection;
