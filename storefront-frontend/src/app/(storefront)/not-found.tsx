import Link from 'next/link';

import styles from './NotFound.module.css';

export const metadata = {
  title: 'Page not found | CliQ.',
  description: 'The page you are looking for does not exist.',
};

export default function NotFound() {
  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <p className={styles.code}>404</p>
        <h1 className={styles.title}>This page has wandered off.</h1>
        <p className={styles.copy}>
          The page you are looking for does not exist or has moved. Let&rsquo;s get you back to
          something lovely.
        </p>
        <Link href="/" className={styles.btn}>
          Return home
        </Link>
      </div>
    </div>
  );
}
