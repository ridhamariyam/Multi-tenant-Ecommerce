'use client';

import styles from './Checkout.module.css';

interface DeleteConfirmModalProps {
  title?: string;
  message?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DeleteConfirmModal({
  title = 'Delete Address',
  message = 'Are you sure you want to delete this address?',
  onConfirm,
  onCancel,
}: DeleteConfirmModalProps) {
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.modalCard} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{title}</h2>
        </div>
        <p style={{ margin: '12px 0 24px', fontSize: '14.5px', color: '#4a4540' }}>
          {message}
        </p>
        <div className={styles.formActions}>
          <button type="button" className={styles.formCancelBtn} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={styles.formSaveBtn}
            style={{ background: '#b42318' }}
            onClick={onConfirm}>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}