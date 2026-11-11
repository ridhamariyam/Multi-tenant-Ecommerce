import { describe, expect, it } from "vitest";
import type { NavItem } from "../../types/cms";
import { idsAfterDrop, reorderedIds } from "./navigation";

const item = (id: string, children: NavItem[] = []): NavItem => ({
  id, menu: "HEADER", label: id, link_type: "HOME", target: null, href: "/", parent_id: null, position: 0, is_active: true, open_in_new_tab: false, children,
});

describe("menu reordering", () => {
  const tree = [item("a", [item("a1"), item("a2")]), item("b")];

  it("moves a top-level item with its children", () => {
    expect(reorderedIds(tree, "b", -1)).toEqual(["b", "a", "a1", "a2"]);
  });

  it("moves a child among its siblings", () => {
    expect(reorderedIds(tree, "a2", -1)).toEqual(["a", "a2", "a1", "b"]);
  });

  it("ignores moves past the ends", () => {
    expect(reorderedIds(tree, "a", -1)).toEqual(["a", "a1", "a2", "b"]);
  });
});

describe("menu drag and drop", () => {
  const tree = [item("a", [item("a1"), item("a2"), item("a3")]), item("b"), item("c")];

  it("reorders top-level items", () => {
    expect(idsAfterDrop(tree, "c", "a")).toEqual(["c", "a", "a1", "a2", "a3", "b"]);
  });

  it("reorders children within their parent", () => {
    expect(idsAfterDrop(tree, "a3", "a1")).toEqual(["a", "a3", "a1", "a2", "b", "c"]);
  });

  it("refuses to move an item to a different level", () => {
    expect(idsAfterDrop(tree, "a1", "b")).toBeNull();
  });
});
