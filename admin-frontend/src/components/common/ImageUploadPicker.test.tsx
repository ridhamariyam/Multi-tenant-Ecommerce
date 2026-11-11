import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ImageUploadPicker from "./ImageUploadPicker";

describe("ImageUploadPicker", () => {
  it("offers device and camera selection without showing a native file control", async () => {
    const onFiles = vi.fn();
    render(<ImageUploadPicker inputLabel="Product photos" accept="image/jpeg,image/png,image/webp" multiple onFiles={onFiles} />);
    const trigger = screen.getByRole("button", { name: /Upload images/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("Product photos")).toHaveAttribute("multiple");
    expect(screen.getByLabelText("Product photos")).toHaveAttribute("hidden");
    expect(screen.getByLabelText("Product photos camera")).toHaveAttribute("capture", "environment");
    await userEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: /Take photo/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Upload from device/ })).toBeInTheDocument();
    const cameraClick = vi.spyOn(screen.getByLabelText("Product photos camera"), "click");
    await userEvent.click(screen.getByRole("menuitem", { name: /Take photo/ }));
    expect(cameraClick).toHaveBeenCalledOnce();
    await userEvent.click(trigger);
    const deviceClick = vi.spyOn(screen.getByLabelText("Product photos"), "click");
    await userEvent.click(screen.getByRole("menuitem", { name: /Upload from device/ }));
    expect(deviceClick).toHaveBeenCalledOnce();
    const first = new File(["a"], "one.png", { type: "image/png" });
    const second = new File(["b"], "two.webp", { type: "image/webp" });
    await userEvent.upload(screen.getByLabelText("Product photos"), [first, second]);
    expect(onFiles).toHaveBeenCalledWith([first, second]);
    await userEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await userEvent.upload(screen.getByLabelText("Product photos camera"), first);
    expect(onFiles).toHaveBeenCalledWith([first]);
  });

  it("opens a live camera, captures a file, and stops the stream", async () => {
    const stop = vi.fn();
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
    const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["photo"], { type: "image/jpeg" })));
    const onFiles = vi.fn();
    try {
      render(<ImageUploadPicker inputLabel="Photo" accept="image/jpeg" onFiles={onFiles} />);
      await userEvent.click(screen.getByRole("button", { name: /Upload images/ }));
      await userEvent.click(screen.getByRole("menuitem", { name: /Take photo/ }));
      expect(getUserMedia).toHaveBeenCalledWith({ audio: false, video: { facingMode: { ideal: "environment" } } });
      const preview = await screen.findByLabelText("Camera preview");
      Object.defineProperty(preview, "videoWidth", { configurable: true, value: 640 });
      Object.defineProperty(preview, "videoHeight", { configurable: true, value: 480 });
      await waitFor(() => expect(screen.getByRole("button", { name: "Capture photo" })).toBeEnabled());
      await userEvent.click(screen.getByRole("button", { name: "Capture photo" }));
      expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ type: "image/jpeg" })]);
      expect(stop).toHaveBeenCalledOnce();
      expect(screen.queryByRole("dialog", { name: "Take photo" })).not.toBeInTheDocument();
    } finally {
      if (original) Object.defineProperty(navigator, "mediaDevices", original);
      else Reflect.deleteProperty(navigator, "mediaDevices");
    }
  });
});
