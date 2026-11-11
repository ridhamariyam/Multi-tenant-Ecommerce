import { redirect } from 'next/navigation';

/**
 * Verification folded into sign-in.
 *
 * MSG91's widget holds the pending code in the browser, so navigating to a
 * separate route would discard it. Both steps now live on /signin; this
 * stays as a redirect so older links do not dead-end.
 */
export default function OtpVerificationPage() {
  redirect('/signin');
}
