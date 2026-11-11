import { cloneElement, isValidElement, useId } from "react";
import type { ReactElement, ReactNode } from "react";
import ContextualGuidance from "../guidance/ContextualGuidance";

// A labelled form control with an optional hint.
function Field({ label, hint, guidance, guidanceDismissible = false, children, wide, required = false, error }: { label: string; hint?: string; guidance?: string; guidanceDismissible?: boolean; children: ReactNode; wide?: boolean; required?: boolean; error?: string | null }) {
  const id = useId();
  const child = isValidElement(children) ? children as ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string; "aria-required"?: boolean }> : null;
  const controlId = child?.props.id ?? `${id}-control`;
  const description = [child?.props["aria-describedby"], hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(child!, {
      id: controlId,
      ...(required ? { "aria-required": true } : {}),
      ...(error ? { "aria-invalid": true } : {}),
      ...(description ? { "aria-describedby": description } : {}),
    })
    : children;
  return (
    <div className={`field${wide ? " field-wide" : ""}`}>
      <label htmlFor={controlId} className={`field-label${required ? " field-label-required" : ""}`}>{label}</label>
      {control}
      {hint && <span id={`${id}-hint`} className="field-hint">{hint}</span>}
      {guidance && <ContextualGuidance dismissible={guidanceDismissible}>{guidance}</ContextualGuidance>}
      {error && <span id={`${id}-error`} className="field-error" role="alert">{error}</span>}
    </div>
  );
}

export default Field;
