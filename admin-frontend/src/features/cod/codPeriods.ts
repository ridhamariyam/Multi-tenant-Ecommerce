export type CodPeriod = "all" | "today" | "yesterday" | "last7" | "lastMonth" | "lastYear" | "custom";

const day = (date: Date) => date.toISOString().slice(0, 10);
const utc = (year: number, month: number, date: number) => new Date(Date.UTC(year, month, date));

// The COD report treats dates as inclusive UTC calendar days.
export function codPeriodRange(period: CodPeriod, now: Date, customStart: string, customEnd: string) {
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth();
  const date = now.getUTCDate();
  const today = day(utc(year, month, date));
  switch (period) {
    case "all": return { start: "0001-01-01", end: today };
    case "today": return { start: today, end: today };
    case "yesterday": {
      const yesterday = day(utc(year, month, date - 1));
      return { start: yesterday, end: yesterday };
    }
    case "last7": return { start: day(utc(year, month, date - 6)), end: today };
    case "lastMonth": return { start: day(utc(year, month - 1, 1)), end: day(utc(year, month, 0)) };
    case "lastYear": return { start: day(utc(year - 1, 0, 1)), end: day(utc(year - 1, 11, 31)) };
    case "custom": return { start: customStart, end: customEnd };
  }
}

export function codCurrentMonthRange(now: Date) {
  return { start: day(utc(now.getUTCFullYear(), now.getUTCMonth(), 1)), end: day(now) };
}
