export type HelpTopicIcon = 'account' | 'returns' | 'shipping' | 'offers' | 'payments' | 'cancel';

export interface HelpQuestion {
  q: string;
  /** Each entry is one paragraph of the answer. */
  a: string[];
}

export interface HelpTopic {
  slug: string;
  title: string;
  icon: HelpTopicIcon;
  summary: string;
  /** A shortcut to the page that resolves most questions in the topic. */
  link?: { label: string; href: string };
  questions: HelpQuestion[];
}

export const SUPPORT_EMAIL = 'hello@cliq.example';

/**
 * Self-serve answers for the help centre, grouped the way shoppers ask.
 * Policies here must stay in step with /faq and with what checkout and
 * the order pages actually allow.
 */
export const HELP_TOPICS: HelpTopic[] = [
  {
    slug: 'account',
    title: 'Account',
    icon: 'account',
    summary:
      'For account related issues, start with the questions below. Still unable to access your account? Write to the studio and we will help you back in.',
    link: { label: 'Go to your account', href: '/account' },
    questions: [
      {
        q: 'How do I sign in to my CliQ account?',
        a: [
          'Select the account icon in the header and enter your mobile number. We send a one-time code by SMS; enter it to sign in.',
          'You can also continue with Google. There is no password to remember either way.',
        ],
      },
      {
        q: 'Why am I not getting an OTP?',
        a: [
          'Check that the mobile number is correct and has network coverage, then wait a minute before asking for a new code.',
          'If the code still does not arrive, sign in with Google or write to us with the number you are using.',
        ],
      },
      {
        q: 'How do I change the phone number or email on my account?',
        a: [
          'Your account is tied to the phone number or Google email you signed in with. Write to the studio from that number or email and tell us the new one; we will move your account over.',
        ],
      },
      {
        q: 'How do I delete my account?',
        a: [
          'Write to the studio from the phone number or email on your account and ask for it to be deleted. Deleting an account cannot be undone.',
        ],
      },
    ],
  },
  {
    slug: 'returns',
    title: 'Returns & Exchanges',
    icon: 'returns',
    summary:
      'Unworn items with tags intact can be returned within 14 days of delivery. Write to the studio with your order number to start a return; refunds go back to the original payment method.',
    link: { label: 'Go to My Orders', href: '/account/orders' },
    questions: [
      {
        q: 'What is the CliQ returns policy?',
        a: [
          'Unworn items with tags intact can be returned within 14 days of delivery.',
          'Please keep the original packaging. Items that have been worn, washed or altered cannot be accepted.',
        ],
      },
      {
        q: 'How do I return an item?',
        a: [
          'Write to the studio with your order number and the items you want to return. We will reply with the pickup details, and the order shows as Return requested in My Orders.',
        ],
      },
      {
        q: 'Can I exchange an item for a different size?',
        a: [
          'Return the item you have and place a new order in the size you want, so the new piece is reserved for you straight away.',
        ],
      },
      {
        q: 'When will I get my refund?',
        a: [
          'Refunds are issued once the returned item reaches the studio and passes inspection. The time it takes to reach you depends on your bank or payment method.',
        ],
      },
    ],
  },
  {
    slug: 'shipping',
    title: 'Shipping & Delivery',
    icon: 'shipping',
    summary:
      'Orders are dispatched within 1–2 business days and typically arrive within 3–7 business days, depending on your location.',
    link: { label: 'Track an order', href: '/account/orders' },
    questions: [
      {
        q: 'How long does shipping take?',
        a: [
          'Orders are dispatched within 1–2 business days and typically arrive within 3–7 business days, depending on your location.',
        ],
      },
      {
        q: 'How do I track my order?',
        a: ['Once your order ships, you can follow its progress from My Orders in your account, including the courier and tracking number.'],
      },
      {
        q: 'Can I change my delivery address?',
        a: [
          'Write to the studio as soon as possible with your order number. We can update the address until the order is dispatched.',
        ],
      },
    ],
  },
  {
    slug: 'offers',
    title: 'Offers & Coupons',
    icon: 'offers',
    summary:
      'Live offers are shown at checkout. Coupon codes are applied to your bag at checkout and are checked again against your order before you pay.',
    link: { label: 'Go to your bag', href: '/cart' },
    questions: [
      {
        q: 'How do I apply a coupon?',
        a: ['Enter the code in the coupon field at checkout and apply it. The discount is shown in your order summary before you pay.'],
      },
      {
        q: 'Why am I not able to apply a coupon?',
        a: [
          'A coupon can be limited by minimum order value, dates, products or how many times it can be used. The message at checkout tells you which condition was not met.',
        ],
      },
      {
        q: 'What happens to my discount if I return an item?',
        a: ['A discount is shared across the items it applied to, so the refund for a returned item is its price after its share of the discount.'],
      },
    ],
  },
  {
    slug: 'payments',
    title: 'Payments',
    icon: 'payments',
    summary:
      'You can pay with UPI, credit and debit cards, net banking, wallets or cash on delivery. Refund timelines differ based on the payment method.',
    link: { label: 'View your orders', href: '/account/orders' },
    questions: [
      {
        q: 'Which payment methods do you accept?',
        a: ['We accept UPI, credit and debit cards, net banking, wallets and cash on delivery.'],
      },
      {
        q: 'Is there an extra charge for cash on delivery?',
        a: ['Cash orders may carry a small fee, and some may ask for part of the total online up front. Both are shown at checkout before you place the order.'],
      },
      {
        q: 'My payment failed but money was deducted. What should I do?',
        a: [
          'A failed payment is usually reversed by your bank automatically within a few working days. If it has not been, write to us with your order number and we will check it.',
        ],
      },
    ],
  },
  {
    slug: 'cancellations',
    title: 'Cancellations & Charges',
    icon: 'cancel',
    summary:
      'You can track the status of your order in My Orders. Orders can be cancelled from the order page until they are processed.',
    link: { label: 'Go to My Orders', href: '/account/orders' },
    questions: [
      {
        q: 'How do I cancel my order?',
        a: [
          'Open the order from My Orders. If it can still be cancelled, you will see a Cancel Order button on the order page.',
          'Orders can be cancelled before they are processed. If the button is not shown, write to the studio and we will do what we can.',
        ],
      },
      {
        q: 'Will I be refunded if I cancel?',
        a: ['Yes. Any amount paid online is refunded to the original payment method once the cancellation is confirmed.'],
      },
      {
        q: 'Why was my order cancelled?',
        a: [
          'An order may be cancelled if an item goes out of stock or the payment could not be confirmed. Write to the studio with your order number and we will tell you what happened.',
        ],
      },
    ],
  },
];

export function findTopic(slug: string | undefined): HelpTopic | undefined {
  return HELP_TOPICS.find(topic => topic.slug === slug);
}
