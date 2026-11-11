import { listIntegrations } from "../../api/integrations";
import DataTable from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import { useApi } from "../../hooks/useApi";
import type { Integration } from "../../types/settings";
import "./integrations.css";

const SETUP_STEPS: Record<string, string> = {
  ccavenue: "Merchant credentials and payment gateway integration are required. Ask the project lead to complete setup.",
  shiprocket: "Courier account configuration and booking integration are required. Ask the project lead to complete setup.",
  msg91_customer_otp: "OTP verification is implemented. Ask the project lead to configure the provider account.",
  msg91_admin_otp: "Admin OTP template and sign-in integration are required. Ask the project lead to complete setup.",
  email: "Email provider configuration and sending integration are required. Ask the project lead to complete setup.",
  whatsapp: "WhatsApp provider configuration and messaging integration are required. Ask the project lead to complete setup.",
};
const IMPLEMENTATION_STEPS: Record<string, string> = {
  ccavenue: "Merchant credentials are present. Ask the project lead to complete and verify payment gateway integration.",
  shiprocket: "Courier credentials are present. Ask the project lead to complete and verify booking integration.",
  msg91_admin_otp: "Credentials are present. Ask the project lead to complete admin OTP sign-in integration.",
  email: "Credentials are present. Ask the project lead to complete email sending integration.",
  whatsapp: "Credentials are present. Ask the project lead to complete messaging integration.",
};

// The current API reports configuration and implementation, not live provider health.
function setupStatus(integration: Integration) {
  if (!integration.credentials_configured) return { text: "Credentials missing", tone: "warn" };
  if (!integration.integrated) return { text: "Configuration incomplete", tone: "info" };
  return { text: "Configured · not verified", tone: "info" };
}

function nextStep(integration: Integration) {
  if (integration.credentials_configured && integration.integrated) return "Provider health cannot be checked here; the sign-in flow is configured.";
  if (integration.credentials_configured) return IMPLEMENTATION_STEPS[integration.key] ?? "Ask the project lead to complete and verify the provider integration.";
  return SETUP_STEPS[integration.key] ?? "Ask the project lead to complete this integration's server setup.";
}

// Read-only: credentials live in the backend's environment, never in this app.
function IntegrationsSection() {
  const list = useApi(() => listIntegrations(), []);
  return (
    <div className="integrations-page">
      <PageHeader title="Integrations" subtitle="External services and their setup progress" />
      <p className="muted integrations-intro">The project lead configures these services on the server. Status shows setup progress, not a verified live connection.</p>
      <div className="panel integrations-table-panel">
        <DataTable
          rows={list.data}
          loading={list.loading}
          error={list.error}
          rowKey={(i) => i.key}
          columns={[
            { key: "name", header: "Service", render: (i) => <strong>{i.name}</strong> },
            { key: "purpose", header: "Used for" },
            { key: "status", header: "Status", render: (i) => {
              const status = setupStatus(i);
              return <span className={`badge badge-${status.tone}`}>{status.text}</span>;
            } },
            { key: "next", header: "Next step", render: (i) => <><span>{nextStep(i)}</span><details className="integrations-technical"><summary>Technical setup</summary><p>{i.note}</p><p>Server settings: <code>{i.required_settings.join(", ")}</code></p></details></> },
          ]}
        />
      </div>
    </div>
  );
}

export default IntegrationsSection;
