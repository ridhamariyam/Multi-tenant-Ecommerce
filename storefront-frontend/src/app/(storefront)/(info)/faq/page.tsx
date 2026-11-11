import type { Metadata } from 'next';

import styles from '../Info.module.css';

export const metadata: Metadata = {
  title: 'FAQs | CliQ.',
  description: 'Answers to common questions about ordering, shipping, returns and sizing at CliQ.',
};

const FAQS: { q: string; a: string }[] = [
  {
    q: 'How long does shipping take?',
    a: 'Orders are dispatched within 1–2 business days and typically arrive within 3–7 business days, depending on your location.',
  },
  {
    q: 'What is your returns policy?',
    a: 'Unworn items with tags intact can be returned within 14 days of delivery. Start a return from your account under My Orders.',
  },
  {
    q: 'How do I choose the right size?',
    a: 'Each product page carries a size guide with measurements. If you are between sizes, we recommend sizing up.',
  },
  {
    q: 'Which payment methods do you accept?',
    a: 'We accept UPI, credit and debit cards, net banking and cash on delivery. Guest orders are cash on delivery; sign in to pay online.',
  },
  {
    q: 'Can I change or cancel my order?',
    a: 'Orders can be changed or cancelled before they are dispatched. Contact the studio at hello@cliq.example as soon as possible.',
  },
  {
    q: 'How do I track my order?',
    a: 'Use Track Order (link in the footer) with your order number and phone number, or see My Orders in your account.',
  },
];

export default function FaqPage() {
  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Help</p>
        <h1 className={styles.title}>Frequently asked questions.</h1>
        <p className={styles.lead}>
          Everything you need to know about ordering, shipping, returns and sizing. Still stuck?
          Write to us at <a href="mailto:hello@cliq.example">hello@cliq.example</a>.
        </p>
        <div>
          {FAQS.map(item => (
            <div key={item.q} className={styles.faqItem}>
              <p className={styles.faqQ}>{item.q}</p>
              <p className={styles.faqA}>{item.a}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
