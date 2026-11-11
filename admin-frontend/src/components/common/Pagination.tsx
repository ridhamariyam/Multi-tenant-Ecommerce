import type { PageMeta } from "../../types/api";

interface PaginationProps {
  meta: PageMeta | null;
  onPageChange: (page: number) => void;
}

function Pagination({ meta, onPageChange }: PaginationProps) {
  if (!meta) return null;
  return (
    <div className="pagination">
      <button disabled={meta.page <= 1} onClick={() => onPageChange(meta.page - 1)}>
        Previous
      </button>
      <span>
        Page {meta.page} of {Math.max(meta.total_pages, 1)} ({meta.total_items} items)
      </span>
      <button disabled={meta.page >= meta.total_pages} onClick={() => onPageChange(meta.page + 1)}>
        Next
      </button>
    </div>
  );
}

export default Pagination;
