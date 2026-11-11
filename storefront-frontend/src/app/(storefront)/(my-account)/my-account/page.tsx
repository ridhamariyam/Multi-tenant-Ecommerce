import { redirect } from 'next/navigation';

import MobileBottomNav from '@/components/luxe/MobileBottomNav';
import { addressApi } from '@/lib/api/addresses';
import { getCurrentUser } from '@/lib/auth/current-user';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';

import MyProfile from './_components/MyProfile';

export const metadata = {
  title: 'My Profile | CliQ.',
  description: 'Manage your CliQ profile and saved addresses.',
};

export default async function MyAccountPage() {
  const [token, user] = await Promise.all([getAccessToken(), getCurrentUser()]);
  if (!token || !user) redirect(signInUrl('/account'));

  const addresses = await addressApi.list(token).catch(() => []);

  return (
    <>
      <MyProfile user={user} initialAddresses={addresses} />
      <MobileBottomNav />
    </>
  );
}
