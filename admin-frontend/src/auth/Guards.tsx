import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="state">Checking your session…</div>;
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

