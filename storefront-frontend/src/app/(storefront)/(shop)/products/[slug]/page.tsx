import type { Metadata } from 'next';

import SingleProductPage from '@/features/product/ProductPage';
import { productMetadata } from '@/features/product/productSeo';
import { catalogueApi } from '@/lib/api/catalogue';
import { brandName } from '@/lib/storefront/brand';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  // Same cached request the page makes; a miss leaves the page to render its 404.
  const product = await (UUID.test(slug) ? catalogueApi.getProduct(slug) : catalogueApi.getProductBySlug(slug)).catch(
    () => null,
  );
  return product ? productMetadata(product, await brandName()) : { title: 'Product not found' };
}

export default async function ProductBySlugPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ variant?: string }>;
}) {
  return <SingleProductPage params={params} searchParams={searchParams} />;
}
