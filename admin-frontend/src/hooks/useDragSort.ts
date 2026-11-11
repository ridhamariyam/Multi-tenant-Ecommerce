import { useState } from "react";
import type { DragEvent } from "react";

/** `ids` with `moving` taken out and dropped where `target` is (before it when moving up, after when moving down). */
export function moveId(ids: string[], moving: string, target: string): string[] {
  const from = ids.indexOf(moving);
  const to = ids.indexOf(target);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = ids.filter((id) => id !== moving);
  next.splice(next.indexOf(target) + (from < to ? 1 : 0), 0, moving);
  return next;
}

// Native HTML5 drag and drop for a list. Spread `dragProps(id)` on each item;
// `onDrop(movingId, targetId)` fires when an item is dropped on another one.
export function useDragSort(onDrop: (moving: string, target: string) => void, enabled = true) {
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const reset = () => {
    setDragging(null);
    setOver(null);
  };

  const dragProps = (id: string) =>
    enabled
      ? {
          draggable: true,
          "data-drag-over": over === id && dragging !== id ? "true" : undefined,
          "data-dragging": dragging === id ? "true" : undefined,
          onDragStart: (e: DragEvent) => {
            setDragging(id);
            if (e.dataTransfer) {
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", id);
            }
          },
          onDragOver: (e: DragEvent) => {
            if (dragging && dragging !== id) {
              e.preventDefault();
              setOver(id);
            }
          },
          onDrop: (e: DragEvent) => {
            e.preventDefault();
            if (dragging && dragging !== id) onDrop(dragging, id);
            reset();
          },
          onDragEnd: reset,
        }
      : {};

  return { dragProps, dragging };
}
