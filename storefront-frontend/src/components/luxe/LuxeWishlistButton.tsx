'use client';

import Link from 'next/link';

import styles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { HeartIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useAuth } from '@/context/AuthContext';
import { useSignInModal } from '@/context/SignInModalContext';
import { useWishlist } from '@/context/WishlistContext';

/** Header link to the wishlist, badged with how much is saved. */
export default function LuxeWishlistButton() {
  const { isSignedIn } = useAuth();
  const { wishlist } = useWishlist();
  const { openSignIn } = useSignInModal();
  const count = wishlist.item_count;

  if (!isSignedIn) {
    return (
      <button
        type="button"
        className={styles.headerRoundBtn}
        aria-label="Wishlist"
        onClick={() => openSignIn('/wishlist')}>
        <HeartIcon size={20} />
      </button>
    );
  }

  return (
    <Link
      href="/wishlist"
      className={styles.headerRoundBtn}
      aria-label={count > 0 ? `Wishlist, ${count} saved` : 'Wishlist'}>
      <HeartIcon size={20} />
      {count > 0 && (
        <span className={styles.headerBadge} aria-hidden="true">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </Link>
  );
}
