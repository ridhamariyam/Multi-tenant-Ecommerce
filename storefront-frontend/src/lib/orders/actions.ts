'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

import { addressApi } from '@/lib/api/addresses';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { checkoutApi, couponApi, orderApi, paymentApi } from '@/lib/api/orders';
import { getActionAccessToken } from '@/lib/auth/session';
import type { CheckoutState } from '@/lib/orders/state';
import { pendingOnlinePayment } from '@/lib/payments/online';
import {
  ONLINE_PAYMENT_METHODS,
  type CheckoutPreview,
  type Order,
  type PaymentMethod,
  type RazorpayVerification,
} from '@/types/orders';

function toState(error: unknown): CheckoutState {
  if (error instanceof ApiError) {
    return {
      status: 'error',
      message: error.message,
      fieldErrors: error.fieldErrors(),
      requestId: error.requestId,
    };
  }

  if (error instanceof ApiUnreachableError) {
    return { status: 'error', message: 'Could not reach CliQ. Try again in a moment.' };
  }

  throw error;
}

export async function saveAddress(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const payload = {
    full_name: String(formData.get('full_name') ?? '').trim(),
    phone: String(formData.get('phone') ?? '').trim(),
    address_line_1: String(formData.get('address_line_1') ?? '').trim(),
    address_line_2: String(formData.get('address_line_2') ?? '').trim() || null,
    city: String(formData.get('city') ?? '').trim(),
    state: String(formData.get('state') ?? '').trim(),
    postal_code: String(formData.get('postal_code') ?? '').trim(),
    country: String(formData.get('country') ?? 'India').trim(),
    is_default: formData.get('is_default') === 'on',
  };

  try {
    await addressApi.create(token, payload);
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/checkout');
  revalidatePath('/account');
  return { status: 'success', message: 'Address saved' };
}

export async function updateAddress(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const addressId = String(formData.get('address_id') ?? '');
  if (!addressId) return { status: 'error', message: 'Missing address.' };

  const payload = {
    full_name: String(formData.get('full_name') ?? '').trim(),
    phone: String(formData.get('phone') ?? '').trim(),
    address_line_1: String(formData.get('address_line_1') ?? '').trim(),
    address_line_2: String(formData.get('address_line_2') ?? '').trim() || null,
    city: String(formData.get('city') ?? '').trim(),
    state: String(formData.get('state') ?? '').trim(),
    postal_code: String(formData.get('postal_code') ?? '').trim(),
    country: String(formData.get('country') ?? 'India').trim(),
    is_default: formData.get('is_default') === 'on',
  };

  try {
    await addressApi.update(token, addressId, payload);
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/checkout');
  revalidatePath('/account');
  return { status: 'success', message: 'Address updated' };
}

export async function deleteAddress(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  try {
    await addressApi.remove(token, String(formData.get('address_id') ?? ''));
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/account');
  return { status: 'success', message: 'Address removed' };
}

/** Validates a code against the live cart and reports what it takes off. */
export async function applyCoupon(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const code = String(formData.get('code') ?? '').trim();
  if (!code) return { status: 'error', message: 'Enter a code.' };

  try {
    const result = await couponApi.apply(token, code);
    revalidatePath('/checkout');
    return { status: 'success', message: `${result.code} applied`, couponCode: result.code };
  } catch (error) {
    return toState(error);
  }
}

const PAYMENT_METHODS: readonly PaymentMethod[] = [...ONLINE_PAYMENT_METHODS, 'CASH_ON_DELIVERY'];

function paymentMethodFrom(formData: FormData): PaymentMethod {
  const value = String(formData.get('payment_method') ?? '');
  return (PAYMENT_METHODS as readonly string[]).includes(value) ? (value as PaymentMethod) : 'CASH_ON_DELIVERY';
}

export async function placeOrder(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const addressId = String(formData.get('address_id') ?? '');
  if (!addressId) return { status: 'error', message: 'Choose a delivery address.' };

  const couponCode = String(formData.get('coupon_code') ?? '').trim() || null;
  const idempotencyKey = String(formData.get('idempotency_key') ?? '') || crypto.randomUUID();
  const paymentMethod = paymentMethodFrom(formData);

  let order: Order;

  try {
    order = await checkoutApi.placeOrder(token, { addressId, couponCode, idempotencyKey, paymentMethod });
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/account/orders');
  revalidatePath('/cart');
  revalidatePath('/', 'layout');

  const payment = pendingOnlinePayment(order);
  if (payment) return { status: 'pay', message: null, payment };

  redirect(`/order-confirmation/${encodeURIComponent(order.order_number)}`);
}

export async function confirmOnlinePayment(
  orderNumber: string,
  verification: RazorpayVerification,
): Promise<CheckoutState> {
  const token = await getActionAccessToken();

  try {
    await paymentApi.verifyRazorpay(token, verification);
  } catch (error) {
    return toState(error);
  }

  revalidatePath(`/order-confirmation/${encodeURIComponent(orderNumber)}`);
  revalidatePath('/account/orders');
  redirect(`/order-confirmation/${encodeURIComponent(orderNumber)}`);
}

export async function cancelOrder(_previous: CheckoutState, formData: FormData): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const orderId = String(formData.get('order_id') ?? '');

  try {
    await orderApi.cancel(token, orderId);
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/order-confirmation/[orderNumber]', 'page');
  revalidatePath('/account/orders/[orderNumber]', 'page');
  revalidatePath('/account/orders');
  return { status: 'success', message: 'Order cancelled' };
}

export async function placeOrderWithAddress(
  _previous: CheckoutState,
  formData: FormData,
): Promise<CheckoutState> {
  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to continue.' };

  const address = {
    full_name: String(formData.get('full_name') ?? '').trim(),
    phone: String(formData.get('phone') ?? '').trim(),
    address_line_1: String(formData.get('address_line_1') ?? '').trim(),
    address_line_2: String(formData.get('address_line_2') ?? '').trim() || null,
    city: String(formData.get('city') ?? '').trim(),
    state: String(formData.get('state') ?? '').trim(),
    postal_code: String(formData.get('postal_code') ?? '').trim(),
    country: String(formData.get('country') ?? 'India').trim(),
    is_default: true,
  };

  const couponCode = String(formData.get('coupon_code') ?? '').trim() || null;
  const idempotencyKey = String(formData.get('idempotency_key') ?? '') || crypto.randomUUID();

  let orderNumber: string;

  try {
    const saved = await addressApi.create(token, address);
    const order = await checkoutApi.placeOrder(token, {
      addressId: saved.id,
      couponCode,
      idempotencyKey,
    });
    orderNumber = order.order_number;
  } catch (error) {
    return toState(error);
  }

  revalidatePath('/account/orders');
  revalidatePath('/cart');
  revalidatePath('/', 'layout');

  redirect(`/order-confirmation/${encodeURIComponent(orderNumber)}`);
}

export async function previewCheckout(couponCode: string | null): Promise<CheckoutPreview | null> {
  const token = await getActionAccessToken();
  if (!token) return null;

  try {
    return await checkoutApi.preview(token, { couponCode: couponCode ?? undefined });
  } catch {
    return null;
  }
}

export async function previewCheckoutFor(
  addressId: string | null,
  couponCode: string | null,
  paymentMethod?: PaymentMethod,
): Promise<{ preview: CheckoutPreview | null; error: string | null }> {
  const token = await getActionAccessToken();
  if (!token) return { preview: null, error: 'Sign in to continue.' };

  try {
    const preview = await checkoutApi.preview(token, {
      addressId: addressId ?? undefined,
      couponCode: couponCode ?? undefined,
      paymentMethod,
    });
    return { preview, error: null };
  } catch (error) {
    if (error instanceof ApiError) return { preview: null, error: error.message };
    if (error instanceof ApiUnreachableError) {
      return { preview: null, error: 'Could not reach CliQ. Try again in a moment.' };
    }
    throw error;
  }
}
