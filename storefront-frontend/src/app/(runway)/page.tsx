import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AuthProvider } from '@/context/AuthContext';
import { SignInModalProvider } from '@/context/SignInModalContext';
import { getCurrentUser } from '@/lib/auth/current-user';
import { getCart } from '@/lib/cart/read';
import { absoluteUrl, DEFAULT_OG_IMAGE, JsonLd } from '@/lib/seo';
import { brandName } from '@/lib/storefront/brand';

import RunwayClient from './_runway/RunwayClient';
import { loadRunwayLooks } from './_runway/load';
import { renderRunwayMarkup } from './_runway/markup';

const HOME_DESCRIPTION =
  'Six complete looks, styled head to toe. Explore the runway, tap a pin to see each piece, and add the whole look to your bag.';

export async function generateMetadata(): Promise<Metadata> {
  const title = `${await brandName()} — Try the Look`;
  return {
    title: { absolute: title },
    description: HOME_DESCRIPTION,
    alternates: { canonical: '/' },
    openGraph: { title, description: HOME_DESCRIPTION, url: '/', images: [DEFAULT_OG_IMAGE] },
  };
}

/** The cart badge and account link are per visitor, so this page is never statically cached. */
export const dynamic = 'force-dynamic';

export default async function RunwayHome() {
  const [looks, cart, user] = await Promise.all([
    loadRunwayLooks(),
    getCart().catch(() => null),
    getCurrentUser().catch(() => null),
  ]);
  // The curated looks are CliQ.'s; a store with none of their products
  // opens on its catalogue until it has a homepage of its own.
  if (looks.length === 0) redirect('/products');

  const first = looks[0]?.model.src;
  const [home, storeName] = await Promise.all([absoluteUrl('/'), brandName()]);

  return (
    <div className="cliq">
      <JsonLd
        data={[
          { '@context': 'https://schema.org', '@type': 'Organization', name: storeName, url: home, logo: `${home}icon.svg` },
          {
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            name: storeName,
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
