export type DashboardPeriod = "today" | "yesterday" | "last7" | "last30" | "month";

export const DASHBOARD_PERIODS: { value: DashboardPeriod; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last7", label: "Last 7 days" },
  { value: "last30", label: "Last 30 days" },
  { value: "month", label: "This month" },
];

const dateText = (date: Date) => date.toISOString().slice(0, 10);
const shift = (date: Date, days: number) => new Date(date.getTime() + days * 86_400_000);

// Dashboard sales and report endpoints both use UTC calendar boundaries.
export function dashboardPeriodRange(period: DashboardPeriod, now = new Date()) {
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const start = period === "yesterday" ? shift(today, -1)
    : period === "last7" ? shift(today, -6)
      : period === "last30" ? shift(today, -29)
        : period === "month" ? new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1)) : today;
  const end = period === "yesterday" ? shift(today, -1) : today;
  const days = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  return {
    start_date: dateText(start), end_date: dateText(end),
    previous_start_date: dateText(shift(start, -days)),
    previous_end_date: dateText(shift(start, -1)),
  };
}

export function currentWeekRange(now = new Date()) {
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const mondayOffset = (today.getUTCDay() + 6) % 7;
  return { start_date: dateText(shift(today, -mondayOffset)), end_date: dateText(today) };
}
