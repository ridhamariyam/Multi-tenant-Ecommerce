import MobileBottomNav from '@/components/luxe/MobileBottomNav';
import { catalogueApi } from '@/lib/api/catalogue';
import { EMPTY_WISHLIST, getWishlist } from '@/lib/wishlist/read';
import type { ProductSummaryStorefront } from '@/types/catalogue';

import ShopWishList, { type WishlistProductCardData } from './_components/ShopWishList';

export const metadata = {
  title: 'Wishlist | CliQ.',
  description: 'Everything you have saved to your CliQ wishlist.',
};

export default async function ShopWishListPage() {
  const wishlist = await getWishlist().catch(() => EMPTY_WISHLIST);
  const products = await Promise.all(
    wishlist.items.map(async item => {
      try {
        const detail = await catalogueApi.getProduct(item.product_id);
        const product: ProductSummaryStorefront = {
          id: detail.id,
          slug: detail.slug,
          category_id: detail.category.id,
          name: detail.name,
          short_description: detail.short_description,
          brand: detail.brand,
          is_featured: detail.is_featured,
          primary_image: detail.images.find(image => image.is_primary) ?? detail.images[0] ?? null,
          price_from: detail.price_from,
          price_to: detail.price_to,
          on_sale: detail.on_sale,
          in_stock: detail.in_stock,
        };
        const colors = [...new Set(detail.variants.map(variant => variant.options.Color).filter((color): color is string => !!color))];
        return { itemId: item.id, product, colors } satisfies WishlistProductCardData;
      } catch {
        // The wishlist endpoint still has the saved item snapshot to render
        // if a product has since become unavailable from the public catalogue.
        return null;
      }
    }),
  );

  return (
    <>
      <ShopWishList products={products.filter((product): product is WishlistProductCardData => product !== null)} />
      <MobileBottomNav />
    </>
  );
}
