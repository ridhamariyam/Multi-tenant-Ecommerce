'use client';

import { useState } from 'react';

import { formatMoney } from '@/lib/format';
import type { PaymentStatus } from '@/types/orders';

import styles from './PaymentHistory.module.css';

function PackageSearchIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true">
      <path d="M21 10V7a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 7v10a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l1.5-.86" />
      <path d="M3.29 7 12 12l8.71-5" />
      <path d="M12 22V12" />
      <circle cx="18.5" cy="15.5" r="2.5" />
      <path d="M20.27 17.27 22 19" />
    </svg>
  );
}

/** One order's payment, as the table shows it. */
export interface PaymentRow {
  orderId: string;
  orderNumber: string;
  paymentId: string;
  method: string;
  amount: string;
  currency: string;
  status: PaymentStatus;
}

interface StatusMeta {
  label: string;
  dotClassName: string;
  textClassName: string;
}

const STATUS_META: Record<PaymentStatus, StatusMeta> = {
  PAID: { label: 'Paid', dotClassName: styles.dotEmerald, textClassName: styles.textEmerald },
  PENDING: { label: 'Pending', dotClassName: styles.dotAmber, textClassName: styles.textAmber },
  PARTIALLY_PAID: { label: 'Partially paid', dotClassName: styles.dotAmber, textClassName: styles.textAmber },
  FAILED: { label: 'Failed', dotClassName: styles.dotRose, textClassName: styles.textRose },
  REFUNDED: { label: 'Refunded', dotClassName: styles.dotBlue, textClassName: styles.textBlue },
};

type FilterValue = 'all' | PaymentStatus;

const FILTERS: FilterValue[] = ['all', 'PAID', 'PENDING', 'FAILED', 'REFUNDED'];

export default function PaymentHistory({ payments: allPayments }: { payments: PaymentRow[] }) {
  const [filter, setFilter] = useState<FilterValue>('all');

  const payments = filter === 'all' ? allPayments : allPayments.filter(p => p.status === filter);

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Payments</h1>
        </div>

        {payments.length !== 0 && (
          <div className={styles.filters}>
            {FILTERS.map(f => {
              const active = filter === f;
              const label = f === 'all' ? 'All' : STATUS_META[f].label;
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className={`${styles.filterButton} ${active ? styles.filterButtonActive : ''}`}>
                  {label}
                </button>
              );
            })}
          </div>
        )}

        <div className={styles.tableCard}>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr className={styles.headRow}>
                  <th className={styles.th}>Order ID</th>
                  <th className={styles.th}>Payment ID</th>
                  <th className={styles.th}>Method</th>
                  <th className={styles.th}>Amount</th>
                  <th className={styles.th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment, i) => {
                  const meta = STATUS_META[payment.status];
                  const isLast = i === payments.length - 1;
                  return (
                    <tr key={payment.orderId} className={`${styles.row} ${!isLast ? styles.rowBorder : ''}`}>
                      <td className={`${styles.td} ${styles.tdOrderId}`}>{payment.orderNumber}</td>
                      <td className={styles.td}>{payment.paymentId}</td>
                      <td className={styles.td}>{payment.method}</td>
                      <td className={`${styles.td} ${styles.tdAmount}`}>
                        {formatMoney(payment.amount, payment.currency)}
                      </td>
                      <td className={styles.td}>
                        <span className={`${styles.statusBadge} ${meta.textClassName}`}>
                          <span className={`${styles.statusDot} ${meta.dotClassName}`} />
                          {meta.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {payments.length === 0 && (
            <div className={styles.emptyState}>
              <PackageSearchIcon className={styles.emptyIcon} />
              <p className={styles.emptyText}>No payment transactions found.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
