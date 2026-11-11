import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AttributeSelect from "./AttributeSelect";

const option = (value: string) => ({ id: value, attribute: "fabric" as const, value, is_active: true, position: 0, product_count: 0 });

describe("attribute picker", () => {
  it("offers the managed values", () => {
    render(<AttributeSelect label="fabric" value="" options={[option("Cotton"), option("Silk")]} onChange={() => undefined} />);

    const labels = within(screen.getByLabelText("fabric")).getAllByRole("option").map((o) => o.textContent);
    expect(labels).toEqual(["Not set", "Cotton", "Silk"]);
  });

  it("keeps an older value that is not in the list", () => {
    render(<AttributeSelect label="fabric" value="Handloom" options={[option("Cotton")]} onChange={() => undefined} />);

    expect((screen.getByLabelText("fabric") as HTMLSelectElement).value).toBe("Handloom");
    expect(screen.getByRole("option", { name: "Handloom (not in list)" })).toBeInTheDocument();
  });

  it("matches list values regardless of case", () => {
    render(<AttributeSelect label="fabric" value="cotton" options={[option("Cotton")]} onChange={() => undefined} />);

    expect((screen.getByLabelText("fabric") as HTMLSelectElement).value).toBe("Cotton");
    expect(screen.queryByText(/not in list/)).not.toBeInTheDocument();
  });

  it("keeps the current selection on cancel and rejects blank or duplicate names", async () => {
    const create = vi.fn(async (value: string) => value);
    render(<AttributeSelect label="fabric" value="Cotton" options={[option("Cotton")]} existingValues={[option("Cotton"), { ...option("Silk"), is_active: false }]} onChange={() => undefined} onCreate={create} />);
    await userEvent.click(screen.getByRole("button", { name: "+ Add new fabric" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Fabric name is required.");
    await userEvent.type(screen.getByRole("textbox", { name: "New fabric name" }), " cotton ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("already exists");
    await userEvent.clear(screen.getByRole("textbox", { name: "New fabric name" }));
    await userEvent.type(screen.getByRole("textbox", { name: "New fabric name" }), "Silk");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("switched off");
    expect(create).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("combobox", { name: "fabric" })).toHaveValue("Cotton");
  });

  it("reports an API failure and allows retry without losing the new value", async () => {
    const create = vi.fn().mockRejectedValueOnce(new Error("Network unavailable")).mockResolvedValueOnce("Linen");
    const onChange = vi.fn();
    render(<AttributeSelect label="fabric" value="" options={[]} onChange={onChange} onCreate={create} />);
    await userEvent.click(screen.getByRole("button", { name: "+ Add new fabric" }));
    await userEvent.type(screen.getByRole("textbox", { name: "New fabric name" }), "  Linen  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
    expect(screen.getByRole("textbox", { name: "New fabric name" })).toHaveValue("  Linen  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(create).toHaveBeenCalledWith("Linen");
    expect(onChange).toHaveBeenCalledWith("Linen");
    expect(await screen.findByRole("status")).toHaveTextContent("Added Linen.");
  });

  it("does not submit the same new value twice while saving", async () => {
    let finish: (value: string) => void = () => undefined;
    const pending = new Promise<string>((resolve) => { finish = resolve; });
    const create = vi.fn(() => pending);
    render(<AttributeSelect label="fabric" value="" options={[]} onChange={() => undefined} onCreate={create} />);
    await userEvent.click(screen.getByRole("button", { name: "+ Add new fabric" }));
    await userEvent.type(screen.getByRole("textbox", { name: "New fabric name" }), "Linen");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(create).toHaveBeenCalledTimes(1);
    finish("Linen");
    expect(await screen.findByRole("status")).toHaveTextContent("Added Linen.");
  });
});
