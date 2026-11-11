import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  showCloseButton?: boolean;
}

function Modal({ title, onClose, children, wide = false, showCloseButton = true }: ModalProps) {
  const titleId = useId();
  const dialog = useRef<HTMLDivElement>(null);

  // Escape closes, like clicking outside -- only the top dialog when one is open over another.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const open = document.querySelectorAll('[role="dialog"]');
      if (open[open.length - 1] === dialog.current) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal ${wide ? "modal-wide" : ""}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h3 id={titleId}>{title}</h3>
          {showCloseButton && (
            // type="button": a dialog opened inside a form must not submit it.
            <button type="button" className="btn-link" onClick={onClose}>Close</button>
          )}
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export default Modal;
