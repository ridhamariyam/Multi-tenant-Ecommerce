import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

// List filters and the page number live in the URL, so a filtered list
// survives a reload and can be shared as a link.
//
//   const { params, setFilter, setPage } = useUrlFilters();
//   setFilter("status", "PAID");   // also returns to page 1
export function useUrlFilters() {
  const [params, setParams] = useSearchParams();

  const setFilter = useCallback(
    (key: string, value: string) =>
      setParams((current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        next.delete("page");
        return next;
      }),
    [setParams]
  );

  const setPage = useCallback(
    (page: number) =>
      setParams((current) => {
        const next = new URLSearchParams(current);
        next.set("page", String(page));
        return next;
      }),
    [setParams]
  );

  return { params, setParams, setFilter, setPage };
}
