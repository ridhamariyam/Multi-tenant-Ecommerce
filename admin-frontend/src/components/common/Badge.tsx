const TONES: Record<string, string> = {
  ACTIVE: "ok",
  VERIFIED: "ok",
  REVIEWED: "ok",
  UNVERIFIED: "warn",
  AWAITING_VERIFICATION: "warn",
  NEEDS_REVIEW: "bad",
  PUBLISHED: "ok",
  PAID: "ok",
  DELIVERED: "ok",
  LIVE: "ok",
  DRAFT: "warn",
  PENDING: "warn",
  PARTIALLY_PAID: "warn",
  CONFIRMED: "info",
  PROCESSING: "info",
  PACKED: "info",
  SHIPPED: "info",
  OUT_FOR_DELIVERY: "info",
  ARCHIVED: "bad",
  CANCELLED: "bad",
  RETURNED: "bad",
  FAILED: "bad",
  INACTIVE: "bad",
  BLOCKED: "bad",
};

function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="muted">-</span>;
  return <span className={`badge badge-${TONES[value] ?? "neutral"}`}>{value.replaceAll("_", " ")}</span>;
}

export default Badge;
