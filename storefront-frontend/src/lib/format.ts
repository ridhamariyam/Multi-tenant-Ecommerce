/**
 * Money arrives as a decimal string and is formatted, never recomputed.

 */
export function formatMoney(amount: string | null | undefined, currency: string, locale = 'en-IN'): string {
  if (amount === null || amount === undefined) return '';

  const value = Number(amount);
  if (!Number.isFinite(value)) return '';

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatPriceRange(
  from: string | null,
  to: string | null,
  currency: string,
  locale = 'en-IN',
): string {
  if (!from && !to) return '';
  if (!to || from === to) return formatMoney(from, currency, locale);
  if (!from) return formatMoney(to, currency, locale);

  return `${formatMoney(from, currency, locale)} - ${formatMoney(to, currency, locale)}`;
}

export function formatDate(iso: string, locale = 'en-IN'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(date);
}

export function formatDateTime(iso: string, locale = 'en-IN'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
