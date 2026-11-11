'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';

import { HeartIcon, MinusIcon, PlusIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useCart } from '@/context/CartContext';
import { useWishlist } from '@/context/WishlistContext';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { orderSizes, sizeLabel } from '@/lib/catalogue/size';
import { formatDate, formatMoney, formatPriceRange } from '@/lib/format';
import type { ProductStorefront, VariantStorefront } from '@/types/catalogue';

import styles from './ProductDetails.module.css';
import SizeGuideModal from './SizeGuideModal';

type Selection = Record<string, string>;

interface Props {
  product: ProductStorefront;
  /** `?variant=` from the URL, so a shared link opens on that variant. */
  initialVariantId?: string;
}

const LOW_STOCK = 5;

function isOption(name: string, wanted: string) {
  return name.toLowerCase() === wanted;
}

/**
 * Start on the linked variant if there is one. Otherwise pre-fill only
 * options with a single value -- the shopper picks everything else, so a
 * size is never chosen for them.
 */
function initialSelection(product: ProductStorefront, variantId?: string): Selection {
  const linked = product.variants.find(variant => variant.id === variantId);
  if (linked) return { ...linked.options };
  return Object.fromEntries(
    product.options.filter(option => option.values.length === 1).map(option => [option.name, option.values[0]]),
  );
}

function findVariant(product: ProductStorefront, selection: Selection): VariantStorefront | null {
  if (product.options.length === 0) return product.variants.length === 1 ? product.variants[0] : null;
  if (!product.options.every(option => selection[option.name])) return null;
  return product.variants.find(v => product.options.every(o => v.options[o.name] === selection[o.name])) ?? null;
}

/** Whether some in-stock variant has `name = value` alongside every other current pick. */
function valueInStock(product: ProductStorefront, selection: Selection, name: string, value: string) {
  return product.variants.some(
    v =>
      v.in_stock &&
      v.options[name] === value &&
      Object.entries(selection).every(([key, chosen]) => key === name || v.options[key] === chosen),
  );
}

/**
 * Option values are free text; only those that are real CSS colors paint a
 * swatch. Checked after mount -- `CSS.supports` doesn't exist on the server,
 * and checking during render would make the two renders disagree.
 */
function usePaintable(values: string[] | undefined): Set<string> {
  const [paintable, setPaintable] = useState<Set<string>>(() => new Set());
  const key = values?.join('|') ?? '';
  useEffect(() => {
    if (typeof CSS === 'undefined' || !CSS.supports) return;
    setPaintable(new Set(key.split('|').filter(value => value && CSS.supports('color', value.replace(/\s+/g, '')))));
  }, [key]);
  return paintable;
}

function Accordion({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details className={styles.accordion} open={defaultOpen}>
      <summary className={styles.accordionSummary}>
        {title}
        <span className={styles.accordionIcon} aria-hidden="true" />
      </summary>
      <div className={styles.accordionBody}>{children}</div>
    </details>
  );
}

