const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** The backend's slug rule for products, pages and articles, worded for a shop owner. Null when fine. */
export function slugProblem(slug: string): string | null {
  return slug && !SLUG.test(slug) ? "URL slug must use lowercase letters, numbers and single hyphens." : null;
}
