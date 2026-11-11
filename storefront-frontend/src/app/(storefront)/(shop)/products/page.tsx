import type { Metadata } from 'next';

import CollectionView, { type CollectionSearchParams, collectionMetadata } from '../collections/_components/CollectionView';
import { PRODUCTS_COLLECTION_SLUG } from '../collections/_components/collectionQuery';

export function generateMetadata(): Promise<Metadata> {
  return collectionMetadata(PRODUCTS_COLLECTION_SLUG);
}

export default async function ProductsPage({ searchParams }: { searchParams: Promise<CollectionSearchParams> }) {
  return <CollectionView slug={PRODUCTS_COLLECTION_SLUG} query={await searchParams} />;
}
