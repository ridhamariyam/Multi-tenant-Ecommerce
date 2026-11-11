import { redirect } from 'next/navigation';

import { signInUrl } from '@/lib/auth/sign-in-url';

/**
 * Sign-in is a modal over the storefront now, not a page.
 *
 * The route is kept as a redirect so existing links still open sign-in,
 * with the post-sign-in destination carried across.
 */
export default async function SignInPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  redirect(signInUrl(next));
}
