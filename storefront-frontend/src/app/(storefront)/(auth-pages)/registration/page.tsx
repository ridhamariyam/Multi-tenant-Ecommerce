import { redirect } from 'next/navigation';

/**
 * Registration folded into sign-in, like /signup.
 *
 * The backend creates an account for any verified number that lacks one, so
 * the username/email/password form here had no endpoint to post to and its
 * buttons only linked between pages.
 */
export default function RegistrationPage() {
  redirect('/signin');
}
