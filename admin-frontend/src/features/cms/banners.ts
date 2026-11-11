import type { BannerItem, SectionType } from "../../types/cms";
import { emptyToNull } from "../../utils/formatters";

/** Trim every field of a slide; a blank field becomes null. Applied on save, not while typing. */
export function cleanBanner(item: BannerItem): BannerItem {
  return Object.fromEntries(
    Object.entries(item).map(([k, v]) => [k, typeof v === "string" ? emptyToNull(v) : v])
  ) as unknown as BannerItem;
}

/** Plain-language description of each section type, shown in the editor. */
export const SECTION_HELP: Record<SectionType, string> = {
  HERO_BANNER: "The big picture at the very top of the homepage, with a headline and a button.",
  PROMO_STRIP: "A thin announcement bar, e.g. “Free shipping over ₹999”.",
  FEATURED_PRODUCTS: "A row of products you pick by hand (or those marked Featured).",
  NEW_ARRIVALS: "Your newest products, updated automatically.",
  BESTSELLERS: "Your best-selling products over a recent period, updated automatically.",
  SEASONAL: "A themed row of products — pick them, or choose a category.",
};

/** Why a hero banner can't be saved yet, or null when it can. Slides left completely empty are ignored. */
export function heroProblem(slides: BannerItem[]): string | null {
  const used = slides.map((s, i) => ({ s, n: i + 1 })).filter(({ s }) => Object.values(s).some(Boolean));
  if (used.length === 0) return "Add a picture for the hero banner — it can't be saved without one.";
  const missing = used.find(({ s }) => !s.image_url);
  return missing ? `Slide ${missing.n} needs a picture.` : null;
}
