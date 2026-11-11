import { describe, expect, it } from "vitest";
import { moveId } from "./useDragSort";

describe("moveId", () => {
  const ids = ["a", "b", "c", "d"];

  it("moves an item up to the drop target's place", () => {
    expect(moveId(ids, "d", "b")).toEqual(["a", "d", "b", "c"]);
  });

  it("moves an item down past the drop target", () => {
    expect(moveId(ids, "a", "c")).toEqual(["b", "c", "a", "d"]);
  });

  it("ignores unknown ids and dropping on itself", () => {
    expect(moveId(ids, "x", "a")).toEqual(ids);
    expect(moveId(ids, "b", "b")).toEqual(ids);
  });
});