function Facts({ rows }: { rows: [string, string | null | undefined][] }) {
  const present = rows.filter((row): row is [string, string] => !!row[1]);
  if (present.length === 0) return null;
  return (
    <dl className={styles.facts}>
      {present.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Product information and purchase form: title, price (with the regular
 * price struck through during a sale), short description, color swatches,
 * size select with a size guide, quantity, Add to Cart, wishlist, and
 * accordions for whatever detail the catalogue holds for this product.
 */
export default function ProductDetails({ product, initialVariantId }: Props) {
  const { addToCart, pending } = useCart();
  const { isVariantSaved, toggleVariant, pending: wishlistPending } = useWishlist();

  const [selection, setSelection] = useState<Selection>(() => initialSelection(product, initialVariantId));
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const closeGuide = useCallback(() => setGuideOpen(false), []);

  const colorOption = product.options.find(option => isOption(option.name, 'color'));
  const sizeOption = product.options.find(option => isOption(option.name, 'size'));
  const otherOptions = product.options.filter(option => option !== colorOption && option !== sizeOption);
  const paintable = usePaintable(colorOption?.values);

  const variant = useMemo(() => findVariant(product, selection), [product, selection]);
  const purchasable = product.variants.some(v => v.in_stock);
  const stock = variant?.available_quantity ?? 0;
  const saved = variant ? isVariantSaved(variant.id) : false;

  // Keep `?variant=` in step with the selection without a navigation.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (variant) url.searchParams.set('variant', variant.id);
    else url.searchParams.delete('variant');
    window.history.replaceState(window.history.state, '', url);
  }, [variant]);

  function choose(name: string, value: string) {
    setSelection(previous => ({ ...previous, [name]: value }));
    setQuantity(1);
    setError(null);
  }

  const missing = product.options.find(option => !selection[option.name]);

  async function handleAddToCart() {
    if (missing) {
      setError(`Please select a ${missing.name.toLowerCase()}.`);
      return;
    }
    if (!variant) {
      setError('That combination is not available.');
      return;
    }
    if (!variant.in_stock) {
      setError('This option is sold out.');
      return;
    }
    const failure = await addToCart(variant.id, quantity);
    if (failure) toast.error(failure);
  }

  async function handleToggleWishlist() {
    if (!variant) {
      setError(missing ? `Please select a ${missing.name.toLowerCase()} to save it.` : 'That combination is not available.');
      return;
    }
    const wasSaved = saved;
    const failure = await toggleVariant(variant.id);
    if (failure) toast.error(failure);
    else if (wasSaved) toast.info('Removed from your wishlist');
    else toast.success('Added to your wishlist');
  }

  // Price: the chosen variant's, else the product's range.
  const onSale = !!variant?.compare_at_price && Number(variant.compare_at_price) > Number(variant.price);
  const priceText = variant
    ? formatMoney(variant.price, STOREFRONT_CURRENCY)
    : formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY);
  const percentOff = onSale
    ? Math.round((1 - Number(variant!.price) / Number(variant!.compare_at_price)) * 100)
    : 0;

  const availability = !purchasable
    ? { text: 'Out of stock', tone: styles.stockOut }
    : !variant
      ? missing
        ? null
        : { text: 'Not available in this combination', tone: styles.stockOut }
      : !variant.in_stock
        ? { text: 'This option is sold out', tone: styles.stockOut }
        : stock <= LOW_STOCK
          ? { text: `Only ${stock} left`, tone: styles.stockLow }
          : { text: 'In stock', tone: styles.stockIn };

  const longDescription = product.description && product.description !== product.short_description;
  const careRows: [string, string | null | undefined][] = [
    ['Fabric', product.fabric],
    ['Composition', product.fabric_details],
    ['Care', product.washing_instructions],
    ['Made in', product.country_of_origin],
  ];
  const fitRows: [string, string | null | undefined][] = [
    ['Sleeve', product.sleeve],
    ['Neckline', product.neckline],
    ['Occasion', product.occasion],
  ];
  const hasCare = careRows.some(([, value]) => value);
  const hasFit = fitRows.some(([, value]) => value) || !!product.size_chart?.note;

  const orderedSizes = sizeOption ? orderSizes(sizeOption.values) : [];
  const sizeAvailable = sizeOption
    ? orderedSizes.filter(value => valueInStock(product, selection, sizeOption.name, value))
    : [];

  const unavailable = !purchasable || (variant ? !variant.in_stock : !missing);
  const addLabel = !purchasable || (variant && !variant.in_stock) ? 'Sold out' : unavailable ? 'Unavailable' : pending ? 'Adding…' : 'Add to cart';

  return (
    <div className={styles.details}>
      {product.brand && <p className={styles.brand}>{product.brand}</p>}
      <h1 className={styles.title}>{product.name}</h1>

      <p className={styles.price}>
        {onSale && (
          <>
            <span className={styles.visuallyHidden}>Regular price</span>
            <s className={styles.compare}>{formatMoney(variant!.compare_at_price!, STOREFRONT_CURRENCY)}</s>
            <span className={styles.visuallyHidden}>Sale price</span>
          </>
        )}
        <span className={onSale ? styles.salePrice : undefined}>{priceText || 'Price on request'}</span>
        {onSale && <span className={styles.saleTag}>{percentOff}% off</span>}
      </p>
      {onSale && variant?.sale_ends_at && (
        <p className={styles.saleEnds}>Sale ends {formatDate(variant.sale_ends_at)}</p>
      )}

      {product.short_description && <p className={styles.lede}>{product.short_description}</p>}

      {longDescription && (
        <Accordion title="Design notes">
          <p className={styles.prose}>{product.description}</p>
        </Accordion>
      )}

      {colorOption && (
        <fieldset className={styles.option}>
          <legend className={styles.optionLabel}>
            {colorOption.name}: <span>{selection[colorOption.name] ?? 'Select'}</span>
          </legend>
          <div className={styles.swatches}>
            {colorOption.values.map(value => {
              const active = selection[colorOption.name] === value;
              const soldOut = !valueInStock(product, selection, colorOption.name, value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => choose(colorOption.name, value)}
                  aria-pressed={active}
                  aria-label={`${value}${soldOut ? ' (sold out)' : ''}`}
                  title={value}
                  className={`${paintable.has(value) ? styles.swatch : styles.chip} ${active ? styles.optionActive : ''} ${
                    soldOut ? styles.optionSoldOut : ''
                  }`}
                  style={paintable.has(value) ? { backgroundColor: value.replace(/\s+/g, '') } : undefined}
                >
                  {paintable.has(value) ? null : value}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}

      {sizeOption && (
        <div className={styles.option}>
          <div className={styles.optionHead}>
            <label htmlFor="pdp-size" className={styles.optionLabel}>
              {sizeOption.name}
            </label>
            {product.size_chart && (
              <button type="button" className={styles.guideLink} onClick={() => setGuideOpen(true)}>
                Size guide
              </button>
            )}
          </div>
          <div className={`${styles.selectWrap} ${error && !selection[sizeOption.name] ? styles.selectInvalid : ''}`}>
            <select
              id="pdp-size"
              className={styles.select}
              value={selection[sizeOption.name] ?? ''}
              onChange={event => choose(sizeOption.name, event.target.value)}
              aria-invalid={!!error && !selection[sizeOption.name]}
            >
              <option value="" disabled>
                Select a size
              </option>
              {orderedSizes.map(value => (
                <option key={value} value={value}>
                  {sizeLabel(value)}
                  {sizeAvailable.includes(value) ? '' : ' — Sold out'}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {otherOptions.map(option => (
        <fieldset key={option.name} className={styles.option}>
          <legend className={styles.optionLabel}>
            {option.name}: <span>{selection[option.name] ?? 'Select'}</span>
          </legend>
          <div className={styles.swatches}>
            {option.values.map(value => (
              <button
                key={value}
                type="button"
                onClick={() => choose(option.name, value)}
                aria-pressed={selection[option.name] === value}
                className={`${styles.chip} ${selection[option.name] === value ? styles.optionActive : ''} ${
                  valueInStock(product, selection, option.name, value) ? '' : styles.optionSoldOut
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </fieldset>
      ))}

      {availability && (
        <p className={`${styles.stock} ${availability.tone}`} role="status">
          <span className={styles.stockDot} aria-hidden="true" />
          {availability.text}
        </p>
      )}

      <div className={styles.buy}>
        <div className={styles.qty}>
          <button
            type="button"
            onClick={() => setQuantity(q => Math.max(1, q - 1))}
            disabled={quantity <= 1}
            aria-label={`Decrease quantity for ${product.name}`}
          >
            <MinusIcon size={12} />
          </button>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={stock || undefined}
            value={quantity}
            onChange={event => {
              const next = Math.floor(Number(event.target.value));
              if (Number.isFinite(next)) setQuantity(Math.max(1, stock ? Math.min(next, stock) : next));
            }}
            aria-label="Quantity"
          />
          <button
            type="button"
            onClick={() => setQuantity(q => q + 1)}
            disabled={!!variant && quantity >= stock}
            aria-label={`Increase quantity for ${product.name}`}
          >
            <PlusIcon size={12} />
          </button>
        </div>

        <button
          type="button"
          className={styles.addButton}
          onClick={handleAddToCart}
          disabled={pending || unavailable}
        >
          {addLabel}
        </button>

        <button
          type="button"
          className={`${styles.wishButton} ${saved ? styles.wishActive : ''}`}
          onClick={handleToggleWishlist}
          disabled={wishlistPending}
          aria-pressed={saved}
          aria-label={saved ? 'Remove from wishlist' : 'Save to wishlist'}
        >
          <HeartIcon size={16} filled={saved} />
        </button>
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.accordions}>
        {hasCare && (
          <Accordion title="Fabrication & care">
            <Facts rows={careRows} />
          </Accordion>
        )}
        {hasFit && (
          <Accordion title="Fit notes">
            <Facts rows={fitRows} />
            {product.size_chart?.note && <p className={styles.prose}>{product.size_chart.note}</p>}
          </Accordion>
        )}
        <Accordion title="Shipping & returns">
          <p className={styles.prose}>
            Delivery times, charges and how to return an item are set out in our{' '}
            <Link href="/faq">shipping &amp; returns policy</Link>.
          </p>
        </Accordion>
      </div>

      {guideOpen && product.size_chart && sizeOption && (
        <SizeGuideModal
          chart={product.size_chart}
          productName={product.name}
          availableSizes={sizeAvailable}
          selectedSize={selection[sizeOption.name]}
          onSelectSize={size => choose(sizeOption.name, size)}
          onClose={closeGuide}
        />
      )}
    </div>
  );
}
