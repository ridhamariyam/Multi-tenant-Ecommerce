import { apiRequest, apiRequestPage } from '@/lib/api/client';
import type { Page, PageParams } from '@/types/api';
import type {
  CategoryStorefront,
  ProductListQuery,
  ProductStorefront,
  ProductSummaryStorefront,
  VariantStorefront,
} from '@/types/catalogue';

/** How long the public catalogue may be served from cache, in seconds. */
const CATALOGUE_REVALIDATE = 60;

export const catalogueApi = {
  listCategories(params: PageParams = {}): Promise<Page<CategoryStorefront>> {
    return apiRequestPage<CategoryStorefront>('/storefront/categories', {
      query: { ...params },
      revalidate: CATALOGUE_REVALIDATE,
      tags: ['categories'],
    });
  },

  getCategory(categoryId: string): Promise<CategoryStorefront> {
    return apiRequest<CategoryStorefront>(`/storefront/categories/${categoryId}`, {
      revalidate: CATALOGUE_REVALIDATE,
      tags: ['categories', `category:${categoryId}`],
    });
  },

  /**
   * List products for the grid.
   *
   * Filtering, sorting and paging all happen server-side; the whole
   * catalogue is never pulled down to be filtered in the browser.
   */
  listProducts(query: ProductListQuery = {}): Promise<Page<ProductSummaryStorefront>> {
    return apiRequestPage<ProductSummaryStorefront>('/storefront/products', {
      query: { ...query },
      revalidate: CATALOGUE_REVALIDATE,
      tags: ['products'],
    });
  },

  getProduct(productId: string): Promise<ProductStorefront> {
    return apiRequest<ProductStorefront>(`/storefront/products/${productId}`, {
      revalidate: CATALOGUE_REVALIDATE,
      tags: ['products', `product:${productId}`],
    });
  },

  getProductBySlug(slug: string): Promise<ProductStorefront> {
    return apiRequest<ProductStorefront>(`/storefront/products/by-slug/${encodeURIComponent(slug)}`, {
      revalidate: CATALOGUE_REVALIDATE,
      tags: ['products', `product-slug:${slug}`],
    });
  },

  listProductVariants(productId: string, params: PageParams = {}): Promise<Page<VariantStorefront>> {
    return apiRequestPage<VariantStorefront>(`/storefront/products/${productId}/variants`, {
      query: { ...params },
      revalidate: CATALOGUE_REVALIDATE,
      tags: [`product:${productId}`],
    });
  },

  /** Stock moves, so a variant read is never served from cache. */
  getVariant(variantId: string): Promise<VariantStorefront> {
    return apiRequest<VariantStorefront>(`/storefront/variants/${variantId}`, {
      cache: 'no-store',
    });
  },
};
