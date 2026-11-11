import { useState } from "react";
import { addMember, listMembers, updateMember } from "../../api/platform";
import { useAuth } from "../../auth/AuthContext";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { AssignableRole, Member } from "../../types/platform";
import "./store.css";

const ROLES: { value: AssignableRole; label: string; help: string }[] = [
  { value: "ADMIN", label: "Admin", help: "Everything except removing the owner." },
  { value: "PRODUCT_MANAGER", label: "Product manager", help: "Products, categories, inventory, content." },
  { value: "ORDER_MANAGER", label: "Order manager", help: "Orders, customers, shipping, returns." },
];
const ROLE_LABEL: Record<string, string> = { OWNER: "Owner", ...Object.fromEntries(ROLES.map((r) => [r.value, r.label])) };

/** People with a CliQ. merchant account who can manage this brand. */
export default function TeamSection() {
  const { brandId, merchant } = useAuth();
  const members = useApi(() => (brandId ? listMembers(brandId) : Promise.reject(new Error("Open a brand first."))), [brandId]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AssignableRole>("ORDER_MANAGER");
  const [error, setError] = useState<string | null>(null);
  const action = useAction();

  if (!brandId) return null;

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError("Enter their merchant account email.");
      return;
    }
    setError(null);
    const added = await action.run(() => addMember(brandId!, email.trim().toLowerCase(), role), "Added to the team.", "Could not add");
    if (added) {
      setEmail("");
      members.reload();
    }
  }

  const active = (members.data ?? []).filter((m) => m.status === "ACTIVE");

  return (
    <div className="store-page">
      <PageHeader title="Team" subtitle="Who can manage this brand, and what they can do" />
      <section className="panel store-panel" aria-labelledby="team-add">
        <h3 id="team-add">Add someone</h3>
        <p className="muted">They need a CliQ. merchant account first (they can create one at the sign-in page).</p>
        <form className="store-team-add" onSubmit={add} noValidate>
          <Field label="Email" error={error}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@yourbrand.com" />
          </Field>
          <Field label="Role" hint={ROLES.find((r) => r.value === role)?.help}>
            <select value={role} onChange={(e) => setRole(e.target.value as AssignableRole)}>
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </Field>
          <button className="primary" disabled={action.busy}>Add to team</button>
        </form>
        <StatusMessage status={action.status} />
      </section>

      <section className="panel store-panel" aria-labelledby="team-list">
        <h3 id="team-list">Members</h3>
        {members.error && <div className="status status-error" role="alert">{members.error}</div>}
        {members.loading && !members.data && <div className="state">Loading the team…</div>}
        <ul className="store-members">
          {active.map((m) => (
            <MemberRow key={m.id} brandId={brandId} member={m} isMe={m.account_id === merchant?.id} onChanged={members.reload} />
          ))}
        </ul>
      </section>
    </div>
  );
}

function MemberRow({ brandId, member, isMe, onChanged }: { brandId: string; member: Member; isMe: boolean; onChanged: () => void }) {
  const action = useAction();
  const owner = member.role === "OWNER";
  return (
    <li className="store-member">
      <div className="store-member-who">
        <strong>{member.name ?? member.email}{isMe && " (you)"}</strong>
        <span className="muted">{member.email}</span>
      </div>
      {owner ? (
        <span className="badge badge-info">Owner</span>
      ) : (
        <>
          <select
            aria-label={`Role for ${member.email}`}
            value={member.role}
            disabled={action.busy}
            onChange={async (e) => {
              if (await action.run(() => updateMember(brandId, member.id, { role: e.target.value as AssignableRole }), "Role updated.", "Could not change the role")) onChanged();
            }}
          >
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            {!ROLE_LABEL[member.role] && <option value={member.role}>{member.role}</option>}
          </select>
          <ConfirmButton
            className="danger"
            message={`Remove ${member.email} from this brand? They lose access immediately.`}
            confirmLabel="Remove"
            disabled={action.busy}
            onConfirm={async () => {
              if (await action.run(() => updateMember(brandId, member.id, { status: "REMOVED" }), null, "Could not remove")) onChanged();
            }}
          >
            Remove
          </ConfirmButton>
        </>
      )}
      <StatusMessage status={action.status} />
    </li>
  );
}
