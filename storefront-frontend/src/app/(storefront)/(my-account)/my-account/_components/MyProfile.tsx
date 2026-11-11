'use client';

import Link from 'next/link';
import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

import AddressFormModal from '@/app/(storefront)/(checkout)/check-out/_components/AddressFormModal';
import DeleteConfirmModal from '@/app/(storefront)/(checkout)/check-out/_components/DeleteConfirmModal';
import { useAuth } from '@/context/AuthContext';
import { deleteAddress } from '@/lib/orders/actions';
import { initialCheckoutState } from '@/lib/orders/state';
import type { UserProfile } from '@/types/auth';
import type { Address } from '@/types/addresses';

import styles from './MyProfile.module.css';

function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true">
      {children}
    </svg>
  );
}

const UserIcon = () => (
  <Icon>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c1.5-3.7 4.2-5.5 8-5.5s6.5 1.8 8 5.5" />
  </Icon>
);

const PinIcon = () => (
  <Icon>
    <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
    <circle cx="12" cy="10" r="2.5" />
  </Icon>
);

const LogoutIcon = () => (
  <Icon>
    <path d="M14 4h5v16h-5" />
    <path d="M11 8l4 4-4 4M3 12h12" />
  </Icon>
);

const EditIcon = () => (
  <Icon>
    <path d="m4 20 4.1-.9L19 8.2 15.8 5 4.9 15.9 4 20Z" />
    <path d="m14.8 6 3.2 3.2" />
  </Icon>
);

const TrashIcon = () => (
  <Icon>
    <path d="M4 7h16M10 11v5M14 11v5M6 7l1 13h10l1-13M9 7V4h6v3" />
  </Icon>
);

const HomeIcon = () => (
  <Icon>
    <path d="m3 11 9-7 9 7v9H3v-9Z" />
    <path d="M9 20v-6h6v6" />
  </Icon>
);

const LockIcon = () => (
  <Icon>
    <rect x="5" y="10" width="14" height="10" rx="1" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </Icon>
);

