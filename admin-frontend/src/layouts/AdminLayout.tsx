import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Header from "./Header";
import { GuidanceContext } from "../components/guidance/GuidanceContext";
import { guidanceForPath, guidanceStorageKey, readGuidance, writeGuidance } from "../components/guidance/guidanceConfig";
import type { GuidanceControls, GuidancePreference } from "../components/guidance/guidanceConfig";
import { useAuth } from "../auth/AuthContext";
import AdminRefreshProvider from "./AdminRefreshProvider";
import Sidebar from "./Sidebar";

// The signed-in shell: sidebar navigation, header and the current screen.
function AdminLayout() {
  const { user } = useAuth();
  const guidanceKey = guidanceStorageKey(user?.tenant_id ?? "", user?.id ?? "");
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector('[role="dialog"]')) {
        setMenuOpen(false);
        document.querySelector<HTMLButtonElement>(".menu-toggle")?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);
  return (
    <AdminRefreshProvider><div className="admin-layout">
      <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      {menuOpen && <button type="button" className="sidebar-backdrop" aria-label="Dismiss menu" onClick={() => setMenuOpen(false)} />}
      <GuidanceArea key={guidanceKey} storageKey={guidanceKey} menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((v) => !v)} />
    </div></AdminRefreshProvider>
  );
}

function GuidanceArea({ storageKey, menuOpen, onToggleMenu }: { storageKey: string; menuOpen: boolean; onToggleMenu: () => void }) {
  const { pathname } = useLocation();
  const [guidance, setGuidance] = useState<GuidancePreference>(() => readGuidance(storageKey));
  const updateGuidance = (change: (current: GuidancePreference) => GuidancePreference) => {
    setGuidance((current) => {
      const next = change(current);
      writeGuidance(storageKey, next);
      return next;
    });
  };
  const controls: GuidanceControls = {
    preference: guidance,
    setEnabled: (enabled) => updateGuidance((current) => ({
      ...current,
      enabled,
      dismissed: enabled && !current.enabled ? [] : current.dismissed,
    })),
    resetDismissed: () => updateGuidance((current) => ({ ...current, enabled: true, dismissed: [] })),
  };
  const showCurrentPage = () => {
    const key = guidanceForPath(pathname)?.key;
    if (key) updateGuidance((current) => ({ ...current, dismissed: current.dismissed.filter((item) => item !== key) }));
  };
  return <GuidanceContext.Provider value={{ enabled: guidance.enabled, dismissed: guidance.dismissed, dismissPage: (key) => updateGuidance((current) => ({ ...current, dismissed: [...new Set([...current.dismissed, key])] })) }}><div className="admin-main">
    <Header menuOpen={menuOpen} onToggleMenu={onToggleMenu} showGuide={guidance.enabled} onOpenGuide={showCurrentPage} />
    <main className="admin-content">
      <Outlet context={controls} />
    </main>
  </div></GuidanceContext.Provider>;
}

export default AdminLayout;
