import type { OnlinePaymentRequest } from '@/types/orders';

export interface CheckoutState {
  /** `pay`: the order is placed and waits on Razorpay Checkout, described by `payment`. */
  status: 'idle' | 'success' | 'error' | 'pay';
  message: string | null;
  fieldErrors?: Record<string, string>;
  requestId?: string | null;
  couponCode?: string;
  payment?: OnlinePaymentRequest;
}

export const initialCheckoutState: CheckoutState = { status: 'idle', message: null };
