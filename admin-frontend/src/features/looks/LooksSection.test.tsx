import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";

describe("lookbooks", () => {
  it("uploads a cover, pins a product where clicked and saves", async () => {
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["catalogue.view", "catalogue.manage"] }))),
      route("GET", "/admin/looks", () => ok([])),
      route("GET", "/catalogue/products", () => ok([{ id: "p-1", name: "Reign Tee" }])),
      route("POST", "/catalogue/images/upload", () => ok({ url: "https://media.example/t/cover.png" })),
      route("POST", "/admin/looks", () => ok({ id: "l-1", title: "Monsoon", slug: "monsoon", description: null, cover_url: "https://media.example/t/cover.png", status: "DRAFT", pins: [], published_at: null })),
    );
    renderApp("/lookbooks");

    await userEvent.click(await screen.findByRole("button", { name: "New look" }));
    await userEvent.type(screen.getByLabelText("Title"), "Monsoon");
    await userEvent.upload(screen.getByLabelText(/Cover photo/), new File(["x"], "cover.png", { type: "image/png" }));
    const canvas = (await screen.findByRole("img", { name: "Look cover" })).parentElement!;
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 400, right: 200, bottom: 400, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.click(canvas, { clientX: 100, clientY: 100 });
    await userEvent.selectOptions(await screen.findByLabelText("Product for pin 1"), "p-1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    const created = calls.find((c) => c.init.method === "POST" && c.url.pathname.endsWith("/admin/looks"))!;
    expect(JSON.parse(String(created.init.body))).toEqual({
      title: "Monsoon", cover_url: "https://media.example/t/cover.png", pins: [{ product_id: "p-1", x: 0.5, y: 0.25 }],
    });
  });
});
