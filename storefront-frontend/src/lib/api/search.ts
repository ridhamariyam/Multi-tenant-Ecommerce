import { apiRequest, apiRequestPage } from '@/lib/api/client';
import type { Page } from '@/types/api';
import type { ProductDiscoveryItem, SearchQuery, SuggestionItem } from '@/types/search';

export const searchApi = {
  /**
   * Search and facet the catalogue.
   *
   * Pages with `size`, not `page_size`, and takes its own sort vocabulary --
   * this endpoint's query contract differs from the product listing's, so
   * the two are deliberately not sharing a params type.
   */
  searchProducts(query: SearchQuery = {}, token?: string | null): Promise<Page<ProductDiscoveryItem>> {
    return apiRequestPage<ProductDiscoveryItem>('/storefront/search-products', {
      query: { ...query },
      token,
      cache: 'no-store',
    });
  },

  suggestions(q: string): Promise<SuggestionItem[]> {
    return apiRequest<SuggestionItem[]>('/storefront/search-suggestions', {
      query: { q },
      cache: 'no-store',
    });
  },

  /** The signed-in shopper's recent searches. */
  history(token: string): Promise<string[]> {
    return apiRequest<string[]>('/storefront/search-history', {
      token,
      cache: 'no-store',
    });
  },
};
