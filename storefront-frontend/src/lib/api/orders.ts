import { apiRequest, apiRequestPage } from '@/lib/api/client';
import type { Page, PageParams } from '@/types/api';
import type {
  CheckoutPreview,
  CouponApplyResult,
  Offer,
  Order,
  OrderSummary,
  OrderTracking,
  InvoiceRead,
  Payment,
  PaymentMethod,
  RazorpayVerification,
} from '@/types/orders';

export const checkoutApi = {
  /**
   * Price the cart before ordering.
   *
   * The only place discount, shipping, tax and total can be read before an
   * order exists. Passing an address lets the backend price delivery to it.
   */
  preview(
    token: string,
    options: { addressId?: string; couponCode?: string; paymentMethod?: PaymentMethod } = {},
  ): Promise<CheckoutPreview> {
    return apiRequest<CheckoutPreview>('/checkout/preview', {
      method: 'POST',
      query: { coupon_code: options.couponCode },
      body: {
        address_id: options.addressId ?? null,
        ...(options.paymentMethod ? { payment_method: options.paymentMethod } : {}),
      },
      token,
      cache: 'no-store',
    });
  },

  /**
   * Place the order.
   *
   * Takes only the address and an optional coupon: every price is computed
   * server-side from the cart, so nothing about money is sent from here.
   * The idempotency key makes a retry safe -- the original order comes back
   * rather than a duplicate being created. Any method but cash comes back
   * with a pending Razorpay payment on the order, ready to open Checkout.
   */
  placeOrder(
    token: string,
    input: {
      addressId: string;
      couponCode?: string | null;
      idempotencyKey: string;
      paymentMethod?: PaymentMethod;
    },
  ): Promise<Order> {
    return apiRequest<Order>('/checkout', {
      method: 'POST',
      body: {
        address_id: input.addressId,
        coupon_code: input.couponCode ?? null,
        payment_method: input.paymentMethod ?? 'CASH_ON_DELIVERY',
      },
      headers: { 'Idempotency-Key': input.idempotencyKey },
      token,
      cache: 'no-store',
    });
  },
};

/** A guest's delivery address, typed in at checkout rather than saved. */
export interface GuestAddressInput {
  full_name: string;
  phone: string;
  address_line_1: string;
  address_line_2?: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
}

export interface GuestContactInput {
  name: string;
  phone: string;
  email?: string | null;
}

/**
 * Checkout without an account. The backend prices and orders the guest cart
 * named by the cart token, and links the order to a customer record by
 * phone, so signing in later with that phone shows it. Guests pay cash on
 * delivery; online payment needs an account.
 */
export const guestCheckoutApi = {
  preview(
    cartToken: string,
    input: { address?: GuestAddressInput | null; pincode?: string | null; couponCode?: string | null },
  ): Promise<CheckoutPreview> {
    return apiRequest<CheckoutPreview>('/checkout/guest/preview', {
      method: 'POST',
      body: {
        ...(input.address ? { address: input.address } : {}),
        ...(!input.address && input.pincode ? { pincode: input.pincode } : {}),
        coupon_code: input.couponCode || null,
        payment_method: 'CASH_ON_DELIVERY',
      },
      headers: { 'X-Cart-Token': cartToken },
      cache: 'no-store',
    });
  },

  placeOrder(
    cartToken: string,
    input: { contact: GuestContactInput; address: GuestAddressInput; couponCode?: string | null; idempotencyKey: string },
  ): Promise<Order> {
    return apiRequest<Order>('/checkout/guest', {
      method: 'POST',
      body: {
        contact: input.contact,
        address: input.address,
        coupon_code: input.couponCode || null,
        payment_method: 'CASH_ON_DELIVERY',
      },
      headers: { 'X-Cart-Token': cartToken, 'Idempotency-Key': input.idempotencyKey },
      cache: 'no-store',
    });
  },

  /** Public lookup: the order number plus the phone it was placed with. */
  track(orderNumber: string, phone: string): Promise<OrderTracking> {
    return apiRequest<OrderTracking>('/storefront/orders/track', {
      query: { order_number: orderNumber, phone },
      cache: 'no-store',
    });
  },
};

export const orderApi = {
  list(token: string, params: PageParams = {}): Promise<Page<OrderSummary>> {
    return apiRequestPage<OrderSummary>('/orders', {
      query: { ...params },
      token,
      cache: 'no-store',
    });
  },

  get(token: string, orderId: string): Promise<Order> {
    return apiRequest<Order>(`/orders/${orderId}`, { token, cache: 'no-store' });
  },

  /** The order's recorded tracking events and shipment details. Same ownership check as `get`. */
  tracking(token: string, orderId: string): Promise<OrderTracking> {
    return apiRequest<OrderTracking>(`/orders/${orderId}/tracking`, { token, cache: 'no-store' });
  },

  invoice(token: string, orderId: string): Promise<InvoiceRead> {
    return apiRequest<InvoiceRead>(`/orders/${orderId}/invoice`, { token, cache: 'no-store' });
  },

  /** Allowed only while `order.can_cancel` is true: before processing, and not yet paid online. */
  cancel(token: string, orderId: string): Promise<Order> {
    return apiRequest<Order>(`/orders/${orderId}/cancel`, {
      method: 'POST',
      token,
      cache: 'no-store',
    });
  },
};

export const couponApi = {
  /** Only live automatic offers; eligibility is checked again at checkout. */
  listOffers(): Promise<Offer[]> {
    return apiRequest<Offer[]>('/coupons/offers', { cache: 'no-store' });
  },

  /** Validate a code against the live cart and return what it takes off. */
  apply(token: string, code: string): Promise<CouponApplyResult> {
    return apiRequest<CouponApplyResult>('/coupons/apply', {
      method: 'POST',
      body: { code },
      token,
      cache: 'no-store',
    });
  },
};

export const paymentApi = {
  /**
   * Look up one payment.
   *
   * There is no customer payment listing; payment history is built from the
   * order list, since each order carries its own payment.
   */
  get(token: string, paymentId: string): Promise<Payment> {
    return apiRequest<Payment>(`/payments/${paymentId}`, { token, cache: 'no-store' });
  },

  /**
   * Hand Razorpay's signed result to the backend, which checks the signature
   * with the store's secret and only then marks the payment paid.
   */
  verifyRazorpay(token: string | null, verification: RazorpayVerification): Promise<Payment> {
    return apiRequest<Payment>('/payments/razorpay/verify', {
      method: 'POST',
      body: verification,
      token,
      cache: 'no-store',
    });
  },
};
