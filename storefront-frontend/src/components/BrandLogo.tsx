'use client';

import { CLIQ_WORDMARK, useBrand } from '@/context/BrandContext';
import { mediaUrl } from '@/lib/media';

/**
 * The store's logo: the CliQ. lockup for the built-in wordmark, an image for
 * any other uploaded logo, otherwise the store name set as text.
 */
export default function BrandLogo({
  cliqMark,
  className,
  textClassName,
}: {
  /** How this spot draws the CliQ. wordmark (its existing CSS lockup). */
  cliqMark: React.ReactNode;
  className?: string;
  textClassName?: string;
}) {
  const { name, logoUrl } = useBrand();
  if (logoUrl === CLIQ_WORDMARK) return <>{cliqMark}</>;
  if (logoUrl) {
    // eslint-disable-next-line @next/next/no-img-element -- remote, per-brand, any size
    return <img src={mediaUrl(logoUrl) ?? logoUrl} alt={name} className={className} />;
  }
  return <span className={textClassName}>{name}</span>;
}
