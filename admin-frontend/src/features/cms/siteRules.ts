import type { SiteSettings } from "../../types/cms";

/** The same checks the backend makes, worded for a shop owner. Null when fine. */
export function siteProblem(f: SiteSettings): string | null {
  return Object.values(siteFieldErrors(f))[0] ?? null;
}

export function siteFieldErrors(f: SiteSettings): Record<string, string> {
  const errors: Record<string, string> = {};
  if (f.contact_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.contact_email.trim())) errors.contact_email = "The email address doesn't look right.";
  for (const [label, value] of [["phone number", f.contact_phone], ["WhatsApp number", f.whatsapp_number]] as const) {
    if (value && !/^\+?[0-9][0-9 ()-]{5,}$/.test(value.trim())) errors[label === "phone number" ? "contact_phone" : "whatsapp_number"] = `The ${label} should only contain digits, spaces, + - ( ).`;
  }
  for (const [network, url] of Object.entries(f.social_links)) {
    if (url && url.trim() && !/^https:\/\/\S+$/.test(url.trim())) errors[network] = `The ${network} link must start with https://`;
    if (url && url.trim().length > 500) errors[network] = `The ${network} link is too long (500 characters at most).`;
  }
  return errors;
}
