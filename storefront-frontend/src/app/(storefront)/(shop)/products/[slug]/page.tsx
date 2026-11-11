import SingleProductPage from '../../single-product/[id]/page';

export default async function ProductBySlugPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ variant?: string }>;
}) {
  return <SingleProductPage params={params} searchParams={searchParams} />;
}
