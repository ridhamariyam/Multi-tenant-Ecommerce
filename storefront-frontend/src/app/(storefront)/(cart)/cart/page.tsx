import { checkoutApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import Cart from './_components/Cart';

/**
 * The cart is open to guests, so the checkout preview is best-effort: it
 * needs a session, and an empty cart has nothing to price. The storefront
 * layout supplies the shared homepage header and footer.
 */
export default async function CartPage() {
  const token = await getAccessToken();
  const preview = token ? await checkoutApi.preview(token).catch(() => null) : null;

  return <Cart preview={preview} />;
}
