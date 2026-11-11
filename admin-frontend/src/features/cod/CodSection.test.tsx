import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["settings.view", "settings.manage", "payments.view", "payments.manage", "reports.view"] })));
const meta = (count: number) => ({ page: 1, page_size: 50, total_items: count, total_pages: 1 });
const rule = {
  pincode: "682001", is_serviceable: true, cod_available: true,
  min_delivery_days: 2, max_delivery_days: 4, shipping_amount: "49.00", city: "Kochi", state: "Kerala",
};

describe("COD page", () => {
  it("manages actual pincode COD rules, preserves delivery fields, and prevents a duplicate add", async () => {
    const rules = [rule];
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/pincodes", (url) => {
        const search = url.searchParams.get("search") ?? "";
        const matching = rules.filter((item) => item.pincode.startsWith(search));
        return ok(matching, meta(matching.length));
      }),
      route("PUT", /\/admin\/pincodes\/\d{6}$/, (url, init) => {
        const next = { ...(JSON.parse(String(init.body)) as typeof rule), pincode: url.pathname.split("/").at(-1)! };
        const index = rules.findIndex((item) => item.pincode === next.pincode);
        if (index >= 0) rules[index] = next;
        else rules.push(next);
        return ok(next);
      }),
      route("DELETE", /\/admin\/pincodes\/\d{6}$/, (url) => {
        const index = rules.findIndex((item) => item.pincode === url.pathname.split("/").at(-1));
        if (index >= 0) rules.splice(index, 1);
        return { status: 204 };
      })
    );
    renderApp("/cod");
    await userEvent.click(await screen.findByRole("tab", { name: "Pincodes" }));
    expect(await screen.findByRole("cell", { name: "682001" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add pincode" }));
    let dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Pincode" }), "682001");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save pincode" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already has a rule");
    expect(calls.filter((call) => call.init.method === "PUT")).toHaveLength(0);
    await userEvent.clear(within(dialog).getByRole("textbox", { name: "Pincode" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Pincode" }), "560001");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save pincode" }));
    await waitFor(() => expect(calls.filter((call) => call.init.method === "PUT")).toHaveLength(1));
    await screen.findByRole("cell", { name: "560001" });

    const existingRow = screen.getByRole("row", { name: /682001/ });
    await userEvent.click(within(existingRow).getByRole("button", { name: "Edit" }));
    dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "COD allowed for this pincode" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save pincode" }));
    await waitFor(() => expect(calls.filter((call) => call.init.method === "PUT")).toHaveLength(2));
    const body = JSON.parse(String(calls.filter((call) => call.init.method === "PUT").at(-1)!.init.body));
    expect(body).toMatchObject({ cod_available: false, shipping_amount: "49.00", min_delivery_days: 2, max_delivery_days: 4 });

    const addedRow = screen.getByRole("row", { name: /560001/ });
    await userEvent.click(within(addedRow).getByRole("button", { name: "Remove" }));
    const confirmation = await screen.findByRole("dialog");
    expect(confirmation).toHaveTextContent("delivery and shipping overrides");
    await userEvent.click(within(confirmation).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "DELETE" && call.url.pathname.endsWith("/560001"))).toBe(true));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search pincode" }), "682");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/pincodes") && call.url.searchParams.get("search") === "682")).toBe(true));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Delivery status" }), "true");
    await waitFor(() => expect(calls.some((call) => call.url.pathname.endsWith("/admin/pincodes") && call.url.searchParams.get("is_serviceable") === "true")).toBe(true));
  });

  it("shows only Rules, Pincodes and Cash reconciliation while preserving stored COD settings", async () => {
    const settings = {
      is_enabled: true, min_order_amount: null, max_order_amount: null,
      fee_amount: "0.00", advance_amount: null, auto_blacklist_threshold: 3,
    };
    const { calls } = mockFetch(
      me,
      route("GET", "/admin/cod/settings", () => ok(settings)),
      route("PUT", "/admin/cod/settings", (_url, init) => ok(JSON.parse(String(init.body))))
    );
    renderApp("/cod");
    expect((await screen.findAllByRole("tab")).map((tab) => tab.textContent)).toEqual(["Rules", "Pincodes", "Cash reconciliation"]);
    expect(within(document.querySelector(".cod-page") as HTMLElement).queryByText(/blocked numbers|report/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/auto-block/i)).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PUT")).toBe(true));
    const payload = JSON.parse(String(calls.find((call) => call.init.method === "PUT")!.init.body));
    expect(payload.auto_blacklist_threshold).toBe(3);
    expect(calls.some((call) => /\/admin\/cod\/(blacklist|report)/.test(call.url.pathname))).toBe(false);
  });
});
