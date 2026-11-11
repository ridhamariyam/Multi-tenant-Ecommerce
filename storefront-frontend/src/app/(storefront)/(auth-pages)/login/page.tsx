import { redirect } from 'next/navigation';

/**
 * The template's password login, folded into sign-in.
 *
 * It authenticated nobody: the "Sign In" button was a link straight to
 * /account-dashboard, so anyone who pressed it landed on an account page
 * without a session behind it. Customers sign in with a code on /signin;
 * staff use the separate admin frontend. The route is kept as a
 * redirect rather than deleted so existing links do not dead-end.
 */
export default function LoginPage() {
  redirect('/signin');
}
