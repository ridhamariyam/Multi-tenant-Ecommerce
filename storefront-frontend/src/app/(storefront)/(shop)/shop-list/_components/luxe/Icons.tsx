/**
 * Small inline icon needed only by the Product Listing page's luxe redesign
 * (the Filter button's sliders glyph) -- kept local to this route since
 * nothing else uses it. HeartIcon/HomeIcon moved to the shared Home icon set
 * (`@/app/(storefront)/(home)/home/_components/luxe/Icons`) once the mobile
 * bottom nav became a shared component too.
 */

type IconProps = { size?: number; className?: string };

export const SlidersIcon = ({ size = 15, className }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    className={className}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 7h8M16 7h4" />
    <circle cx="13" cy="7" r="2.2" />
    <path d="M4 12h2M10 12h10" />
    <circle cx="7" cy="12" r="2.2" />
    <path d="M4 17h10M18 17h2" />
    <circle cx="16" cy="17" r="2.2" />
  </svg>
);
