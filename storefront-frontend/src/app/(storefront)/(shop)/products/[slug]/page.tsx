import SingleProductPage from '@/features/product/ProductPage';

export default async function ProductBySlugPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ variant?: string }>;
}) {
  return <SingleProductPage params={params} searchParams={searchParams} />;
}
