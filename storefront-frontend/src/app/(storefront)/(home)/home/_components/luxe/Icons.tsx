/** Small inline line-icons for the CliQ.-style home page, kept dependency-free. */

type IconProps = { size?: number; className?: string };

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

export const SearchIcon = ({ size = 18, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </svg>
);

export const UserIcon = ({ size = 18, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 20c1.6-3.6 5-5.5 8-5.5s6.4 1.9 8 5.5" />
  </svg>
);

export const BagIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M6 8h12l-1 12H7L6 8Z" />
    <path d="M9 8V6a3 3 0 0 1 6 0v2" />
  </svg>
);

export const ArrowRightIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M5 12h14" />
    <path d="M13 6l6 6-6 6" />
  </svg>
);

export const ArrowLeftIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M19 12H5" />
    <path d="M11 6l-6 6 6 6" />
  </svg>
);

export const ArrowUpRightIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M7 17 17 7" />
    <path d="M9 7h8v8" />
  </svg>
);

export const ChevronDownIcon = ({ size = 14, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export const ChevronLeftIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M15 6l-6 6 6 6" />
  </svg>
);

export const ChevronRightIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M9 6l6 6-6 6" />
  </svg>
);

export const StarIcon = ({ size = 15, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="currentColor">
    <path d="M12 2.5l2.9 6.1 6.6.7-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.2 1.3-6.6-4.9-4.6 6.6-.7L12 2.5Z" />
  </svg>
);

export const GiftIcon = ({ size = 30, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <rect x="4" y="9" width="16" height="11" rx="1.5" />
    <path d="M4 9h16v3.5H4z" />
    <path d="M12 9v11" />
    <path d="M12 9c-1.2-3.2-6-3.6-6-.8 0 1.4 1.6 1.8 6 .8Z" />
    <path d="M12 9c1.2-3.2 6-3.6 6-.8 0 1.4-1.6 1.8-6 .8Z" />
  </svg>
);

export const TruckIcon = ({ size = 30, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M3 7h11v9H3z" />
    <path d="M14 10h4l3 3v3h-7z" />
    <circle cx="7.5" cy="18" r="1.6" />
    <circle cx="17" cy="18" r="1.6" />
  </svg>
);

export const HandshakeIcon = ({ size = 30, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M2 12l4-4 4 3 3-3 4 4" />
    <path d="M9 11l4 4-1.5 1.5a2 2 0 0 1-2.8 0L6 13.8" />
    <path d="M13.5 15.5 15 17a2 2 0 0 0 2.8 0L20 14.8" />
  </svg>
);

export const MenuIcon = ({ size = 22, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const CloseIcon = ({ size = 22, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export const MinusIcon = ({ size = 14, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M5 12h14" />
  </svg>
);

export const PlusIcon = ({ size = 14, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const XSocialIcon = ({ size = 15, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="currentColor">
    <path d="M18.9 3H21l-6.6 7.6L22.2 21h-6.8l-5.3-6.9L3.9 21H1.8l7-8.1L1 3h7l4.8 6.3L18.9 3Zm-1.2 16h1.9L7.4 4.9H5.4L17.7 19Z" />
  </svg>
);

export const InstagramIcon = ({ size = 16, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="17.2" cy="6.8" r="1" fill="currentColor" stroke="none" />
  </svg>
);

/*
 * A properly symmetric heart -- mirror-imaged left/right around x=12, so it
 * sits dead-center in its viewBox at any size. Used for wishlist toggles
 * (Product Listing cards, the mobile bottom nav's Wishlist tab).
 */
const HEART_PATH =
  'M12 20.5c-.24 0-.47-.08-.66-.23C6.6 16.87 3.5 14 3.5 10.5 3.5 7.8 5.6 5.75 8.25 5.75c1.53 0 2.97.73 3.75 1.9.78-1.17 2.22-1.9 3.75-1.9 2.65 0 4.75 2.05 4.75 4.75 0 3.5-3.1 6.37-7.84 9.77-.19.15-.42.23-.66.23Z';

export const HeartIcon = ({
  size = 16,
  filled = false,
  className,
}: IconProps & { filled?: boolean }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    className={className}
    fill={filled ? 'currentColor' : 'none'}
    stroke="currentColor"
    strokeWidth={filled ? 0 : 1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d={HEART_PATH} />
  </svg>
);

export const HomeIcon = ({ size = 20, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
    <path d="M4 11.5 12 4l8 7.5" />
    <path d="M6 10v9h12v-9" />
  </svg>
);

export const TikTokIcon = ({ size = 15, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="currentColor">
    <path d="M14.5 3h2.9c.2 1.6 1.4 3 3.1 3.3v2.9c-1.5-.1-2.9-.6-4-1.4v6.6a5.6 5.6 0 1 1-5.6-5.6c.3 0 .6 0 .9.1V12a2.7 2.7 0 1 0 1.9 2.6V3Z" />
  </svg>
);
