import { addressApi } from '@/lib/api/addresses';
import { checkoutApi, couponApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import type { Address } from '@/types/addresses';
import type { Offer } from '@/types/orders';
import Checkout from './_components/Checkout';
import GuestCheckout from './_components/GuestCheckout';

/**
 * Price the cart and load saved addresses before the form renders.
 *
 * Signed-out shoppers get guest checkout (cash on delivery). For a signed-in
 * customer a failed call degrades to an empty address list and no preview
 * rather than crashing, and the form surfaces the real error on its next action.
 */
export default async function CheckoutPageRoute() {
  const token = await getAccessToken();

  // Guests check out without an account (cash on delivery).
  if (!token) {
    const offers = await couponApi.listOffers().catch((): Offer[] => []);
    return <GuestCheckout availableOffers={offers} />;
  }

  const [addresses, preview, offers] = await Promise.all([
    addressApi.list(token).catch((): Address[] => []),
    checkoutApi.preview(token).catch(() => null),
    couponApi.listOffers().catch((): Offer[] => []),
  ]);

  return <Checkout initialAddresses={addresses} initialPreview={preview} availableOffers={offers} />;
}
