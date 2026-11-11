import { useEffect, useState } from "react";
import { createCampaign, listCampaigns, marketingSummary, segmentAudience, sendCampaign } from "../../api/marketing";
import type { Campaign, Segment } from "../../api/marketing";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";

const SEGMENTS: { value: Segment["kind"]; label: string }[] = [
  { value: "ALL", label: "Everyone subscribed" },
  { value: "ORDERED_WITHIN", label: "Ordered in the last N days" },
  { value: "NO_ORDERS", label: "Subscribed but never ordered" },
  { value: "TAG", label: "Customers with a tag" },
];
const describe = (s: Segment) =>
  s.kind === "ORDERED_WITHIN" ? `Ordered in the last ${s.days ?? 90} days` : s.kind === "TAG" ? `Tagged “${s.tag}”` : SEGMENTS.find((x) => x.value === s.kind)?.label ?? s.kind;

/** Email campaigns to customers who agreed to marketing email. */
export default function CampaignsSection() {
  const { can } = useAuth();
  const summary = useApi(marketingSummary, []);
  const campaigns = useApi(listCampaigns, []);
  const canSend = can(P.customersManage);
  return (
    <div className="campaigns-page">
      <PageHeader title="Email campaigns" subtitle="Only customers who opted in receive these; every email has an unsubscribe link." />
      {summary.data && (
        <p className="muted">
          <strong>{summary.data.subscribed}</strong> of {summary.data.customers} customers get marketing email.
        </p>
      )}
      {canSend && <Composer onCreated={() => campaigns.reload()} />}
      <section className="panel" aria-label="Campaigns">
        <h3>Campaigns</h3>
        {campaigns.error && <div className="status status-error" role="alert">{campaigns.error}</div>}
        {campaigns.data?.length === 0 && <p className="muted">No campaigns yet.</p>}
        <ul className="platform-list">
          {(campaigns.data ?? []).map((c) => <CampaignRow key={c.id} campaign={c} canSend={canSend} onSent={() => campaigns.reload()} />)}
        </ul>
      </section>
    </div>
  );
}

function CampaignRow({ campaign, canSend, onSent }: { campaign: Campaign; canSend: boolean; onSent: () => void }) {
  const action = useAction();
  return (
    <li className="platform-row">
      <div className="platform-row-main">
        <strong>{campaign.name}</strong>
        <span className="muted">“{campaign.subject}” · {describe(campaign.segment)}</span>
        {campaign.status === "SENT" ? (
          <span>Sent to {campaign.recipients} on {new Date(campaign.sent_at!).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>
        ) : (
          <span>Draft · would reach {campaign.audience ?? 0} customers now</span>
        )}
        <StatusMessage status={action.status} />
      </div>
      {campaign.status === "DRAFT" && canSend && (
        <ConfirmButton
          className="primary"
          title="Send this campaign?"
          confirmLabel="Send now"
          message={`“${campaign.subject}” goes to ${campaign.audience ?? 0} customers. This can't be undone.`}
          disabled={action.busy || !campaign.audience}
          onConfirm={async () => {
            if (await action.run(() => sendCampaign(campaign.id), "Sending. Emails go out over the next few minutes.", "Could not send")) onSent();
          }}
        >
          Send
        </ConfirmButton>
      )}
    </li>
  );
}

function Composer({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState({ name: "", subject: "", body: "" });
  const [segment, setSegment] = useState<Segment>({ kind: "ALL" });
  const [audience, setAudience] = useState<number | null>(null);
  const action = useAction();

  useEffect(() => {
    let stale = false;
    if (segment.kind === "TAG" && !segment.tag?.trim()) return setAudience(null);
    segmentAudience(segment).then((r) => !stale && setAudience(r.data?.count ?? null)).catch(() => !stale && setAudience(null));
    return () => { stale = true; };
  }, [segment]);

  return (
    <form
      className="panel form"
      aria-label="New campaign"
      onSubmit={async (e) => {
        e.preventDefault();
        const created = await action.run(() => createCampaign({ ...form, segment }), "Draft saved. Review it below, then send.", "Could not save");
        if (created) {
          setForm({ name: "", subject: "", body: "" });
          onCreated();
        }
      }}
    >
      <h3>New campaign</h3>
      <StatusMessage status={action.status} />
      <div className="form-grid">
        <Field label="Name (only you see it)"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={150} required /></Field>
        <Field label="Subject"><input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} maxLength={200} required /></Field>
        <Field label="Message" hint="Plain text. Leave a blank line between paragraphs." wide>
          <textarea rows={7} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} maxLength={20000} required />
        </Field>
        <Field label="Send to">
          <select value={segment.kind} onChange={(e) => setSegment({ kind: e.target.value as Segment["kind"], days: 90 })}>
            {SEGMENTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </Field>
        {segment.kind === "ORDERED_WITHIN" && (
          <Field label="Days"><input type="number" min={1} max={3650} value={segment.days ?? 90} onChange={(e) => setSegment({ ...segment, days: Number(e.target.value) || 90 })} /></Field>
        )}
        {segment.kind === "TAG" && (
          <Field label="Tag"><input value={segment.tag ?? ""} onChange={(e) => setSegment({ ...segment, tag: e.target.value })} maxLength={50} /></Field>
        )}
      </div>
      <p className="muted">Reaches <strong>{audience ?? "…"}</strong> customers right now.</p>
      <button className="primary" disabled={action.busy}>Save draft</button>
    </form>
  );
}
