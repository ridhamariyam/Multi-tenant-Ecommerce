import { Link, useOutletContext } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { P } from "../auth/permissions";
import PageHeader from "../components/common/PageHeader";
import type { GuidanceControls } from "../components/guidance/guidanceConfig";
import ContextualGuidance from "../components/guidance/ContextualGuidance";

export function Profile() {
  const { user } = useAuth();
  return <>
    <PageHeader title="Profile" subtitle="Your CliQ workspace account" />
    <div className="panel account-panel"><dl className="account-fields">
      <div><dt>Name</dt><dd>{user?.name || "—"}</dd></div>
      <div><dt>Email</dt><dd>{user?.email || "—"}</dd></div>
      <div><dt>Phone</dt><dd>{user?.phone || "—"}</dd></div>
      <div><dt>Role</dt><dd>{user?.role}</dd></div>
    </dl></div>
  </>;
}

export function Settings() {
  const { can, isAdmin } = useAuth();
  const { preference, setEnabled, resetDismissed } = useOutletContext<GuidanceControls>();
  const destinations = [
    { label: "Website settings", to: "/cms", permission: P.cmsView },
    { label: "Delivery", to: "/delivery", permission: P.settingsView },
    { label: "GST & invoicing", to: "/gst", permission: P.settingsView },
    { label: "Integrations", to: "/integrations", permission: P.settingsView },
  ].filter((item) => can(item.permission));
  return <>
    <PageHeader title="Settings" subtitle="Manage your CliQ workspace" />
    <div className="panel account-panel"><div className="account-settings-links">
      <Link to="/profile">Your profile <span aria-hidden="true">↗</span></Link>
      {destinations.map((item) => <Link key={item.to} to={item.to}>{item.label}<span aria-hidden="true">↗</span></Link>)}
      {isAdmin && <Link to="/staff">Staff & permissions <span aria-hidden="true">↗</span></Link>}
    </div></div>
    <section className="panel account-panel guidance-settings" aria-labelledby="guidance-settings-title">
      <h3 id="guidance-settings-title">Admin guidance</h3>
      <label className="guidance-toggle">
        <input type="checkbox" checked={preference.enabled} onChange={(event) => setEnabled(event.target.checked)} />
        <span><strong>Show page guidance</strong><small>Show short hints beside controls throughout Admin.</small></span>
      </label>
      <ContextualGuidance dismissible>Turn this off to hide hints on every Admin page. Turning it back on shows them again.</ContextualGuidance>
      <div className="guidance-reset">
        <p>Restore hints you have dismissed on all pages.</p>
        <button type="button" onClick={resetDismissed}>Show guidance again</button>
      </div>
    </section>
  </>;
}
