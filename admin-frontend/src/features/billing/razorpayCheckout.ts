/** Razorpay Checkout for a subscription (the platform's own account). */

interface Instance {
  open(): void;
  on(event: "payment.failed", handler: (r: { error?: { description?: string } }) => void): void;
}
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => Instance;
  }
}

export type SubscriptionResult =
  | { kind: "paid"; razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string }
  | { kind: "dismissed" };

let loading: Promise<void> | null = null;

function load(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null;
      script.remove();
      reject(new Error("Could not load Razorpay. Check your connection and try again."));
    };
    document.body.appendChild(script);
  });
  return loading;
}

export async function authorizeSubscription(
  opts: { keyId: string; subscriptionId: string; description: string; email?: string | null },
  onFailed: (message: string) => void,
): Promise<SubscriptionResult> {
  await load();
  const Razorpay = window.Razorpay;
  if (!Razorpay) throw new Error("Could not load Razorpay.");
  return new Promise((resolve) => {
    const checkout = new Razorpay({
      key: opts.keyId,
      subscription_id: opts.subscriptionId,
      name: "CliQ.",
      description: opts.description,
      prefill: opts.email ? { email: opts.email } : undefined,
      modal: { confirm_close: true, ondismiss: () => resolve({ kind: "dismissed" }) },
      handler: (r: { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string }) =>
        resolve({ kind: "paid", ...r }),
    });
    checkout.on("payment.failed", (r) => onFailed(r.error?.description ?? "The payment did not go through."));
    checkout.open();
  });
}
