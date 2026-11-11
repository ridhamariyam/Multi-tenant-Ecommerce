'use client';

import { createContext, useContext } from 'react';

import type { StorefrontBrand } from '@/lib/storefront/brand';

export interface BrandView {
  name: string;
  logoUrl: string | null;
}

const BrandContext = createContext<BrandView>({ name: 'CliQ.', logoUrl: null });

/** The current store's name and logo, for client components (header, footer). */
export function BrandProvider({ brand, children }: { brand: StorefrontBrand | null; children: React.ReactNode }) {
  return (
    <BrandContext.Provider value={{ name: brand?.name ?? 'CliQ.', logoUrl: brand?.logoUrl ?? null }}>
      {children}
    </BrandContext.Provider>
  );
}

export function useBrand(): BrandView {
  return useContext(BrandContext);
}

/** The built-in CliQ. wordmark, drawn with CSS rather than as an image. */
export const CLIQ_WORDMARK = '/images/cliq-wordmark.svg';
