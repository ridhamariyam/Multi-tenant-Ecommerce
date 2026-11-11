import { notFound } from 'next/navigation';

/**
 * Any URL no route matches lands here and renders `(storefront)/not-found.tsx`
 * inside the storefront layout. A root `app/not-found.tsx` cannot do this job:
 * the app has one root layout per route group, and Next refuses to build a
 * root not-found page without a root layout.
 */
export default function MissingPage() {
  notFound();
}
