'use client';

import { useState } from 'react';
import { toast } from 'react-toastify';

import { formatMoney } from '@/lib/format';
import { confirmOnlinePayment } from '@/lib/orders/actions';
import { payWithRazorpay, type CheckoutOutcome } from '@/lib/payments/razorpay';
import type { OnlinePaymentRequest } from '@/types/orders';

/**
 * Reopen Razorpay Checkout for an order that is placed but not yet paid --
 * the shopper closed the window, or a payment failed. It pays against the
 * same Razorpay order the backend created at checkout.
 */
export default function PayNowButton({ request, className }: { request: OnlinePaymentRequest; className?: string }) {
  const [busy, setBusy] = useState(false);

  async function pay() {
    setBusy(true);

    let outcome: CheckoutOutcome;
    try {
      outcome = await payWithRazorpay(request, { onAttemptFailed: message => toast.error(message) });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not open the payment window.');
      setBusy(false);
      return;
    }

    if (outcome.kind === 'dismissed') {
      setBusy(false);
      return;
    }

    // Outside any try: on success the action redirects back here, freshly
    // loaded, and that redirect must reach Next rather than a catch block.
    const result = await confirmOnlinePayment(request.orderNumber, outcome.verification);
    if (result.status === 'error') toast.error(result.message ?? 'We could not confirm your payment yet.');
    setBusy(false);
  }

  return (
    <button type="button" className={className} onClick={pay} disabled={busy}>
      {busy ? 'Processing payment…' : `Pay ${formatMoney((request.amount / 100).toFixed(2), request.currency)}`}
    </button>
  );
}
