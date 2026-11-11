import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// In-app links and explicit actions use the branded dialog. Only a real page
// unload (refresh, tab close, or leaving the site) uses the browser prompt.
export function useUnsavedChanges(dirty: boolean, onDiscard: () => void) {
  const location = useLocation();
  const navigate = useNavigate();
  const [pendingLeave, setPendingLeave] = useState<(() => void) | null>(null);

  const requestLeave = useCallback((leave: () => void) => {
    if (dirty) setPendingLeave(() => leave);
    else leave();
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const onLinkClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
      const target = new URL(link.href, window.location.href);
      if (target.origin !== window.location.origin || `${target.pathname}${target.search}` === `${location.pathname}${location.search}`) return;
      event.preventDefault();
      event.stopPropagation();
      setPendingLeave(() => () => navigate(`${target.pathname}${target.search}${target.hash}`));
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", onLinkClick, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", onLinkClick, true);
    };
  }, [dirty, location.pathname, location.search, navigate]);

  const discardLeave = () => {
    const leave = pendingLeave;
    setPendingLeave(null);
    onDiscard();
    leave?.();
  };

  return { requestLeave, pendingLeave: pendingLeave !== null, cancelLeave: () => setPendingLeave(null), discardLeave };
}
