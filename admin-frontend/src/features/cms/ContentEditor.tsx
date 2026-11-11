import { Fragment } from "react";
import type { ReactNode } from "react";
import ConfirmButton from "../../components/common/ConfirmButton";
import Modal from "../../components/common/Modal";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { ApiResponse } from "../../types/api";
import type { ContentStatus } from "../../types/cms";
import PublishControls from "./PublishControls";

interface ContentItem {
  id: string;
  title: string;
  status: ContentStatus;
  published_at: string | null;
  is_live: boolean;
}

export interface ContentFormProps<T> {
  item: T | null;
  busy: boolean;
  onSubmit: (data: object) => void;
}

/** The edit modal for a CMS page or blog article: load, publish, save and delete. */
function ContentEditor<T extends ContentItem>({
  kind,
  itemId,
  canEdit,
  load,
  create,
  update,
  remove,
  onClose,
  onCreated,
  renderForm,
}: {
  kind: "pages" | "blog";
  itemId: string | null;
  canEdit: boolean;
  load: (id: string) => Promise<ApiResponse<T>>;
  create: (data: object) => Promise<ApiResponse<T>>;
  update: (id: string, data: object) => Promise<ApiResponse<T>>;
  remove: (id: string) => Promise<unknown>;
  onClose: () => void;
  onCreated: (id: string) => void;
  renderForm: (props: ContentFormProps<T>) => ReactNode;
}) {
  const noun = kind === "pages" ? "page" : "article";
  const Noun = noun[0].toUpperCase() + noun.slice(1);
  const loaded = useApi(
    () => (itemId ? load(itemId) : Promise.resolve({ success: true, message: "", data: null as T | null, meta: null })),
    [itemId]
  );
  const action = useAction();
  const item = loaded.data;

  const save = async (data: object) => {
    const saved = await action.run(() => (item ? update(item.id, data) : create(data)), `${Noun} saved`, `Could not save ${noun}`);
    if (saved && !item) onCreated(saved.data.id);
    else if (saved) loaded.reload();
  };

  return (
    <Modal title={item ? `Edit “${item.title}”` : `New ${noun}`} onClose={onClose} wide>
      <StatusMessage status={action.status} />
      {loaded.error && <div className="status status-error">{loaded.error}</div>}
      {item && <PublishControls kind={kind} item={item} action={action} onDone={loaded.reload} />}
      {(item || !itemId) && (
        // Keyed by id, not by save time: publishing reloads the item and must not
        // wipe changes typed but not saved yet.
        <Fragment key={item?.id ?? "new"}>{renderForm({ item, busy: action.busy, onSubmit: save })}</Fragment>
      )}
      {item && canEdit && (
        <div className="form-actions" style={{ marginTop: 12 }}>
          <ConfirmButton
            message={`Delete this ${noun} permanently?`}
            onConfirm={() => action.run(async () => { await remove(item.id); onClose(); }, `${Noun} deleted`, `Could not delete ${noun}`)}
          >
            Delete {noun}
          </ConfirmButton>
        </div>
      )}
    </Modal>
  );
}

export default ContentEditor;
