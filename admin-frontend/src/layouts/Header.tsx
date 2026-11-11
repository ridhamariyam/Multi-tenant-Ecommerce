import { useLocation } from "react-router-dom";
import { NAV_GROUPS } from "../routes";
import { useAdminRefresh } from "../hooks/AdminRefreshContext";
import DashboardQuickActions from "../features/overview/DashboardQuickActions";
import Notifications from "./Notifications";
import { useAuth } from "../auth/AuthContext";

function Header({ onToggleMenu, menuOpen, showGuide = false, onOpenGuide }: { onToggleMenu: () => void; menuOpen: boolean; showGuide?: boolean; onOpenGuide?: () => void }) {
  const workspace = useAdminRefresh();
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const section = NAV_GROUPS.flatMap((group) => group.items).find((item) => item.path === "/" ? pathname === "/" : pathname === item.path || pathname.startsWith(`${item.path}/`));
  return (
    <header className="admin-header">
      <button className="menu-toggle" onClick={onToggleMenu} aria-label="Toggle menu" aria-expanded={menuOpen} aria-controls="admin-navigation">
        ☰
      </button>
      <div className="header-location"><span className="muted">Workspace</span><span aria-hidden="true"> / </span><strong>{pathname === "/profile" ? "Profile" : pathname === "/settings" ? "Settings" : section?.label ?? "Admin"}</strong></div>
      {showGuide && <button type="button" className="header-help-button" onClick={onOpenGuide} aria-label="Show page guidance">Help</button>}
      <DashboardQuickActions />
      <button type="button" className="header-icon-button" aria-label="Refresh workspace data" title={workspace?.busy ? "Refreshing workspace data…" : "Refresh workspace data"} aria-busy={workspace?.busy ?? false} disabled={!workspace || workspace.busy} onClick={workspace?.refresh}>
        <svg className={workspace?.busy ? "refresh-spinning" : undefined} aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-1l2 6 M18 17a7 7 0 0 1-12 1l-2-6" /></svg>
      </button>
      <Notifications />
      <button type="button" onClick={() => logout()}>Sign out</button>
    </header>
  );
}

export default Header;
