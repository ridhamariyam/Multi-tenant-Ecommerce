import type { ReactNode } from "react";
import Modal from "./Modal";

interface ConfirmDialogProps {
  title?: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// A styled "are you sure?" step for one-way actions (delete, unpublish, cancel...).
function ConfirmDialog({ title = "Please confirm", message, confirmLabel = "Yes, continue", cancelLabel = "Cancel", danger = true, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    // Keep clicks inside the dialog from reaching rows/cards it was opened from.
    <div onClick={(e) => e.stopPropagation()}>
      <Modal title={title} onClose={onCancel} showCloseButton={false}>
        <div className="form">
          <p style={{ margin: 0 }}>{message}</p>
          <div className="form-actions">
            <button type="button" onClick={onCancel} autoFocus>
              {cancelLabel}
            </button>
            <button type="button" className={danger ? "danger-solid" : "primary"} onClick={onConfirm}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default ConfirmDialog;
