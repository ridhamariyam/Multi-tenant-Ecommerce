import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { getSite, updateSite } from "../../api/cms";
import { mediaUrl } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Field from "../../components/common/Field";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { SiteSettings, SocialNetwork } from "../../types/cms";
import { SOCIAL_NETWORKS } from "../../types/cms";
import MediaPicker from "./MediaPicker";
import { siteFieldErrors, siteProblem } from "./siteRules";

const NETWORK_NAMES: Record<SocialNetwork, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X (Twitter)",
  youtube: "YouTube",
  pinterest: "Pinterest",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
};

// Website-wide content shown in the header and footer of every page.
function SiteSettingsTab({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const site = useApi(() => getSite(), []);
  if (site.error) return <div className="status status-error">{site.error}</div>;
  if (!site.data) return <div className="state">Loading…</div>;
  return <SiteForm initial={site.data} onDirtyChange={onDirtyChange} />;
}

function SiteForm({ initial, onDirtyChange }: { initial: SiteSettings; onDirtyChange: (dirty: boolean) => void }) {
  const { can } = useAuth();
  const canSave = can(P.cmsPublish);
  const action = useAction();
  const [f, setF] = useState<SiteSettings>(initial);
  const [baseline, setBaseline] = useState(JSON.stringify(initial));
  useEffect(() => onDirtyChange(canSave && JSON.stringify(f) !== baseline), [f, baseline, canSave, onDirtyChange]);
  const [attempted, setAttempted] = useState(false);
  const fieldErrors = attempted ? siteFieldErrors(f) : {};
  const [uploading, setUploading] = useState(false);
  const set = (k: keyof SiteSettings) => (e: { target: { value: string } }) => setF((prev) => ({ ...prev, [k]: e.target.value }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    const problem = siteProblem(f);
    if (problem) return;
    setAttempted(false);
    const blank = (v: string | null) => (v && v.trim() ? v.trim() : null);
    action.run(
      async () => {
        const saved = await updateSite({
          logo_url: blank(f.logo_url),
          logo_alt: blank(f.logo_alt),
          tagline: blank(f.tagline),
          contact_email: blank(f.contact_email),
          contact_phone: blank(f.contact_phone),
          whatsapp_number: blank(f.whatsapp_number),
          address: blank(f.address),
          social_links: Object.fromEntries(Object.entries(f.social_links).filter(([, url]) => url && url.trim()).map(([k, url]) => [k, url!.trim()])),
          copyright_text: blank(f.copyright_text),
        });
        setF(saved.data);
        setBaseline(JSON.stringify(saved.data));
      },
      "Saved — live on the website now",
      "Could not save"
    );
  };

  return (
    <form className="form" onSubmit={submit} noValidate>
      <p className="help">These appear on every page of your website: the logo at the top, and the tagline, contact details and social links at the bottom. Leave anything blank to hide it.</p>
      {!canSave && <p className="notice">You can view these settings; saving them needs the “publish website content” permission.</p>}
      <StatusMessage status={action.status} />
      <fieldset disabled={!canSave} className="form" style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="panel">
          <h3>Logo</h3>
          <div className="grid-2">
            <MediaPicker label="Logo picture" hint="Without a logo, the website shows the name “CliQ.” in text." value={f.logo_url ?? ""} onChange={(v) => setF((prev) => ({ ...prev, logo_url: v || null }))} onUploadingChange={setUploading} />
            <div className="form">
              <Field label="Logo description" hint="Read out by screen readers, e.g. “CliQ.”"><input value={f.logo_alt ?? ""} onChange={set("logo_alt")} maxLength={255} /></Field>
              <div>
                <span className="field-label">How it looks in the header</span>
                <div className="preview-box" style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 64 }}>
                  {f.logo_url ? <img src={mediaUrl(f.logo_url)} alt={f.logo_alt ?? ""} style={{ maxHeight: 40, maxWidth: 200 }} /> : <strong style={{ letterSpacing: "0.2em" }}>CliQ.</strong>}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="panel">
          <h3>Footer text</h3>
          <div className="form-grid">
            <Field label="Tagline" hint="The short line under the name in the footer" wide><textarea value={f.tagline ?? ""} onChange={set("tagline")} maxLength={500} rows={2} /></Field>
            <Field label="Copyright line" hint="e.g. © 2026 CliQ. All rights reserved."><input value={f.copyright_text ?? ""} onChange={set("copyright_text")} maxLength={255} /></Field>
          </div>
        </div>
        <div className="panel">
          <h3>Contact details</h3>
          <div className="form-grid">
            <Field label="Email" error={fieldErrors.contact_email}><input type="email" value={f.contact_email ?? ""} onChange={set("contact_email")} placeholder="hello@cliq.example" /></Field>
            <Field label="Phone" error={fieldErrors.contact_phone}><input value={f.contact_phone ?? ""} onChange={set("contact_phone")} placeholder="+91 98765 43210" /></Field>
            <Field label="WhatsApp number" error={fieldErrors.whatsapp_number} hint="Shown as a “Chat on WhatsApp” link"><input value={f.whatsapp_number ?? ""} onChange={set("whatsapp_number")} placeholder="+91 98765 43210" /></Field>
            <Field label="Address" wide><textarea value={f.address ?? ""} onChange={set("address")} maxLength={500} rows={2} /></Field>
          </div>
        </div>
        <div className="panel">
          <h3>Social media</h3>
          <p className="muted">Paste the full link to each profile (starting with https://). Leave blank to hide that icon.</p>
          <div className="form-grid">
            {SOCIAL_NETWORKS.map((network) => (
              <Field key={network} label={NETWORK_NAMES[network]} error={fieldErrors[network]}>
                <input
                  value={f.social_links[network] ?? ""}
                  onChange={(e) => setF((prev) => ({ ...prev, social_links: { ...prev.social_links, [network]: e.target.value } }))}
                  placeholder={`https://${network === "x" ? "x" : network}.com/cliq`}
                  maxLength={500}
                />
              </Field>
            ))}
          </div>
        </div>
      </fieldset>
      {Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please correct the highlighted fields before continuing.</div>}
      {canSave && <div className="form-actions"><button className="primary" disabled={action.busy || uploading}>{uploading ? "Waiting for the logo to finish uploading…" : "Save website details"}</button></div>}
    </form>
  );
}

export default SiteSettingsTab;
