import { redirect } from 'next/navigation';

/**
 * Registration folded into sign-in.
 *
 * The backend creates an account for any verified number that lacks one, so
 * the two screens collected the same single field and posted to the same
 * endpoint. The route is kept as a redirect rather than deleted so existing
 * links and bookmarks still land somewhere useful.
 */
export default function SignUpPage() {
  redirect('/signin');
}
