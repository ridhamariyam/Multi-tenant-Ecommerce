import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

const category = (id: string, name: string, parent_id: string | null = null, status = "ACTIVE") => ({
  id, tenant_id: "t1", name, parent_id, status, description: null, hsn_code: "6104", gst_rate: "5",
});
const me = route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["catalogue.view", "catalogue.manage"] })));
const categoriesPage = (rows: ReturnType<typeof category>[], page = 1, pageSize = 100) => ok(
  rows.slice((page - 1) * pageSize, page * pageSize),
  { page, page_size: pageSize, total_items: rows.length, total_pages: Math.ceil(rows.length / pageSize) },
);

describe("Categories page", () => {
  it("separates category management from compact filter-value lists", async () => {
    mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([category("c1", "Kurtas")])),
      route("GET", "/catalogue/attributes", () => ok([
        { id: "a1", attribute: "fabric", value: "Cotton", is_active: true, position: 0, product_count: 2 },
        { id: "a2", attribute: "occasion", value: "Wedding", is_active: false, position: 0, product_count: 0 },
      ])),
    );
    renderApp("/categories");
    expect(await screen.findByRole("columnheader", { name: "Category name" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Filter values" }));
    expect(screen.queryByRole("columnheader", { name: "Category name" })).not.toBeInTheDocument();
    expect(await within(screen.getByRole("region", { name: "fabric values" })).findByText("Cotton")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "occasion values" })).getByText("Wedding")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "occasion values" })).getByText("INACTIVE")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "sleeve values" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "neckline values" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Categories & subcategories" }));
    expect(await screen.findByRole("columnheader", { name: "Category name" })).toBeInTheDocument();
  });

  it("keeps 105 fabric values in one contained list with Add outside the scroller and actions reachable", async () => {
    const values = Array.from({ length: 105 }, (_, index) => ({ id: `a${index}`, attribute: "fabric", value: `Fabric ${index}`, is_active: true, position: index, product_count: 0 }));
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([])),
      route("GET", "/catalogue/attributes", () => ok(values)),
      route("PATCH", /\/catalogue\/attributes\/a104$/, (_url, init) => {
        Object.assign(values[104], JSON.parse(init.body as string));
        return ok(values[104]);
      }),
      route("POST", "/catalogue/attributes", (_url, init) => {
        const body = JSON.parse(init.body as string);
        const added = { id: "a105", attribute: "fabric", value: body.value, is_active: true, position: 105, product_count: 0 };
        values.push(added);
        return ok(added);
      }),
    );
    renderApp("/categories");
    await userEvent.click(await screen.findByRole("tab", { name: "Filter values" }));
    const card = screen.getByRole("region", { name: "fabric values" });
    const list = card.querySelector(".attribute-values-list")!;
    expect(list).toContainElement(await within(card).findByText("Fabric 0"));
    expect(list).toContainElement(within(card).getByText("Fabric 104"));
    expect(list).not.toContainElement(within(card).getByRole("textbox", { name: "New fabric" }));
    list.scrollTop = 10000;
    fireEvent.scroll(list);
    const last = within(card).getByText("Fabric 104").closest("li")!;
    await userEvent.click(within(last).getByRole("button", { name: "Rename" }));
    await userEvent.clear(within(last).getByRole("textbox", { name: "Rename Fabric 104" }));
    await userEvent.type(within(last).getByRole("textbox", { name: "Rename Fabric 104" }), "Handloom 104");
    await userEvent.click(within(last).getByRole("button", { name: "Save" }));
    expect(await within(card).findByText("Handloom 104")).toBeInTheDocument();
    await userEvent.click(within(within(card).getByText("Handloom 104").closest("li")!).getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(within(within(card).getByText("Handloom 104").closest("li")!).getByText("INACTIVE")).toBeInTheDocument());
    await userEvent.type(within(card).getByRole("textbox", { name: "New fabric" }), "Linen");
    await userEvent.click(within(card).getByRole("button", { name: "Add" }));
    expect(await within(card).findByText("Linen")).toBeInTheDocument();
    expect(calls.filter((call) => call.init.method === "PATCH")).toHaveLength(2);
    expect(calls.filter((call) => call.init.method === "POST" && call.url.pathname.endsWith("/catalogue/attributes"))).toHaveLength(1);
  });
  it("requires a name but keeps tax defaults optional when creating a draft", async () => {
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([])),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("POST", "/catalogue/categories", () => ok(category("draft", "Kurtas", null, "DRAFT"))),
    );
    renderApp("/categories");
    await userEvent.click(await screen.findByRole("button", { name: "New category" }));
    const dialog = screen.getByRole("dialog", { name: "New category" });
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Status" }), "DRAFT");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create category" }));
    const name = within(dialog).getByRole("textbox", { name: "Name" });
    expect(name).toHaveAccessibleDescription("Category name is required.");
    expect(calls.some((call) => call.init.method === "POST")).toBe(false);
    await userEvent.type(name, "   ");
    expect(name).toHaveAttribute("aria-invalid", "true");
    await userEvent.clear(name);
    await userEvent.type(name, "Kurtas");
    expect(name).not.toHaveAttribute("aria-invalid");
    expect(within(dialog).getByRole("textbox", { name: "Legacy HSN code" })).not.toHaveAttribute("aria-required");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create category" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "POST")).toBe(true));
    const posted = calls.find((call) => call.init.method === "POST");
    expect(JSON.parse(posted!.init.body as string)).toMatchObject({ name: "Kurtas", status: "DRAFT", hsn_code: null, gst_rate: null });
  });

  it("shows hierarchy and filters real active, draft and archived categories", async () => {
    mockFetch(me,
      route("GET", "/catalogue/categories", (url) => {
        expect(url.searchParams.get("include_archived")).toBe("true");
        return categoriesPage([category("c1", "Kurtas"), category("c2", "Cotton Kurtas", "c1"), category("c3", "Unfinished", null, "DRAFT"), category("c4", "Retired", "c1", "ARCHIVED")]);
      }),
      route("GET", "/catalogue/attributes", () => ok([])),
    );
    renderApp("/categories");
    expect(await screen.findByText(/Cotton Kurtas/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Category ID" })).toBeInTheDocument();
    const row = screen.getByText(/Cotton Kurtas/).closest("tr")!;
    expect(within(row).getByText("c2")).toBeInTheDocument();
    expect(within(row).getByText("Kurtas")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category status" }), "DRAFT");
    expect(screen.getByText("Unfinished")).toBeInTheDocument();
    expect(screen.queryByText(/Cotton Kurtas/)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category status" }), "ACTIVE");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search categories" }), "cotton");
    expect(screen.getByText(/Cotton Kurtas/)).toBeInTheDocument();
    expect(screen.queryByText("Unfinished")).not.toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search categories" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category status" }), "ARCHIVED");
    const archived = screen.getByText("Retired").closest("tr")!;
    expect(within(archived).getByText("Kurtas")).toBeInTheDocument();
    expect(within(archived).getByText("ARCHIVED")).toBeInTheDocument();
    expect(within(archived).getByText("6104")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 1 (1 items)")).toBeInTheDocument();
  });

  it("archives through the API, refreshes the list and restores through supported PATCH", async () => {
    let currentStatus = "ACTIVE";
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([category("c1", "Kurtas", null, currentStatus)])),
      route("DELETE", "/catalogue/categories/c1", () => { currentStatus = "ARCHIVED"; return ok(null); }),
      route("PATCH", "/catalogue/categories/c1", () => { currentStatus = "DRAFT"; return ok(category("c1", "Kurtas", null, "DRAFT")); }),
      route("GET", "/catalogue/attributes", () => ok([])),
    );
    renderApp("/categories");
    await screen.findByText("Kurtas");
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "DELETE" && call.url.pathname.endsWith("/catalogue/categories/c1"))).toBe(true));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category status" }), "ARCHIVED");
    const row = (await screen.findByText("Kurtas")).closest("tr")!;
    expect(within(row).getByText("ARCHIVED")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Restore to draft" }));
    await waitFor(() => expect(calls.some((call) => call.init.method === "PATCH" && JSON.parse(call.init.body as string).status === "DRAFT")).toBe(true));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category status" }), "DRAFT");
    expect(await screen.findByText("Kurtas")).toBeInTheDocument();
  });

  it("offers Draft editing but routes archiving through the guarded archive action", async () => {
    mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([category("c1", "Kurtas")])),
      route("GET", "/catalogue/attributes", () => ok([])),
      route("DELETE", "/catalogue/categories/c1", () => ({ status: 409, body: { detail: "Category still has sub-categories" } })),
    );
    renderApp("/categories");
    await userEvent.click(await screen.findByRole("button", { name: "Kurtas" }));
    const dialog = screen.getByRole("dialog", { name: "Edit Kurtas" });
    expect(within(dialog).getByRole("option", { name: "Draft" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("option", { name: "Archived" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    expect(await screen.findByText(/Could not archive/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kurtas" })).toBeInTheDocument();
  });

  it("keeps category edits when continuing and confirms before closing a changed form", async () => {
    mockFetch(me,
      route("GET", "/catalogue/categories", () => categoriesPage([category("c1", "Kurtas")])),
      route("GET", "/catalogue/attributes", () => ok([])),
    );
    renderApp("/categories");
    await userEvent.click(await screen.findByRole("button", { name: "Kurtas" }));
    const name = within(screen.getByRole("dialog", { name: "Edit Kurtas" })).getByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Cotton Kurtas");
    await userEvent.click(within(screen.getByRole("dialog", { name: "Edit Kurtas" })).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("dialog", { name: "Unsaved changes" })).getByRole("button", { name: "Continue editing" }));
    expect(name).toHaveValue("Cotton Kurtas");
    await userEvent.click(within(screen.getByRole("dialog", { name: "Edit Kurtas" })).getByRole("button", { name: "Cancel" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Unsaved changes" })).getByRole("button", { name: "Discard changes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("loads every API page before filtering or showing local pagination", async () => {
    const rows = Array.from({ length: 100 }, (_, index) => category(`c${index}`, `Category ${index}`));
    rows.push(category("archived", "Old stock", null, "ARCHIVED"));
    const { calls } = mockFetch(me,
      route("GET", "/catalogue/categories", (url) => categoriesPage(rows, Number(url.searchParams.get("page") ?? 1))),
      route("GET", "/catalogue/attributes", () => ok([])),
    );
    renderApp("/categories");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Category status" }), "ARCHIVED");
    expect(await screen.findByText("Old stock")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.pathname.endsWith("/catalogue/categories")).map((call) => call.url.searchParams.get("page"))).toEqual(["1", "2"]);
    expect(screen.getByText("Page 1 of 1 (1 items)")).toBeInTheDocument();
  });
});
