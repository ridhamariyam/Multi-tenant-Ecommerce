import { render, screen } from "@testing-library/react";
import type { FormEvent } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Modal from "./Modal";

describe("modal", () => {
  it("closes without submitting the form it was opened from", async () => {
    const onSubmit = vi.fn((e: FormEvent) => e.preventDefault());
    const onClose = vi.fn();
    render(
      <form onSubmit={onSubmit}>
        <Modal title="Choose an image" onClose={onClose}>Pictures</Modal>
      </form>
    );

    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("closes only the top dialog on Escape", async () => {
    const closeOuter = vi.fn();
    const closeInner = vi.fn();
    render(
      <Modal title="Edit section" onClose={closeOuter}>
        <Modal title="Choose an image" onClose={closeInner}>Pictures</Modal>
      </Modal>
    );

    await userEvent.keyboard("{Escape}");

    expect(closeInner).toHaveBeenCalledOnce();
    expect(closeOuter).not.toHaveBeenCalled();
  });

  it("can omit only the header Close button while keeping dismissal behavior", async () => {
    const onClose = vi.fn();
    render(<Modal title="New coupon" onClose={onClose} showCloseButton={false}>Coupon form</Modal>);

    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
