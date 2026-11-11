/**
 * Where to send someone who has to sign in first.
 *
 * Sign-in is a modal rather than a page, so a server-side redirect lands on
 * the homepage with `?signin=1`; the shell sees the flag and opens the modal,
 * and `next` is where a successful sign-in returns them.
 */
export const SIGN_IN_PARAM = 'signin';

export function signInUrl(next?: string): string {
  const params = new URLSearchParams({ [SIGN_IN_PARAM]: '1' });
  if (next) params.set('next', next);
  return `/?${params.toString()}`;
}
