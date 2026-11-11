/**
 * Display labels for size option values.
 *
 * Some variants store a size spelled out ("Medium") where the rest of the
 * catalogue uses the short form ("M"). The stored value is never changed --
 * existing variants and the orders that reference them keep it -- but the
 * storefront shows and filters both as the same size.
 */
const SPELLED_OUT: Record<string, string> = {
  'EXTRA SMALL': 'XS',
  'X-SMALL': 'XS',
  SMALL: 'S',
  MEDIUM: 'M',
  LARGE: 'L',
  'EXTRA LARGE': 'XL',
  'X-LARGE': 'XL',
};

const SIZE_ORDER = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];

export function sizeLabel(value: string): string {
  const trimmed = value.trim();
  return SPELLED_OUT[trimmed.toUpperCase()] ?? trimmed;
}

/** Keep standard clothing sizes in their usual order while preserving the
 * original catalogue values used for variant matching and cart requests. */
export function orderSizes(values: readonly string[]): string[] {
  return [...values].sort((a, b) => {
    const ai = SIZE_ORDER.indexOf(sizeLabel(a).toUpperCase());
    const bi = SIZE_ORDER.indexOf(sizeLabel(b).toUpperCase());
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
}

/** `sizeLabel` for the size option, the value unchanged for any other option. */
export function optionValueLabel(optionName: string, value: string): string {
  return optionName.trim().toLowerCase() === 'size' ? sizeLabel(value) : value;
}
