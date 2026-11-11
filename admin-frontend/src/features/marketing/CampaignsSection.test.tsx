import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const draft = {
  id: "c-1", name: "Diwali drop", subject: "New festive edit", body: "Hello\n\nNew pieces are in.",
  segment: { kind: "ALL" }, status: "DRAFT", recipients: 0, sent_at: null, created_at: "2026-11-11T00:00:00Z", audience: 12,
};

describe("email campaigns", () => {
  it("drafts a campaign for a segment, then sends it after confirming", async () => {
    let sent = false;
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["customers.view", "customers.manage"] }))),
      route("GET", "/admin/marketing/summary", () => ok({ customers: 40, subscribed: 12 })),
      route("POST", "/admin/marketing/audience", () => ok({ count: 12 })),
      route("GET", "/admin/marketing/campaigns", () => ok(sent ? [{ ...draft, status: "SENT", recipients: 12, sent_at: "2026-11-11T10:00:00Z", audience: null }] : [draft])),
      route("POST", "/admin/marketing/campaigns", () => ok(draft)),
      route("POST", "/admin/marketing/campaigns/c-1/send", () => { sent = true; return ok({ ...draft, status: "SENT", recipients: 12 }); }),
    );
    renderApp("/campaigns");

    expect(await screen.findByText(/of 40 customers get marketing email/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Name (only you see it)"), "Diwali drop");
    await userEvent.type(screen.getByLabelText("Subject"), "New festive edit");
    await userEvent.type(screen.getByLabelText(/Message/), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Draft saved. Review it below, then send.")).toBeInTheDocument();
    const created = calls.find((c) => c.init.method === "POST" && c.url.pathname.endsWith("/campaigns"))!;
    expect(JSON.parse(String(created.init.body))).toMatchObject({ name: "Diwali drop", segment: { kind: "ALL" } });

    const row = (await screen.findByText("Draft · would reach 12 customers now")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Send" }));
    await userEvent.click(await screen.findByRole("button", { name: "Send now" }));

    expect(await screen.findByText(/Sent to 12 on/)).toBeInTheDocument();
  });
});
