import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Field from "./Field";

describe("Field", () => {
  it("marks only required fields and associates inline errors with their controls", () => {
    const view = render(<>
      <Field label="Product name" required error="Product name is required."><input /></Field>
      <Field label="Description"><textarea /></Field>
    </>);
    const name = screen.getByRole("textbox", { name: "Product name" });
    expect(name).toHaveAttribute("aria-required", "true");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name).toHaveAccessibleDescription("Product name is required.");
    expect(screen.getByText("Product name")).toHaveClass("field-label-required");
    expect(screen.getByRole("textbox", { name: "Description" })).not.toHaveAttribute("aria-required");
    view.rerender(<Field label="Product name" required><input /></Field>);
    expect(screen.getByRole("textbox", { name: "Product name" })).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText("Product name is required.")).not.toBeInTheDocument();
  });
});
