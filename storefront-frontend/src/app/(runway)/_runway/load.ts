import { apiRequest } from '@/lib/api/client';
import { catalogueApi } from '@/lib/api/catalogue';
import { orderSizes } from '@/lib/catalogue/size';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import type { ProductStorefront, VariantStorefront } from '@/types/catalogue';

import { DEFAULT_PINS, RUNWAY_LOOKS, type RunwayLookConfig } from './config';

export interface RunwayVariant {
  id: string;
  /** Available to buy right now. */
  a: boolean;
  /** Option values, in the order of `RunwayPiece.options`. */
  o: string[];
}

export interface RunwayPiece {
  slug: string;
  name: string;
  vendor: string;
  url: string;
  image: string | null;
  imageAlt: string;
  price: number | null;
  priceLabel: string;
  options: { name: string; values: string[] }[];
  variants: RunwayVariant[];
  /** Set when there is nothing to choose: the plus adds this variant directly. */
  directVariantId: string | null;
  soldOut: boolean;
  pin: [number, number];
  tag: string | null;
}

export interface RunwayLook {
  name: string;
  model: { src: string; srcLarge: string };
  pieces: RunwayPiece[];
  total: number | null;
  totalLabel: string;
}

const money = (value: number | null) => (value === null ? '' : formatMoney(value.toFixed(2), STOREFRONT_CURRENCY));

const isAvailable = (v: VariantStorefront) => v.in_stock && v.available_quantity > 0;

/** Option keys are not consistently cased in the catalogue (`size` vs `Size`). */
function optionValue(v: VariantStorefront, name: string): string {
  if (name in v.options) return v.options[name];
  const key = Object.keys(v.options).find(k => k.toLowerCase() === name.toLowerCase());
  return key ? v.options[key] : '';
}

function toPiece(product: ProductStorefront, index: number, pin?: [number, number], tag?: string): RunwayPiece {
  const variants = product.variants ?? [];
  let options = (product.options ?? []).filter(o => o.name);

  /* No declared options but several variants: let the shopper pick by variant name. */
  const byName = options.length === 0 && variants.length > 1;
  if (byName) options = [{ name: 'Option', values: variants.map(v => v.name) }];

  const runwayVariants: RunwayVariant[] = variants.map(v => ({
    id: v.id,
    a: isAvailable(v),
    o: byName ? [v.name] : options.map(o => optionValue(v, o.name)),
  }));

  /* Every value any variant offers, keeping the catalogue's order first. */
  options = options.map((o, i) => {
    const values = [...o.values];
    for (const v of runwayVariants) if (v.o[i] && !values.includes(v.o[i])) values.push(v.o[i]);
    return { name: o.name, values: o.name.trim().toLowerCase() === 'size' ? orderSizes(values) : values };
  });

  const available = variants.filter(isAvailable);
  const prices = (available.length ? available : variants).map(v => Number(v.price)).filter(Number.isFinite);
  const price = prices.length ? Math.min(...prices) : product.price_from ? Number(product.price_from) : null;
  const primary = product.images?.find(i => i.is_primary) ?? product.images?.[0] ?? null;

  return {
    slug: product.slug ?? product.id,
    name: product.name,
    vendor: product.brand || product.category?.name || '',
    url: `/products/${encodeURIComponent(product.slug ?? product.id)}`,
    image: mediaUrl(primary?.url),
    imageAlt: primary?.alt_text ?? '',
    price,
    priceLabel: money(price),
    options,
    variants: runwayVariants,
    directVariantId: variants.length === 1 && available.length === 1 ? available[0].id : null,
    soldOut: available.length === 0,
    pin: pin ?? DEFAULT_PINS[index] ?? DEFAULT_PINS[DEFAULT_PINS.length - 1],
    tag: tag ?? null,
  };
}

/**
 * Resolve every look's products from the API.
 *
 * Each slug is fetched once even when several looks share it, and a slug
 * that fails (deleted, draft, API down) is dropped rather than failing the
 * page: the look then simply shows fewer pieces.
 */
interface PublishedLook {
  title: string;
  cover_url: string | null;
  pins: { product_slug: string; x: number; y: number }[];
}

/** The brand's own published lookbooks (console → Lookbooks), as runway looks. */
async function brandLooks(): Promise<RunwayLookConfig[]> {
  const looks = await apiRequest<PublishedLook[]>('/storefront/looks', { revalidate: 60 }).catch(() => []);
  return looks
    .filter(l => l.cover_url && l.pins.length)
    .map(l => {
      const src = mediaUrl(l.cover_url) ?? l.cover_url!;
      return {
        name: l.title,
        model: { src, srcLarge: src },
        pieces: l.pins.map(p => ({ slug: p.product_slug, pin: [Math.round(p.x * 100), Math.round(p.y * 100)] as [number, number] })),
      };
    });
}

export async function loadRunwayLooks(): Promise<RunwayLook[]> {
  const own = await brandLooks();
  // A brand's own lookbooks win; the built-in looks only fill in until it has some.
  const configured = own.length ? own : RUNWAY_LOOKS;
  const slugs = [...new Set(configured.flatMap(l => l.pieces.map(p => p.slug)))];
  const fetched = await Promise.all(
    slugs.map(slug => catalogueApi.getProductBySlug(slug).then(p => [slug, p] as const, () => [slug, null] as const)),
  );
  const bySlug = new Map(fetched);

  return configured.map(look => {
    const pieces: RunwayPiece[] = [];
    for (const cfg of look.pieces.slice(0, own.length ? 6 : 3)) {
      const product = bySlug.get(cfg.slug);
      if (product) pieces.push(toPiece(product, pieces.length, cfg.pin, cfg.tag));
    }
    const priced = pieces.filter(p => !p.soldOut && p.price !== null);
    const total = priced.length ? priced.reduce((sum, p) => sum + (p.price ?? 0), 0) : null;
    return { name: look.name, model: look.model, pieces, total, totalLabel: money(total) };
  }).filter(look => look.pieces.length > 0); // another brand's store has none of these products
}
