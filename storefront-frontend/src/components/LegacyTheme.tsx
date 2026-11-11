'use client';

import { usePathname } from 'next/navigation';

import { LEGACY_ROUTES } from '@/constant/legacyRoutes';

const STYLESHEETS = [
  '/assets/icons/iconly/index.min.css',
  '/assets/vendor/lightgallery/css/lightgallery-bundle.min.css',
  '/assets/vendor/swiper/swiper-bundle.min.css',
  '/assets/vendor/animate/animate.css',
  '/assets/css/style.css',
  '/assets/css/skin/skin-1.css',
];

/** Loads the template's theme for its own routes only. */
export default function LegacyTheme() {
  const path = usePathname();
  if (!LEGACY_ROUTES.has(path)) return null;

  return (
    <>
      {STYLESHEETS.map(href => (
        <link key={href} rel="stylesheet" href={href} />
      ))}
    </>
  );
}
