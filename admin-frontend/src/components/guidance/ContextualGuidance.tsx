import { useContext } from "react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { GuidanceContext } from "./GuidanceContext";
import { guidanceForPath } from "./guidanceConfig";

export default function ContextualGuidance({ children, dismissible = false }: { children: ReactNode; dismissible?: boolean }) {
  const state = useContext(GuidanceContext);
  const { pathname } = useLocation();
  const page = guidanceForPath(pathname);
  if (!state?.enabled || !page || state.dismissed.includes(page.key)) return null;

  return <div className="contextual-guidance">
    <span className="contextual-guidance-icon" aria-hidden="true">ⓘ</span>
    <span>{children}</span>
    {dismissible && <button type="button" onClick={() => state.dismissPage(page.key)}>Got it</button>}
  </div>;
}
