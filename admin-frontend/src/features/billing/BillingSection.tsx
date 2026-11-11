import { useState } from "react";
import { cancelSubscription, confirmCheckout, getBilling, startCheckout } from "../../api/billing";
import type { Billing, Plan } from "../../api/billing";
import { useAuth } from "../../auth/AuthContext";
import ConfirmButton from "../../components/common/ConfirmButton";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { formatMoney } from "../../utils/formatters";
import { authorizeSubscription } from "./razorpayCheckout";
import "./billing.css";

const FEATURE_LABELS: Record<string, string> = {
  custom_domains: "Your own domain",
  sheets_export: "Google Sheets order export",
  ai_studio: "AI studio",
  lookbooks: "Lookbooks",
};

const STATUS_TEXT: Record<string, string> = {
  TRIALING: "Free trial",
  ACTIVE: "Active",
  PAST_DUE: "Payment failed — Razorpay is retrying",
  CANCELLED: "Cancelled",
};

const date = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { dateStyle: "medium" });
const limit = (n: number | null, unit: string) => (n === null ? `Unlimited ${unit}` : `${n} ${unit}`);
const price = (p: Plan) => (p.monthly_price === 0 ? "Free" : `${formatMoney(p.monthly_price / 100, p.currency)}/month`);

/** The brand's plan, what it uses, and upgrading / cancelling through Razorpay. */
export default function BillingSection() {
  const billing = useApi(getBilling, []);
  return (
    <div className="billing-page">
      <PageHeader title="Plan & billing" subtitle="Your plan, its limits, and payments to CliQ." />
      {billing.error && <div className="status status-error" role="alert">{billing.error}</div>}
      {!billing.data && !billing.error && <div className="state">Loading…</div>}
      {billing.data && <BillingView initial={billing.data} />}
    </div>
  );
}

function BillingView({ initial }: { initial: Billing }) {
  const { merchant } = useAuth();
  const [data, setData] = useState(initial);
  const action = useAction();
  const current = data.plan;
  const effective = data.effective_plan ?? current;
  const sub = data.subscription;
  const paid = sub?.billing_provider === "razorpay";

  async function upgrade(plan: Plan) {
    const started = await action.run(() => startCheckout(plan.code), null, "Could not start the payment");
    if (!started?.data) return;
    const c = started.data;
    let result;
    try {
      result = await authorizeSubscription(
        {
          keyId: c.key_id,
          subscriptionId: c.subscription_id,
          description: c.trial_days ? `${c.plan_name} — ${c.trial_days} days free, then monthly` : `${c.plan_name} — monthly`,
          email: merchant?.email,
        },
        (message) => action.setStatus({ type: "error", text: message }),
      );
    } catch (e) {
      action.setStatus({ type: "error", text: e instanceof Error ? e.message : String(e) });
      return;
    }
    if (result.kind === "dismissed") {
      action.setStatus({ type: "error", text: "Payment window closed. Your plan has not changed." });
      return;
    }
    const { kind: _kind, ...signed } = result;
    void _kind;
    const confirmed = await action.run(() => confirmCheckout(signed), `You're on ${c.plan_name}.`, "Could not confirm the payment");
    if (confirmed?.data) setData(confirmed.data);
  }

  return (
    <>
      <StatusMessage status={action.status} />
      <section className="panel billing-current" aria-labelledby="billing-current">
        <h3 id="billing-current">Current plan: {current?.name ?? "Unlimited"}</h3>
        {sub && (
          <p className="muted">
            {STATUS_TEXT[sub.status] ?? sub.status}
            {sub.status === "TRIALING" && <> until {date(sub.current_period_end)} — first charge then</>}
            {sub.status === "ACTIVE" && paid && !sub.cancel_at_period_end && <> · renews {date(sub.current_period_end)}</>}
            {sub.cancel_at_period_end && <> · ends {date(sub.current_period_end)}, then Free</>}
          </p>
        )}
        {sub?.lapsed && effective && (
          <div className="status status-error" role="alert">
            Your subscription lapsed, so the {effective.name} plan's limits apply until you pay again.
          </div>
        )}
        {effective && (
          <dl className="billing-usage">
            <div><dt>Products</dt><dd>{data.usage.products} / {effective.product_limit ?? "∞"}</dd></div>
            <div><dt>Team</dt><dd>{data.usage.staff} / {effective.staff_limit ?? "∞"}</dd></div>
          </dl>
        )}
        {paid && !sub?.cancel_at_period_end && (
          <ConfirmButton
            className="btn"
            title="Cancel your subscription?"
            confirmLabel="Cancel subscription"
            message="You keep your plan until the end of the period you've paid for, then move to Free. Nothing is deleted, but you can't add beyond Free's limits."
            onConfirm={async () => {
              const r = await action.run(() => cancelSubscription(), "Subscription cancelled.", "Could not cancel");
              if (r?.data) setData(r.data);
            }}
          >
            Cancel subscription
          </ConfirmButton>
        )}
      </section>

      {!data.online_billing && (
        <div className="notice" role="status">Online payment for plans isn't set up yet. Contact the CliQ team to change plans.</div>
      )}

      <div className="billing-plans">
        {data.plans.map((plan) => {
          const isCurrent = plan.code === current?.code;
          return (
            <section key={plan.code} className={`panel billing-plan ${isCurrent ? "is-current" : ""}`} aria-label={plan.name}>
              <h3>{plan.name}</h3>
              <p className="billing-price">{price(plan)}</p>
              <ul>
                <li>{limit(plan.product_limit, "products")}</li>
                <li>{limit(plan.staff_limit, plan.staff_limit === 1 ? "team member" : "team members")}</li>
                {plan.monthly_ai_credits > 0 && <li>{plan.monthly_ai_credits} AI credits a month</li>}
                {Object.entries(FEATURE_LABELS).map(([key, label]) => (
                  <li key={key} className={plan.features[key] ? "" : "billing-missing"}>{plan.features[key] ? "✓" : "—"} {label}</li>
                ))}
              </ul>
              {isCurrent ? (
                <span className="badge badge-ok">Your plan</span>
              ) : plan.monthly_price > 0 ? (
                <button className="primary" disabled={action.busy || !data.online_billing} onClick={() => upgrade(plan)}>
                  {sub?.trial_used ? `Switch to ${plan.name}` : `Start 14-day free trial`}
                </button>
              ) : null}
            </section>
          );
        })}
      </div>
      <p className="muted billing-note">
        Prices include no GST yet; invoices come from Razorpay. Paid plans renew monthly by UPI AutoPay or card until you cancel.
      </p>
    </>
  );
}
