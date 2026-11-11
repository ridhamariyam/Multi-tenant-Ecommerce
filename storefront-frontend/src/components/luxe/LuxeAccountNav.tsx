'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, useTransition } from 'react';

import styles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { UserIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useAuth } from '@/context/AuthContext';
import { useSignInModal } from '@/context/SignInModalContext';

const ACCOUNT_LINKS = [
  { label: 'My Account', href: '/account' },
  { label: 'My Orders', href: '/account/orders' },
  { label: 'Wishlist', href: '/wishlist' },
];

/** The account icon opens sign-in while logged out and the account menu while signed in. */
export default function LuxeAccountNav() {
  const { user, logout } = useAuth();
  const { openSignIn } = useSignInModal();
  const [open, setOpen] = useState(false);
  const [signingOut, startSignOut] = useTransition();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className={styles.accountMenu} ref={menuRef}>
      <button
        type="button"
        className={`${styles.headerRoundBtn} ${styles.accountIconButton}`}
        aria-label="Account"
        aria-haspopup={user ? 'menu' : undefined}
        aria-expanded={user ? open : undefined}
        onClick={() => (user ? setOpen(value => !value) : openSignIn())}>
        <UserIcon size={20} />
      </button>

      {user && open && (
        <div className={styles.profileDropdown} role="menu">
          <div className={styles.profileHead}>
            <p className={styles.profileHeadName}>{user.name?.trim() || 'Welcome back'}</p>
            <p className={styles.profileHeadContact}>{user.email ?? user.phone ?? ''}</p>
          </div>

          {ACCOUNT_LINKS.map(link => (
            <Link
              key={link.href}
              href={link.href}
              role="menuitem"
              className={styles.profileItem}
              onClick={() => setOpen(false)}>
              {link.label}
            </Link>
          ))}

          <button
            type="button"
            role="menuitem"
            className={`${styles.profileItem} ${styles.profileSignOut}`}
            disabled={signingOut}
            onClick={() => startSignOut(() => void logout())}>
            {signingOut ? 'Signing out...' : 'Sign out'}
          </button>
        </div>
      )}
    </div>
  );
}
