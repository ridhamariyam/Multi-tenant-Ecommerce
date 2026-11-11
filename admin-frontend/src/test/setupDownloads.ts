import { vi } from "vitest";

/** jsdom has no object URLs or real link clicks; capture what would be downloaded. */
export function captureDownloads() {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  return () => click.mock.instances.map((a) => (a as unknown as HTMLAnchorElement).download);
}
