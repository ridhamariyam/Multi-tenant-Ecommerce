import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, merchant, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="state">Checking your session…</div>;
  // A merchant signed in without a brand open picks one first.
  if (!user && merchant) return <Navigate to="/brands" replace />;
  if (!user) return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Hides a screen the signed-in user has no permission for. */
export function RequirePermission({
  permission,
  adminOnly = false,
  children,
}: {
  permission?: string;
  adminOnly?: boolean;
  children: ReactNode;
}) {
  const { can, isAdmin } = useAuth();
  const allowed = adminOnly ? isAdmin : !permission || can(permission);
  if (!allowed) {
    return (
      <div className="state">
        <h2>No access</h2>
        <p>Your account does not have permission for this page. Ask an admin to grant it.</p>
      </div>
    );
  }
  return <>{children}</>;
}


/** Screens that exist only for a merchant account with a brand open (store, domains, team). */
export function RequireBrand({ children }: { children: ReactNode }) {
  const { brandId, isAdmin } = useAuth();
  if (!brandId) {
    return (
      <div className="state">
        <h2>Not available here</h2>
        <p>Store settings are managed by signing in with a merchant account.</p>
      </div>
    );
  }
  if (!isAdmin) {
    return (
      <div className="state">
        <h2>No access</h2>
        <p>Only the brand&apos;s owner or admins can change these settings.</p>
      </div>
    );
  }
  return <>{children}</>;
}
