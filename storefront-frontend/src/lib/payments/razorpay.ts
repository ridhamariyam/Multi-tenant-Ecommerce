import { razorpayMethod } from '@/lib/payments/online';
import type { OnlinePaymentRequest, RazorpayVerification } from '@/types/orders';

/**
 * Razorpay Checkout, in the browser.
 *
 * Only the public key id is used here. Whether a payment really succeeded is
 * decided by the backend from Razorpay's signature -- the `paid` outcome is
 * just what Checkout reported, and still has to be verified.
 */

const CHECKOUT_SCRIPT = 'https://checkout.razorpay.com/v1/checkout.js';

interface RazorpayFailure {
  error?: { description?: string; reason?: string };
}

interface RazorpayInstance {
  open(): void;
  on(event: 'payment.failed', handler: (response: RazorpayFailure) => void): void;
}

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance;
  }
}

export type CheckoutOutcome = { kind: 'paid'; verification: RazorpayVerification } | { kind: 'dismissed' };

let scriptLoading: Promise<void> | null = null;

function loadCheckoutScript(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();

  scriptLoading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = CHECKOUT_SCRIPT;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      scriptLoading = null;
      script.remove();
      reject(new Error('Could not load the payment window. Check your connection and try again.'));
    };
    document.body.appendChild(script);
  });

  return scriptLoading;
}

/**
 * Open Checkout for one order and wait for the shopper to pay or close it.
 *
 * A failed attempt does not end it: Checkout stays open so the shopper can
 * retry, and `onAttemptFailed` is told why the attempt failed.
 */
export async function payWithRazorpay(
  request: OnlinePaymentRequest,
  {
    onAttemptFailed,
    keyId,
    storeName,
  }: { onAttemptFailed?: (message: string) => void; keyId?: string | null; storeName?: string } = {},
): Promise<CheckoutOutcome> {
  // The brand's own Razorpay key (from /storefront/resolve); the build-time key
  // only for deployments that still configure it.
  const key = keyId || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID;
  if (!key) throw new Error('Online payment is not set up for this store yet.');

  await loadCheckoutScript();
  const Razorpay = window.Razorpay;
  if (!Razorpay) throw new Error('Could not load the payment window. Try again in a moment.');

  return new Promise<CheckoutOutcome>(resolve => {
    const checkout = new Razorpay({
      key,
      order_id: request.razorpayOrderId,
      amount: request.amount,
      currency: request.currency,
      name: storeName || 'Checkout',
      description: `Order #${request.orderNumber}`,
      prefill: {
        name: request.name,
        contact: request.contact,
        method: razorpayMethod(request.method),
      },
      notes: { order_number: request.orderNumber },
      theme: { color: '#1a1a1a' },
      modal: {
        confirm_close: true,
        ondismiss: () => resolve({ kind: 'dismissed' }),
      },
      handler: (verification: RazorpayVerification) => resolve({ kind: 'paid', verification }),
    });

    checkout.on('payment.failed', response => {
      onAttemptFailed?.(response.error?.description ?? 'The payment did not go through. Please try again.');
    });

    checkout.open();
  });
}
