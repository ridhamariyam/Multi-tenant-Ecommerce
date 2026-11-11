import type { Metadata } from 'next';

import styles from '../Info.module.css';

export const metadata: Metadata = {
  title: 'About | CliQ.',
  description: 'CliQ. styles complete looks, head to toe — pick a look, tap a piece, and make it yours.',
};

export default function AboutPage() {
  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Our Story</p>
        <h1 className={styles.title}>Complete looks, styled head to toe.</h1>
        <p className={styles.lead}>
          CliQ. starts with the outfit, not the single piece. Every look is put together in full, so
          you can see how everything works before you choose what to wear.
        </p>
        <div className={styles.body}>
          <h2 className={styles.sectionTitle}>What we make</h2>
          <p>
            Looks built around clean silhouettes and easy layers, styled to wear together and work
            on their own.
          </p>
          <h2 className={styles.sectionTitle}>How it works</h2>
          <p>
            Explore the runway on our home page, open a look, and tap a pin to see each piece. Add
            one piece, or the whole look, to your bag in a couple of clicks.
          </p>
        </div>
      </div>
    </div>
  );
}
