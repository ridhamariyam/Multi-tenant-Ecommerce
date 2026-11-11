import { apiRequest } from '@/lib/api/client';
import type { StorefrontHomeSection } from '@/types/cms';

/** Public CMS content is read fresh so a newly activated hero is visible promptly. */
export const cmsApi = {
  getHomepage(): Promise<StorefrontHomeSection[]> {
    return apiRequest<StorefrontHomeSection[]>('/storefront/cms/home', { cache: 'no-store' });
  },
};
