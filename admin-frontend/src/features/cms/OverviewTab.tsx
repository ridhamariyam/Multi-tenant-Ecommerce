import { STOREFRONT_ORIGIN } from "../../api/client";
import DataTable from "../../components/common/DataTable";
import type { CmsTab, WebsitePart } from "./websiteMap";
import { STOREFRONT_PAGES, TAB_LABELS, WEBSITE_MAP } from "./websiteMap";

interface Row {
  key: string;
  area: string;
  part: WebsitePart;
}

const cmsTab = (part: WebsitePart): CmsTab | null => (part.managedBy === "storefront" ? null : part.managedBy.cms);

const rows: Row[] = WEBSITE_MAP.flatMap(({ area, parts }) => parts.map((part) => ({ key: `${area}-${part.name}`, area, part })));

function ManagedBadge({ part }: { part: WebsitePart }) {
  const tab = cmsTab(part);
  return tab
    ? <span className="badge badge-ok">CMS · {TAB_LABELS[tab]}</span>
    : <span className="badge badge-neutral">Storefront-managed</span>;
}

function ViewLink({ path }: { path: string | null }) {
  if (!path || path.includes("…") || !STOREFRONT_ORIGIN) return null;
  return <a className="btn" href={`${STOREFRONT_ORIGIN}${path}`} target="_blank" rel="noreferrer">View</a>;
}

// The whole website at a glance: what each part is and where it is changed.
function OverviewTab({ onOpen }: { onOpen: (tab: CmsTab) => void }) {
  return (
    <div className="panel">
      <p className="muted">
        Everything on your website, and where it is managed. <strong>CMS</strong> parts you change in the tabs above.{" "}
        <strong>Storefront-managed</strong> pages were designed and built into the website itself — they are listed so you can see the whole site, and changing them needs the website team.
      </p>
      <DataTable
        rows={rows}
        rowKey={(r) => r.key}
        columns={[
          { key: "area", header: "Area", render: (r) => r.area },
          { key: "name", header: "Part", render: (r) => r.part.name },
          { key: "path", header: "On the website", render: (r) => r.part.path ?? "-" },
          { key: "managed", header: "Managed in", render: (r) => <ManagedBadge part={r.part} /> },
          { key: "note", header: "Notes", render: (r) => <span className="muted">{r.part.note || "-"}</span> },
          {
            key: "actions",
            header: "Actions",
            render: (r) => {
              const tab = cmsTab(r.part);
              return (
                <div className="toolbar">
                  {tab && <button type="button" onClick={() => onOpen(tab)}>Open {TAB_LABELS[tab]}</button>}
                  <ViewLink path={r.part.path} />
                </div>
              );
            },
          },
        ]}
      />
    </div>
  );
}

/** The information pages built into the storefront, shown read-only under the CMS pages. */
export function StorefrontPages() {
  return (
    <div className="panel">
      <div className="panel-title">
        <h3>Existing website pages</h3>
      </div>
      <p className="muted">These pages were designed and built into the website itself. They can't be edited here — changes to them go through the website team.</p>
      <DataTable
        rows={STOREFRONT_PAGES}
        rowKey={(p) => p.name}
        columns={[
          { key: "name", header: "Page", render: (p) => p.name },
          { key: "path", header: "On the website", render: (p) => p.path ?? "-" },
          { key: "managed", header: "Managed in", render: (p) => <ManagedBadge part={p} /> },
          { key: "note", header: "Notes", render: (p) => <span className="muted">{p.note}</span> },
          { key: "actions", header: "Actions", render: (p) => <ViewLink path={p.path} /> },
        ]}
      />
    </div>
  );
}

export default OverviewTab;
