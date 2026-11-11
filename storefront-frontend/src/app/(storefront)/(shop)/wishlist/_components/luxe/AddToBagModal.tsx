'use client';

import Image from 'next/image';
import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';

import { CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import productStyles from '@/elements/SingleProductPage/luxe/Product.module.css';
import { useCart } from '@/context/CartContext';
import { mediaUrl } from '@/lib/media';
import { catalogueApi } from '@/lib/api/catalogue';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { sizeLabel } from '@/lib/catalogue/size';
import { formatMoney } from '@/lib/format';
import type { ProductStorefront, VariantStorefront } from '@/types/catalogue';
import type { WishlistItem } from '@/types/cart';

import styles from './AddToBagModal.module.css';

/**
 * Every variant that is "the same item, a different size" as the one
 * already saved to the wishlist -- every option held equal except Size.
 *
 * If the product has no Size option at all (e.g. a one-size piece), the
 * only match is the saved variant itself, so the modal still asks the
 * shopper to actively pick that one chip before enabling Add to Bag.
 */
function sizeChoicesFor(product: ProductStorefront, savedVariant: VariantStorefront | undefined) {
  const sizeOption = product.options.find(option => option.name.toLowerCase() === 'size');
  const otherOptionNames = product.options
    .map(option => option.name)
    .filter(name => name !== sizeOption?.name);

  return product.variants
    .filter(variant => otherOptionNames.every(name => variant.options[name] === savedVariant?.options[name]))
    .map(variant => ({
      variant,
      label: sizeOption && variant.options[sizeOption.name] ? sizeLabel(variant.options[sizeOption.name]) : variant.name,
    }))
    .filter(choice => choice.label);
}

/**
 * The CliQ "Add to Bag" modal: real product image/gallery, name, price and
 * every size the saved item comes in, fetched fresh from the catalogue when
 * it opens (the wishlist only carries the one saved variant). No size is
 * pre-selected, and Add to Bag stays disabled until the shopper picks one --
 * only then is a real `variant_id` handed to `CartContext`.
 */
export default function AddToBagModal({ item, onClose }: { item: WishlistItem; onClose: () => void }) {
  const { addToCart, pending } = useCart();

  const [product, setProduct] = useState<ProductStorefront | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [activeImage, setActiveImage] = useState(0);
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    catalogueApi
      .getProduct(item.product_id)
      .then(result => {
        if (cancelled) return;
        setProduct(result);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [item.product_id]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const savedVariant = product?.variants.find(variant => variant.id === item.variant_id);
  const sizeChoices = product ? sizeChoicesFor(product, savedVariant) : [];
  const selectedChoice = sizeChoices.find(choice => choice.variant.id === selectedVariantId);

  const displayPrice = selectedChoice?.variant.price ?? savedVariant?.price ?? String(item.unit_price);
  const images = product?.images ?? (item.image ? [{ id: 'wishlist', url: item.image.url, alt_text: item.image.alt_text, sort_order: 0, is_primary: true }] : []);

  async function handleAddToBag() {
    if (!selectedVariantId) return;
    const failure = await addToCart(selectedVariantId, 1);
    if (failure) {
      toast.error(failure);
      return;
    }
    onClose();
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={event => event.stopPropagation()} role="dialog" aria-modal="true">
        {/*
         * Mobile: everything above the actions scrolls in `.scrollArea`;
         * the helper text + Cancel/Add to Bag live in `.modalFooter`,
         * pinned so they're reachable even if the rest doesn't fit the
         * viewport. Both wrappers unwrap (`display: contents`) from
         * tablet up, where the whole modal already scrolls as one piece
         * -- unchanged from before.
         */}
        <div className={styles.scrollArea}>
          {/* Decorative bottom-sheet drag handle -- mobile only, see .module.css */}
          <div className={styles.sheetHandle} aria-hidden="true" />

          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <CloseIcon size={18} />
          </button>

          <div className={styles.body}>
            <div className={styles.gallery}>
              <div className={styles.mainImage}>
                {images[activeImage] ? (
                  <Image
                    src={images[activeImage].url}
                    alt={images[activeImage].alt_text ?? item.product_name}
                    fill
                    sizes="(max-width: 767px) 90vw, 380px"
                  />
                ) : (
                  <div className={styles.mediaEmpty}>No image yet</div>
                )}
              </div>

              {images.length > 1 && (
                <div className={styles.thumbRow}>
                  {images.map((image, index) => (
                    <button
                      key={image.id}
                      type="button"
                      className={`${styles.thumb} ${index === activeImage ? styles.thumbActive : ''}`}
                      onClick={() => setActiveImage(index)}
                      aria-label={`Show photo ${index + 1}`}>
                      <Image src={mediaUrl(image.url)} alt={image.alt_text ?? item.product_name} fill sizes="70px" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className={styles.details}>
              <div className={styles.headerInfo}>
                {product?.category?.name && <p className={styles.category}>{product.category.name}</p>}

                <h2 className={styles.name}>{item.product_name}</h2>
                <p className={styles.variantLine}>
                  {selectedChoice?.variant.name ?? savedVariant?.name ?? item.variant_name}
                </p>

                <p className={styles.price}>{formatMoney(displayPrice, STOREFRONT_CURRENCY)}</p>
              </div>

              <div className={styles.divider} />

              <div className={styles.sizeSection}>
                {loadError ? (
                  <p className={styles.error}>Couldn&apos;t load this product&apos;s sizes right now. Try again shortly.</p>
                ) : !product ? (
                  <p className={styles.loading}>Loading sizes…</p>
                ) : (
                  <>
                    <span className={productStyles.optionLabel}>Select Size</span>
                    <div className={styles.sizeRow}>
                      {sizeChoices.map(choice => (
                        <button
                          key={choice.variant.id}
                          type="button"
                          disabled={!choice.variant.in_stock}
                          className={`${productStyles.chip} ${
                            selectedVariantId === choice.variant.id ? productStyles.chipActive : ''
                          } ${!choice.variant.in_stock ? styles.chipDisabled : ''}`}
                          onClick={() => setSelectedVariantId(choice.variant.id)}
                          aria-pressed={selectedVariantId === choice.variant.id}
                          aria-label={choice.variant.in_stock ? choice.label : `${choice.label}, out of stock`}>
                          {choice.label}
                        </button>
                      ))}
                    </div>

                    <p className={selectedVariantId ? styles.helperOk : styles.helperPrompt}>
                      {selectedVariantId
                        ? `You are adding size ${selectedChoice?.label} (selected variant) to your bag.`
                        : 'Please select a size to continue.'}
                    </p>

                    <div className={styles.infoBox}>
                      <span>This item will be added to your bag with the selected size.</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className={styles.modalFooter}>
          <div className={styles.actionRow}>
            <button type="button" className={styles.cancelBtn} onClick={onClose} disabled={pending}>
              Cancel
            </button>
            <button
              type="button"
              className={styles.addBtn}
              disabled={!selectedVariantId || pending || !product}
              onClick={handleAddToBag}>
              {pending ? 'Adding…' : 'Add to Bag'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
