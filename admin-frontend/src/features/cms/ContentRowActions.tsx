import { publish, unpublish } from "../../api/cms";
import { STOREFRONT_ORIGIN } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import ConfirmButton from "../../components/common/ConfirmButton";
import type { useAction } from "../../hooks/useAction";
import type { ContentStatus } from "../../types/cms";

interface Row {
  id: string;
  title: string;
  status: ContentStatus;
  is_live: boolean;
}

/** Edit / publish / unpublish / view (or preview) / delete buttons for a page or article in a list. */
function ContentRowActions({
  kind,
  row,
  path,
  action,
  onEdit,
  onPreview,
  onDelete,
  onChanged,
}: {
  kind: "pages" | "blog";
  row: Row;
  path: string;
  action: ReturnType<typeof useAction>;
  onEdit: () => void;
  /** Shown when the website link can't be: not live yet, or no website address set up. */
  onPreview?: () => void;
  onDelete: () => Promise<unknown>;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const noun = kind === "pages" ? "page" : "article";
  return (
    <div className="toolbar" onClick={(e) => e.stopPropagation()}>
      <button type="button" onClick={onEdit}>Edit</button>
      {can(P.cmsPublish) &&
        (row.status === "PUBLISHED" ? (
          <ConfirmButton
            className=""
            title={`Unpublish this ${noun}?`}
            message={`“${row.title}” will be hidden from the website until you publish it again.`}
            confirmLabel="Unpublish"
            onConfirm={() => action.run(async () => { await unpublish(kind, row.id); onChanged(); }, "Unpublished — hidden from the website", "Could not unpublish")}
          >
            Unpublish
          </ConfirmButton>
        ) : (
          <button
            type="button"
            className="primary"
            onClick={() => action.run(async () => { await publish(kind, row.id, null); onChanged(); }, "Published — now on the website", "Could not publish")}
          >
            Publish
          </button>
        ))}
      {row.is_live && STOREFRONT_ORIGIN ? (
        <a className="btn" href={`${STOREFRONT_ORIGIN}${path}`} target="_blank" rel="noreferrer">View on website</a>
      ) : (
        onPreview && <button type="button" onClick={onPreview}>Preview</button>
      )}
      {can(P.cmsManage) && (
        <ConfirmButton
          title={`Delete this ${noun}?`}
          message={`“${row.title}” will be removed permanently. Menu links pointing to it will stop working.`}
          confirmLabel="Delete"
          onConfirm={() => action.run(async () => { await onDelete(); onChanged(); }, "Deleted", "Could not delete")}
        >
          Delete
        </ConfirmButton>
      )}
    </div>
  );
}

export default ContentRowActions;
