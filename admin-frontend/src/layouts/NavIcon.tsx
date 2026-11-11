// Small, decorative line icons; navigation labels remain the accessible names.
const paths: Record<string, string> = {
  "/": "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  "/reports": "M4 20V10h4v10 M10 20V4h4v16 M16 20v-7h4v7",
  "/orders": "M5 7h14l1 14H4L5 7z M8 7V5a4 4 0 0 1 8 0v2",
  "/customers": "M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3 M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 3a4 4 0 0 1 0 8 M22 21v-3a4 4 0 0 0-3-4",
  "/payments": "M3 5h18v14H3z M3 9h18 M7 15h4",
  "/cod": "M3 6h18v12H3z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M6 10v4 M18 10v4",
  "/coupons": "M3 3h9l9 9-9 9-9-9V3z M7 7h.01",
  "/products": "m12 2 9 5v10l-9 5-9-5V7l9-5z M3 7l9 5 9-5 M12 12v10 M7 5l9 5",
  "/categories": "M3 5h7l2 3h9v12H3V5z",
  "/inventory": "M3 3h18v18H3z M3 9h18 M9 9v12 M13 14h4 M13 17h4",
  "/reviews": "m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1 3-6z",
  "/cms": "M3 4h18v16H3z M3 9h18 M8 9v11 M12 13h5 M12 16h3",
  "/delivery": "M2 6h12v12H2z M14 10h4l4 4v4h-8 M7 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4 M18 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4",
  "/gst": "M5 2h14v20l-3-2-4 2-4-2-3 2V2z M8 7h8 M8 11h8 M8 15h4",
  "/return-reasons": "M8 4 3 9l5 5 M3 9h12a6 6 0 0 1 0 12h-3",
  "/integrations": "M8 2v5 M16 2v5 M5 7h14v3a7 7 0 0 1-14 0V7z M12 17v5",
  "/staff": "m12 2 8 3v6c0 5-8 11-8 11S4 16 4 11V5l8-3z m-4 10 3 3 5-6",
  "/activity": "M3 12h4l3-8 4 16 3-8h4",
};

export default function NavIcon({ path }: { path: string }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[path] ?? paths["/"]} /></svg>;
}
