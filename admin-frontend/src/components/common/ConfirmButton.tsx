import { useState } from "react";
import type { ReactNode } from "react";
import ConfirmDialog from "./ConfirmDialog";

// A button that asks first (in a styled dialog) -- for archiving, deleting and other one-way actions.
function ConfirmButton({
  message,
  onConfirm,
  children,
  className = "danger",
  disabled,
  confirmLabel,
  title,
}: {
  message: ReactNode;
  onConfirm: () => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  confirmLabel?: string;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={className}
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        {children}
      </button>
      {open && (
        <ConfirmDialog
          title={title}
          message={message}
          confirmLabel={confirmLabel ?? (typeof children === "string" ? children : "Yes, continue")}
          onCancel={() => setOpen(false)}
          onConfirm={() => {
            setOpen(false);
            onConfirm();
          }}
        />
      )}
    </>
  );
}

export default ConfirmButton;
