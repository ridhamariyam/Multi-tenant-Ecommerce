import { useEffect, useRef, useState } from "react";
import type { FocusEvent, KeyboardEvent } from "react";

// A dropdown menu's keyboard and pointer behaviour.
//
// Opening focuses the first menu item. It closes on a click outside, on focus
// leaving it, and on Escape (which returns focus to the trigger). Arrow keys,
// Home and End move between the [role="menuitem"] elements.
export function useMenu() {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    container.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const outside = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const onBlur = (event: FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    const index = items.indexOf(document.activeElement as HTMLElement);
    const next =
      event.key === "ArrowDown" ? (index + 1) % items.length
      : event.key === "ArrowUp" ? (index + items.length - 1) % items.length
      : event.key === "Home" ? 0
      : event.key === "End" ? items.length - 1
      : -1;
    if (next >= 0) {
      event.preventDefault();
      items[next]?.focus();
    }
  };

  return { open, setOpen, container, trigger, onBlur, onMenuKeyDown };
}
