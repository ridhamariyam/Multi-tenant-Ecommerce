import type { Metadata } from "next";
import "../index.css";
import "../screens/admin.css";

export const metadata: Metadata = {
  title: "CliQ. Admin",
  description: "CliQ. store administration",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
