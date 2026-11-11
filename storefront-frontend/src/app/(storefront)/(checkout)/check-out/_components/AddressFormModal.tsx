'use client';

import { useActionState, useEffect } from 'react';

import { saveAddress, updateAddress } from '@/lib/orders/actions';
import { initialCheckoutState } from '@/lib/orders/state';
import type { Address } from '@/types/addresses';

import styles from './Checkout.module.css';

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M5 5l14 14M19 5 5 19" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Add/edit address modal.
 *
 * Same fields either way; editing just carries the address id and
 * pre-filled values, and posts to `updateAddress` (PATCH) instead of
 * `saveAddress` (POST). Both actions return the whole cart-page's worth of
 * revalidation, so `onSaved` only needs to close the modal and ask the
 * parent to refetch -- see `Checkout.tsx`.
 */
export default function AddressFormModal({
  address,
  onClose,
  onSaved,
}: {
  address: Address | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const action = address ? updateAddress : saveAddress;
  const [state, formAction, pending] = useActionState(action, initialCheckoutState);

  useEffect(() => {
    if (state.status === 'success') onSaved();
  }, [state, onSaved]);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalCard} onClick={event => event.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{address ? 'Edit Address' : 'Add New Address'}</h2>
          <button type="button" className={styles.modalCloseBtn} onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </div>

        <form action={formAction} className={styles.formGrid}>
          {address && <input type="hidden" name="address_id" value={address.id} />}

          <div className={`${styles.formField} ${styles.formFieldFull}`}>
            <label className={styles.formLabel} htmlFor="full_name">
              Full name
            </label>
            <input
              id="full_name"
              name="full_name"
              className={styles.formInput}
              defaultValue={address?.full_name}
              disabled={pending}
              required
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="phone">
              Phone
            </label>
            <input
              id="phone"
              name="phone"
              placeholder="+91XXXXXXXXXX"
              className={styles.formInput}
              defaultValue={address?.phone}
              disabled={pending}
              required
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="country">
              Country
            </label>
            <input
              id="country"
              name="country"
              className={styles.formInput}
              defaultValue={address?.country ?? 'India'}
              disabled={pending}
              required
            />
          </div>

          <div className={`${styles.formField} ${styles.formFieldFull}`}>
            <label className={styles.formLabel} htmlFor="address_line_1">
              Address line 1
            </label>
            <input
              id="address_line_1"
              name="address_line_1"
              className={styles.formInput}
              defaultValue={address?.address_line_1}
              disabled={pending}
              required
            />
          </div>

          <div className={`${styles.formField} ${styles.formFieldFull}`}>
            <label className={styles.formLabel} htmlFor="address_line_2">
              Address line 2 (optional)
            </label>
            <input
              id="address_line_2"
              name="address_line_2"
              className={styles.formInput}
              defaultValue={address?.address_line_2 ?? ''}
              disabled={pending}
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="city">
              City
            </label>
            <input
              id="city"
              name="city"
              className={styles.formInput}
              defaultValue={address?.city}
              disabled={pending}
              required
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="state">
              State
            </label>
            <input
              id="state"
              name="state"
              className={styles.formInput}
              defaultValue={address?.state}
              disabled={pending}
              required
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="postal_code">
              Postal code
            </label>
            <input
              id="postal_code"
              name="postal_code"
              className={styles.formInput}
              defaultValue={address?.postal_code}
              disabled={pending}
              required
            />
          </div>

          <label className={styles.formCheckboxRow}>
            <input type="checkbox" name="is_default" defaultChecked={address?.is_default ?? false} disabled={pending} />
            Set as default address
          </label>

          {state.status === 'error' && <p className={styles.formError}>{state.message}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.formCancelBtn} onClick={onClose} disabled={pending}>
              Cancel
            </button>
            <button type="submit" className={styles.formSaveBtn} disabled={pending}>
              {pending ? 'Saving…' : 'Save Address'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
