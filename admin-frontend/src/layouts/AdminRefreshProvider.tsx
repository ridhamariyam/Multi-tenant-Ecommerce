import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AdminRefreshContext } from "../hooks/AdminRefreshContext";

export default function AdminRefreshProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const [pending, setPending] = useState(0);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  const begin = useCallback(() => setPending((value) => value + 1), []);
  const end = useCallback(() => setPending((value) => Math.max(0, value - 1)), []);
  const value = useMemo(() => ({ version, busy: pending > 0, refresh, begin, end }), [version, pending, refresh, begin, end]);
  return <AdminRefreshContext.Provider value={value}>{children}</AdminRefreshContext.Provider>;
}
