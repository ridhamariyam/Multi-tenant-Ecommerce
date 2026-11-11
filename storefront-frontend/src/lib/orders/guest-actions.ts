'use server';

import { cookies } from 'next/headers';

import { guestCartApi } from '@/lib/api/cart';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { guestCheckoutApi, type GuestAddressInput, type GuestContactInput } from '@/lib/api/orders';
import { getActionAccessToken } from '@/lib/auth/session';
import { clearGuestCart, readGuestCart } from '@/lib/cart/guest-cart';
import type { CheckoutPreview, Order, OrderTracking, PaymentMethod, RazorpayVerification } from '@/types/orders';

/**
 * Guest checkout.
 *
 * The storefront keeps a guest's cart in its own cookie, while the backend
 * prices and orders a guest cart of its own (named by a cart token). Each
 * call here first makes the backend cart match the cookie, so the price the
 * guest sees and the order they place are for exactly what is in their bag.
 */

const CART_TOKEN_COOKIE = 'cliq_guest_cart_token';
const CART_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

export interface GuestCheckoutInput {
  contact: GuestContactInput;
  address: GuestAddressInput;
  couponCode: string | null;
  idempotencyKey: string;
  paymentMethod: PaymentMethod;
}

export type GuestPreviewResult = { preview: CheckoutPreview | null; error: string | null };

export type GuestPlaceResult =
  | { status: 'placed'; order: Order }
  | { status: 'error'; message: string; fieldErrors: Record<string, string> };

class EmptyCartError extends Error {}

function message(error: unknown): string {
  if (error instanceof EmptyCartError) return 'Your bag is empty -- add something before checking out.';
  if (error instanceof ApiError) {
    if (error.isRateLimited) return 'Too many attempts. Please wait a minute and try again.';
    return error.message;
  }
  if (error instanceof ApiUnreachableError) return 'Could not reach CliQ. Try again in a moment.';
  throw error;
}

/** Same lines and quantities, in any order. */
function sameLines(a: { variant_id: string; quantity: number }[], b: { variant_id: string; quantity: number }[]) {
  if (a.length !== b.length) return false;
  const wanted = new Map(a.map(line => [line.variant_id, line.quantity]));
  return b.every(line => wanted.get(line.variant_id) === line.quantity);
}

async function syncedCartToken(): Promise<string> {
  const lines = await readGuestCart();
  if (lines.length === 0) throw new EmptyCartError();

  const store = await cookies();
  let token = store.get(CART_TOKEN_COOKIE)?.value ?? null;

  // A token can be spent (its order placed), expired, or never issued.
  let current = token ? await guestCartApi.get(token).catch(() => null) : null;
  if (!token || !current) {
    const created = await guestCartApi.create();
    if (!created.guest_token) throw new ApiUnreachableError();
    token = created.guest_token;
    current = created;
    store.set(CART_TOKEN_COOKIE, token, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: CART_TOKEN_MAX_AGE_SECONDS,
    });
  }

  if (!sameLines(lines, current.items)) {
    if (current.items.length > 0) await guestCartApi.clear(token);
    for (const line of lines) await guestCartApi.addItem(token, line.variant_id, line.quantity);
  }

  return token;
}

/** Price the guest's bag; an address (or just a pincode) adds delivery, GST and the COD fee. */
export async function previewGuestCheckout(input: {
  address?: GuestAddressInput | null;
  pincode?: string | null;
  couponCode?: string | null;
  paymentMethod?: PaymentMethod;
}): Promise<GuestPreviewResult> {
  try {
    const token = await syncedCartToken();
    const preview = await guestCheckoutApi.preview(token, input);
    return { preview, error: null };
  } catch (error) {
    return { preview: null, error: message(error) };
  }
}

export async function placeGuestOrder(input: GuestCheckoutInput): Promise<GuestPlaceResult> {
  // Someone who signed in on another tab checks out from their account instead.
  if (await getActionAccessToken()) {
    return { status: 'error', message: 'You are signed in -- reload the page to check out from your account.', fieldErrors: {} };
  }

  try {
    const token = await syncedCartToken();
    const order = await guestCheckoutApi.placeOrder(token, input);

    // The backend cart is spent; empty the bag the shopper sees too.
    await clearGuestCart();
    (await cookies()).delete(CART_TOKEN_COOKIE);

    return { status: 'placed', order };
  } catch (error) {
    const fieldErrors = error instanceof ApiError ? error.fieldErrors() : {};
    return { status: 'error', message: message(error), fieldErrors };
  }
}

export type TrackResult = { tracking: OrderTracking | null; error: string | null };

/** Public order tracking: the order number plus the phone it was placed with. */
export async function trackOrder(orderNumber: string, phone: string): Promise<TrackResult> {
  const number = orderNumber.trim();
  const digits = phone.trim();
  if (!number || !digits) return { tracking: null, error: 'Enter your order number and phone number.' };

  try {
    return { tracking: await guestCheckoutApi.track(number, digits), error: null };
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.status === 422)) {
      return { tracking: null, error: 'No order matches that order number and phone number.' };
    }
    return { tracking: null, error: message(error) };
  }
}

/** Confirm a guest's Razorpay payment. The order stays placed either way. */
export async function confirmGuestPayment(verification: RazorpayVerification): Promise<{ ok: boolean; message: string | null }> {
  try {
    await guestCheckoutApi.verifyPayment(verification);
    return { ok: true, message: null };
  } catch (error) {
    return { ok: false, message: message(error) };
  }
}
