import { useState } from "react";
import type { FormEvent } from "react";
import { createStaff, listPermissions, listStaff, resetStaffPassword, updateStaff } from "../../api/staff";
import { useAuth } from "../../auth/AuthContext";
import Badge from "../../components/common/Badge";
import GuidedControl from "../../components/guidance/GuidedControl";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import type { PermissionInfo, StaffMember } from "../../types/user";
import { formatDate } from "../../utils/formatters";
import "./users.css";

export const MIN_PASSWORD = 8;

// Admin only: every person gets their own account; staff get exactly the permissions ticked.
function UserSection() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const staff = useApi(() => listStaff({ page, search, status: status || undefined }), [page, search, status]);
  const permissions = useApi(() => listPermissions(), []);
  const action = useAction();
  const [editing, setEditing] = useState<StaffMember | "new" | null>(null);
  const [resetting, setResetting] = useState<StaffMember | null>(null);

  return (
    <div className="record-page staff-page">
      <PageHeader title="Staff & permissions" subtitle="Individual accounts for everyone who uses the admin panel" actions={<button className="primary" onClick={() => setEditing("new")}>Add staff member</button>} />
      <StatusMessage status={action.status} />
      <div className="filters staff-filters">
        <GuidedControl className="guided-control--wide" hint="Find staff by name, email or phone." dismissible><input type="search" aria-label="Search staff" placeholder="Search name, email, phone" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></GuidedControl>
        <GuidedControl hint="Show active or inactive staff accounts."><select aria-label="Staff status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option>
        </select></GuidedControl>
        {(search || status) && <button type="button" onClick={() => { setSearch(""); setStatus(""); setPage(1); }}>Clear filters</button>}
      </div>
      <div className="panel record-table-panel staff-table-panel">
        <DataTable
          rows={staff.data}
          loading={staff.loading}
          error={staff.error}
          empty="No staff accounts."
          rowKey={(s) => s.id}
          columns={[
            { key: "name", header: "Name", render: (s) => <>{s.name ?? "-"} {s.id === user?.id && <span className="muted">(you)</span>}</> },
            { key: "email", header: "Email", render: (s) => s.email ?? "-" },
            { key: "phone", header: "Phone" },
            { key: "role", header: "Role", render: (s) => <Badge value={s.role} /> },
            { key: "access", header: "Access", render: (s) => s.role === "ADMIN" ? "Full access" : s.permissions === null ? "Legacy read-only" : <details className="staff-access"><summary>{s.permissions.length} permissions</summary><ul>{s.permissions.map((key) => <li key={key}>{permissions.data?.find((p) => p.key === key)?.description ?? key}</li>)}</ul></details> },
            { key: "status", header: "Status", render: (s) => <Badge value={s.status} /> },
            { key: "created_at", header: "Added", render: (s) => formatDate(s.created_at) },
            { key: "x", header: "Actions", render: (s) => <div className="toolbar"><button onClick={() => setEditing(s)}>Edit</button><button onClick={() => setResetting(s)}>Reset password</button></div> },
          ]}
        />
        <Pagination meta={staff.meta} onPageChange={setPage} />
      </div>
      {editing && (
        <StaffModal
          member={editing === "new" ? null : editing}
          isSelf={editing !== "new" && editing.id === user?.id}
          permissions={permissions.data ?? []}
          busy={action.busy}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            const ok = await action.run(() => (editing === "new" ? createStaff(data) : updateStaff(editing.id, data)), editing === "new" ? "Staff account created" : "Staff account updated", "Could not save staff account");
            if (ok) { setEditing(null); staff.reload(); }
          }}
        />
      )}
      {resetting && (
        <PasswordModal
          member={resetting}
          busy={action.busy}
          onClose={() => setResetting(null)}
          onSave={async (password) => {
            const ok = await action.run(() => resetStaffPassword(resetting.id, password), "Password reset — their existing sessions were signed out", "Could not reset password");
            if (ok) setResetting(null);
          }}
        />
      )}
    </div>
  );
}

