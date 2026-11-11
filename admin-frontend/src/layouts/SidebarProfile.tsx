import { useId } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useMenu } from "../hooks/useMenu";

export default function SidebarProfile({ onNavigate }: { onNavigate: () => void }) {
  const { user, logout } = useAuth();
  const { open, setOpen, container, trigger, onBlur, onMenuKeyDown } = useMenu();
  const menuId = useId();
  const name = user?.name ?? user?.email ?? user?.phone ?? "Admin";
  const navigate = () => { setOpen(false); onNavigate(); };
  return <div className="sidebar-profile" ref={container} onBlur={onBlur}>
    {open && <div id={menuId} className="sidebar-profile-menu" role="menu" aria-label="Account" onKeyDown={onMenuKeyDown}>
      <Link role="menuitem" to="/profile" onClick={navigate}>Profile</Link>
      <Link role="menuitem" to="/settings" onClick={navigate}>Settings</Link>
      <button type="button" role="menuitem" className="sidebar-signout" onClick={() => { navigate(); logout(); }}>Sign out</button>
    </div>}
    <button type="button" className="sidebar-profile-trigger" ref={trigger} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={() => setOpen(!open)} onKeyDown={(event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
    }}>
      <span className="account-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
      <span className="account-detail">Signed in as {name}<small>{user?.role}</small></span>
      <span className="profile-chevron" aria-hidden="true">⌃</span>
    </button>
  </div>;
}
