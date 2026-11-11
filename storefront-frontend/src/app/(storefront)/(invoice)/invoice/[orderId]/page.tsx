import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { ApiError } from '@/lib/api/errors';
import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';
import Invoice from '../_components/Invoice';
import styles from '../_components/Invoice.module.css';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function InvoicePage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  if (!UUID.test(orderId)) notFound();

  const token = await getAccessToken();
  if (!token) redirect(signInUrl(`/invoice/${orderId}`));

  try {
    const [order, invoice] = await Promise.all([orderApi.get(token, orderId), orderApi.invoice(token, orderId)]);
    return <Invoice order={order} invoice={invoice} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isForbidden)) notFound();
    if (error instanceof ApiError && error.isUnauthenticated) redirect(signInUrl(`/invoice/${orderId}`));
    return (
      <main className={styles.errorPage}>
        <section className={styles.errorPanel} role="alert">
          <h1>We couldn&apos;t load this invoice</h1>
          <p>The invoice service could not return this order&apos;s details. Please try again shortly.</p>
          <Link href="/account/orders">Back to My Orders</Link>
        </section>
      </main>
    );
  }
}
