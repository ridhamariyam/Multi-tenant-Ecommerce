import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import styles from '../../Info.module.css';
import { POLICY_SLUGS } from '../slugs';

type Section = { heading: string; body: string };
type Policy = { title: string; lead: string; sections: Section[] };

const CONTACT = 'hello@cliq.example';

const POLICIES: Record<(typeof POLICY_SLUGS)[number], Policy> = {
  privacy: {
    title: 'Privacy policy',
    lead: 'What CliQ collects when you shop with us, why, and the choices you have.',
    sections: [
      {
        heading: 'What we collect',
        body: 'Your mobile number or Google account details when you sign in, your name, delivery addresses, order history, wishlist and any reviews you write.',
      },
      {
        heading: 'How we use it',
        body: 'To sign you in, process and deliver orders, handle returns and refunds, send order updates, and meet our tax and accounting obligations.',
      },
      {
        heading: 'Who we share it with',
        body: 'Only the providers needed to run the store: Razorpay for payments, MSG91 for sign-in codes, and our courier partners for delivery. We never see or store your full card details, and we do not sell your data.',
      },
      {
        heading: 'Your choices',
        body: `You can update your profile and addresses from your account, and delete your account there at any time. Past orders are kept for our records with your personal details removed. For anything else, write to ${CONTACT}.`,
      },
    ],
  },
  terms: {
    title: 'Terms and conditions',
    lead: 'The terms that apply when you use this site or place an order with CliQ.',
    sections: [
      {
        heading: 'Orders',
        body: 'Placing an order is an offer to buy. It is accepted once we confirm it. We may cancel an order if an item is unavailable or a price is shown in error, and any payment taken is refunded.',
      },
      {
        heading: 'Prices and payment',
        body: 'Prices are in Indian rupees. Applicable taxes are shown at checkout before you pay. We accept UPI, cards, net banking and cash on delivery where available.',
      },
      {
        heading: 'Your account',
        body: 'Keep access to your mobile number and account secure. You are responsible for activity under your account.',
      },
      {
        heading: 'Contact',
        body: `Questions about these terms can be sent to ${CONTACT}.`,
      },
    ],
  },
  'shipping-returns': {
    title: 'Shipping, returns and refunds',
    lead: 'How your order reaches you, and what to do if it is not right.',
    sections: [
      {
        heading: 'Shipping',
        body: 'Orders are dispatched within 1–2 business days and typically arrive within 3–7 business days, depending on your location. You can follow your order from My Orders in your account.',
      },
      {
        heading: 'Cancellations',
        body: 'You can cancel an order from My Orders until it has been dispatched.',
      },
      {
        heading: 'Returns',
        body: 'Unworn items with tags intact can be returned within 14 days of delivery. Start a return from your account under My Orders.',
      },
      {
        heading: 'Refunds',
        body: `Refunds go back to your original payment method once the returned item has been received and checked. If a refund has not reached you, write to ${CONTACT}.`,
      },
    ],
  },
};

type Props = { params: Promise<{ slug: string }> };

function find(slug: string): Policy | undefined {
  return Object.hasOwn(POLICIES, slug) ? POLICIES[slug as keyof typeof POLICIES] : undefined;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const policy = find(slug);
  return policy ? { title: policy.title, description: policy.lead, alternates: { canonical: `/policies/${slug}` } } : {};
}

export default async function PolicyPage({ params }: Props) {
  const policy = find((await params).slug);
  if (!policy) notFound();

  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Legal</p>
        <h1 className={styles.title}>{policy.title}</h1>
        <p className={styles.lead}>{policy.lead}</p>
        {policy.sections.map(section => (
          <div key={section.heading} className={styles.faqItem}>
            <p className={styles.faqQ}>{section.heading}</p>
            <p className={styles.faqA}>{section.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
