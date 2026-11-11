import type { Metadata } from 'next';

import { AuthProvider } from '@/context/AuthContext';
import { SignInModalProvider } from '@/context/SignInModalContext';
import { getCurrentUser } from '@/lib/auth/current-user';
import { getCart } from '@/lib/cart/read';
import { absoluteUrl, DEFAULT_OG_IMAGE, JsonLd, SITE_NAME } from '@/lib/seo';

import RunwayClient from './_runway/RunwayClient';
import { loadRunwayLooks } from './_runway/load';
import { renderRunwayMarkup } from './_runway/markup';

const HOME_DESCRIPTION =
  'Six complete looks, styled head to toe. Explore the runway, tap a pin to see each piece, and add the whole look to your bag.';

export const metadata: Metadata = {
  title: { absolute: 'CliQ. — Try the Look' },
  description: HOME_DESCRIPTION,
  alternates: { canonical: '/' },
  openGraph: { title: 'CliQ. — Try the Look', description: HOME_DESCRIPTION, url: '/', images: [DEFAULT_OG_IMAGE] },
};

/** The cart badge and account link are per visitor, so this page is never statically cached. */
export const dynamic = 'force-dynamic';

export default async function RunwayHome() {
  const [looks, cart, user] = await Promise.all([
    loadRunwayLooks(),
    getCart().catch(() => null),
    getCurrentUser().catch(() => null),
  ]);
  const first = looks[0]?.model.src;
  const home = await absoluteUrl('/');

  return (
    <div className="cliq">
      <JsonLd
        data={[
          { '@context': 'https://schema.org', '@type': 'Organization', name: SITE_NAME, url: home, logo: `${home}icon.svg` },
          {
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            name: SITE_NAME,
            url: home,
            potentialAction: {
              '@type': 'SearchAction',
              target: { '@type': 'EntryPoint', urlTemplate: `${home}search-result?q={search_term_string}` },
              'query-input': 'required name=search_term_string',
            },
          },
        ]}
      />
      {first ? <link rel="preload" as="image" href={first} fetchPriority="high" /> : null}
      {/* Sign-in redirects land on /?signin=1, so the modal has to live on this page too. */}
      <AuthProvider user={user}>
        <SignInModalProvider>
          <RunwayClient initialCount={cart?.item_count ?? 0} />
        </SignInModalProvider>
      </AuthProvider>
      <main dangerouslySetInnerHTML={{ __html: renderRunwayMarkup(looks) }} />
    </div>
  );
}
