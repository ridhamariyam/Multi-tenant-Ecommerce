'use client';

import Link from 'next/link';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import collectionStyles from '@/app/(storefront)/(shop)/collections/_components/Collection.module.css';
import CollectionCard from '@/app/(storefront)/(shop)/collections/_components/CollectionCard';
import type { ProductSummaryStorefront } from '@/types/catalogue';
import type { WishlistItem } from '@/types/cart';

import { useWishlist } from '@/context/WishlistContext';
import WishlistCard from './luxe/WishlistCard';

export interface WishlistProductCardData {
  itemId: string;
  product: ProductSummaryStorefront;
  colors: string[];
}

export default function ShopWishList({ products }: { products: WishlistProductCardData[] }) {
  const { wishlist } = useWishlist();
  const productByItemId = new Map(products.map(product => [product.itemId, product]));

  return (
    <main className={`${homeStyles.page} ${collectionStyles.page}`}>
      <section className={`${homeStyles.container} ${collectionStyles.intro}`}>
        <nav className={collectionStyles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Wishlist</span>
        </nav>
        <h1 className={collectionStyles.title}>Wishlist</h1>
        <p className={collectionStyles.description}>
          {wishlist.item_count} saved {wishlist.item_count === 1 ? 'item' : 'items'}
        </p>
      </section>

      <section className={`${homeStyles.container} ${collectionStyles.listing}`} aria-label="Wishlist products">
        {wishlist.items.length === 0 ? (
          <div className={collectionStyles.empty}>
            <p>Your wishlist is empty.</p>
            <Link href="/products" className={collectionStyles.outlineButton}>
              Continue Shopping
            </Link>
          </div>
        ) : (
          <div className={collectionStyles.grid}>
            {wishlist.items.map((item: WishlistItem, index) => {
              const productCard = productByItemId.get(item.id);
              return productCard ? (
                <CollectionCard
                  key={item.id}
                  product={productCard.product}
                  colors={productCard.colors}
                  priority={index < 4}
                  wishlistItem={item}
                />
              ) : (
                <WishlistCard key={item.id} item={item} />
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