export default function MyProfile({
  user,
  initialAddresses,
}: {
  user: UserProfile;
  initialAddresses: Address[];
}) {
  const router = useRouter();
  const { logout } = useAuth();
  const [addressEditor, setAddressEditor] = useState<Address | null | undefined>(undefined);
  const [addressToDelete, setAddressToDelete] = useState<Address | null>(null);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [activeSection, setActiveSection] = useState('personal');
  const [pendingDelete, startDelete] = useTransition();
  const [pendingLogout, startLogout] = useTransition();

  const identifier = user.phone || user.email || '';
  const identifierLabel = user.phone ? 'Phone' : 'Email';

  function handleAddressSaved() {
    setAddressEditor(undefined);
    router.refresh();
  }

  function selectSection(section: string) {
    setActiveSection(section);
  }

  function handleDelete() {
    if (!addressToDelete) return;
    const formData = new FormData();
    formData.set('address_id', addressToDelete.id);
    startDelete(async () => {
      const result = await deleteAddress(initialCheckoutState, formData);
      if (result.status === 'success') {
        setAddressToDelete(null);
        router.refresh();
      }
    });
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <div className={styles.breadcrumb}>
          <Link href="/">Home</Link>
          <span>›</span>
          <span>My Profile</span>
        </div>

        <header className={styles.pageHeader}>
          <div>
            <h1>My Profile</h1>
            <p>Manage your account information and preferences.</p>
          </div>
          <div className={styles.welcome}>
            <span>
              <UserIcon />
            </span>
            <div>
              <strong>Hello, {user.name?.trim() || 'there'}</strong>
              <small>Glad to have you back!</small>
            </div>
          </div>
        </header>

        <div className={styles.layout}>
          {/* Sidebar Navigation */}
          <nav className={styles.nav} aria-label="Profile sections">
            <a
              className={activeSection === 'personal' ? styles.active : undefined}
              aria-current={activeSection === 'personal' ? 'page' : undefined}
              href="#personal"
              onClick={() => selectSection('personal')}>
              <UserIcon />
              My Profile
            </a>
            <a
              className={activeSection === 'addresses' ? styles.active : undefined}
              aria-current={activeSection === 'addresses' ? 'page' : undefined}
              href="#addresses"
              onClick={() => selectSection('addresses')}>
              <PinIcon />
              My Addresses
            </a>
            <button type="button" onClick={() => setLogoutOpen(true)}>
              <LogoutIcon />
              Logout
            </button>
          </nav>

          {/* Main Sections */}
          <div className={styles.sections}>
            {/* Personal Information */}
            <section className={styles.card} id="personal">
              <div className={styles.heading}>
                <UserIcon />
                <div>
                  <h2>Personal Information</h2>
                  <p>Your basic account details.</p>
                </div>
              </div>
              <div className={styles.personalFields}>
                <label>
                  Name
                  <input value={user.name ?? ''} readOnly disabled />
                </label>
                <label>
                  Login {identifierLabel}
                  <span className={styles.readOnly}>
                    <input value={identifier} readOnly disabled />
                    <LockIcon />
                  </span>
                  <small>Your login identifier cannot be changed.</small>
                </label>
              </div>
            </section>

            {/* My Addresses */}
            <section className={styles.card} id="addresses">
              <div className={styles.cardTop}>
                <div className={styles.heading}>
                  <PinIcon />
                  <div>
                    <h2>My Addresses</h2>
                    <p>Manage your saved addresses.</p>
                  </div>
                </div>
                <button
                  className={styles.addButton}
                  type="button"
                  onClick={() => setAddressEditor(null)}>
                  Add New Address
                </button>
              </div>

              {initialAddresses.length ? (
                <div className={styles.addressGrid}>
                  {initialAddresses.map(address => (
                    <article className={styles.addressCard} key={address.id}>
                      <div className={styles.addressTitle}>
                        <HomeIcon />
                        <strong>{address.full_name}</strong>
                        {address.is_default && <b>Default</b>}
                      </div>
                      <div className={styles.addressButtons}>
                        <button type="button" onClick={() => setAddressEditor(address)}>
                          <EditIcon />
                          Edit
                        </button>
                        <button
                          className={styles.delete}
                          type="button"
                          onClick={() => setAddressToDelete(address)}>
                          <TrashIcon />
                          Delete
                        </button>
                      </div>
                      <address>
                        {address.address_line_1}
                        {address.address_line_2 && (
                          <>
                            <br />
                            {address.address_line_2}
                          </>
                        )}
                        <br />
                        {address.city}, {address.state}
                        <br />
                        {address.country} - {address.postal_code}
                        <br />
                        {address.phone}
                      </address>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.empty}>
                  No saved addresses yet. Add one to use at checkout.
                </p>
              )}
            </section>
          </div>
        </div>
      </div>

      {/* Modals */}
      {addressEditor !== undefined && (
        <AddressFormModal
          address={addressEditor}
          onClose={() => setAddressEditor(undefined)}
          onSaved={handleAddressSaved}
        />
      )}

      {addressToDelete && (
        <DeleteConfirmModal
          title="Delete Address"
          message="Are you sure you want to delete this address?"
          onConfirm={handleDelete}
          onCancel={() => !pendingDelete && setAddressToDelete(null)}
        />
      )}

      {logoutOpen && (
        <div className={styles.overlay} onClick={() => !pendingLogout && setLogoutOpen(false)}>
          <div
            className={styles.logoutModal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-title"
            onClick={event => event.stopPropagation()}>
            <button
              className={styles.close}
              type="button"
              aria-label="Close"
              onClick={() => setLogoutOpen(false)}>
              ×
            </button>
            <span className={styles.logoutBadge}>
              <LogoutIcon />
            </span>
            <h2 id="logout-title">Are you sure you want to logout?</h2>
            <p>You will need to login again to access your account.</p>
            <div>
              <button
                type="button"
                onClick={() => setLogoutOpen(false)}
                disabled={pendingLogout}>
                Cancel
              </button>
              <button
                type="button"
                className={styles.confirmLogout}
                disabled={pendingLogout}
                onClick={() => startLogout(() => void logout())}>
                {pendingLogout ? 'Logging out…' : 'Logout'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}