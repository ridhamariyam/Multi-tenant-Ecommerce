import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import PageHeader from "../../components/common/PageHeader";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import Tabs from "../../components/common/Tabs";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import BlogTab from "./BlogTab";
import FaqTab from "./FaqTab";
import HomeSectionsTab from "./HomeSectionsTab";
import MediaTab from "./MediaTab";
import NavigationTab from "./NavigationTab";
import OverviewTab from "./OverviewTab";
import PagesTab from "./PagesTab";
import SiteSettingsTab from "./SiteSettingsTab";
import type { CmsTab } from "./websiteMap";
import { TAB_LABELS } from "./websiteMap";

const TAB_ORDER: CmsTab[] = ["overview", "home", "site", "pages", "faqs", "navigation", "blog", "media"];

function CmsSection() {
  const { can } = useAuth();
  const [tab, setTab] = useState<CmsTab>("overview");
  const [siteDirty, setSiteDirty] = useState(false);
  const { requestLeave, pendingLeave, cancelLeave, discardLeave } = useUnsavedChanges(siteDirty, () => setSiteDirty(false));
  return (
    <>
      <PageHeader
        title="Website content"
        subtitle={`Change what customers see on your website — no developer needed. ${can(P.cmsPublish) ? "You can publish changes." : "You can prepare drafts; someone with publish rights makes them live."}`}
      />
      <Tabs
        active={tab}
        onChange={(next) => requestLeave(() => setTab(next))}
        tabs={TAB_ORDER.map((key) => ({ key, label: TAB_LABELS[key] }))}
      />
      {tab === "overview" && <OverviewTab onOpen={setTab} />}
      {tab === "home" && <HomeSectionsTab />}
      {tab === "site" && <SiteSettingsTab onDirtyChange={setSiteDirty} />}
      {tab === "pages" && <PagesTab />}
      {tab === "faqs" && <FaqTab />}
      {tab === "navigation" && <NavigationTab />}
      {tab === "blog" && <BlogTab />}
      {tab === "media" && <MediaTab />}
      {pendingLeave && <ConfirmDialog title="Unsaved changes" message="You have unsaved changes. Do you want to discard them?" cancelLabel="Continue editing" confirmLabel="Discard changes" onCancel={cancelLeave} onConfirm={discardLeave} />}
    </>
  );
}

export default CmsSection;
