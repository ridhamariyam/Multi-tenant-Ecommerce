import Cart from '@/app/(storefront)/(cart)/cart-items/_components/Cart';
import { checkoutApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';

/**
 * `/shop-cart` is a legacy URL for the same real cart as `/cart-items`.
 * The storefront layout supplies its shared homepage header and footer.
 */
export default async function ShopCartPage() {
  const token = await getAccessToken();
  const preview = token ? await checkoutApi.preview(token).catch(() => null) : null;

  return <Cart preview={preview} />;
}
