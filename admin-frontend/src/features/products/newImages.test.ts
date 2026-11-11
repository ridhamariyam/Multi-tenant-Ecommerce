import { describe, expect, it } from "vitest";
import { checkNewImages } from "./newImages";

const file = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type });

describe("photos for a new product", () => {
  it("needs an uploaded photo", () => {
    expect(checkNewImages([])).toMatch(/at least one photo/);
    expect(checkNewImages([file("a.png", "image/png")])).toBeNull();
  });

  it("rejects other file types and big files", () => {
    expect(checkNewImages([file("a.pdf", "application/pdf")])).toMatch(/only JPEG, PNG or WebP/);
    expect(checkNewImages([file("big.jpg", "image/jpeg", 5 * 1024 * 1024 + 1)])).toMatch(/larger than 5 MB/);
  });
});
