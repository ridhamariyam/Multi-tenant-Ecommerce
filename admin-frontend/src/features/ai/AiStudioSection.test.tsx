import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockFetch, ok, profile, route } from "../../test/fetchMock";
import { renderApp } from "../../test/renderApp";
import { setBrandId } from "../../utils/storage";

const credits = (configured = true) => ({ balance: 20, configured, provider: configured ? "fashn" : null, price_table: { "balanced:1k": 2, "fast:1k": 1 }, ledger: [] });
const job = {
  id: "j-1", product_id: "p-1", virtual_model_id: "m-1", status: "completed", resolution: "1k", generation_mode: "balanced",
  num_images: 1, credits_reserved: 2, credits_charged: 2, error_message: null, created_at: "2026-11-11T10:00:00Z",
  finished_at: "2026-11-11T10:01:00Z", provider: "fashn",
  outputs: [{ id: "o-1", url: "https://media.example/o-1.jpg", review_status: "PENDING", width: 768, height: 1024 }],
};

describe("AI studio", () => {
  it("queues a generation with an idempotency key and approves a result", async () => {
    setBrandId("brand-1");
    const { calls } = mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["catalogue.view", "catalogue.manage"] }))),
      route("GET", "/admin/ai/credits", () => ok(credits())),
      route("GET", "/admin/ai/jobs", () => ok([job])),
      route("GET", "/catalogue/products", () => ok([{ id: "p-1", name: "Reign Tee" }])),
      route("GET", "/platform/virtual-models", () => ok([{ id: "m-1", name: "Aria", description: null, gender_presentation: "FEMALE", image_url: null }])),
      route("POST", "/admin/ai/jobs", () => ok({ ...job, id: "j-2", status: "queued", outputs: [] })),
      route("POST", "/admin/ai/outputs/o-1/review", () => ok({ ...job.outputs[0], review_status: "APPROVED" })),
    );
    renderApp("/ai-studio");

    expect(await screen.findByText("AI credits left")).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText("Product"), "p-1");
    await userEvent.selectOptions(await screen.findByLabelText("Model"), "m-1");
    expect(screen.getByText(/Costs/)).toHaveTextContent("Costs 2 credits");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText(/Queued. Results appear below/)).toBeInTheDocument();
    const post = calls.find((c) => c.init.method === "POST" && c.url.pathname.endsWith("/admin/ai/jobs"))!;
    expect((post.init.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
    expect(JSON.parse(String(post.init.body))).toMatchObject({ product_id: "p-1", virtual_model_id: "m-1", num_images: 1 });

    const card = screen.getByRole("img", { name: "Generated product photo" }).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Use on product" }));
    expect(await screen.findByText("Added to the product's photos.")).toBeInTheDocument();
  });

  it("explains when no AI provider is configured", async () => {
    setBrandId("brand-1");
    mockFetch(
      route("GET", "/auth/me", () => ok(profile({ role: "ADMIN", permissions: ["catalogue.view", "catalogue.manage"] }))),
      route("GET", "/admin/ai/credits", () => ok(credits(false))),
      route("GET", "/admin/ai/jobs", () => ok([])),
    );
    renderApp("/ai-studio");

    expect(await screen.findByText(/isn't set up on the server yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
  });
});
