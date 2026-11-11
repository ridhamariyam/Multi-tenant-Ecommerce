import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import CollectionView, { type CollectionSearchParams, collectionMetadata } from '../_components/CollectionView';
import { PRODUCTS_COLLECTION_SLUG } from '../_components/collectionQuery';

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  return collectionMetadata((await params).slug);
}

export default async function CollectionPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<CollectionSearchParams>;
}) {
  const { slug } = await params;
  const query = await searchParams;

  // The main collection lives at /products; keep one URL for it.
  if (slug === PRODUCTS_COLLECTION_SLUG) {
    const qs = new URLSearchParams(Object.entries(query).filter((e): e is [string, string] => !!e[1])).toString();
    redirect(qs ? `/products?${qs}` : '/products');
  }

  return <CollectionView slug={slug} query={query} />;
}
