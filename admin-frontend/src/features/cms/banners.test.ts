import { describe, expect, it } from "vitest";
import { cleanBanner, heroProblem } from "./banners";

describe("banner slides", () => {
  it("keeps inner spaces and trims only the ends on save", () => {
    const slide = cleanBanner({
      image_url: " /media/a.png ",
      mobile_image_url: "",
      heading: "  Festive Drop — New In ",
      text: "Test text from the CMS",
      link_url: null,
      cta_label: "Shop now",
      alt_text: "   ",
    });
    expect(slide).toEqual({
      image_url: "/media/a.png",
      mobile_image_url: null,
      heading: "Festive Drop — New In",
      text: "Test text from the CMS",
      link_url: null,
      cta_label: "Shop now",
      alt_text: null,
    });
  });
});

describe("hero banner rule", () => {
  const slide = (o: Partial<Record<string, string | null>> = {}) =>
    ({ image_url: null, mobile_image_url: null, heading: null, text: null, link_url: null, cta_label: null, alt_text: null, ...o });

  it("needs at least one slide with a picture", () => {
    expect(heroProblem([])).toMatch(/can't be saved without one/);
    expect(heroProblem([slide()])).toMatch(/can't be saved without one/);
  });

  it("names the slide that is missing its picture", () => {
    expect(heroProblem([slide({ image_url: "/media/a.png" }), slide({ heading: "Sale" })])).toBe("Slide 2 needs a picture.");
  });

  it("accepts slides that all have pictures, ignoring blank extra slides", () => {
    expect(heroProblem([slide({ image_url: "/media/a.png" }), slide()])).toBeNull();
  });
});
