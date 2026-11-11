/** Money arrives from the API as decimal strings; compare it in whole paise. */
function paise(amount: string | number | null | undefined): number {
  const value = Number(amount ?? 0);
  return Number.isFinite(value) ? Math.round(value * 100) : 0;
}

export interface Totals {
  subtotal: string;
  discount_amount?: string | null;
  shipping_amount: string;
  cod_fee?: string | null;
  tax_amount: string;
  total_amount: string;
}

/**
 * True when the store's prices already include GST: the backend's total is
 * then subtotal - discount + shipping + COD fee, and the tax line is a part
 * of it rather than something added on top. Totals are always shown as the
 * backend computed them; this only decides how the tax line is labelled.
 */
export function taxIncludedInPrices(totals: Totals): boolean {
  const withoutTax =
    paise(totals.subtotal) - paise(totals.discount_amount) + paise(totals.shipping_amount) + paise(totals.cod_fee);
  const total = paise(totals.total_amount);
  const tax = paise(totals.tax_amount);
  return tax > 0 && withoutTax + tax !== total && withoutTax === total;
}

export function taxLabel(totals: Totals, label = 'Tax'): string {
  return taxIncludedInPrices(totals) ? `${label} (included in prices)` : label;
}
