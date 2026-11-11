import { useCallback, useEffect, useState } from "react";
import { useAdminRefresh } from "./AdminRefreshContext";
import type { ApiResponse, PageMeta } from "../types/api";

interface Loaded<T> {
  key: string;
  data: T | null;
  meta: PageMeta | null;
  error: string | null;
}

// Loads data from the backend whenever `deps` change.
//
//   const { data, loading, error, reload } = useApi(() => listOrders(query), [query]);
export function useApi<T>(fetcher: () => Promise<ApiResponse<T>>, deps: unknown[]) {
  const workspace = useAdminRefresh();
  const begin = workspace?.begin;
  const end = workspace?.end;
  const [version, setVersion] = useState(0);
  const key = JSON.stringify([deps, version, workspace?.version ?? 0]);
  const [loaded, setLoaded] = useState<Loaded<T>>({ key: "", data: null, meta: null, error: null });

  useEffect(() => {
    let cancelled = false;
    begin?.();
    fetcher()
      .then((response) => {
        if (!cancelled) setLoaded({ key, data: response.data, meta: response.meta, error: null });
      })
      .catch((error: Error) => {
        // Drop the previous result: it belongs to other `deps` (e.g. an older filter).
        if (!cancelled) setLoaded({ key, data: null, meta: null, error: error.message });
      })
      .finally(() => end?.());
    return () => {
      cancelled = true;
    };
    // `deps` is the caller's dependency list; `fetcher` is recreated every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, begin, end]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return {
    data: loaded.data,
    meta: loaded.meta,
    error: loaded.error,
    loading: loaded.key !== key,
    reload,
  };
}