function StaffModal({ member, isSelf, permissions, busy, onClose, onSave }: { member: StaffMember | null; isSelf: boolean; permissions: PermissionInfo[]; busy: boolean; onClose: () => void; onSave: (d: object) => void }) {
  const [name, setName] = useState(member?.name ?? "");
  const [email, setEmail] = useState(member?.email ?? "");
  const [phone, setPhone] = useState(member?.phone ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"ADMIN" | "STAFF">(member?.role ?? "STAFF");
  const [status, setStatus] = useState<"ACTIVE" | "INACTIVE">(member?.status ?? "ACTIVE");
  const [granted, setGranted] = useState<string[]>(member?.permissions ?? member?.effective_permissions ?? []);
  const [attempted, setAttempted] = useState(false);
  const [pendingChange, setPendingChange] = useState<{ data: object; message: string } | null>(null);
  const signature = JSON.stringify({ name, email, phone, password, role, status, granted: [...granted].sort() });
  const [baseline] = useState(signature);
  const { requestLeave, pendingLeave, cancelLeave, discardLeave } = useUnsavedChanges(signature !== baseline, () => {});

  const groups = permissions.reduce<Record<string, PermissionInfo[]>>((acc, p) => {
    (acc[p.key.split(".")[0]] ??= []).push(p);
    return acc;
  }, {});
  const validate = () => {
    const problems: Record<string, string> = {};
    if (!name.trim()) problems.name = "Name is required.";
    if (!member) {
      if (!email.trim()) problems.email = "Email is required.";
      else if (!/^\S+@\S+\.\S+$/.test(email.trim())) problems.email = "Enter a valid email address.";
      if (!phone.trim()) problems.phone = "Phone is required.";
      if (password.length < MIN_PASSWORD) problems.password = `Password must be at least ${MIN_PASSWORD} characters.`;
    }
    return problems;
  };
  const fieldErrors = attempted ? validate() : {};

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (Object.keys(validate()).length) {
      setTimeout(() => (e.target as HTMLFormElement).querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    setAttempted(false);
    const perms = role === "STAFF" ? granted : null;
    const data = member ? { name: name.trim(), role, status, permissions: perms } : { name: name.trim(), email: email.trim(), phone: phone.trim(), password, role, permissions: perms };
    if (member?.status === "ACTIVE" && status === "INACTIVE") return setPendingChange({ data, message: "Deactivate this account? It will be signed out and cannot sign in until reactivated." });
    if (role === "ADMIN" && member?.role !== "ADMIN") return setPendingChange({ data, message: "Grant full admin access to this account?" });
    onSave(data);
  };

  return (
    <Modal title={member ? `Edit ${member.name ?? member.email}` : "Add staff member"} onClose={() => requestLeave(onClose)} showCloseButton={false} wide>
      <form className="form" onSubmit={submit} noValidate>
        <div className="form-grid">
          <Field label="Name" required error={fieldErrors.name}><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Email" required={!member} error={fieldErrors.email} hint={member ? "Cannot be changed here" : "Used to sign in"}><input type="email" value={email} disabled={!!member} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Phone" required={!member} error={fieldErrors.phone}><input value={phone} disabled={!!member} onChange={(e) => setPhone(e.target.value)} /></Field>
          {!member && <Field label="Temporary password" required error={fieldErrors.password} hint={`At least ${MIN_PASSWORD} characters`}><input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>}
          <Field label="Role" required hint={isSelf ? "You cannot change your own role" : undefined} guidance="Roles and access determine which Admin actions this person can use." guidanceDismissible>
            <select value={role} disabled={isSelf} onChange={(e) => setRole(e.target.value as "ADMIN" | "STAFF")}>
              <option value="STAFF">Staff (chosen permissions)</option>
              <option value="ADMIN">Admin (full access)</option>
            </select>
          </Field>
          {member && (
            <Field label="Status" required hint={isSelf ? "You cannot deactivate yourself" : "Inactive accounts are signed out and cannot sign in"}>
              <select value={status} disabled={isSelf} onChange={(e) => setStatus(e.target.value as "ACTIVE" | "INACTIVE")}>
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
              </select>
            </Field>
          )}
        </div>
        {role === "STAFF" && (
          <div className="panel">
            <div className="panel-title">
              <h4>Permissions</h4>
              <div className="toolbar"><button type="button" onClick={() => setGranted(permissions.filter((p) => p.key.endsWith(".view")).map((p) => p.key))}>View-only preset</button><button type="button" onClick={() => setGranted([])}>Clear</button></div>
            </div>
            {member?.permissions === null && <p className="notice">This account currently has legacy read-only access. Saving applies exactly the boxes ticked below.</p>}
            <div className="grid-3">
              {Object.entries(groups).map(([group, perms]) => (
                <div key={group}>
                  <strong style={{ textTransform: "capitalize" }}>{group}</strong>
                  {perms.map((p) => (
                    <label key={p.key} className="check" title={p.key}>
                      <input type="checkbox" checked={granted.includes(p.key)} onChange={(e) => setGranted(e.target.checked ? [...granted, p.key] : granted.filter((k) => k !== p.key))} />
                      {p.description}
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
        {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
        <div className="form-actions"><button type="button" onClick={() => requestLeave(onClose)}>Cancel</button><button className="primary" disabled={busy}>Save</button></div>
      </form>
      {pendingChange && <ConfirmDialog message={pendingChange.message} confirmLabel="Confirm change" onCancel={() => setPendingChange(null)} onConfirm={() => { onSave(pendingChange.data); setPendingChange(null); }} />}
      {pendingLeave && <ConfirmDialog title="Unsaved changes" message="You have unsaved changes. Do you want to discard them?" cancelLabel="Continue editing" confirmLabel="Discard changes" onCancel={cancelLeave} onConfirm={discardLeave} />}
    </Modal>
  );
}

function PasswordModal({ member, busy, onClose, onSave }: { member: StaffMember; busy: boolean; onClose: () => void; onSave: (password: string) => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [attempted, setAttempted] = useState(false);
  const { requestLeave, pendingLeave, cancelLeave, discardLeave } = useUnsavedChanges(!!password || !!confirm, () => {});
  const passwordError = password.length < MIN_PASSWORD ? `Password must be at least ${MIN_PASSWORD} characters.` : null;
  const confirmError = !confirm.trim() ? "Confirm the new password." : password !== confirm ? "Passwords do not match." : null;
  return (
    <Modal title={`Reset password for ${member.name ?? member.email}`} onClose={() => requestLeave(onClose)} showCloseButton={false}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); setAttempted(true); if (!passwordError && !confirmError) onSave(password); }} noValidate>
        <Field label="New password" required error={attempted ? passwordError : null}><input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <Field label="Confirm" required error={attempted ? confirmError : null}><input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
        {attempted && (passwordError || confirmError) && <div className="status status-error" role="alert">Please correct the password fields before continuing.</div>}
        <div className="form-actions"><button type="button" onClick={() => requestLeave(onClose)}>Cancel</button><button className="primary" disabled={busy}>Reset password</button></div>
      </form>
      {pendingLeave && <ConfirmDialog title="Unsaved changes" message="You have unsaved changes. Do you want to discard them?" cancelLabel="Continue editing" confirmLabel="Discard changes" onCancel={cancelLeave} onConfirm={discardLeave} />}
    </Modal>
  );
}

export default UserSection;
