import { useState } from "react";
import { disconnectPaymentGateway, getPaymentGateway, savePaymentGateway } from "../../api/payments";
import type { PaymentGateway } from "../../api/payments";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";

/**
 * Online payments go straight to the brand's own Razorpay account. The key
 * secret and webhook secret are sent once, checked with Razorpay, stored
 * encrypted and never shown again.
 */
export default function PaymentGatewayPanel({ canEdit }: { canEdit: boolean }) {
  const gw = useApi(getPaymentGateway, []);
  if (gw.error) return <div className="status status-error" role="alert">{gw.error}</div>;
  if (!gw.data) return <div className="state">Loading payments…</div>;
  return <GatewayForm initial={gw.data} canEdit={canEdit} />;
}

function GatewayForm({ initial, canEdit }: { initial: PaymentGateway; canEdit: boolean }) {
  const [current, setCurrent] = useState(initial);
  const [keyId, setKeyId] = useState(initial.source === "own" ? initial.key_id ?? "" : "");
  const [keySecret, setKeySecret] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const action = useAction();
  const own = current.source === "own";

  return (
    <section className="panel order-sheet-panel" aria-labelledby="payment-gateway-title">
      <h3 id="payment-gateway-title">Online payments — Razorpay</h3>
      {current.source === "platform" ? (
        <div className="notice" role="status">
          This store uses the platform&apos;s Razorpay account{current.key_id ? <> (<code>{current.key_id}</code>, {current.mode})</> : " — not configured on the server yet"}.
        </div>
      ) : (
        <p className="muted">
          {own && current.connected
            ? <>Connected: <code>{current.key_id}</code> ({current.mode === "live" ? "live — real payments" : "test mode"}). Customers pay straight into your Razorpay account.</>
            : "Connect your Razorpay account to accept UPI, cards and net banking. Until then customers can only pay cash on delivery."}
        </p>
      )}

      {current.source !== "platform" && (
        <>
          <ol className="order-sheet-steps">
            <li>In Razorpay Dashboard open <strong>Account &amp; Settings → API Keys</strong> and generate a key. Copy the Key Id and Key Secret.</li>
            <li>
              Open <strong>Account &amp; Settings → Webhooks → Add New Webhook</strong>, set the URL to{" "}
              <code className="order-sheet-email">{current.webhook_url}</code>, choose a secret, and tick <em>payment.captured</em>, <em>order.paid</em>, <em>refund.processed</em> and <em>refund.failed</em>.
            </li>
            <li>Paste the keys and the webhook secret below and save. We check them with Razorpay first.</li>
          </ol>

          <StatusMessage status={action.status} />
          <form
            className="form"
            onSubmit={async (e) => {
              e.preventDefault();
              const saved = await action.run(
                () => savePaymentGateway({ key_id: keyId.trim(), key_secret: keySecret || null, webhook_secret: webhookSecret || null, is_enabled: true }),
                "Razorpay connected. Customers can now pay online.",
                "Could not connect Razorpay",
              );
              if (saved?.data) {
                setCurrent(saved.data);
                setKeySecret("");
                setWebhookSecret("");
              }
            }}
          >
            <fieldset className="form" disabled={!canEdit || action.busy} style={{ border: 0, padding: 0 }}>
              <div className="form-grid">
                <Field label="Key Id" hint="Starts with rzp_live_ (real payments) or rzp_test_ (testing).">
                  <input value={keyId} onChange={(e) => setKeyId(e.target.value)} placeholder="rzp_live_…" maxLength={64} required autoComplete="off" />
                </Field>
                <Field label="Key Secret" hint={own ? "Leave empty to keep the saved secret." : undefined}>
                  <input type="password" value={keySecret} onChange={(e) => setKeySecret(e.target.value)} maxLength={200} required={!own} autoComplete="new-password" />
                </Field>
                <Field label="Webhook secret" hint={current.has_webhook_secret ? "Saved. Leave empty to keep it." : "Confirms payments even if the customer closes the page."}>
                  <input type="password" value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} maxLength={200} autoComplete="new-password" />
                </Field>
              </div>
              {canEdit && (
                <div className="order-sheet-actions">
                  <button className="primary" disabled={action.busy}>{own ? "Update" : "Connect Razorpay"}</button>
                  {own && (
                    <ConfirmButton
                      message="Customers will only be able to pay cash on delivery until you connect Razorpay again."
                      confirmLabel="Disconnect"
                      title="Turn off online payments?"
                      onConfirm={async () => {
                        const result = await action.run(() => disconnectPaymentGateway(), "Disconnected. Only cash on delivery is offered now.", "Could not disconnect");
                        if (result?.data) {
                          setCurrent(result.data);
                          setKeyId("");
                        }
                      }}
                    >
                      Disconnect
                    </ConfirmButton>
                  )}
                </div>
              )}
            </fieldset>
          </form>
          {own && !current.has_webhook_secret && (
            <div className="status status-warn" role="status">Add the webhook secret so payments are confirmed even when a customer closes the page before returning.</div>
          )}
        </>
      )}
    </section>
  );
}
