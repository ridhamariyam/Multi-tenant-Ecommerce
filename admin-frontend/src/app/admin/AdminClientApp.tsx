"use client";

import dynamic from "next/dynamic";

const AdminApp = dynamic(() => import("../../App"), {
  ssr: false,
  loading: () => <div className="state">Loading CliQ. Admin…</div>,
});

export default function AdminClientApp() {
  return <AdminApp />;
}
