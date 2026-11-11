import type { NavItem } from "../../types/cms";

// Flattened display order, with one item moved among its siblings.
export function reorderedIds(tree: NavItem[], id: string, delta: number): string[] {
  const swap = (list: NavItem[]): NavItem[] => {
    const i = list.findIndex((n) => n.id === id);
    if (i >= 0 && i + delta >= 0 && i + delta < list.length) {
      const next = [...list];
      const [item] = next.splice(i, 1);
      next.splice(i + delta, 0, item);
      return next;
    }
    return list.map((n) => ({ ...n, children: swap(n.children) }));
  };
  return swap(tree).flatMap((n) => [n.id, ...n.children.map((c) => c.id)]);
}

/** Flattened order after dropping `moving` onto `target`; null if they are not siblings
 * (menus nest one level, and moving between parents is done by editing the item). */
export function idsAfterDrop(tree: NavItem[], moving: string, target: string): string[] | null {
  const siblingsOf = (id: string): NavItem[] | null => {
    if (tree.some((n) => n.id === id)) return tree;
    return tree.find((n) => n.children.some((c) => c.id === id))?.children ?? null;
  };
  const siblings = siblingsOf(moving);
  if (!siblings || siblings !== siblingsOf(target)) return null;
  const from = siblings.findIndex((n) => n.id === moving);
  const to = siblings.findIndex((n) => n.id === target);
  return reorderedIds(tree, moving, to - from);
}
