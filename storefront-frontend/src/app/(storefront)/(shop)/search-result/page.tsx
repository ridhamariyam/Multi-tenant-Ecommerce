import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import ProductCard from '@/elements/Shop/ProductCard';
import { catalogueApi } from '@/lib/api/catalogue';
import { searchApi } from '@/lib/api/search';
import { getAccessToken } from '@/lib/auth/session';
import type { ProductStorefront, ProductSummaryStorefront } from '@/types/catalogue';

import styles from './SearchResults.module.css';
import SearchForm from './SearchForm';

const PAGE_SIZE = 24;

export const metadata: Metadata = {
  title: 'Search | CliQ.',
  description: 'Search CliQ products by name, category, brand, or keyword.',
};

function toSummary(product: ProductStorefront): ProductSummaryStorefront {
  return {
    id: product.id,
    slug: product.slug,
    category_id: product.category.id,
    name: product.name,
    short_description: product.short_description,
    brand: product.brand,
    is_featured: product.is_featured,
    primary_image: product.images.find(image => image.is_primary) ?? product.images[0] ?? null,
    price_from: product.price_from,
    price_to: product.price_to,
    on_sale: product.on_sale,
    in_stock: product.in_stock,
  };
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="6.8" />
      <path d="m16 16 4.3 4.3" />
    </svg>
  );
}

export default async function SearchResultPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const { q = '', page: pageParam } = await searchParams;
  const query = q.trim();
  const page = Math.max(1, Number(pageParam ?? 1) || 1);

  if (query !== q) {
    redirect(query ? `/search-result?q=${encodeURIComponent(query)}` : '/search-result');
  }

  let searchFailed = false;
  let products: ProductSummaryStorefront[] = [];
  let total = 0;

  if (query) {
    try {
      const token = await getAccessToken();
      const results = await searchApi.searchProducts({ q: query, page, size: PAGE_SIZE }, token);
      total = results.meta.total_items;
      const detailed = await Promise.all(results.items.map(item => catalogueApi.getProduct(item.id)));
      products = detailed.map(toSummary);
    } catch {
      searchFailed = true;
    }
  }

  const heading = query ? `Search results for “${query}”` : 'Search CliQ';

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <nav className={styles.breadcrumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <Link href="/products">Shop</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Search</span>
        </nav>

        <header>
          <h1 className={styles.heading}>{heading}</h1>
          <p className={styles.subheading}>
            Find your next favourite by product name, category, brand, or keyword.
          </p>
        </header>

        <SearchForm initialQuery={query} />

        {!query && (
          <section className={styles.prompt} aria-live="polite">
            <div className={styles.emptyMark}>
              <SearchIcon />
            </div>
            <h2>What are you looking for?</h2>
            <p>Try a product name, a category, or a keyword like cotton.</p>
          </section>
        )}

        {query && searchFailed && (
          <section className={styles.error} role="alert">
            <h2>We couldn’t load search results</h2>
            <p>Please check your connection and try searching again.</p>
          </section>
        )}

        {query && !searchFailed && (
          <section aria-label="Search results" aria-live="polite">
            <p className={styles.resultMeta}>
              {total} {total === 1 ? 'product' : 'products'} found
            </p>

            {products.length === 0 ? (
              <div className={styles.empty}>
                <div className={styles.emptyMark}>
                  <SearchIcon />
                </div>
                <h2>No products found</h2>
                <p>We couldn’t find a match for “{query}”. Try another name, category, or keyword.</p>
                <Link href="/products" className={styles.continueButton}>
                  Continue Shopping
                </Link>
              </div>
            ) : (
              <div className={styles.grid}>
                {products.map(product => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            )}

            {total > PAGE_SIZE && (
              <nav className={styles.pagination} aria-label="Search result pages">
                {page > 1 && (
                  <Link href={`/search-result?q=${encodeURIComponent(query)}&page=${page - 1}`}>
                    Previous
                  </Link>
                )}
                <span>Page {page}</span>
                {page * PAGE_SIZE < total && (
                  <Link href={`/search-result?q=${encodeURIComponent(query)}&page=${page + 1}`}>
                    Next
                  </Link>
                )}
              </nav>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
