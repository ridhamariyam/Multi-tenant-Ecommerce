import { useContext } from "react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { GuidanceContext } from "./GuidanceContext";
import ContextualGuidance from "./ContextualGuidance";
import { guidanceForPath } from "./guidanceConfig";

// Keeps a control and its optional first-time help in the same compact layout cell.
export default function GuidedControl({ children, hint, dismissible = false, className = "" }: { children: ReactNode; hint: string; dismissible?: boolean; className?: string }) {
  const guidance = useContext(GuidanceContext);
  const { pathname } = useLocation();
  const page = guidanceForPath(pathname);
  if (!guidance?.enabled || !page || guidance.dismissed.includes(page.key)) return <>{children}</>;
  return <div className={`guided-control ${className}`.trim()}>
    {children}
    <ContextualGuidance dismissible={dismissible}>{hint}</ContextualGuidance>
  </div>;
}
