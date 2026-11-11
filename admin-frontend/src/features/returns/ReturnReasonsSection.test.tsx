import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["orders.view", "settings.manage"] })));
const reason = (id: string, label: string, is_active = true) => ({ id, label, is_active, position: 0 });

describe("Return reasons settings", () => {
  it("adds only missing suggestions and keeps historical reasons editable", async () => {
    const rows = [reason("r1", "size too small"), reason("r2", "Old reason", false)];
    const { calls } = mockFetch(me,
      route("GET", "/admin/return-reasons", () => ok(rows)),
      route("POST", "/admin/return-reasons", (_url, init) => {
        const body = JSON.parse(init.body as string);
        const added = reason(`r${rows.length + 1}`, body.label);
        rows.push(added);
        return ok(added);
      }),
      route("PATCH", "/admin/return-reasons/r2", (_url, init) => {
        const body = JSON.parse(init.body as string);
        Object.assign(rows[1], body);
        return ok(rows[1]);
      }),
    );
    renderApp("/return-reasons");
    expect(await screen.findByText("size too small")).toBeInTheDocument();
    const guidance = screen.getByText("Add a reason customers can choose when returning an order.");
    expect(guidance.closest(".field")).toContainElement(screen.getByRole("textbox", { name: /New reason/ }));
    expect(guidance.closest(".return-reasons-controls")?.nextElementSibling).toHaveClass("return-reasons-table-panel");
    expect(screen.getByRole("button", { name: "Add 7 suggested reasons" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 7 suggested reasons" }));
    await waitFor(() => expect(calls.filter((call) => call.init.method === "POST").length).toBe(7));
    expect(calls.filter((call) => call.init.method === "POST").every((call) => JSON.parse(call.init.body as string).label !== "Size too small")).toBe(true);
    expect(await screen.findByText("Product damaged or defective")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /suggested reasons/ })).not.toBeInTheDocument();
    const oldRow = screen.getByText("Old reason").closest("tr")!;
    await userEvent.click(within(oldRow).getByRole("button", { name: "Rename" }));
    await userEvent.clear(within(oldRow).getByRole("textbox", { name: "Reason label" }));
    await userEvent.type(within(oldRow).getByRole("textbox", { name: "Reason label" }), "Legacy reason");
    await userEvent.click(within(oldRow).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PATCH")).toBe(true));
  });

  it("confirms deactivation rather than deleting an existing reason", async () => {
    const rows = [reason("r1", "Damaged")];
    const { calls } = mockFetch(me,
      route("GET", "/admin/return-reasons", () => ok(rows)),
      route("PATCH", "/admin/return-reasons/r1", () => { rows[0].is_active = false; return ok(rows[0]); }),
    );
    renderApp("/return-reasons");
    const row = (await screen.findByText("Damaged")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Deactivate" }));
    expect(calls.some((call) => call.init.method === "PATCH")).toBe(false);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PATCH")).toBe(true));
    expect(calls.some((call) => call.init.method === "DELETE")).toBe(false);
    expect(await screen.findByRole("button", { name: "Activate" })).toBeInTheDocument();
  });
});
