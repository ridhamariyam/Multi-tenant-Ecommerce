import Link from 'next/link';

import styles from './NotFoundHero.module.css';

/** The open-box illustration under the button. Purely decorative. */
function BoxIllustration() {
  return (
    <svg className={styles.illustration} viewBox="0 0 240 180" fill="none" aria-hidden="true">
      <ellipse cx="120" cy="158" rx="62" ry="8" fill="#efe8d9" />

      {/* sparkle lines */}
      <g stroke="#cdbe9e" strokeWidth="3" strokeLinecap="round">
        <path d="M95 25 85 5" />
        <path d="M120 20V0" />
        <path d="M145 25l10-20" />
      </g>

      {/* open lid, left half */}
      <path d="M60 70 120 25v45z" fill="#efe6d3" />
      {/* open lid, right half */}
      <path d="M180 70 120 25v45z" fill="#e2d5bc" />

      {/* box body */}
      <path d="M60 70h120l-15 80H75z" fill="#d7c9ac" />
    </svg>
  );
}

/**
 * The 404 page's hero: oversized numeral, heading, subtext, a link home,
 * and the box illustration. All static -- there is nothing here that needs
 * to be a client component.
 */
export default function NotFoundHero() {
  return (
    <div className={styles.hero}>
      <p className={styles.numeral} aria-hidden="true">
        404
      </p>

      <h1 className={styles.heading}>Page Not Found</h1>
      <p className={styles.subtitle}>The page you&apos;re looking for doesn&apos;t exist or may have been moved.</p>

      <Link href="/" className={styles.homeBtn}>
        Go to Homepage
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 12h16M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </Link>

      <BoxIllustration />
    </div>
  );
}
