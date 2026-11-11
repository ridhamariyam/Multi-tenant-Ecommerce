import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { NAV_GROUPS } from "../routes";
import NavIcon from "./NavIcon";
import SidebarProfile from "./SidebarProfile";

// Shows only the screens the signed-in account may open.
function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const { can, isAdmin } = useAuth();
  return (
    <nav id="admin-navigation" className={`admin-sidebar${open ? " open" : ""}`} aria-label="Admin sections">
      <div className="brand"><span className="brand-name">CliQ.</span><span className="brand-caption">LIMITLESS STYLE</span><span className="brand-workspace">Admin workspace</span></div>
      <button type="button" className="sidebar-close" onClick={onNavigate} aria-label="Close menu">×</button>
      <div className="sidebar-navigation">
      {NAV_GROUPS.map((group) => {
        const items = group.items.filter((item) => (item.adminOnly ? isAdmin : !item.permission || can(item.permission)));
        if (items.length === 0) return null;
        return (
          <div key={group.title}>
            <div className="nav-group">{group.title}</div>
            {items.map((item) => (
              <NavLink key={item.path} to={item.path} end={item.path === "/"} onClick={onNavigate}>
                <NavIcon path={item.path} /><span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        );
      })}
      </div>
      <SidebarProfile onNavigate={onNavigate} />
    </nav>
  );
}

export default Sidebar;
