interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  change?: number | null;
}

function StatCard({ label, value, hint, change }: StatCardProps) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {change !== undefined && change !== null && (
        <span className={`stat-change ${change >= 0 ? "up" : "down"}`}>
          {change >= 0 ? "▲" : "▼"} {Math.abs(change)}%
        </span>
      )}
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export default StatCard;
